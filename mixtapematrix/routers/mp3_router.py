import os
from typing import List
from eyed3 import id3

from .files import FileRouter, File

class TagRouter(FileRouter):
    def source(self, file_path: File, tag: str, value: str) -> List[File]:
        """
        param file_path: File
        param tag: str A tag to identify matching files (e.g. Artist)
        param value: str A value to match the tag against (e.g. David Byrne)
        """
        with self.open(file_path) as f:
            if f.is_dir:
                for root, dirs, files in os.walk(f.path):
                    for file in files:
                        if file.endswith(".mp3"):
                            audiofile = id3.load(f"{root}/{file}")
                            if tag in audiofile.tag:
                                if audiofile.tag[tag] == value:
                                    yield File(path=f"{root}/{file}")
            
            else:
                raise ValueError(f"Tag routers only work on directories, not individual files.")


        # TODO: actually do it, we need to probably return a list of files from Source
        # which have the Tag specified 

        return File(path=file_path.path.replace(".tags", ""))

