from .files import FileRouter, File
from typing import List


class TagRouter(FileRouter):
    def source(self, file_path: File) -> List[File]:
        # TODO: actually do it, we need to probably return a list of files from Source
        # which have the Tag specified 

        return File(path=file_path.path.replace(".tags", ""))

