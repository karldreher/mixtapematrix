import os
import sys
from abc import ABC, abstractmethod
from pydantic import BaseModel, field_validator, computed_field
import shutil
from typing import Generator


class File(BaseModel):
    path: str
    __hash__ = object.__hash__

    @computed_field
    @property
    def is_dir(self) -> bool:
        return os.path.isdir(self.path)

    @computed_field
    @property
    def is_file(self) -> bool:
        return os.path.isfile(self.path)

    @field_validator("path")
    @classmethod
    def validate_path(cls, path):
        if not os.path.exists(path):
            # TODO Valid behavior, but needs nicer looking error, just a exit 1 would do.  No stacktrace needed.
            raise ValueError(f"File {path} does not exist")

        return path


class FileRouter(ABC):
    @abstractmethod
    # TODO: is file_path always a List of Files?
    # Is it actually a Class Attribute rather than a method?
    def source(file_path: File):
        return file_path

    @classmethod
    # TODO is this a class method or a static method?
    def deeply_copy(cls, source: File, root_source: File, destination: File) -> None:
        destination_file = source.path.replace(root_source.path, destination.path)
        try:
            if os.path.exists(destination_file):
                # Do nothing, we already copied this file
                # logging.debug(f"File {destination_file} already exists, skipping")
                pass
            else:
                new_dir = os.path.dirname(destination_file)
                if not os.path.exists(new_dir):
                    os.makedirs(new_dir)
                if source.is_dir:
                    shutil.copytree(source.path, destination_file)
                elif source.is_file:
                    shutil.copyfile(source.path, destination_file)
        except Exception as e:
            print(f"Error copying {source.path} to {destination_file}: {e}")
            sys.exit(1)


def search_files(
    source_path: str, exclude_path: str = None
) -> Generator[str, None, None]:
    """
    Walk the source path and yield all files.
    If exclude_path is provided, skip any files in that path.
    """
    for root, dirs, files in os.walk(source_path):
        if exclude_path and exclude_path in root:
            continue
        for file in files:
            yield os.path.join(root, file)
