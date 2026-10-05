import pytest
from click.testing import CliRunner
from helpers import make_mp3, write_config

from mixtapematrix.main import cli
from mixtapematrix.routers import mp3_router


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "d1" / "one.mp3", artist="Alpha", album="First", genre="Funk")
    make_mp3(root / "d1" / "two.mp3", artist="Alpha", album="First", genre="Funk")
    make_mp3(root / "d2" / "three.mp3", artist="Alpha", album="Third", genre="Metal")
    make_mp3(root / "d2" / "four.mp3", artist="Beta", album="First", genre="Funk")
    make_mp3(root / "d2" / "loose.mp3", artist="Beta", genre="Funk")  # no album
    make_mp3(root / "d3" / "plain.mp3")  # no tag: skipped
    return root


def describe(tmp_path, library, *args):
    config = write_config(tmp_path, [library])
    result = CliRunner().invoke(
        cli, ["describe", "tag", *args, "--config", str(config)]
    )
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def test_artist_is_the_top_level_above_albums_and_songs(tmp_path, library):
    assert describe(tmp_path, library, "artist") == [
        "Alpha",
        "├── First",
        "│   ├── one",
        "│   └── two",
        "└── Third",
        "    └── three",
        "Beta",
        "├── (unknown album)",
        "│   └── loose",
        "└── First",
        "    └── four",
    ]


def test_artist_value_shows_one_artist(tmp_path, library):
    assert describe(tmp_path, library, "artist", "alpha") == [
        "Alpha",
        "├── First",
        "│   ├── one",
        "│   └── two",
        "└── Third",
        "    └── three",
    ]


def test_album_is_the_top_level_above_its_songs(tmp_path, library):
    assert describe(tmp_path, library, "album") == [
        "(unknown album)",
        "└── loose",
        "First",
        "├── four",
        "├── one",
        "└── two",
        "Third",
        "└── three",
    ]


def test_album_value_shows_one_album(tmp_path, library):
    assert describe(tmp_path, library, "album", "third") == ["Third", "└── three"]


def test_genre_is_the_top_level_above_artist_album_song(tmp_path, library):
    assert describe(tmp_path, library, "genre") == [
        "Funk",
        "├── Alpha",
        "│   └── First",
        "│       ├── one",
        "│       └── two",
        "└── Beta",
        "    ├── (unknown album)",
        "    │   └── loose",
        "    └── First",
        "        └── four",
        "Metal",
        "└── Alpha",
        "    └── Third",
        "        └── three",
    ]


def test_genre_value_shows_one_genre(tmp_path, library):
    assert describe(tmp_path, library, "genre", "METAL") == [
        "Metal",
        "└── Alpha",
        "    └── Third",
        "        └── three",
    ]


def test_filter_flags_narrow_the_described_files(tmp_path, library):
    assert describe(tmp_path, library, "genre", "--artist", "beta") == [
        "Funk",
        "└── Beta",
        "    ├── (unknown album)",
        "    │   └── loose",
        "    └── First",
        "        └── four",
    ]


def test_no_matches_prints_nothing(tmp_path, library):
    assert describe(tmp_path, library, "genre", "polka") == []
    assert describe(tmp_path, library, "artist", "nobody") == []


def test_case_variants_share_one_node(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "a.mp3", artist="alpha", album="x")
    make_mp3(root / "b.mp3", artist="ALPHA", album="X")
    assert describe(tmp_path, root, "artist") == [
        "ALPHA",
        "└── X",
        "    ├── a",
        "    └── b",
    ]


def test_invalid_field_is_a_usage_error(tmp_path, library):
    config = write_config(tmp_path, [library])
    result = CliRunner().invoke(
        cli, ["describe", "tag", "bogus", "--config", str(config)]
    )
    assert result.exit_code == 2


def test_describe_uses_the_cache(tmp_path, library, monkeypatch):
    calls = []
    real = mp3_router.read_tags
    monkeypatch.setattr(
        mp3_router, "read_tags", lambda p: (calls.append(p), real(p))[1]
    )
    first = describe(tmp_path, library, "artist")
    assert len(calls) == 6
    calls.clear()
    assert describe(tmp_path, library, "artist") == first
    assert calls == []


def test_missing_config_fails_cleanly():
    result = CliRunner().invoke(
        cli, ["describe", "tag", "artist", "--config", "nope.yaml"]
    )
    assert result.exit_code == 1
    assert "Config file not found" in result.output


def test_album_artist_is_the_top_level_and_skips_files_without_one(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "a.mp3", artist="One", album="Mix", album_artist="Various")
    make_mp3(root / "b.mp3", artist="Two", album="Solo")  # no album_artist
    assert describe(tmp_path, root, "album_artist") == [
        "Various",
        "└── One",
        "    └── Mix",
        "        └── a",
    ]
