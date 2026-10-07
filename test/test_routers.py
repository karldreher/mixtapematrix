import logging
import os
import struct

import pytest
from helpers import make_mp3

from mixtapematrix.routers.files import File
from mixtapematrix.routers.mp3_router import configure_tag_logging


def test_file(mkdirs):
    file = File(path="test/source")
    assert file.is_dir
    assert not file.is_file


def test_invalid_file():
    with pytest.raises(ValueError):
        File(path="test/source/invalid")


# TODO: test TagRouter, need fixture for some mp3 files


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "a" / "one.mp3", artist="Alpha", album="First", genre="Funk")
    make_mp3(root / "a" / "two.mp3", artist="Beta", album="Second", genre="Metal")
    make_mp3(root / "b" / "three.mp3", artist="Alpha", album="Third", genre="Funk")
    (root / "b" / "plain.mp3").touch()  # no tag
    return root


def make_router(tmp_path, library, mp3_files, cache=True, exclude_paths=()):
    from mixtapematrix.cache import TagCache, parse_ttl
    from mixtapematrix.config import MatrixConfig
    from mixtapematrix.routers.mp3_router import TagRouter

    destination = tmp_path / "out"
    destination.mkdir(exist_ok=True)
    matrix = MatrixConfig(
        source_path=str(library),
        exclude_paths=[str(p) for p in exclude_paths],
        destination_path=str(destination),
        mp3_files=mp3_files,
    )
    config = tmp_path / "matrix.yaml"
    config.touch()
    tag_cache = TagCache(config, library, parse_ttl("1d")) if cache else None
    return TagRouter(matrix, cache=tag_cache)


def matched(router):
    return sorted(os.path.basename(f.path) for f in router.source)


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


def test_multiple_excluded_paths(tmp_path, library):
    router = make_router(
        tmp_path,
        library,
        [{"artist": "Alpha"}, {"artist": "Beta"}],
        cache=False,
        exclude_paths=[library / "a", library / "b"],
    )
    assert matched(router) == []


def test_excluded_directory_and_single_file(tmp_path, library):
    by_dir = make_router(
        tmp_path, library, [{"artist": "Alpha"}], False, [library / "a"]
    )
    assert matched(by_dir) == ["three.mp3"]
    by_file = make_router(
        tmp_path, library, [{"artist": "Alpha"}], False, [library / "a" / "one.mp3"]
    )
    assert matched(by_file) == ["three.mp3"]


def test_exclude_path_is_not_a_substring_match(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "rock" / "x.mp3", artist="Alpha")
    make_mp3(root / "Crockett" / "y.mp3", artist="Alpha")
    make_mp3(root / "rock" / "deep" / "z.mp3", artist="Alpha")
    router = make_router(tmp_path, root, [{"artist": "Alpha"}], False, [root / "rock"])
    assert matched(router) == ["y.mp3"]


def test_relative_and_absolute_excludes_resolve_the_same(
    tmp_path, library, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    relative = make_router(
        tmp_path, "library", [{"artist": "Alpha"}], False, ["library/a"]
    )
    absolute = make_router(
        tmp_path, library, [{"artist": "Alpha"}], False, [library / "a"]
    )
    assert matched(relative) == matched(absolute) == ["three.mp3"]


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "library"
    files = {
        "r1": ("Artist Name", "Album Name 1", "rock", None),
        "r3": ("Artist Name", "Album Name 3", "rock", None),
        "f1": ("Artist Name", "Album Name 1", "funk", None),
        "fb": ("Artist B", "Album Name 5", "funk", "Various"),
        "fc2": ("Artist C", "Album Name 2", "funk", None),
        "fc4": ("Artist C", "Album Name 4", "funk", None),
    }
    for name, (artist, album, genre, album_artist) in files.items():
        tags = {"artist": artist, "album": album, "genre": genre}
        if album_artist:
            tags["album_artist"] = album_artist
        make_mp3(root / f"{name}.mp3", **tags)
    (root / "plain.mp3").touch()
    return root


ENTRY_1 = {"artist": "Artist Name", "exclude": {"album": "Album Name 1"}}
ENTRY_2 = {
    "genre": "funk",
    "exclude": {"artist": "Artist B", "album": "Album Name 2"},
}


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([ENTRY_1], ["r3"]),
        ([ENTRY_2], ["f1", "fc4"]),
        # f1 is excepted by entry 1 but rescued by entry 2.
        ([ENTRY_1, ENTRY_2], ["f1", "fc4", "r3"]),
        # an exception on each of the four tags
        ([{"genre": "funk", "exclude": {"artist": "Artist C"}}], ["f1", "fb"]),
        (
            [{"genre": "funk", "exclude": {"album": "Album Name 1"}}],
            ["fb", "fc2", "fc4"],
        ),
        ([{"artist": "Artist Name", "exclude": {"genre": "rock"}}], ["f1"]),
        (
            [{"genre": "funk", "exclude": {"album_artist": "various"}}],
            ["f1", "fc2", "fc4"],
        ),
        # case-insensitive, both for the entry and for the exception
        ([{"genre": "FUNK", "exclude": {"artist": "ARTIST c"}}], ["f1", "fb"]),
        # nested: exclude artist C unless it is album 4
        (
            [
                {
                    "genre": "funk",
                    "exclude": {
                        "artist": "Artist C",
                        "exclude": {"album": "Album Name 4"},
                    },
                }
            ],
            ["f1", "fb", "fc4"],
        ),
        # the exception removes every match of its entry
        ([{"artist": "Artist B", "exclude": {"genre": "funk"}}], []),
        # no exclude: behaves as before
        ([{"artist": "Artist C"}], ["fc2", "fc4"]),
    ],
)
def test_exclude_blocks(tmp_path, catalog, entries, expected):
    router = make_router(tmp_path, catalog, entries, cache=False)
    names = [name.removesuffix(".mp3") for name in matched(router)]
    assert names == expected


def test_exclude_changes_need_no_tag_rereads(tmp_path, catalog, read_counter):
    first = make_router(tmp_path, catalog, [{"artist": "Artist Name"}])
    assert len(matched(first)) == 3
    read_counter.clear()
    second = make_router(tmp_path, catalog, [ENTRY_1])
    assert matched(second) == ["r3.mp3"]
    assert read_counter == []


@pytest.fixture
def genres_tree(tmp_path):
    root = tmp_path / "library"
    for folder in ("rock", "rockabilly", "Crockett", "pop"):
        make_mp3(root / folder / "deep" / f"{folder}.mp3", artist="Alpha")
    return root


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        # prefix: rock and rockabilly, not Crockett
        ("{root}/rock**", ["Crockett.mp3", "pop.mp3"]),
        # everything beneath rock only
        ("{root}/rock/**", ["Crockett.mp3", "pop.mp3", "rockabilly.mp3"]),
        ("{root}/**", []),
    ],
)
def test_tail_glob_excludes(tmp_path, genres_tree, pattern, expected):
    router = make_router(
        tmp_path,
        genres_tree,
        [{"artist": "Alpha"}],
        False,
        [pattern.format(root=genres_tree)],
    )
    assert matched(router) == expected


def test_relative_tail_glob_resolves_like_absolute(tmp_path, genres_tree, monkeypatch):
    monkeypatch.chdir(tmp_path)
    router = make_router(
        tmp_path, "library", [{"artist": "Alpha"}], False, ["library/rock/**"]
    )
    assert matched(router) == ["Crockett.mp3", "pop.mp3", "rockabilly.mp3"]


def test_glob_exclude_need_not_exist(tmp_path, genres_tree):
    router = make_router(
        tmp_path, genres_tree, [{"artist": "Alpha"}], False, [f"{genres_tree}/nope/**"]
    )
    assert len(matched(router)) == 4


def test_tag_warnings_are_silent_by_default(capsys):
    configure_tag_logging(verbose=False)
    logging.getLogger("eyed3.id3.tag").warning("Non standard genre name: Dance & DJ")
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_tag_warnings_shown_when_verbose(capsys):
    configure_tag_logging(verbose=True)
    try:
        logging.getLogger("eyed3.id3.tag").warning("Non standard genre name: X")
        assert "Non standard genre name: X" in capsys.readouterr().err
    finally:
        configure_tag_logging(verbose=False)


def test_verbose_tag_warnings_name_the_file(tmp_path, capsys):
    from mixtapematrix.routers import mp3_router

    path = tmp_path / "quirky.mp3"
    make_mp3(path, artist="A")
    configure_tag_logging(verbose=True)
    try:
        token = mp3_router._current_file.set(str(path))
        logging.getLogger("eyed3.id3.tag").warning("Invalid date: 0106")
        mp3_router._current_file.reset(token)
        assert f"{path}: Invalid date: 0106" in capsys.readouterr().err
    finally:
        configure_tag_logging(verbose=False)


@pytest.fixture
def folders(library):
    make_mp3(library / "a" / "deep" / "four.mp3", artist="Gamma", genre="Pop")
    make_mp3(library / "rock" / "x.mp3", artist="Delta", genre="Rock")
    make_mp3(library / "rockabilly" / "y.mp3", artist="Epsilon", genre="Rock")
    return library


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        # every tagged mp3 beneath the folder, nested ones included, whatever its tags
        ([{"folder": "a"}], ["four.mp3", "one.mp3", "two.mp3"]),
        # whole path components: rock does not match rockabilly
        ([{"folder": "rock"}], ["x.mp3"]),
        # untagged mp3s are still not copied
        ([{"folder": "b"}], ["three.mp3"]),
        # any key matches, as for tags
        (
            [{"folder": "a", "artist": "Alpha"}],
            ["four.mp3", "one.mp3", "three.mp3", "two.mp3"],
        ),
        ([{"folder": "rock"}, {"artist": "Beta"}], ["two.mp3", "x.mp3"]),
        # trailing-** prefix patterns, as in exclude_paths: rock** includes rockabilly
        ([{"folder": "rock**"}], ["x.mp3", "y.mp3"]),
        ([{"folder": "a/**"}], ["four.mp3", "one.mp3", "two.mp3"]),
        ([{"folder": "a/deep/**"}], ["four.mp3"]),
        ([{"folder": "nope/**"}], []),  # glob entries need not exist
        ([{"artist": "Alpha", "exclude": {"folder": "a/**"}}], ["three.mp3"]),
        ([{"folder": "a", "exclude": {"folder": "a/d**"}}], ["one.mp3", "two.mp3"]),
        # tags may exclude folders, folders may exclude tags, and either may nest
        ([{"artist": "Alpha", "exclude": {"folder": "a"}}], ["three.mp3"]),
        ([{"folder": "a", "exclude": {"genre": "metal"}}], ["four.mp3", "one.mp3"]),
        ([{"folder": "a", "exclude": {"folder": "a/deep"}}], ["one.mp3", "two.mp3"]),
        (
            [
                {
                    "folder": "a",
                    "exclude": {
                        "folder": "a/deep",
                        "exclude": {"artist": "Gamma"},
                    },
                }
            ],
            ["four.mp3", "one.mp3", "two.mp3"],
        ),
    ],
)
def test_folder_entries(tmp_path, folders, entries, expected):
    def absolute(entry):
        entry = dict(entry)
        if "folder" in entry:
            entry["folder"] = str(folders / entry["folder"])
        if "exclude" in entry:
            entry["exclude"] = absolute(entry["exclude"])
        return entry

    router = make_router(tmp_path, folders, [absolute(e) for e in entries])
    assert matched(router) == expected


def test_exclude_paths_win_over_folder(tmp_path, folders):
    router = make_router(
        tmp_path,
        folders,
        [{"folder": str(folders / "a")}],
        exclude_paths=[folders / "a" / "deep"],
    )
    assert matched(router) == ["one.mp3", "two.mp3"]


def test_folder_entry_reads_no_extra_tags(tmp_path, folders, read_counter):
    router = make_router(tmp_path, folders, [{"folder": str(folders / "a")}])
    matched(router)
    read_counter.clear()
    router = make_router(tmp_path, folders, [{"folder": str(folders / "rock")}])
    assert matched(router) == ["x.mp3"]
    assert read_counter == []  # changing folders reuses the tag cache


def test_folder_must_be_absolute():
    from mixtapematrix.config import Mp3Match

    with pytest.raises(ValueError, match="absolute"):
        Mp3Match(folder="a")


@pytest.mark.parametrize("where", ["missing", "outside", "outside_glob"])
def test_bad_folders_fail_before_copying(tmp_path, folders, where):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    folder = {
        "missing": folders / "nope",
        "outside": outside,
        "outside_glob": tmp_path / "elsewh**",
    }[where]
    router = make_router(tmp_path, folders, [{"folder": str(folder)}])
    with pytest.raises(ValueError, match="Folder"):
        matched(router)


def test_prune_keeps_files_copied_through_a_folder(tmp_path, folders):
    import yaml
    from click.testing import CliRunner

    from mixtapematrix.main import cli

    out = tmp_path / "dest"
    (out / "stale").mkdir(parents=True)
    (out / "stale" / "old.mp3").touch()
    config = tmp_path / "matrix.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "matrix": [
                    {
                        "source_path": str(folders),
                        "destination_path": str(out),
                        "mp3_files": [{"folder": str(folders / "a")}],
                    }
                ]
            }
        )
    )
    result = CliRunner().invoke(cli, ["run", "--config", str(config), "--prune"])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in out.rglob("*.mp3")) == [
        "four.mp3",
        "one.mp3",
        "two.mp3",
    ]


BAD_PATTERNS = ["/m/*/rock", "/m/ro?k", "/m/[rp]ock", "/m/*.mp3"]
GOOD_PATTERNS = ["/m/rock", "/m/rock**", "/m/rock/**"]


def path_pattern_fields():
    """Each way a config takes a path pattern: name -> builder from one value."""
    from mixtapematrix.config import MatrixConfig, Mp3Match

    return {
        "exclude_paths": lambda value: MatrixConfig(
            source_path="/m",
            exclude_paths=[value],
            destination_path="/d",
            mp3_files=[{"artist": "x"}],
        ),
        "folder": lambda value: Mp3Match(folder=value),
    }


@pytest.mark.parametrize("field", ["exclude_paths", "folder"])
@pytest.mark.parametrize("pattern", BAD_PATTERNS)
def test_path_fields_reject_the_same_patterns(field, pattern):
    with pytest.raises(ValueError, match="trailing '\\*\\*'"):
        path_pattern_fields()[field](pattern)


@pytest.mark.parametrize("field", ["exclude_paths", "folder"])
@pytest.mark.parametrize("pattern", GOOD_PATTERNS)
def test_path_fields_accept_the_same_patterns(field, pattern):
    path_pattern_fields()[field](pattern)


def test_path_fields_use_the_shared_pattern_type():
    """New location fields must use PathPattern so the glob contract stays in one place."""
    from mixtapematrix.config import MatrixConfig, Mp3Match
    from mixtapematrix.routers.files import PathPattern

    assert MatrixConfig.model_fields["exclude_paths"].annotation == list[PathPattern]
    assert Mp3Match.model_fields["folder"].annotation == PathPattern | None
