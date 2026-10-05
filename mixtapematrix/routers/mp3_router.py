import logging
import os
from collections.abc import Generator, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

import click
from eyed3.id3 import Genre, Tag

from ..cache import TAG_FIELDS, Entry, TagCache, Tags
from ..config import MatrixConfig, Mp3Match
from ..progress import ProgressFactory, no_progress
from .files import File, FileRouter, make_exclusion_test, search_files

_EYED3_LOGGER = logging.getLogger("eyed3")
_eyed3_handlers: list[logging.Handler] = []
# The file being parsed on this thread, so every eyed3 message can name it.
_current_file: ContextVar[str | None] = ContextVar("current_file", default=None)


class _FilePrefix(logging.Filter):
    """Prefixes each eyed3 log record with the file being read on this thread."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Rewrite the record's message in place; always lets the record through."""
        if path := _current_file.get():
            # Bake the formatted message into msg and clear args, so the handler
            # does not apply %-formatting a second time.
            record.msg, record.args = f"{path}: {record.getMessage()}", None
        return True


def configure_tag_logging(verbose: bool = False) -> None:
    """
    eyed3 reports tag quirks (non-standard genres, unparseable dates, unsupported
    frames) as warnings. They do not stop a tag from being read, so they are shown
    only when verbose. Genuinely unreadable files still surface via _load_tag.
    """
    while _eyed3_handlers:
        _EYED3_LOGGER.removeHandler(_eyed3_handlers.pop())
    if verbose:
        handler = logging.StreamHandler()  # binds the current sys.stderr
        handler.addFilter(_FilePrefix())
        _eyed3_handlers.append(handler)
        _EYED3_LOGGER.addHandler(handler)
        _EYED3_LOGGER.setLevel(logging.WARNING)
    else:
        _EYED3_LOGGER.setLevel(logging.CRITICAL + 1)


def _load_tag(path: str) -> Tag | None:
    """
    Read only the ID3 tag of an MP3, skipping audio stream parsing.
    Returns None (and reports) if the file cannot be read or has no tag.
    """
    try:
        tag = Tag()
        return tag if tag.parse(path) else None
    except Exception as e:  # noqa: BLE001
        # eyed3 can raise almost anything on a malformed tag (struct.error,
        # IndexError, ...). One bad file must not abort the whole scan.
        click.echo(f"Error loading {path}: {e}")
        return None


def read_tags(path: str) -> Tags | None:
    """The values of TAG_FIELDS for an MP3, or None if it has no readable tag."""
    # eyed3 parses frames lazily (genre on access), so the file stays current
    # until the values are read, not just until the parse returns.
    token = _current_file.set(path)
    try:
        tag = _load_tag(path)
        if tag is None:
            return None
        # Genre is a special case: the tag is a Genre object (or None), compare by name.
        # isinstance narrows the type: eyed3's setter accepts ints, the getter returns Genre | None.
        genre = tag.genre
        return (
            tag.artist,
            tag.album,
            genre.name if isinstance(genre, Genre) else None,
            tag.album_artist,
        )
    finally:
        _current_file.reset(token)


def _tag_matches(tags: Tags, key: str, value: str) -> bool:
    """Case-insensitive match of a single tag (genre, artist, album, ...) against a value."""
    tag_value = tags[TAG_FIELDS.index(key)]
    return tag_value is not None and tag_value.lower() == value.lower()


def _entry_matches(tags: Tags, entry: Mp3Match) -> bool:
    """
    An entry matches when any of its own tags match and its exclude block does not.
    An exclude block is evaluated the same way, so nested excludes work to any depth.
    """
    own = [(k, v) for k in TAG_FIELDS if (v := getattr(entry, k)) is not None]
    if not any(_tag_matches(tags, k, v) for k, v in own):
        return False
    return entry.exclude is None or not _entry_matches(tags, entry.exclude)


class TagRouter(FileRouter):
    def __init__(
        self,
        matrix_config: MatrixConfig,
        cache: TagCache | None = None,
        progress: ProgressFactory = no_progress,
    ):
        self.matrix_config = matrix_config
        self.cache = cache
        self.progress = progress

    def _discover_tags(self, mp3_paths: list[str]) -> dict[str, Entry]:
        """
        Tags for every MP3, keyed by path relative to the source. Files whose mtime
        matches the cache are not re-read. The cache is rewritten when anything changed.
        """
        root = self.matrix_config.source.path
        cached = self.cache.load() if self.cache else {}
        found: dict[str, Entry] = {}
        misses: list[tuple[str, int]] = []
        for path in mp3_paths:
            try:
                mtime = os.stat(path).st_mtime_ns
            except OSError as e:
                click.echo(f"Error reading {path}: {e}")
                continue
            hit = cached.get(os.path.relpath(path, root))
            if hit and hit[0] == mtime:
                found[os.path.relpath(path, root)] = hit
            else:
                misses.append((path, mtime))

        # Tag reads are I/O-bound, so overlap them; map() preserves input order.
        label = f"Discovering files in {root}"
        with ThreadPoolExecutor() as pool, self.progress(label, len(misses)) as bar:
            read = pool.map(lambda miss: read_tags(miss[0]), misses)
            for (path, mtime), tags in zip(misses, read, strict=True):
                found[os.path.relpath(path, root)] = (mtime, tags)
                bar.update(1)

        if self.cache and (misses or found.keys() != cached.keys()):
            self.cache.save(found)
        return found

    def _check_source(self) -> None:
        if self.matrix_config.source.is_file:
            raise ValueError(
                f"{self.matrix_config.source.path} is not a directory. TagRouter only works on directories, not individual files."
            )
        _ = self.matrix_config.excluded_files  # fails fast on a missing literal path

    def _mp3_paths(self) -> list[str]:
        """Every non-excluded MP3 under the source directory."""
        self._check_source()
        return [
            p
            for p in search_files(
                self.matrix_config.source.path, self.matrix_config.exclude_paths
            )
            if p.lower().endswith(".mp3")
        ]

    def cached_entries(self) -> Iterator[tuple[str, Tags]] | None:
        """
        (absolute path, tags) of every tagged MP3 the tag cache lists, or None when
        there is no usable cache (missing, expired, outdated, corrupt or empty).

        This trusts the cache: the source is not walked and no file is stat'ed, so
        files added, deleted or retagged since the cache was written are not seen.
        The current exclude_paths are still applied, because the cache may have been
        built under different ones. Nothing is written back to the cache.
        """
        self._check_source()
        cached = self.cache.load() if self.cache else {}
        if not cached:
            return None
        return self._from_cache(cached)

    def _from_cache(self, cached: dict[str, Entry]) -> Iterator[tuple[str, Tags]]:
        root = self.matrix_config.source.path
        is_excluded = make_exclusion_test(self.matrix_config.exclude_paths)
        dirs: dict[str, bool] = {"": False}  # relative dir -> excluded, by memo

        def dir_excluded(rel_dir: str) -> bool:
            # Like the walk: a directory is removed if it, or any directory above it
            # beneath the source, is. The source directory itself is never tested.
            if rel_dir not in dirs:
                dirs[rel_dir] = dir_excluded(os.path.dirname(rel_dir)) or is_excluded(
                    os.path.join(root, rel_dir), True
                )
            return dirs[rel_dir]

        for rel, (_, tags) in cached.items():
            if tags is None:
                continue
            path = os.path.join(root, rel)
            if dir_excluded(os.path.dirname(rel)) or is_excluded(path, False):
                continue
            yield os.path.abspath(path), tags

    def entries(self, refresh: bool = False) -> Iterator[tuple[str, Tags]]:
        """
        (absolute path, tags) of every tagged MP3, regardless of the matrix filters.
        A valid tag cache is read as is, without touching the source. With `refresh`
        (or without a usable cache) the source is walked, every file is checked
        against the cache, and discovery refills it.
        """
        if not refresh and (cached := self.cached_entries()) is not None:
            yield from cached
            return
        root = self.matrix_config.source.path
        for path, (_, tags) in self._discover_tags(self._mp3_paths()).items():
            if tags is not None:
                yield os.path.abspath(os.path.join(root, path)), tags

    def untagged(self) -> list[str]:
        """
        Absolute, sorted paths of every MP3 that has no readable ID3 tag.

        The tag cache is used here only to skip files, never to answer: a file whose
        cache entry still matches its mtime and holds tags is known to be tagged, so
        it is not opened. The cache also records untagged files as (mtime, None), but
        a recorded "no tag" is not trusted, so those files are read again, as are
        files missing from the cache. Nothing is written back to the cache: this
        pass reads only the files that can be untagged, so it is not a complete
        discovery and must not be saved as one.
        """
        root = self.matrix_config.source.path
        cached = self.cache.load() if self.cache else {}
        unknown: list[str] = []
        for path in self._mp3_paths():
            try:
                mtime = os.stat(path).st_mtime_ns
            except OSError as e:
                click.echo(f"Error reading {path}: {e}")
                continue
            hit = cached.get(os.path.relpath(path, root))
            if hit and hit[0] == mtime and hit[1] is not None:
                continue  # Cached as tagged and unchanged: cannot be untagged.
            unknown.append(path)

        label = f"Checking files in {root}"
        found: list[str] = []
        with ThreadPoolExecutor() as pool, self.progress(label, len(unknown)) as bar:
            for path, tags in zip(unknown, pool.map(read_tags, unknown), strict=True):
                if tags is None:
                    found.append(os.path.abspath(path))
                bar.update(1)
        return sorted(found, key=str.casefold)

    @property
    def source(self) -> Generator[File]:
        """
        A property that returns a generator of files that match the tag criteria.
        This uses the matrix_config to determine the tag and value to search for.
        No arguments are needed, as the matrix_config is already set in the constructor.
        """
        source_path = self.matrix_config.source.path
        mp3_paths = self._mp3_paths()

        found = self._discover_tags(mp3_paths)
        for file_path in mp3_paths:
            _, tags = found.get(os.path.relpath(file_path, source_path), (0, None))
            if tags is None:
                continue  # No ID3 tag: this tool only works with tagged files.
            if any(
                _entry_matches(tags, entry) for entry in self.matrix_config.mp3_files
            ):
                yield File(path=file_path)
