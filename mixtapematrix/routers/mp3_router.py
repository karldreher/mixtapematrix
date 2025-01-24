from typing import Generator
import eyed3

from .files import FileRouter, File, search_files
from ..config import MatrixConfig


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
        exclude_path = self.matrix_config.exclude.path if self.matrix_config.exclude else None

        for i in self.matrix_config.mp3_files:
            # Dynamically search for the tag in the MP3 file
            for k, v in i.items():
                for file_path in search_files(source_path, exclude_path):
                    if file_path.endswith(".mp3"):
                        try:
                            audiofile = eyed3.load(path=file_path)
                        except Exception as e:
                            print(f"Error loading {file_path}: {e}")
                            continue
                        if k == "genre":
                            # Genre is a special case
                            # We most likely want to support just a few select tags, but genre should be one
                            if audiofile.tag.genre.name.lower() == v.lower():
                                yield File(path=file_path)

                        # All other tags, but primarily geared toward artist / album
                        audiofile_tag = getattr(audiofile.tag, k)
                        if str(audiofile_tag).lower() == v.lower():
                            yield File(path=file_path)
