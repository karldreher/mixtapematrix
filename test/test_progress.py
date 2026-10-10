import io
import sys
from contextlib import contextmanager

import helpers
import pytest
from click.testing import CliRunner
from helpers import make_mp3

from mixtapematrix import service
from mixtapematrix.main import cli
from mixtapematrix.progress import TerminalProgress


class FakeTty(io.StringIO):
    def isatty(self):
        return True


def write_config(tmp_path, names=("a.mp3", "b.mp3", "c.mp3"), cache=False):
    library = tmp_path / "library"
    for name in names:
        make_mp3(library / name, artist="Alpha")
    return helpers.write_config(
        tmp_path, [library], cache=cache, mp3_files=[{"artist": "Alpha"}]
    )


def recording_factory(calls):
    """A progress factory that records (label, total, steps) instead of drawing."""

    @contextmanager
    def factory(label, total):
        call = {"label": label, "total": total, "steps": 0}
        calls.append(call)

        class Bar:
            def update(self, n):
                call["steps"] += n

        yield Bar()

    return factory


def test_bar_hidden_when_stderr_is_not_a_terminal(capsys):
    with TerminalProgress()("Copying", 3) as bar:
        bar.update(1)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_bar_hidden_when_there_is_no_work(monkeypatch):
    monkeypatch.setattr(sys, "stderr", FakeTty())
    with TerminalProgress()("Copying", 0) as bar:
        bar.update(0)
    assert sys.stderr.getvalue() == ""


def test_bar_drawn_on_a_terminal(monkeypatch):
    monkeypatch.setattr(sys, "stderr", FakeTty())
    with TerminalProgress()("Copying", 2) as bar:
        bar.update(2)
    drawn = sys.stderr.getvalue()
    assert "Copying" in drawn and "█" in drawn
    assert "\x1b[32m" in drawn  # dark green fill
    assert "2/2" in drawn and "100%" in drawn


def test_blank_line_separates_two_bars_only(monkeypatch):
    monkeypatch.setattr(sys, "stderr", FakeTty())
    progress = TerminalProgress()
    with progress("Discovering", 1) as bar:
        bar.update(1)
    assert not sys.stderr.getvalue().startswith("\n")
    with progress("Copying", 0):  # no work: no bar, no blank line
        pass
    before = sys.stderr.getvalue()
    with progress("Copying", 1) as bar:
        bar.update(1)
    added = sys.stderr.getvalue()[len(before) :]
    assert added.startswith("\n")
    assert added.count("Copying") >= 1


def test_lone_bar_has_no_leading_blank_line(monkeypatch):
    monkeypatch.setattr(sys, "stderr", FakeTty())
    with TerminalProgress()("Copying", 1) as bar:
        bar.update(1)
    assert not sys.stderr.getvalue().startswith("\n")


def test_discovery_bar_counts_cache_misses(tmp_path):
    config = write_config(tmp_path, cache=True)
    calls = []
    for _ in range(2):
        main_run(config, calls)
    discovery = [c for c in calls if c["label"].startswith("Discovering")]
    # Cold cache reads all three files; the warm second run has nothing to read.
    assert [(c["total"], c["steps"]) for c in discovery] == [(3, 3), (0, 0)]
    assert str(tmp_path / "library") in discovery[0]["label"]


def test_copy_bar_total_matches_matched_files(tmp_path):
    config = write_config(tmp_path)
    calls = []
    main_run(config, calls)
    copying = [c for c in calls if c["label"].startswith("Copying")]
    assert [(c["total"], c["steps"]) for c in copying] == [(3, 3)]


@pytest.mark.parametrize("flag", ["--verbose", "--debug"])
def test_verbose_and_debug_runs_show_no_bars(tmp_path, flag):
    config = write_config(tmp_path)
    calls = []
    main_run(config, calls, flag)
    assert calls == []


def main_run(config, calls, *args):
    """Run the CLI with terminal_progress replaced by a recording factory."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(service, "TerminalProgress", lambda: recording_factory(calls))
        result = CliRunner().invoke(cli, ["run", "--config", str(config), *args])
    assert result.exit_code == 0, result.output
