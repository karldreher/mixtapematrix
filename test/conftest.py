from pytest import fixture


@fixture
def mkdirs():
    from pathlib import Path

    Path("test/output").mkdir(parents=True, exist_ok=True)
    Path("test/source").mkdir(parents=True, exist_ok=True)
    Path("test/source/exclude").mkdir(parents=True, exist_ok=True)
    yield
    # source must be empty, so exclude is deleted first
    Path("test/source/exclude").rmdir()
    Path("test/output").rmdir()
    Path("test/source").rmdir()


@fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    """Keep tests away from the real user cache directory."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))


@fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """The single-instance lock is taken on the home directory; isolate it per test
    so tests never contend with each other or with a real mmatrix run."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
