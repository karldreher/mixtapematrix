import os

import pytest
from click.testing import CliRunner
from eyed3.id3 import Tag
from helpers import cache_files, make_mp3, write_config

from mixtapematrix.main import cli


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "tagged1.mp3", artist="Alpha")
    make_mp3(root / "d" / "tagged2.mp3", artist="Beta")
    make_mp3(root / "Zed.mp3")  # no tag
    make_mp3(root / "d" / "apple.mp3")  # no tag
    return root


def untagged(tmp_path, library, *args):
    config = write_config(tmp_path, [library])
    result = CliRunner().invoke(
        cli, ["describe", "untagged", "--config", str(config), *args]
    )
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def test_lists_only_untagged_files_as_sorted_full_paths(tmp_path, library):
    assert untagged(tmp_path, library) == [
        str(library / "d" / "apple.mp3"),
        str(library / "Zed.mp3"),
    ]


def test_everything_tagged_prints_nothing(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "a.mp3", artist="Alpha")
    assert untagged(tmp_path, root) == []


def test_tag_filters_are_not_accepted(tmp_path, library):
    config = write_config(tmp_path, [library])
    result = CliRunner().invoke(
        cli, ["describe", "untagged", "--artist", "Alpha", "--config", str(config)]
    )
    assert result.exit_code == 2
    assert "No such option" in result.output


def test_cached_tagged_files_are_skipped_and_untagged_are_reread(
    tmp_path, library, read_counter
):
    config = write_config(tmp_path, [library])
    CliRunner().invoke(cli, ["list", "tag", "artist", "--config", str(config)])
    assert len(read_counter) == 4  # warms the cache: every file read once
    read_counter.clear()
    assert len(untagged(tmp_path, library)) == 2
    assert sorted(os.path.basename(p) for p in read_counter) == [
        "Zed.mp3",
        "apple.mp3",
    ]  # tagged ones skipped


def test_cache_is_never_written(tmp_path, library):
    config = write_config(tmp_path, [library])
    CliRunner().invoke(cli, ["list", "tag", "artist", "--config", str(config)])
    before = cache_files(tmp_path)
    assert before
    # A new untagged file the cache has not seen must not be added to it.
    make_mp3(library / "new.mp3")
    assert str(library / "new.mp3") in untagged(tmp_path, library)
    assert cache_files(tmp_path) == before


def test_without_a_cache_block_nothing_is_skipped_or_written(
    tmp_path, library, read_counter
):
    config = write_config(tmp_path, [library], cache=False)
    result = CliRunner().invoke(cli, ["describe", "untagged", "--config", str(config)])
    assert result.exit_code == 0
    assert len(read_counter) == 4
    assert cache_files(tmp_path) == {}


def test_no_cache_reads_every_file(tmp_path, library, read_counter):
    config = write_config(tmp_path, [library])
    CliRunner().invoke(cli, ["list", "tag", "artist", "--config", str(config)])
    read_counter.clear()
    untagged(tmp_path, library, "--no-cache")
    assert len(read_counter) == 4


def test_cached_no_tag_is_not_trusted(tmp_path):
    root = tmp_path / "library"
    plain = root / "plain.mp3"
    make_mp3(plain)
    config = write_config(tmp_path, [root])
    # The cache records plain.mp3 as untagged...
    CliRunner().invoke(cli, ["list", "tag", "artist", "--config", str(config)])
    assert untagged(tmp_path, root) == [str(plain)]
    # ...then it gains a tag, with its mtime restored so the entry still matches.
    stat = plain.stat()
    tag = Tag()
    tag.artist = "Now Tagged"
    tag.save(str(plain))
    os.utime(plain, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert untagged(tmp_path, root) == []


def test_changed_file_cached_as_tagged_is_checked_again(tmp_path):
    root = tmp_path / "library"
    song = root / "song.mp3"
    make_mp3(song, artist="Alpha")
    config = write_config(tmp_path, [root])
    CliRunner().invoke(cli, ["list", "tag", "artist", "--config", str(config)])
    assert untagged(tmp_path, root) == []
    stat = song.stat()
    song.write_bytes(b"")  # tag stripped, so the cached entry no longer applies
    os.utime(song, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert untagged(tmp_path, root) == [str(song)]


def test_missing_config_fails_cleanly():
    result = CliRunner().invoke(cli, ["describe", "untagged", "--config", "nope.yaml"])
    assert result.exit_code == 1
    assert "Config file not found" in result.output
