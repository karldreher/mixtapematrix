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
                        try:
                            audiofile = eyed3.load(path=os.path.join(root, file))
                        except Exception as e:
                            print(f"Error loading {os.path.join(root, file)}: {e}")
                            continue
                        if tag == "genre":
                            # Genre is a special case
                            # We most likely want to support just a few select tags, but genre should be one
                            if audiofile.tag.genre.name.lower() == value:
                                yield File(path=os.path.join(root, file))

                        # All other tags, but primarily geared toward artist / album
                        audiofile_tag = getattr(audiofile.tag, tag)
                        if str(audiofile_tag).lower() == value.lower():
                            yield File(path=os.path.join(root, file))
        else:
            raise ValueError(
                "MP3 TagRouter only works on directories, not individual files."
            )
