import os
import random
import struct
import time
from datetime import timedelta

import ormsgpack
import pytest
from click.testing import CliRunner
from compression import zstd

from mixtapematrix import cache as cache_module
from mixtapematrix.cache import (
    CACHE_SCHEMA_VERSION,
    CACHE_SUFFIX,
    TAG_FIELDS,
    TMP_SUFFIX,
    TagCache,
    cache_dir,
    cache_key,
    clean_cache,
    list_cache,
    parse_ttl,
)
from mixtapematrix.main import cli

NOW = 1_800_000_000


def make_cache(tmp_path, ttl="2d", now=NOW, name="matrix.yaml", source="library", **kw):
    config = tmp_path / name
    config.touch()
    root = tmp_path / source
    root.mkdir(exist_ok=True)
    return TagCache(config, root, parse_ttl(ttl), now=lambda: now, **kw)


ENTRIES = {
    "a/one.mp3": (1_700_000_000_000_000_000, ("Artist", "Album", "Funk", None)),
    "a/two.mp3": (1_700_000_000_500_000_000, ("Artist", "Album", None, "Various")),
    "b/three.mp3": (1_699_999_999_000_000_000, None),
}


def test_schema_version_guard():
    # Adding or changing a cached property must come with a CACHE_SCHEMA_VERSION bump.
    # If this fails, bump CACHE_SCHEMA_VERSION and update the expected values.
    assert (CACHE_SCHEMA_VERSION, TAG_FIELDS) == (
        1,
        ("artist", "album", "genre", "album_artist"),
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30m", timedelta(minutes=30)),
        ("1h", timedelta(hours=1)),
        ("2d", timedelta(days=2)),
        ("3w", timedelta(weeks=3)),
        ("1mo", timedelta(days=30)),
        ("12mo", timedelta(days=360)),
    ],
)
def test_parse_ttl_valid(value, expected):
    assert parse_ttl(value) == expected


@pytest.mark.parametrize(
    "value", ["0h", "00m", "1.5d", "1h30m", "2y", "1M", "abc", "", "d", "-1d", "2d\n"]
)
def test_parse_ttl_invalid(value):
    with pytest.raises(ValueError, match="Invalid cache ttl"):
        parse_ttl(value)


def test_round_trip(tmp_path):
    cache = make_cache(tmp_path)
    cache.save(ENTRIES)
    assert cache.path.parent == cache_dir()
    assert cache.load() == ENTRIES


def test_load_without_cache_returns_empty(tmp_path):
    assert make_cache(tmp_path).load() == {}


def test_expired_cache_is_deleted(tmp_path):
    cache = make_cache(tmp_path, ttl="1h")
    cache.save(ENTRIES)
    later = make_cache(tmp_path, ttl="1h", now=NOW + 3600)
    assert later.load() == {}
    assert not later.path.exists()


def test_unexpired_cache_is_kept(tmp_path):
    cache = make_cache(tmp_path, ttl="1h")
    cache.save(ENTRIES)
    assert make_cache(tmp_path, ttl="1h", now=NOW + 3599).load() == ENTRIES


def test_rewrite_keeps_original_created_at(tmp_path):
    cache = make_cache(tmp_path, ttl="1h")
    cache.save(ENTRIES)
    midway = make_cache(tmp_path, ttl="1h", now=NOW + 1800)
    midway.load()
    midway.save({"c.mp3": (1, None)})
    assert make_cache(tmp_path, ttl="1h", now=NOW + 3600).load() == {}


def test_corrupt_cache_is_deleted_and_reported(tmp_path):
    messages = []
    cache = make_cache(tmp_path, log=messages.append)
    cache.save(ENTRIES)
    cache.path.write_bytes(b"not a cache")
    assert cache.load() == {}
    assert not cache.path.exists()
    assert any("unreadable" in m for m in messages)


def test_truncated_body_is_deleted(tmp_path):
    cache = make_cache(tmp_path)
    cache.save(ENTRIES)
    cache.path.write_bytes(cache.path.read_bytes()[:-5])
    assert cache.load() == {}
    assert not cache.path.exists()


def test_schema_version_mismatch_is_deleted(tmp_path, monkeypatch):
    cache = make_cache(tmp_path)
    cache.save(ENTRIES)
    monkeypatch.setattr(cache_module, "CACHE_SCHEMA_VERSION", CACHE_SCHEMA_VERSION + 1)
    assert cache.load() == {}
    assert not cache.path.exists()


HEADER = {
    "version": CACHE_SCHEMA_VERSION,
    "created_at": NOW,
    "ttl_seconds": 172800,
    "config_path": "/cfg/matrix.yaml",
    "source_root": "/lib",
}
BODY = {
    "strings": ["Album", "Artist"],
    "paths": ["a.mp3", "b.mp3"],
    "mtime": [10, 5],
    "artist": [1, -2],
    "album": [0, -2],
    "genre": [-1, -2],
    "album_artist": [-1, -2],
}


def write_raw(cache, header=HEADER, body=BODY):
    packed = ormsgpack.packb(header)
    payload = zstd.compress(ormsgpack.packb(body))
    cache.path.parent.mkdir(parents=True, exist_ok=True)
    cache.path.write_bytes(struct.pack(">I", len(packed)) + packed + payload)


def test_valid_raw_cache_loads(tmp_path):
    cache = make_cache(tmp_path)
    write_raw(cache)
    assert cache.load() == {
        "a.mp3": (10, ("Artist", "Album", None, None)),
        "b.mp3": (15, None),
    }


BAD_HEADERS = {
    "wrong type": {**HEADER, "created_at": "yesterday"},
    "bool for int": {**HEADER, "version": True},
    "missing key": {k: v for k, v in HEADER.items() if k != "source_root"},
    "extra key": {**HEADER, "owner": "someone"},
}

BAD_BODIES = {
    "tag id out of range": {**BODY, "artist": [2, -2]},
    "tag id below -2": {**BODY, "genre": [-3, -2]},
    "non-int tag id": {**BODY, "album": ["Album", -2]},
    "non-string in strings": {**BODY, "strings": ["Album", 7]},
    "non-string path": {**BODY, "paths": ["a.mp3", None]},
    "non-int mtime": {**BODY, "mtime": [10, 5.5]},
    "mismatched mtime length": {**BODY, "mtime": [10]},
    "mismatched column length": {**BODY, "album_artist": [-1]},
    "missing column": {k: v for k, v in BODY.items() if k != "genre"},
    "extra key": {**BODY, "comment": []},
}


@pytest.mark.parametrize("header", BAD_HEADERS.values(), ids=BAD_HEADERS)
def test_invalid_header_is_deleted_and_reported(tmp_path, header):
    messages = []
    cache = make_cache(tmp_path, log=messages.append)
    write_raw(cache, header=header)
    assert cache.load() == {}
    assert not cache.path.exists()
    assert any("unreadable" in m for m in messages)


@pytest.mark.parametrize("body", BAD_BODIES.values(), ids=BAD_BODIES)
def test_invalid_body_is_deleted_and_reported(tmp_path, body):
    messages = []
    cache = make_cache(tmp_path, log=messages.append)
    write_raw(cache, body=body)
    assert cache.load() == {}
    assert not cache.path.exists()
    assert any("unreadable" in m for m in messages)


@pytest.mark.parametrize("header", BAD_HEADERS.values(), ids=BAD_HEADERS)
def test_clean_reports_invalid_header_as_unreadable(tmp_path, header):
    cache = make_cache(tmp_path)
    write_raw(cache, header=header)
    assert [r.reason for r in clean_cache(now=lambda: NOW)] == ["unreadable"]


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    cache = make_cache(tmp_path)
    cache.save(ENTRIES)
    assert [p.name for p in cache.path.parent.iterdir()] == [cache.path.name]


def test_save_failure_is_reported_not_raised(tmp_path, monkeypatch):
    messages = []
    cache = make_cache(tmp_path, log=messages.append)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    cache.save(ENTRIES)
    assert any("disk full" in m for m in messages)
    assert not list(cache.path.parent.glob(f"*{TMP_SUFFIX}"))


def test_key_unique_per_config_and_source(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    src1, src2 = tmp_path / "s1", tmp_path / "s2"
    keys = {cache_key(c, s) for c in (a, b) for s in (src1, src2)}
    assert len(keys) == 4


def test_two_configs_sharing_a_source_do_not_collide(tmp_path):
    first = make_cache(tmp_path, name="a.yaml")
    second = make_cache(tmp_path, name="b.yaml")
    assert first.path != second.path
    first.save(ENTRIES)
    second.save({"x.mp3": (1, None)})
    assert first.load() == ENTRIES


def test_cache_stays_compact_for_large_library(tmp_path):
    rng = random.Random(0)
    artists = [f"Artist {i}" for i in range(6000)]
    albums = [f"Album {i}" for i in range(4000)]
    genres = [f"Genre {i}" for i in range(50)]
    tracks = 100_000
    entries = {}
    for i in range(tracks):
        artist = rng.choice(artists)
        path = f"{artist}/{rng.choice(albums)}/{i:06d} Track {rng.randrange(10**6)}.mp3"
        mtime = 1_700_000_000_000_000_000 + rng.randrange(10**15)
        entries[path] = (mtime, (artist, rng.choice(albums), rng.choice(genres), None))
    cache = make_cache(tmp_path)
    cache.save(entries)
    assert cache.path.stat().st_size < 3_000_000
    assert cache.load() == entries


def write_cache_file(tmp_path, name, ttl="2d", now=NOW, **kw):
    cache = make_cache(tmp_path, ttl=ttl, now=now, name=name, **kw)
    cache.save(ENTRIES)
    return cache


def names(directory):
    return sorted(p.name for p in directory.iterdir())


def test_clean_removes_expired_keeps_valid(tmp_path):
    expired = write_cache_file(tmp_path, "old.yaml", ttl="1h", now=NOW - 7200)
    valid = write_cache_file(tmp_path, "new.yaml", ttl="1d")
    removed = clean_cache(now=lambda: NOW)
    assert [r.reason for r in removed] == ["expired"]
    assert not expired.path.exists()
    assert valid.path.exists()


def test_clean_removes_orphaned_config_and_source(tmp_path):
    gone_config = write_cache_file(tmp_path, "gone.yaml")
    gone_source = write_cache_file(tmp_path, "keep.yaml", source="other")
    gone_config.config_path.unlink()
    gone_source.source_root.rmdir()
    removed = clean_cache(now=lambda: NOW)
    assert {r.reason for r in removed} == {
        "orphaned: config file is gone",
        "orphaned: source path is gone",
    }


def test_clean_removes_unreadable_and_unknown_version(tmp_path, monkeypatch):
    bad = write_cache_file(tmp_path, "bad.yaml")
    bad.path.write_bytes(b"junk")
    old = write_cache_file(tmp_path, "old.yaml", source="src2")
    monkeypatch.setattr(cache_module, "CACHE_SCHEMA_VERSION", CACHE_SCHEMA_VERSION + 1)
    reasons = sorted(r.reason for r in clean_cache(now=lambda: NOW))
    assert reasons == ["unknown format version", "unreadable"]
    assert not old.path.exists()


def test_clean_all_removes_every_cache_file(tmp_path):
    first = write_cache_file(tmp_path, "a.yaml")
    second = write_cache_file(tmp_path, "b.yaml")
    removed = clean_cache(all_files=True, now=lambda: NOW)
    assert len(removed) == 2
    assert sum(r.size for r in removed) > 0
    assert not first.path.exists()
    assert not second.path.exists()
    assert not cache_dir().exists()


@pytest.mark.parametrize("all_files", [False, True])
def test_clean_removes_temp_files_and_ignores_foreign_files(tmp_path, all_files):
    write_cache_file(tmp_path, "a.yaml")
    directory = cache_dir()
    (directory / f"stray{TMP_SUFFIX}").write_bytes(b"partial")
    (directory / "notes.txt").write_text("keep me")
    removed = clean_cache(all_files=all_files, now=lambda: NOW)
    assert "interrupted write" in {r.reason for r in removed}
    assert (directory / "notes.txt").exists()
    assert not (directory / f"stray{TMP_SUFFIX}").exists()


def test_clean_leaves_valid_cache_untouched_by_default(tmp_path):
    cache = write_cache_file(tmp_path, "a.yaml")
    assert clean_cache(now=lambda: NOW) == []
    assert cache.path.name.endswith(CACHE_SUFFIX)
    assert cache.path.exists()


def test_clean_with_missing_directory_is_a_noop():
    assert not cache_dir().exists()
    assert clean_cache() == []
    assert clean_cache(all_files=True) == []


def test_clean_does_not_follow_symlinks(tmp_path):
    outside = tmp_path / "outside.mmcache"
    outside.write_bytes(b"precious")
    directory = cache_dir()
    directory.mkdir(parents=True)
    (directory / f"link{CACHE_SUFFIX}").symlink_to(outside)
    assert clean_cache(all_files=True) == []
    assert outside.exists()


def test_list_reports_status_and_header(tmp_path):
    ok = write_cache_file(tmp_path, "ok.yaml")
    expired = write_cache_file(tmp_path, "old.yaml", ttl="1h", now=NOW - 7200)
    bad = write_cache_file(tmp_path, "bad.yaml")
    bad.path.write_bytes(b"junk")
    (cache_dir() / f"stray{TMP_SUFFIX}").write_bytes(b"partial")
    listed = {i.name: i for i in list_cache(now=lambda: NOW)}
    assert {n: i.status for n, i in listed.items()} == {
        ok.path.name: "ok",
        expired.path.name: "expired",
        bad.path.name: "unreadable",
    }
    assert listed[ok.path.name].header.source_root == str(ok.source_root)
    assert listed[bad.path.name].header is None
    assert all(i.size > 0 for i in listed.values())


def test_list_with_missing_directory_is_empty():
    assert list_cache() == []


def test_list_command_output(tmp_path):
    assert CliRunner().invoke(cli, ["cache", "list"]).output == "No cache files\n"
    cache = write_cache_file(tmp_path, "a.yaml", now=time.time())
    out = CliRunner().invoke(cli, ["cache", "list"]).output
    assert out.startswith(f"{cache.path.name}  ok  ")
    assert f"{cache.source_root}  (config: {cache.config_path})" in out
