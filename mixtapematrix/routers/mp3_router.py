from concurrent.futures import ThreadPoolExecutor
from typing import Generator
from eyed3.id3 import Tag

from .files import FileRouter, File, search_files
from ..config import MatrixConfig


def _load_tag(path: str) -> Tag | None:
    """
    Read only the ID3 tag of an MP3, skipping audio stream parsing.
    Returns None (and reports) if the file cannot be read or has no tag.
    """
    try:
        tag = Tag()
        return tag if tag.parse(path) else None
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None


def _tag_matches(tag: Tag, key: str, value: str) -> bool:
    """Case-insensitive match of a single tag (genre, artist, album, ...) against a value."""
    if key == "genre":
        # Genre is a special case: the tag is a Genre object (or None), compare by name.
        return tag.genre is not None and tag.genre.name.lower() == value.lower()
    return str(getattr(tag, key)).lower() == value.lower()


def _file_matches(path: str, criteria: list[tuple[str, str]]) -> bool:
    """True if the MP3 at path matches any criterion. Returns a bool so parsed tags are not retained."""
    tag = _load_tag(path)
    return tag is not None and any(_tag_matches(tag, k, v) for k, v in criteria)


class TagRouter(FileRouter):
    def __init__(self, matrix_config: MatrixConfig):
        self.matrix_config = matrix_config

    @property
    def source(self) -> Generator[File, None, None]:
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
        exclude_path = (
            self.matrix_config.exclude.path if self.matrix_config.exclude else None
        )

        criteria = [
            (k, v) for entry in self.matrix_config.mp3_files for k, v in entry.items()
        ]

        mp3_paths = [
            p
            for p in search_files(source_path, exclude_path)
            if p.lower().endswith(".mp3")
        ]

        # Tag reads are I/O-bound, so overlap them; map() preserves walk order.
        with ThreadPoolExecutor() as pool:
            matches = pool.map(lambda p: _file_matches(p, criteria), mp3_paths)
            for file_path, matched in zip(mp3_paths, matches):
                if matched:
                    yield File(path=file_path)
