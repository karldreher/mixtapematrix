from pytest import fixture

from mixtapematrix.routers import mp3_router


@fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    """Keep tests away from the real user cache directory."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))


@fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """The single-instance lock is taken on the home directory; isolate it per test
    so tests never contend with each other or with a real mixtape run."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


@fixture
def read_counter(monkeypatch):
    """The path of every file whose tags are read from disk, in call order."""
    calls = []
    real = mp3_router.read_tags

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(mp3_router, "read_tags", counting)
    return calls
