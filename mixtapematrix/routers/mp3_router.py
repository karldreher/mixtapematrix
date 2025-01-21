from typing import Generator
import eyed3

from .files import FileRouter, File, search_files
from ..config import MatrixConfig


class TagRouter(FileRouter):
    @staticmethod
    def source(matrix_config: MatrixConfig) -> Generator[File, None, None]:
        """
        param file_path: The file path to search for MP3 files
        #### TODO: file_path could be better named
        param excluded_path: A path to exclude from the search
        param tag: A tag to identify matching files (e.g. Artist)
        param value: A value to match the tag against (e.g. David Byrne)
        """
        if matrix_config.source.is_file:
            raise ValueError(
                f"{matrix_config.source.path} is not a directory.  TagRouter only works on directories, not individual files."
            )
        source_path = matrix_config.source.path
        exclude_path = matrix_config.exclude.path if matrix_config.exclude else None

        for i in matrix_config.mp3_files:
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
