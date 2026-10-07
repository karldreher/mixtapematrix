import os
import shutil
import sys
from collections.abc import Callable, Generator, Iterable
from functools import cache
from typing import Annotated

from pydantic import AfterValidator


def copy_file(source: str, root: str, destination: str) -> str:
    """
    Copy `source`, a file beneath `root`, to the same relative path beneath
    `destination` unless it is already there. Returns the path it belongs at.
    """
    target = os.path.join(destination, os.path.relpath(source, root))
    try:
        if not os.path.exists(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
    except OSError as e:
        print(f"Error copying {source} to {target}: {e}")
        sys.exit(1)
    return target


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


def _validate_path_pattern(path: str) -> str:
    body = path[: -len(GLOB_TAIL)] if is_glob(path) else path
    if any(char in body for char in "*?["):
        raise ValueError(
            f"Path '{path}' is not supported: wildcards are only "
            "allowed as a trailing '**', e.g. /music/rock** or /music/rock/**."
        )
    return path


PathPattern = Annotated[str, AfterValidator(_validate_path_pattern)]
"""
A path or a trailing-`**` prefix pattern (see glob_prefix). Every config field that
takes locations (exclude_paths, mp3_files folder) uses this type, so the syntax
they accept is defined, and enforced, in one place.
"""


@cache
def subtree_test(pattern: str) -> Callable[[str], bool]:
    """
    A test for whether an absolute path is the pattern's directory or beneath it.
    A plain pattern matches whole path components; a trailing-`**` pattern matches
    by prefix, exactly as in make_exclusion_test.
    """
    if is_glob(pattern):
        prefix = glob_prefix(pattern)
        return lambda path: path.startswith(prefix)
    folder = os.path.abspath(pattern)
    beneath = os.path.join(folder, "")
    return lambda path: path == folder or path.startswith(beneath)


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
