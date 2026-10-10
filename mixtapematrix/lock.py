"""Single-instance lock: detects another mixtape process running at the same time."""

import functools
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import click

# The lock lives only in the kernel: no file is created and nothing touches the
# network. The OS releases it when the process exits or is killed, so it can
# never go stale. It is scoped to the current user.
#   macOS/Linux: an exclusive flock on the user's (already existing) home directory.
#   Windows:     a named mutex in the user's session.
_WINDOWS_MUTEX = "Local\\mixtapematrix"
_ERROR_ALREADY_EXISTS = 183


class LockError(RuntimeError):
    pass


class AlreadyRunningError(LockError):
    def __init__(self):
        super().__init__("Another mixtape instance is already running.")


@contextmanager
def single_instance() -> Iterator[None]:
    """Hold the single-instance lock for as long as the context is open."""
    if sys.platform == "win32":
        with _windows_mutex():
            yield
    else:
        with _home_flock():
            yield


def hold_lock() -> None:
    """Hold the lock until the running command finishes. A second instance is
    warned about, not blocked: concurrent runs are discouraged, not forbidden."""
    try:
        click.get_current_context().with_resource(single_instance())
    except LockError as e:
        click.echo(f"Warning: {e} Continuing anyway.", err=True)


def locked(func: Callable) -> Callable:
    """Decorate a command that writes (files or the cache) so it holds the lock.
    Read-only commands are left undecorated."""

    @functools.wraps(func)
    def command(*args, **kwargs):
        hold_lock()
        return func(*args, **kwargs)

    return command


@contextmanager
def _home_flock() -> Iterator[None]:
    import fcntl

    fd = os.open(Path.home(), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as e:
        os.close(fd)
        raise AlreadyRunningError from e
    except OSError as e:
        os.close(fd)
        raise LockError(f"Could not acquire the single-instance lock: {e}") from e
    try:
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


@contextmanager
def _windows_mutex() -> Iterator[None]:  # pragma: no cover
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateMutexW(None, False, _WINDOWS_MUTEX)
    error = ctypes.get_last_error()
    if not handle:
        raise LockError(f"Could not acquire the single-instance lock: error {error}")
    if error == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        raise AlreadyRunningError
    try:
        yield
    finally:
        kernel32.CloseHandle(handle)
