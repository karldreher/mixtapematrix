import pytest
import yaml
from click.testing import CliRunner
from eyed3.id3 import Tag

from mixtapematrix.main import cli
from mixtapematrix.routers import mp3_router


def make_mp3(path, **tags):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    if tags:
        tag = Tag()
        for key, value in tags.items():
            setattr(tag, key, value)
        tag.save(str(path))


def write_config(tmp_path, sources, cache=True):
    data = {
        "matrix": [
            {
                "source_path": str(source),
                "destination_path": str(tmp_path / f"out{i}"),
                "mp3_files": [{"artist": "nobody"}],  # list ignores matrix filters
            }
            for i, source in enumerate(sources)
        ]
    }
    for i in range(len(sources)):
        (tmp_path / f"out{i}").mkdir()
    if cache:
        data["cache"] = {"ttl": "1d"}
    config = tmp_path / "matrix.yaml"
    config.write_text(yaml.safe_dump(data))
    return config


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "one.mp3", artist="beta", genre="Funk", album="First")
    make_mp3(root / "two.mp3", artist="Alpha", genre="Metal", album="Second")
    make_mp3(root / "three.mp3", artist="ALPHA", genre="Funk", album="Third")
    make_mp3(root / "plain.mp3")  # no tag
    make_mp3(root / "no_album.mp3", artist="Gamma")  # artist only
    return root


@pytest.fixture
def read_counter(monkeypatch):
    calls = []
    real = mp3_router.read_tags

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(mp3_router, "read_tags", counting)
    return calls


def list_tag(config, field, *args):
    result = CliRunner().invoke(
        cli, ["list", "tag", field, "--config", str(config), *args]
    )
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def test_lists_sorted_distinct_values_case_insensitively(tmp_path, library):
    config = write_config(tmp_path, [library])
    assert list_tag(config, "artist") == ["Alpha", "beta", "Gamma"]
    assert list_tag(config, "genre") == ["Funk", "Metal"]


def test_skips_files_without_the_tag(tmp_path, library):
    config = write_config(tmp_path, [library])
    assert list_tag(config, "album") == ["First", "Second", "Third"]


def test_merges_every_matrix_source(tmp_path, library):
    other = tmp_path / "other"
    make_mp3(other / "x.mp3", artist="Delta")
    config = write_config(tmp_path, [library, other])
    assert list_tag(config, "artist") == ["Alpha", "beta", "Delta", "Gamma"]


def test_invalid_field_is_a_usage_error(tmp_path, library):
    config = write_config(tmp_path, [library])
    result = CliRunner().invoke(cli, ["list", "tag", "bogus", "--config", str(config)])
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_second_run_is_served_from_the_cache(tmp_path, library, read_counter):
    config = write_config(tmp_path, [library])
    first = list_tag(config, "artist")
    assert len(read_counter) == 5  # cold cache: every file read, then saved
    read_counter.clear()
    assert list_tag(config, "artist") == first
    assert read_counter == []


def test_no_cache_reads_every_file(tmp_path, library, read_counter):
    config = write_config(tmp_path, [library])
    list_tag(config, "artist")
    read_counter.clear()
    list_tag(config, "artist", "--no-cache")
    assert len(read_counter) == 5


def test_list_group_appears_in_help():
    result = CliRunner().invoke(cli, [])
    assert "list" in result.output


def test_filters_by_a_second_tag(tmp_path, library):
    config = write_config(tmp_path, [library])
    assert list_tag(config, "album", "--artist", "alpha") == ["Second", "Third"]
    assert list_tag(config, "artist", "--genre", "FUNK") == ["ALPHA", "beta"]


def test_filters_combine_with_and(tmp_path, library):
    config = write_config(tmp_path, [library])
    args = ["--artist", "Alpha", "--genre", "Metal"]
    assert list_tag(config, "album", *args) == ["Second"]


def test_filter_with_no_matches_prints_nothing(tmp_path, library):
    config = write_config(tmp_path, [library])
    assert list_tag(config, "album", "--artist", "Nobody") == []


def test_album_artist_filter_accepts_both_spellings(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "a.mp3", artist="One", album_artist="Various", album="Mix")
    make_mp3(root / "b.mp3", artist="Two", album_artist="Other", album="Solo")
    config = write_config(tmp_path, [root])
    assert list_tag(config, "album", "--album-artist", "various") == ["Mix"]
    assert list_tag(config, "album", "--album_artist", "various") == ["Mix"]


def test_filtering_does_not_bypass_the_cache(tmp_path, library, read_counter):
    config = write_config(tmp_path, [library])
    list_tag(config, "artist")
    read_counter.clear()
    list_tag(config, "album", "--artist", "Alpha")
    assert read_counter == []
