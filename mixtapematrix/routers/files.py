import os
import shutil
import sys
from abc import ABC, abstractmethod
from collections.abc import Generator

from pydantic import BaseModel, computed_field, field_validator


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

    @field_validator("path", mode="after")
    @classmethod
    def validate_path(cls, path):
        if path.startswith("/example/"):
            # This is used when creating default configs.
            return path
        if not os.path.exists(path):
            # TODO Valid behavior, but needs nicer looking error, just a exit 1 would do.  No stacktrace needed.
            raise ValueError(f"File {path} does not exist")

        return path


class FileRouter(ABC):
    @property
    @abstractmethod
    def source(self) -> Generator[File]:
        raise NotImplementedError

    @staticmethod
    def deeply_copy(source: File, root_source: File, destination: File) -> None:
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


def search_files(source_path: str, exclude_path: str | None = None) -> Generator[str]:
    """
    Walk the source path and yield all files.
    If exclude_path is provided, skip any files in that path.
    """
    for root, dirs, files in os.walk(source_path):
        if exclude_path:
            # Prune in place so os.walk does not descend into excluded subtrees.
            dirs[:] = [d for d in dirs if exclude_path not in os.path.join(root, d)]
            if exclude_path in root:
                continue
        for file in files:
            yield os.path.join(root, file)
