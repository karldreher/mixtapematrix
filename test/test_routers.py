import pytest

from mixtapematrix.routers.files import File


def test_file(mkdirs):
    file = File(path="test/source")
    assert file.is_dir
    assert not file.is_file


def test_invalid_file():
    with pytest.raises(ValueError):
        File(path="test/source/invalid")


# TODO: test TagRouter, need fixture for some mp3 files
