"""
On-disk cache of the ID3 tags discovered while scanning a source library.

Each cache file holds one `source_path`'s tags: a small msgpack header (readable
without decoding the body, so `mixtape cache clean` stays cheap) followed by a
zstd-compressed columnar body. Tag strings are stored once in a string table and
referenced by index, which keeps the file small.
"""

import hashlib
import os
import re
import struct
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal, get_args

import ormsgpack
from compression import zstd

# Internal cache layout version (not user-configurable). Bump it whenever the
# cached properties or their encoding change (e.g. adding a tag field), so older
# caches are discarded and rebuilt.
CACHE_SCHEMA_VERSION = 1

TagField = Literal["artist", "album", "genre", "album_artist"]
# Order matters: Tags is positional and the cache stores one column per field in it.
TAG_FIELDS: tuple[TagField, ...] = get_args(TagField)


def tag_index(field: str) -> int:
    """The position of a tag field in Tags; unknown names raise a ValueError naming them."""
    try:
        return TAG_FIELDS.index(field)
    except ValueError:
        raise ValueError(
            f"Unknown tag field {field!r}; expected one of {', '.join(TAG_FIELDS)}"
        ) from None


CACHE_SUFFIX = ".mmcache"
TMP_SUFFIX = ".mmcache.tmp"

# Prometheus-style durations, limited to a single unit. Prometheus has no month
# unit; "mo" is a fixed 30 days.
TTL_PATTERN = r"^([1-9][0-9]*)(m|h|d|w|mo)$"
_TTL_RE = re.compile(TTL_PATTERN)
_TTL_UNITS = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "mo": timedelta(days=30),
}

# Column markers: a tag value that is missing, and a file with no readable tag.
_ABSENT = -1
_NO_TAG = -2

_HEADER_LEN = struct.Struct(">I")
_ZSTD_LEVEL = 19  # writes happen once per expiry, so favor size over speed

_READ_ERRORS = (
    OSError,
    struct.error,
    ormsgpack.MsgpackDecodeError,
    zstd.ZstdError,
    KeyError,
    IndexError,
    TypeError,
    ValueError,
)

Tags = tuple[str | None, ...]
"""Values for TAG_FIELDS, in order."""
Entry = tuple[int, Tags | None]
"""(mtime_ns, tags); tags is None when the file has no readable ID3 tag."""


def parse_ttl(value: str) -> timedelta:
    """Parse a duration like `30m`, `2d` or `1mo`. Raises ValueError otherwise."""
    match = _TTL_RE.fullmatch(value)
    if not match:
        raise ValueError(
            f"Invalid cache ttl '{value}': use a positive whole number followed by "
            "m, h, d, w, or mo (for example 30m, 2d, 1mo)"
        )
    return int(match[1]) * _TTL_UNITS[match[2]]


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base and os.path.isabs(base) else Path.home() / ".cache"
    return root / "mixtapematrix"


def cache_key(config_path: Path, source_root: Path) -> str:
    # The key includes the config file's path, so a cache belongs to one config
    # file: two configs never read, write, or delete each other's cache, even
    # when they share a source_path or use different TTLs. The consequence is
    # that moving or renaming a config orphans its cache; `mixtape cache clean`
    # removes it.
    identity = f"{config_path.resolve()}\0{source_root.resolve()}"
    return hashlib.sha256(identity.encode()).hexdigest()


@dataclass(frozen=True)
class CacheHeader:
    version: int
    created_at: int
    ttl_seconds: int
    config_path: str
    source_root: str

    def expired(self, ttl_seconds: float, now: float) -> bool:
        return now - self.created_at >= ttl_seconds


def _read_header(f) -> CacheHeader:
    (length,) = _HEADER_LEN.unpack(f.read(_HEADER_LEN.size))
    # A header with missing or extra keys raises TypeError, which callers treat as unreadable.
    return CacheHeader(**ormsgpack.unpackb(f.read(length)))


def _encode(entries: dict[str, Entry]) -> bytes:
    items = sorted(entries.items())
    # Every distinct tag value, stored once. Rows hold an index into this sorted
    # table instead of the text, which compresses far better. Untagged entries
    # (tags is None) contribute nothing, and absent fields (None) are skipped.
    strings = sorted(
        {s for _, (_, tags) in items if tags for s in tags if s is not None}
    )
    ids = {s: i for i, s in enumerate(strings)}
    mtimes: list[int] = []
    columns: dict[str, list[int]] = {field: [] for field in TAG_FIELDS}
    previous = 0
    for _, (mtime, tags) in items:
        mtimes.append(mtime - previous)
        previous = mtime
        row = (
            [_NO_TAG] * len(TAG_FIELDS)
            if tags is None
            else [_ABSENT if value is None else ids[value] for value in tags]
        )
        for field, tag_id in zip(TAG_FIELDS, row, strict=True):
            columns[field].append(tag_id)
    body = {
        "strings": strings,
        "paths": [p for p, _ in items],
        "mtime": mtimes,
        **columns,
    }
    return zstd.compress(ormsgpack.packb(body), level=_ZSTD_LEVEL)


def _decode(data: bytes) -> dict[str, Entry]:
    body = ormsgpack.unpackb(zstd.decompress(data))
    strings, paths, mtimes = body["strings"], body["paths"], body["mtime"]
    columns = [body[field] for field in TAG_FIELDS]
    if any(len(column) != len(paths) for column in [mtimes, *columns]):
        raise ValueError("cache columns have mismatched lengths")
    lookup = [*strings, None, None]  # _NO_TAG (-2) and _ABSENT (-1) index the Nones
    resolved = zip(*([lookup[t] for t in column] for column in columns), strict=True)
    entries: dict[str, Entry] = {}
    mtime = 0
    for path, delta, first, tags in zip(
        paths, mtimes, columns[0], resolved, strict=True
    ):
        mtime += delta
        entries[path] = (mtime, None if first == _NO_TAG else tags)
    return entries


class TagCache:
    """The cache for one (config file, source_path) pair."""

    def __init__(
        self,
        config_path: str | Path,
        source_root: str | Path,
        ttl: timedelta,
        log: Callable[[str], None] = lambda _: None,
        debug: Callable[[str], None] = lambda _: None,
        now: Callable[[], float] = time.time,
    ):
        self.config_path = Path(config_path).resolve()
        self.source_root = Path(source_root).resolve()
        self.ttl = ttl
        self.log = log
        self.debug = debug
        self.now = now
        self.path = (
            cache_dir()
            / f"{cache_key(self.config_path, self.source_root)}{CACHE_SUFFIX}"
        )
        self._created_at: int | None = None

    def load(self) -> dict[str, Entry]:
        """
        Cached entries keyed by path relative to source_root.
        Returns {} when there is no cache. An expired, outdated, or corrupt cache
        is deleted first, so the caller rebuilds it from scratch.
        """
        self._created_at = None
        if not self.path.exists():
            return {}
        try:
            with self.path.open("rb") as f:
                header = _read_header(f)
                if header.version != CACHE_SCHEMA_VERSION:
                    return self._discard("cache format changed")
                if header.expired(self.ttl.total_seconds(), self.now()):
                    return self._discard("cache expired")
                entries = _decode(f.read())
        except _READ_ERRORS as e:
            self.log(f"Tag cache {self.path.name} is unreadable ({e}); rebuilding")
            return self._discard()
        self._created_at = header.created_at
        return entries

    def _discard(self, reason: str | None = None) -> dict[str, Entry]:
        if reason:
            self.debug(f"Deleting tag cache {self.path.name}: {reason}")
        self.path.unlink(missing_ok=True)
        return {}

    def save(self, entries: dict[str, Entry]) -> None:
        """Write the cache atomically. Failing to write is reported, not fatal."""
        # Rewrites keep the original created_at so the cache still expires on schedule.
        header = ormsgpack.packb(
            asdict(
                CacheHeader(
                    version=CACHE_SCHEMA_VERSION,
                    created_at=self._created_at or int(self.now()),
                    ttl_seconds=int(self.ttl.total_seconds()),
                    config_path=str(self.config_path),
                    source_root=str(self.source_root),
                )
            )
        )
        payload = _HEADER_LEN.pack(len(header)) + header + _encode(entries)
        tmp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=TMP_SUFFIX)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            os.replace(tmp, self.path)
        except OSError as e:
            self.log(f"Could not write tag cache {self.path.name}: {e}")
        finally:
            if tmp:
                Path(tmp).unlink(missing_ok=True)


@dataclass(frozen=True)
class Removed:
    name: str
    reason: str
    size: int


def _stale_reason(path: Path, now: float) -> str | None:
    try:
        with path.open("rb") as f:
            header = _read_header(f)
    except _READ_ERRORS:
        return "unreadable"
    if header.version != CACHE_SCHEMA_VERSION:
        return "unknown format version"
    if header.expired(header.ttl_seconds, now):
        return "expired"
    if not Path(header.config_path).exists():
        return "orphaned: config file is gone"
    if not Path(header.source_root).exists():
        return "orphaned: source path is gone"
    return None


def clean_cache(
    all_files: bool = False,
    now: Callable[[], float] = time.time,
    directory: Path | None = None,
) -> list[Removed]:
    """
    Delete stale cache files, or every cache file when all_files is set.
    Only files this module created (by suffix) are ever touched. The CLI holds the
    single-instance lock, so no other process can be mid-write while this runs.
    """
    directory = directory or cache_dir()
    if not directory.is_dir():
        return []
    removed: list[Removed] = []
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file():
            continue
        if path.name.endswith(TMP_SUFFIX):
            reason = "interrupted write"
        elif path.name.endswith(CACHE_SUFFIX):
            reason = "all" if all_files else _stale_reason(path, now())
        else:
            continue
        if reason is None:
            continue
        size = path.stat().st_size
        path.unlink()
        removed.append(Removed(path.name, reason, size))
    # Leave no empty directory behind.
    with suppress(OSError):
        directory.rmdir()
    return removed
