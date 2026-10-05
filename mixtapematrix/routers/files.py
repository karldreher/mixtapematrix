import os
import shutil
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable

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
    def deeply_copy(source: File, root_source: File, destination: File) -> str:
        """Copy source into destination, returning the path it was copied to."""
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
        return destination_file


def destination_path(source: File, root_source: File, destination: File) -> str:
    """Where deeply_copy places a source file inside the destination."""
    return source.path.replace(root_source.path, destination.path)


def paths_overlap(a: str, b: str) -> bool:
    """True when either resolved (os.path.realpath) directory is, or is inside, the other."""
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


GLOB_TAIL = "**"


def is_glob(path: str) -> bool:
    """A trailing-`**` exclude pattern, e.g. /music/rock** or /music/rock/**."""
    return path.endswith(GLOB_TAIL)


def glob_prefix(pattern: str) -> str:
    """
    The absolute path prefix a trailing-`**` pattern stands for. `rock**` matches
    anything whose path starts with `rock`; `rock/**` matches everything beneath rock.
    """
    head = pattern[: -len(GLOB_TAIL)]
    prefix = os.path.abspath(head)
    return (
        prefix + os.sep if head.endswith(("/", os.sep)) and prefix != os.sep else prefix
    )


ExclusionTest = Callable[[str, bool], bool]
"""(path, is_dir) -> whether the exclude_paths rules remove that path."""


def make_exclusion_test(exclude_paths: Iterable[str] = ()) -> ExclusionTest:
    """
    A test for whether a single path is removed by `exclude_paths`.
    A plain exclude path removes that directory (or file) and everything beneath it,
    matched on whole paths after resolving to absolute, never by substring.
    A path ending in `**` is a prefix pattern: see glob_prefix.
    """
    exclude_paths = list(exclude_paths)
    patterns = [p for p in exclude_paths if is_glob(p)]
    prefixes = tuple(glob_prefix(p) for p in patterns)
    excluded = {os.path.abspath(p) for p in exclude_paths if not is_glob(p)}
    if not excluded and not prefixes:
        return lambda path, is_dir: False

    def is_excluded(path: str, is_dir: bool) -> bool:
        absolute = os.path.abspath(path)
        if absolute in excluded:
            return True
        # A directory is tested with a trailing separator so `rock/**` also prunes rock.
        return absolute.startswith(prefixes) or (
            is_dir and (absolute + os.sep).startswith(prefixes)
        )

    return is_excluded


def search_files(source_path: str, exclude_paths: Iterable[str] = ()) -> Generator[str]:
    """
    Walk the source path and yield all files, except those `exclude_paths` removes
    (see make_exclusion_test).
    """
    is_excluded = make_exclusion_test(exclude_paths)

    for root, dirs, files in os.walk(source_path):
        # Prune in place so os.walk never descends into (or stats) excluded subtrees.
        dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d), True)]
        for file in files:
            path = os.path.join(root, file)
            if not is_excluded(path, False):
                yield path
