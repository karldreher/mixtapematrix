import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

from eyed3.id3 import Genre, Tag

from ..cache import TAG_FIELDS, Entry, TagCache, Tags
from ..config import MatrixConfig, Mp3Match
from .files import File, FileRouter, search_files


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
        print(f"Error loading {path}: {e}")
        return None


def read_tags(path: str) -> Tags | None:
    """The values of TAG_FIELDS for an MP3, or None if it has no readable tag."""
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
    def __init__(self, matrix_config: MatrixConfig, cache: TagCache | None = None):
        self.matrix_config = matrix_config
        self.cache = cache

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
                print(f"Error reading {path}: {e}")
                continue
            hit = cached.get(os.path.relpath(path, root))
            if hit and hit[0] == mtime:
                found[os.path.relpath(path, root)] = hit
            else:
                misses.append((path, mtime))

        # Tag reads are I/O-bound, so overlap them; map() preserves input order.
        with ThreadPoolExecutor() as pool:
            read = pool.map(lambda miss: read_tags(miss[0]), misses)
            for (path, mtime), tags in zip(misses, read, strict=True):
                found[os.path.relpath(path, root)] = (mtime, tags)

        if self.cache and (misses or found.keys() != cached.keys()):
            self.cache.save(found)
        return found

    @property
    def source(self) -> Generator[File]:
        """
        A property that returns a generator of files that match the tag criteria.
        This uses the matrix_config to determine the tag and value to search for.
        No arguments are needed, as the matrix_config is already set in the constructor.
        """
        if self.matrix_config.source.is_file:
            raise ValueError(
                f"{self.matrix_config.source.path} is not a directory. TagRouter only works on directories, not individual files."
            )
        source_path = self.matrix_config.source.path
        exclude_paths = [f.path for f in self.matrix_config.excluded_files]

        mp3_paths = [
            p
            for p in search_files(source_path, exclude_paths)
            if p.lower().endswith(".mp3")
        ]

        found = self._discover_tags(mp3_paths)
        for file_path in mp3_paths:
            _, tags = found.get(os.path.relpath(file_path, source_path), (0, None))
            if tags and any(
                _entry_matches(tags, entry) for entry in self.matrix_config.mp3_files
            ):
                yield File(path=file_path)
