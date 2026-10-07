import subprocess
import sys
import textwrap

import pytest
from click.testing import CliRunner

from mixtapematrix.lock import AlreadyRunningError, LockError, single_instance
from mixtapematrix.main import cli

COMMANDS = [
    ["run", "--config", "missing.yaml"],
    ["init"],
    ["cache", "list"],
    ["cache", "clean"],
    ["cache", "clean", "--all"],
]


def test_lock_is_exclusive_and_released():
    with single_instance(), pytest.raises(AlreadyRunningError), single_instance():
        pass
    with single_instance():
        pass


@pytest.mark.parametrize("args", COMMANDS)
def test_second_instance_warns_and_proceeds(tmp_path, monkeypatch, args):
    monkeypatch.chdir(tmp_path)
    with single_instance():
        result = CliRunner().invoke(cli, args)
    assert "Warning: Another mixtape instance is already running." in result.output
    assert "Continuing anyway" in result.output
    if args[0] == "run":
        # run proceeds to its own work, which fails here only for the missing config
        assert result.exit_code != 0
        assert "Config file not found: missing.yaml" in result.output
    else:
        assert result.exit_code == 0
    assert (tmp_path / "matrix.yaml").exists() == (args[0] == "init")


def test_no_warning_when_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["cache", "clean"])
    assert result.exit_code == 0
    assert "Warning" not in result.output


def test_lock_is_released_after_a_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(cli, ["cache", "clean"]).exit_code == 0
    assert runner.invoke(cli, ["cache", "clean"]).exit_code == 0


def test_lock_is_released_after_a_failing_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(cli, ["run", "--config", "missing.yaml"]).exit_code != 0
    assert runner.invoke(cli, ["cache", "clean"]).exit_code == 0


def test_lock_is_released_after_init_exits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(cli, ["init"]).exit_code == 0  # init calls sys.exit
    assert runner.invoke(cli, ["cache", "clean"]).exit_code == 0


def test_help_does_not_need_the_lock():
    with single_instance():
        assert CliRunner().invoke(cli, ["--help"]).exit_code == 0


def test_lock_held_by_another_process_blocks_and_dies_with_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import sys
                from mixtapematrix.lock import single_instance
                with single_instance():
                    print("locked", flush=True)
                    sys.stdin.read()
                """
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        result = CliRunner().invoke(cli, ["cache", "clean"])
        assert result.exit_code == 0
        assert "already running" in result.output
    finally:
        holder.kill()  # no clean shutdown: the OS must release the lock
        holder.wait()
    result = CliRunner().invoke(cli, ["cache", "clean"])
    assert result.exit_code == 0
    assert "Warning" not in result.output  # the killed holder's lock is gone


def test_lock_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    before = sorted(tmp_path.rglob("*"))
    with single_instance():
        pass
    assert sorted(tmp_path.rglob("*")) == before
    assert list(home.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX-only")
def test_unexpected_os_error_is_a_lock_error(monkeypatch):
    import fcntl

    def unsupported(*args):
        raise OSError("flock unsupported")

    monkeypatch.setattr(fcntl, "flock", unsupported)
    with pytest.raises(LockError, match="Could not acquire"), single_instance():
        pass
    assert not isinstance(LockError("x"), AlreadyRunningError)
