from typing import Generator
import eyed3

from .files import FileRouter, File, search_files
from ..config import MatrixConfig


def _load_mp3(path: str):
    """Load an MP3 with eyed3, returning None (and reporting) if it cannot be read."""
    try:
        return eyed3.load(path=path)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None


def _tag_matches(audiofile, key: str, value: str) -> bool:
    """Case-insensitive match of a single tag (genre, artist, album, ...) against a value."""
    if key == "genre":
        # Genre is a special case: the tag is a Genre object, compare by name.
        return audiofile.tag.genre.name.lower() == value.lower()
    return str(getattr(audiofile.tag, key)).lower() == value.lower()


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

        for file_path in search_files(source_path, exclude_path):
            if not file_path.endswith(".mp3"):
                continue
            audiofile = _load_mp3(file_path)
            if audiofile is None:
                continue
            if any(_tag_matches(audiofile, k, v) for k, v in criteria):
                yield File(path=file_path)
