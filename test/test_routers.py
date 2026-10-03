import os
import struct

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


def make_mp3(path, **tags):
    from eyed3.id3 import Tag

    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    tag = Tag()
    for key, value in tags.items():
        setattr(tag, key, value)
    tag.save(str(path))


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "a" / "one.mp3", artist="Alpha", album="First", genre="Funk")
    make_mp3(root / "a" / "two.mp3", artist="Beta", album="Second", genre="Metal")
    make_mp3(root / "b" / "three.mp3", artist="Alpha", album="Third", genre="Funk")
    (root / "b" / "plain.mp3").touch()  # no tag
    return root


def make_router(tmp_path, library, mp3_files, cache=True):
    from mixtapematrix.cache import TagCache, parse_ttl
    from mixtapematrix.config import MatrixConfig
    from mixtapematrix.routers.mp3_router import TagRouter

    destination = tmp_path / "out"
    destination.mkdir(exist_ok=True)
    matrix = MatrixConfig(
        source_path=str(library),
        destination_path=str(destination),
        mp3_files=mp3_files,
    )
    config = tmp_path / "matrix.yaml"
    config.touch()
    tag_cache = TagCache(config, library, parse_ttl("1d")) if cache else None
    return TagRouter(matrix, cache=tag_cache)


def matched(router):
    return sorted(os.path.basename(f.path) for f in router.source)


@pytest.fixture
def read_counter(monkeypatch):
    from mixtapematrix.routers import mp3_router

    calls = []
    real = mp3_router.read_tags

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(mp3_router, "read_tags", counting)
    return calls


def test_router_matches_without_cache(tmp_path, library, read_counter):
    router = make_router(tmp_path, library, [{"artist": "alpha"}], cache=False)
    assert matched(router) == ["one.mp3", "three.mp3"]
    assert matched(router) == ["one.mp3", "three.mp3"]
    assert len(read_counter) == 8  # nothing cached: every file read on every run


def test_cache_hit_skips_tag_reads(tmp_path, library, read_counter):
    router = make_router(tmp_path, library, [{"artist": "Alpha"}])
    assert matched(router) == ["one.mp3", "three.mp3"]
    assert len(read_counter) == 4
    read_counter.clear()
    assert matched(router) == ["one.mp3", "three.mp3"]
    assert read_counter == []


def test_changing_criteria_reuses_cache(tmp_path, library, read_counter):
    matched(make_router(tmp_path, library, [{"artist": "Alpha"}]))
    read_counter.clear()
    router = make_router(tmp_path, library, [{"genre": "metal"}])
    assert matched(router) == ["two.mp3"]
    assert read_counter == []


def test_changed_file_is_reread_and_new_file_added(tmp_path, library, read_counter):
    router = make_router(tmp_path, library, [{"artist": "Alpha"}])
    matched(router)
    read_counter.clear()
    changed = library / "a" / "two.mp3"
    make_mp3(changed, artist="Alpha", album="Second")
    os.utime(changed, ns=(1, 1))
    make_mp3(library / "c" / "four.mp3", artist="Alpha")
    assert matched(router) == ["four.mp3", "one.mp3", "three.mp3", "two.mp3"]
    assert sorted(os.path.basename(p) for p in read_counter) == [
        "four.mp3",
        "two.mp3",
    ]


def test_deleted_files_are_pruned_from_cache(tmp_path, library):
    router = make_router(tmp_path, library, [{"artist": "Alpha"}])
    matched(router)
    (library / "a" / "one.mp3").unlink()
    assert matched(router) == ["three.mp3"]
    assert "a/one.mp3" not in router.cache.load()


def test_untagged_files_are_cached_as_no_tag(tmp_path, library, read_counter):
    router = make_router(tmp_path, library, [{"artist": "Alpha"}])
    matched(router)
    entries = router.cache.load()
    assert entries["b/plain.mp3"][1] is None
    read_counter.clear()
    matched(router)
    assert read_counter == []


@pytest.mark.parametrize(
    "error", [struct.error("bad"), IndexError("bad"), RuntimeError("bad")]
)
def test_unparseable_file_does_not_abort_scan(tmp_path, library, monkeypatch, error):
    from eyed3.id3 import Tag

    real_parse = Tag.parse

    def flaky_parse(self, path, *args, **kwargs):
        if path.endswith("two.mp3"):
            raise error
        return real_parse(self, path, *args, **kwargs)

    monkeypatch.setattr(Tag, "parse", flaky_parse)
    router = make_router(tmp_path, library, [{"artist": "Alpha"}])
    assert matched(router) == ["one.mp3", "three.mp3"]
    # The bad file is cached as unreadable, so the cache is still written.
    assert router.cache.load()["a/two.mp3"][1] is None
