from pytest import fixture


@fixture
def mkdirs():
    from pathlib import Path

    Path("test/source").mkdir(parents=True, exist_ok=True)
    yield
    Path("test/source").rmdir()
