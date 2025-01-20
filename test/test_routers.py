from mixtapematrix.routers.files import File
from mixtapematrix.routers.mp3_router import TagRouter


def test_file(mkdirs):
    file = File(path="test/source")
    assert file.is_dir == True
    assert file.is_file == False

# TODO: test TagRouter, need fixture for some mp3 files
