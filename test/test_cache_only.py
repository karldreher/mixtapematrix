"""list tag and describe tag read a valid cache as is; --refresh rescans."""

import os

import pytest
from click.testing import CliRunner
from helpers import cache_files, make_mp3, write_config

from mixtapematrix import cache as cache_module
from mixtapematrix.main import cli
from mixtapematrix.routers import mp3_router
from mixtapematrix.routers.mp3_router import TagRouter


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "one.mp3", artist="Alpha")
    make_mp3(root / "keep" / "two.mp3", artist="Beta")
    make_mp3(root / "skip" / "three.mp3", artist="Gamma")
    make_mp3(root / "skipme" / "four.mp3", artist="Delta")
    return root


@pytest.fixture
def config(tmp_path, library):
    return write_config(tmp_path, [library])


def invoke(config, *args):
    result = CliRunner().invoke(cli, [*args, "--config", str(config)])
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def artists(config, *args):
    return invoke(config, "list", "tag", "artist", *args)


@pytest.fixture
def no_scan(monkeypatch):
    """Fail the test if anything walks the source or validates files against it."""

    def fail(*args, **kwargs):
        raise AssertionError("the source was scanned")

    monkeypatch.setattr(mp3_router, "search_files", fail)
    monkeypatch.setattr(TagRouter, "_discover_tags", fail)


def test_warm_cache_is_read_without_scanning(config, monkeypatch):
    first = artists(config)  # cold: scans and fills the cache
    assert first == ["Alpha", "Beta", "Delta", "Gamma"]
    with monkeypatch.context() as m:
        m.setattr(mp3_router, "search_files", None)  # any call would fail
        m.setattr(TagRouter, "_discover_tags", None)
        assert artists(config) == first


def test_describe_tag_is_also_cache_only(config, monkeypatch, tmp_path):
    expected = invoke(config, "describe", "tag", "artist")
    with monkeypatch.context() as m:
        m.setattr(mp3_router, "search_files", None)
        m.setattr(TagRouter, "_discover_tags", None)
        assert invoke(config, "describe", "tag", "artist") == expected


def test_changes_show_only_after_refresh(tmp_path, library, config):
    artists(config)
    make_mp3(library / "new.mp3", artist="Epsilon")
    (library / "one.mp3").unlink()
    stale = ["Alpha", "Beta", "Delta", "Gamma"]
    assert artists(config) == stale  # cache read as is
    before = cache_files(tmp_path)

    assert artists(config, "--refresh") == ["Beta", "Delta", "Epsilon", "Gamma"]
    assert cache_files(tmp_path) != before  # --refresh rewrote the cache
    assert artists(config) == ["Beta", "Delta", "Epsilon", "Gamma"]


def test_plain_runs_never_write_the_cache(tmp_path, config):
    artists(config)
    before = cache_files(tmp_path)
    assert before
    artists(config)
    invoke(config, "describe", "tag", "artist")
    assert cache_files(tmp_path) == before


@pytest.mark.parametrize(
    "exclude",
    [
        lambda root: [root / "skip"],  # a directory
        lambda root: [f"{root}/skip**"],  # a prefix pattern: skip and skipme
        lambda root: [f"{root}/skip/**"],  # everything beneath skip
    ],
)
def test_current_excludes_apply_to_cached_entries(tmp_path, library, exclude):
    config = write_config(tmp_path, [library])
    artists(config)  # cache built with no excludes
    write_config(tmp_path, [library], exclude_paths=exclude(library))  # same path
    result = artists(config)
    assert "Gamma" not in result
    assert ("Delta" not in result) == ("skip**" in str(exclude(library)[0]))
    assert {"Alpha", "Beta"} <= set(result)


@pytest.mark.parametrize("breakage", ["none", "empty", "corrupt", "schema"])
def test_unusable_cache_falls_back_to_a_scan(tmp_path, config, monkeypatch, breakage):
    if breakage == "none":
        config = write_config(tmp_path, [tmp_path / "library"], cache=False)
    else:
        artists(config)
        (path,) = cache_files(tmp_path)
        if breakage == "empty":
            from mixtapematrix.cache import TagCache, parse_ttl

            TagCache(config, tmp_path / "library", parse_ttl("1d")).save({})
        elif breakage == "corrupt":
            path.write_bytes(b"garbage")
        else:
            monkeypatch.setattr(cache_module, "CACHE_SCHEMA_VERSION", 99)
    # A discarded cache is reported first; the values follow from a full scan.
    assert artists(config)[-4:] == ["Alpha", "Beta", "Delta", "Gamma"]


def test_unusable_cache_is_refilled_for_next_time(tmp_path, config):
    artists(config)
    (path,) = cache_files(tmp_path)
    path.write_bytes(b"garbage")
    artists(config)  # scans and rewrites
    assert cache_files(tmp_path)[path] != b"garbage"


def test_no_cache_reads_every_file_and_leaves_the_cache_alone(
    tmp_path, config, monkeypatch
):
    artists(config)
    before = cache_files(tmp_path)
    calls = []
    real = mp3_router.read_tags
    monkeypatch.setattr(
        mp3_router, "read_tags", lambda p: (calls.append(p), real(p))[1]
    )
    assert artists(config, "--no-cache") == ["Alpha", "Beta", "Delta", "Gamma"]
    assert len(calls) == 4
    assert cache_files(tmp_path) == before


def test_describe_untagged_still_sees_files_the_cache_has_not(
    tmp_path, library, config
):
    artists(config)
    make_mp3(library / "fresh.mp3")  # untagged, added after the cache was built
    assert invoke(config, "describe", "untagged") == [str(library / "fresh.mp3")]


def test_help_explains_staleness_and_refresh():
    for command in (["list", "tag"], ["describe", "tag"]):
        out = CliRunner().invoke(cli, [*command, "--help"]).output
        assert "--refresh" in out
    assert (
        "--refresh"
        not in CliRunner().invoke(cli, ["describe", "untagged", "--help"]).output
    )


def test_cached_paths_are_absolute(tmp_path, library, config):
    invoke(config, "describe", "tag", "artist")
    lines = invoke(config, "describe", "tag", "artist")
    assert all(
        os.path.isabs(line.split("── ")[-1]) for line in lines if line.endswith(".mp3")
    )
