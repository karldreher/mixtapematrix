import os
from typing import Generator
import eyed3

from .files import FileRouter, File

class TagRouter(FileRouter):
    @staticmethod
    def source(file_path: File, tag: str, value: str) -> Generator[File, None, None]:
        """
        param file_path: File
        param tag: str A tag to identify matching files (e.g. Artist)
        param value: str A value to match the tag against (e.g. David Byrne)
        """
        if file_path.is_dir:
            for root, dirs, files in os.walk(file_path.path):
                for file in files:
                    if file.endswith(".mp3"):
                        audiofile = eyed3.load(f"{root}/{file}")
                        audiofile_tag = getattr(audiofile.tag, tag)
                        if audiofile_tag == value:
                            yield File(path=f"{root}/{file}")
        else:
            raise ValueError(f"MP3 TagRouter only works on directories, not individual files.")

