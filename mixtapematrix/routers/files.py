import os
import shutil
import sys
from abc import ABC, abstractmethod
from collections.abc import Generator, Iterable

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
        destination_file = destination_path(source, root_source, destination)
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
        except OSError as e:
            print(f"Error copying {source.path} to {destination_file}: {e}")
            sys.exit(1)


def destination_path(source: File, root_source: File, destination: File) -> str:
    """Where deeply_copy places a source file inside the destination."""
    return source.path.replace(root_source.path, destination.path)


def paths_overlap(a: str, b: str) -> bool:
    """True when either directory is the same as, or inside, the other."""
    a, b = os.path.realpath(a), os.path.realpath(b)
    return os.path.commonpath([a, b]) in (a, b)


def prune_destination(root: str, keep: set[str]) -> list[str]:
    """
    Delete everything under root that is not in keep, then remove directories left
    empty. root itself is never removed. Returns the deleted paths (empty
    directories included).
    """
    removed: list[str] = []
    try:
        for current, dirs, files in os.walk(root, topdown=False):
            # Symlinks to directories are listed in dirs but never descended into.
            links = [d for d in dirs if os.path.islink(os.path.join(current, d))]
            for name in files + links:
                path = os.path.join(current, name)
                if path not in keep:
                    os.remove(path)
                    removed.append(path)
            if current != root and not os.listdir(current):
                os.rmdir(current)
                removed.append(current)
    except OSError as e:
        print(f"Error pruning {root}: {e}")
        sys.exit(1)
    return removed


def search_files(source_path: str, exclude_paths: Iterable[str] = ()) -> Generator[str]:
    """
    Walk the source path and yield all files.
    Each exclude path removes that directory (or file) and everything beneath it.
    Excludes match whole paths after resolving to absolute, never by substring.
    """
    excluded = {os.path.abspath(path) for path in exclude_paths}
    for root, dirs, files in os.walk(source_path):
        # Prune in place so os.walk never descends into (or stats) excluded subtrees.
        dirs[:] = [
            d for d in dirs if os.path.abspath(os.path.join(root, d)) not in excluded
        ]
        for file in files:
            path = os.path.join(root, file)
            if os.path.abspath(path) not in excluded:
                yield path
