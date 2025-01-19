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
                        # TODO Genre is weird, it could be an Enum.
                        # We might want to support just a couple select tags, but genre should be one
                        print(f"audiofile_tag: {audiofile_tag}")
                        if str(audiofile_tag).lower() == value.lower():
                            yield File(path=f"{root}/{file}")
        else:
            raise ValueError(f"MP3 TagRouter only works on directories, not individual files.")

