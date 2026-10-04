import io
import sys
from contextlib import contextmanager

import pytest
import yaml
from click.testing import CliRunner
from eyed3.id3 import Tag

from mixtapematrix import main
from mixtapematrix.main import cli
from mixtapematrix.progress import terminal_progress


class FakeTty(io.StringIO):
    def isatty(self):
        return True


def make_library(root, names):
    """MP3s tagged artist=Alpha, one per name."""
    root.mkdir(parents=True)
    for name in names:
        (root / name).touch()
        tag = Tag()
        tag.artist = "Alpha"
        tag.save(str(root / name))


def write_config(tmp_path, names=("a.mp3", "b.mp3", "c.mp3"), cache=False):
    make_library(tmp_path / "library", names)
    (tmp_path / "out").mkdir()
    data = {
        "matrix": [
            {
                "source_path": str(tmp_path / "library"),
                "destination_path": str(tmp_path / "out"),
                "mp3_files": [{"artist": "Alpha"}],
            }
        ]
    }
    if cache:
        data["cache"] = {"ttl": "1d"}
    config = tmp_path / "matrix.yaml"
    config.write_text(yaml.safe_dump(data))
    return config


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
    with terminal_progress("Copying", 3) as bar:
        bar.update(1)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_bar_hidden_when_there_is_no_work(monkeypatch):
    monkeypatch.setattr(sys, "stderr", FakeTty())
    with terminal_progress("Copying", 0) as bar:
        bar.update(0)
    assert sys.stderr.getvalue() == ""


def test_bar_drawn_on_a_terminal(monkeypatch):
    monkeypatch.setattr(sys, "stderr", FakeTty())
    with terminal_progress("Copying", 2) as bar:
        bar.update(2)
    drawn = sys.stderr.getvalue()
    assert "Copying" in drawn and "█" in drawn
    # The finished bar is erased: the stream ends by clearing its line.
    assert drawn.endswith("\x1b[1A\r\x1b[2K")


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
        mp.setattr(main, "terminal_progress", recording_factory(calls))
        result = CliRunner().invoke(cli, ["run", "--config", str(config), *args])
    assert result.exit_code == 0, result.output
