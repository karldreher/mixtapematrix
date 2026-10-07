import pytest
from click.testing import CliRunner
from helpers import make_mp3, write_config

from mixtapematrix.main import cli


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


@pytest.fixture
def song(library):
    """The full path a song is shown as, from its path under the library."""
    return lambda rel: str(library / rel)


def describe(tmp_path, library, *args):
    config = write_config(tmp_path, [library])
    result = CliRunner().invoke(
        cli, ["describe", "tag", *args, "--config", str(config)]
    )
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def test_songs_are_shown_as_full_paths(tmp_path, library, song):
    lines = describe(tmp_path, library, "album", "third")
    assert lines == ["Third", f"└── {song('d2/three.mp3')}"]
    assert song("d2/three.mp3").startswith("/")


def test_relative_source_path_is_shown_as_an_absolute_path(
    tmp_path, library, song, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    config = write_config(tmp_path, ["library"])
    result = CliRunner().invoke(
        cli, ["describe", "tag", "album", "third", "--config", str(config)]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["Third", f"└── {song('d2/three.mp3')}"]


def test_artist_is_the_top_level_above_albums_and_songs(tmp_path, library, song):
    assert describe(tmp_path, library, "artist") == [
        "Alpha",
        "├── First",
        f"│   ├── {song('d1/one.mp3')}",
        f"│   └── {song('d1/two.mp3')}",
        "└── Third",
        f"    └── {song('d2/three.mp3')}",
        "Beta",
        "├── (unknown album)",
        f"│   └── {song('d2/loose.mp3')}",
        "└── First",
        f"    └── {song('d2/four.mp3')}",
    ]


def test_artist_value_shows_one_artist(tmp_path, library, song):
    assert describe(tmp_path, library, "artist", "alpha") == [
        "Alpha",
        "├── First",
        f"│   ├── {song('d1/one.mp3')}",
        f"│   └── {song('d1/two.mp3')}",
        "└── Third",
        f"    └── {song('d2/three.mp3')}",
    ]


def test_album_is_the_top_level_above_its_songs(tmp_path, library, song):
    assert describe(tmp_path, library, "album") == [
        "(unknown album)",
        f"└── {song('d2/loose.mp3')}",
        "First",
        f"├── {song('d1/one.mp3')}",
        f"├── {song('d1/two.mp3')}",
        f"└── {song('d2/four.mp3')}",
        "Third",
        f"└── {song('d2/three.mp3')}",
    ]


def test_genre_is_the_top_level_above_artist_album_song(tmp_path, library, song):
    assert describe(tmp_path, library, "genre") == [
        "Funk",
        "├── Alpha",
        "│   └── First",
        f"│       ├── {song('d1/one.mp3')}",
        f"│       └── {song('d1/two.mp3')}",
        "└── Beta",
        "    ├── (unknown album)",
        f"    │   └── {song('d2/loose.mp3')}",
        "    └── First",
        f"        └── {song('d2/four.mp3')}",
        "Metal",
        "└── Alpha",
        "    └── Third",
        f"        └── {song('d2/three.mp3')}",
    ]


def test_genre_value_shows_one_genre(tmp_path, library, song):
    assert describe(tmp_path, library, "genre", "METAL") == [
        "Metal",
        "└── Alpha",
        "    └── Third",
        f"        └── {song('d2/three.mp3')}",
    ]


def test_filter_flags_narrow_the_described_files(tmp_path, library, song):
    assert describe(tmp_path, library, "genre", "--artist", "beta") == [
        "Funk",
        "└── Beta",
        "    ├── (unknown album)",
        f"    │   └── {song('d2/loose.mp3')}",
        "    └── First",
        f"        └── {song('d2/four.mp3')}",
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
        f"    ├── {root / 'a.mp3'}",
        f"    └── {root / 'b.mp3'}",
    ]


def test_album_artist_is_the_top_level_and_skips_files_without_one(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "a.mp3", artist="One", album="Mix", album_artist="Various")
    make_mp3(root / "b.mp3", artist="Two", album="Solo")  # no album_artist
    assert describe(tmp_path, root, "album_artist") == [
        "Various",
        "└── One",
        "    └── Mix",
        f"        └── {root / 'a.mp3'}",
    ]


def test_invalid_field_is_a_usage_error(tmp_path, library):
    config = write_config(tmp_path, [library])
    result = CliRunner().invoke(
        cli, ["describe", "tag", "bogus", "--config", str(config)]
    )
    assert result.exit_code == 2


def test_describe_uses_the_cache(tmp_path, library, read_counter):
    first = describe(tmp_path, library, "artist")
    assert len(read_counter) == 6
    read_counter.clear()
    assert describe(tmp_path, library, "artist") == first
    assert read_counter == []


def test_missing_config_fails_cleanly():
    result = CliRunner().invoke(
        cli, ["describe", "tag", "artist", "--config", "nope.yaml"]
    )
    assert result.exit_code == 1
    assert "Config file not found" in result.output
