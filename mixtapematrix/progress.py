import sys
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import Protocol

import click


class Bar(Protocol):
    def update(self, n_steps: int) -> None: ...


class _NoBar:
    """Stands in for a bar that is not shown, so callers never branch on it."""

    def update(self, n_steps: int) -> None:
        pass


# A factory taking (label, total) and returning a context manager that yields a Bar.
ProgressFactory = Callable[[str, int], AbstractContextManager[Bar]]


def no_progress(label: str, total: int) -> AbstractContextManager[Bar]:
    """The default factory: shows nothing."""
    return nullcontext(_NoBar())


def terminal_progress(label: str, total: int) -> AbstractContextManager[Bar]:
    """
    A progress bar on stderr, shown only when there is work to track (total > 0)
    and stderr is a terminal. Redirected or piped runs get no output at all, where
    click.progressbar alone would still print the label.
    """
    if total <= 0 or not sys.stderr.isatty():
        return no_progress(label, total)
    return _bar(label, total)


# click ends a finished bar with a newline; step back up and erase that line.
_ERASE_FINISHED_BAR = "\x1b[1A\r\x1b[2K"


@contextmanager
def _bar(label: str, total: int):
    """The bar is erased, label included, once the work finishes."""
    with click.progressbar(
        length=total,
        label=label,
        fill_char="█",
        empty_char="░",
        bar_template="%(label)s  %(bar)s  %(info)s",
        file=sys.stderr,
    ) as bar:
        yield bar
    sys.stderr.write(_ERASE_FINISHED_BAR)
    sys.stderr.flush()
