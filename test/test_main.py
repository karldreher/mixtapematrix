import json
from datetime import timedelta

import click
import pytest
import yaml
from click.testing import CliRunner
from helpers import cache_files, make_mp3, write_config
from jsonschema import Draft202012Validator

from mixtapematrix.config import ConfigFile, Mp3Match
from mixtapematrix.main import MixtapeMatrix, cli


def transform_config(tmp_path, *commands):
    source, destination = tmp_path / "source", tmp_path / "output"
    (source / "exclude").mkdir(parents=True)
    destination.mkdir()
    config = tmp_path / "matrix.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "matrix": [
                    {
                        "source_path": str(source),
                        "exclude_paths": [str(source / "exclude")],
                        "destination_path": str(destination),
                        "mp3_files": [{"genre": "funk"}, {"artist": "Fear Factory"}],
                    }
                ],
                "transform": {"commands": list(commands)},
            }
        )
    )
    return config


def test_config(tmp_path):
    config = MixtapeMatrix(str(transform_config(tmp_path, "true"))).config_data
    assert config.matrix[0].source_path == str(tmp_path / "source")
    assert config.matrix[0].destination_path == str(tmp_path / "output")
    assert config.transform.commands == ["true"]


def test_invalid_config():
    with pytest.raises(ValueError):
        ConfigFile.model_validate({"rotten": ["anything"]})


def test_dangerous_transform():
    with pytest.raises(ValueError, match="dangerous"):
        ConfigFile.model_validate(
            {"matrix": [], "transform": {"commands": ["rm -rf /"]}}
        )


def test_cli():
    assert isinstance(cli, click.Group)


def test_bare_command_shows_help_and_exits_1():
    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 1
    assert "Usage:" in result.output
    assert "run" in result.output
    assert "init" in result.output


def test_help_exits_0():
    assert CliRunner().invoke(cli, ["--help"]).exit_code == 0


def test_run_missing_config_fails():
    result = CliRunner().invoke(cli, ["run", "--config", "does-not-exist.yaml"])
    assert result.exit_code == 1
    assert "Config file not found: does-not-exist.yaml" in result.output
    assert "mixtape init" in result.output


def test_list_tag_missing_config_fails_cleanly():
    result = CliRunner().invoke(
        cli, ["list", "tag", "artist", "--config", "does-not-exist.yaml"]
    )
    assert result.exit_code == 1
    assert "Config file not found: does-not-exist.yaml" in result.output
    assert not isinstance(result.exception, FileNotFoundError)


def test_run_executes_transform_commands(tmp_path):
    marker = tmp_path / "ran"
    config = transform_config(tmp_path, f"touch {marker}")
    result = CliRunner().invoke(cli, ["run", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert marker.exists()


def test_init_creates_config_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(cli, ["init"]).exit_code == 0
    assert runner.invoke(cli, ["init"]).exit_code == 1


def test_init_writes_schema_and_modeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(cli, ["init"]).exit_code == 0
    schema = json.loads((tmp_path / "matrix.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert schema == ConfigFile.model_json_schema(mode="validation")
    text = (tmp_path / "matrix.yaml").read_text()
    assert text.splitlines()[0] == (
        "# yaml-language-server: $schema=./matrix.schema.json"
    )


def test_default_template_validates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(cli, ["init"])
    data = yaml.safe_load((tmp_path / "matrix.yaml").read_text())
    Draft202012Validator(ConfigFile.json_schema()).validate(data)
    assert ConfigFile.model_validate(data).matrix[0].mp3_files


def test_schema_forbids_extras_and_describes_every_property():
    schema = ConfigFile.json_schema()
    matrix = schema["$defs"]["MatrixConfig"]
    assert all(d["additionalProperties"] is False for d in schema["$defs"].values())
    assert all("description" in p for p in matrix["properties"].values())


def test_unknown_key_rejected():
    with pytest.raises(ValueError):
        ConfigFile.model_validate(
            {
                "matrix": [
                    {
                        "source_path": "a",
                        "destination_path": "b",
                        "mp3_files": [{"artst": "x"}],
                    }
                ]
            }
        )


def test_init_no_json_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(cli, ["init", "--no-json-schema"]).exit_code == 0
    assert not (tmp_path / "matrix.schema.json").exists()
    text = (tmp_path / "matrix.yaml").read_text()
    assert "yaml-language-server" not in text
    ConfigFile.model_validate(yaml.safe_load(text))


def test_init_force_overwrites(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "matrix.yaml").write_text("matrix: []\n")
    runner = CliRunner()
    assert runner.invoke(cli, ["init"]).exit_code == 1
    assert (tmp_path / "matrix.yaml").read_text() == "matrix: []\n"
    assert runner.invoke(cli, ["init", "--force"]).exit_code == 0
    assert "source_path" in (tmp_path / "matrix.yaml").read_text()
    assert (tmp_path / "matrix.schema.json").exists()


@pytest.mark.parametrize("json_schema", [True, False])
def test_default_config_yaml_validates_against_schema(json_schema):
    data = yaml.safe_load(ConfigFile.default_config_yaml(json_schema=json_schema))
    Draft202012Validator(ConfigFile.json_schema()).validate(data)
    ConfigFile.model_validate(data)


def write_cache_config(tmp_path):
    source = tmp_path / "library"
    make_mp3(source / "song.mp3", artist="Alpha")
    return write_config(tmp_path, [source], mp3_files=[{"artist": "Alpha"}])


def test_cache_block_accepted_and_in_schema():
    schema = ConfigFile.json_schema()
    assert "ttl" in schema["$defs"]["CacheConfig"]["properties"]
    assert "cache" in schema["properties"]
    config = ConfigFile.model_validate(
        {"matrix": [], "cache": {"ttl": "2d"}},
    )
    assert config.cache.ttl == timedelta(days=2)
    assert ConfigFile.model_validate({"matrix": []}).cache is None


@pytest.mark.parametrize("ttl", ["0h", "1.5d", "1h30m", "2y", "1M", "abc", ""])
def test_invalid_ttl_rejected(ttl):
    with pytest.raises(ValueError, match="Invalid cache ttl"):
        ConfigFile.model_validate({"matrix": [], "cache": {"ttl": ttl}})


def test_ttl_parsed_into_timedelta():
    config = ConfigFile.model_validate({"matrix": [], "cache": {"ttl": "1mo"}})
    assert config.cache.ttl == timedelta(days=30)


@pytest.mark.parametrize("ttl", [30, 1.5, None, ["1d"]])
def test_non_string_ttl_rejected(ttl):
    with pytest.raises(ValueError, match="must be a string"):
        ConfigFile.model_validate({"matrix": [], "cache": {"ttl": ttl}})


def test_invalid_ttl_rejected_by_json_schema():
    validator = Draft202012Validator(ConfigFile.json_schema())
    assert not validator.is_valid({"matrix": [], "cache": {"ttl": "1h30m"}})
    assert validator.is_valid({"matrix": [], "cache": {"ttl": "1mo"}})


def test_default_config_documents_per_file_cache():
    text = ConfigFile.default_config_yaml()
    assert "belongs to this config file" in text
    assert "mixtape cache clean" in text


def test_run_writes_cache_only_when_configured(tmp_path):
    config = write_cache_config(tmp_path)
    result = CliRunner().invoke(cli, ["run", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert len(cache_files(tmp_path)) == 1


def test_run_without_cache_block_writes_nothing(tmp_path):
    config = write_cache_config(tmp_path)
    data = yaml.safe_load(config.read_text())
    del data["cache"]
    config.write_text(yaml.safe_dump(data))
    assert CliRunner().invoke(cli, ["run", "--config", str(config)]).exit_code == 0
    assert not cache_files(tmp_path)


def test_run_no_cache_flag_bypasses_cache(tmp_path):
    config = write_cache_config(tmp_path)
    args = ["run", "--config", str(config), "--no-cache"]
    assert CliRunner().invoke(cli, args).exit_code == 0
    assert not cache_files(tmp_path)


def test_cache_clean_command(tmp_path):
    config = write_cache_config(tmp_path)
    runner = CliRunner()
    runner.invoke(cli, ["run", "--config", str(config)])
    result = runner.invoke(cli, ["cache", "clean"])
    assert result.exit_code == 0
    assert "Removed 0 cache file(s)" in result.output
    assert len(cache_files(tmp_path)) == 1
    result = runner.invoke(cli, ["cache", "clean", "--all"])
    assert result.exit_code == 0
    assert "Removed 1 cache file(s)" in result.output
    assert not cache_files(tmp_path)


def test_cache_clean_with_no_cache_directory(tmp_path):
    result = CliRunner().invoke(cli, ["cache", "clean", "--all"])
    assert result.exit_code == 0
    assert "Removed 0 cache file(s)" in result.output


def prune_config(tmp_path):
    """write_cache_config plus stale files in the destination."""
    config = write_cache_config(tmp_path)
    out = tmp_path / "out0"
    (out / "old").mkdir()
    (out / "old" / "gone.mp3").touch()
    (out / "notes.txt").touch()
    return config, out


def test_run_without_prune_keeps_extra_files(tmp_path):
    config, out = prune_config(tmp_path)
    assert CliRunner().invoke(cli, ["run", "--config", str(config)]).exit_code == 0
    assert (out / "song.mp3").exists()
    assert (out / "notes.txt").exists()
    assert (out / "old" / "gone.mp3").exists()


def test_run_prune_deletes_unmatched_files_and_empty_dirs(tmp_path):
    config, out = prune_config(tmp_path)
    result = CliRunner().invoke(cli, ["run", "--config", str(config), "--prune"])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in out.rglob("*")) == ["song.mp3"]
    assert "Pruned" in result.output


def test_run_prune_shared_destination_keeps_all_matrix_output(tmp_path):
    config, out = prune_config(tmp_path)
    data = yaml.safe_load(config.read_text())
    second = tmp_path / "library2"
    second.mkdir()
    make_mp3(second / "other.mp3", artist="Beta")
    data["matrix"].append(
        {
            "source_path": str(second),
            "destination_path": str(out),
            "mp3_files": [{"artist": "Beta"}],
        }
    )
    config.write_text(yaml.safe_dump(data))
    result = CliRunner().invoke(cli, ["run", "--config", str(config), "--prune"])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in out.iterdir()) == ["other.mp3", "song.mp3"]


def test_run_prune_refuses_destination_overlapping_source(tmp_path):
    config, _ = prune_config(tmp_path)
    data = yaml.safe_load(config.read_text())
    data["matrix"][0]["destination_path"] = data["matrix"][0]["source_path"]
    config.write_text(yaml.safe_dump(data))
    result = CliRunner().invoke(cli, ["run", "--config", str(config), "--prune"])
    assert result.exit_code != 0
    assert "overlaps" in result.output
    assert (tmp_path / "library" / "song.mp3").exists()


def test_run_refuses_destination_inside_source_without_prune(tmp_path):
    config, _ = prune_config(tmp_path)
    data = yaml.safe_load(config.read_text())
    nested = tmp_path / "library" / "copies"
    nested.mkdir()
    data["matrix"][0]["destination_path"] = str(nested)
    config.write_text(yaml.safe_dump(data))
    result = CliRunner().invoke(cli, ["run", "--config", str(config)])
    assert result.exit_code != 0
    assert "overlaps" in result.output
    assert list(nested.iterdir()) == []


def test_legacy_exclude_path_rejected_with_migration_message():
    with pytest.raises(ValueError, match="exclude_paths") as error:
        ConfigFile.model_validate(
            {
                "matrix": [
                    {
                        "source_path": "a",
                        "exclude_path": "a/skip",
                        "destination_path": "b",
                        "mp3_files": [{"artist": "x"}],
                    }
                ]
            }
        )
    assert "- a/skip" in str(error.value)


def test_exclude_only_entry_rejected():
    with pytest.raises(ValueError, match="at least one tag"):
        Mp3Match(exclude={"album": "X"})
    with pytest.raises(ValueError, match="at least one tag"):
        Mp3Match(artist="A", exclude={"exclude": {"album": "X"}})
    with pytest.raises(ValueError, match="at least one"):
        Mp3Match(exclude={"folder": "/music/a"})
    Mp3Match(folder="/music/a", exclude={"folder": "/music/a/b"})


def test_missing_exclude_path_is_a_one_line_error(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    missing = tmp_path / "missing"
    config = write_config(tmp_path, [library], exclude_paths=[missing])
    result = CliRunner().invoke(cli, ["run", "--config", str(config)])
    assert result.exit_code != 0
    assert result.output.strip() == (
        f"Error: matrix[0].exclude_paths: {missing} does not exist"
    )


def test_missing_glob_exclude_path_is_accepted(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    config = write_config(tmp_path, [library], exclude_paths=[f"{library}/nope/**"])
    result = CliRunner().invoke(cli, ["list", "tag", "artist", "--config", str(config)])
    assert result.exit_code == 0, result.output


def test_schema_describes_exclude_options():
    schema = ConfigFile.json_schema()
    matrix = schema["$defs"]["MatrixConfig"]["properties"]
    assert "exclude_paths" in matrix and "exclude_path" not in matrix
    assert matrix["exclude_paths"]["type"] == "array"
    match = schema["$defs"]["Mp3Match"]["properties"]
    assert "description" in match["exclude"]
    assert "Mp3Match" in str(match["exclude"])


def overlap_config(*matrices):
    """A config dict from (source, destination) path pairs."""
    return {
        "matrix": [
            {
                "source_path": str(source),
                "destination_path": str(destination),
                "mp3_files": [{"artist": "x"}],
            }
            for source, destination in matrices
        ]
    }


@pytest.mark.parametrize(
    "layout",
    [
        "inside",  # destination inside source
        "contains",  # source inside destination
        "same",
        "symlink",
        "dotdot",
    ],
)
def test_overlapping_source_and_destination_rejected(tmp_path, layout):
    library = tmp_path / "library"
    library.mkdir()
    (tmp_path / "link").symlink_to(library)
    destination = {
        "inside": library / "copies",
        "contains": tmp_path,
        "same": library,
        "symlink": tmp_path / "link" / "copies",
        "dotdot": tmp_path / "elsewhere" / ".." / "library",
    }[layout]
    with pytest.raises(ValueError, match="overlaps") as error:
        ConfigFile.model_validate(overlap_config((library, destination)))
    assert str(library) in str(error.value)


def test_overlap_between_matrices_rejected(tmp_path):
    with pytest.raises(ValueError, match="overlaps"):
        ConfigFile.model_validate(
            overlap_config(
                (tmp_path / "a", tmp_path / "out"),
                (tmp_path / "b", tmp_path / "a" / "copies"),
            )
        )


def test_sibling_directories_accepted(tmp_path):
    config = ConfigFile.model_validate(
        overlap_config(
            (tmp_path / "library", tmp_path / "out"),
            (tmp_path / "library2", tmp_path / "out2"),
        )
    )
    assert len(config.matrix) == 2


def test_overlapping_config_reports_one_line_without_traceback(tmp_path):
    config = tmp_path / "matrix.yaml"
    config.write_text(
        yaml.safe_dump(overlap_config((tmp_path / "library", tmp_path / "library")))
    )
    for args in (["run"], ["list", "tag", "artist"], ["describe", "untagged"]):
        result = CliRunner().invoke(cli, [*args, "--config", str(config)])
        assert result.exit_code != 0
        assert "overlaps" in result.output
        assert isinstance(result.exception, SystemExit)
        assert len(result.output.strip().splitlines()) == 1


def path_config(tmp_path, source, destination):
    config = tmp_path / "matrix.yaml"
    config.write_text(yaml.safe_dump(overlap_config((source, destination))))
    return config


COMMANDS = [
    ["run"],
    ["list", "tag", "artist"],
    ["describe", "tag", "artist"],
    ["describe", "untagged"],
]


@pytest.fixture
def library_dirs(tmp_path):
    source, destination = tmp_path / "library", tmp_path / "out"
    source.mkdir()
    destination.mkdir()
    return source, destination


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize(
    ("field", "problem", "make_bad"),
    [
        ("source_path", "does not exist", None),
        ("destination_path", "does not exist", None),
        ("source_path", "is not a directory", "file"),
        ("destination_path", "is not a directory", "file"),
    ],
)
def test_bad_source_or_destination_is_a_one_line_error(
    tmp_path, library_dirs, command, field, problem, make_bad
):
    paths = dict(zip(("source_path", "destination_path"), library_dirs, strict=True))
    bad = tmp_path / "bad"
    if make_bad == "file":
        bad.touch()
    paths[field] = bad
    config = path_config(tmp_path, *paths.values())
    result = CliRunner().invoke(cli, [*command, "--config", str(config)])
    assert result.exit_code != 0
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.output.strip() == f"Error: matrix[0].{field}: {bad} {problem}"


def test_bad_path_is_reported_before_discovery(tmp_path, library_dirs, monkeypatch):
    from mixtapematrix.routers import mp3_router

    def fail(*args, **kwargs):
        raise AssertionError("tags were read")

    monkeypatch.setattr(mp3_router, "read_tags", fail)
    (library_dirs[0] / "song.mp3").touch()
    config = path_config(tmp_path, library_dirs[0], tmp_path / "missing")
    result = CliRunner().invoke(cli, ["run", "--config", str(config)])
    assert result.exit_code != 0
    assert "destination_path" in result.output


def test_default_config_validates_but_fails_the_path_check():
    config = ConfigFile.model_validate(yaml.safe_load(ConfigFile.default_config_yaml()))
    with pytest.raises(click.ClickException, match="source_path"):
        config.check_paths()


def test_run_prune_treats_differently_spelled_destinations_as_one(tmp_path):
    config, out = prune_config(tmp_path)
    data = yaml.safe_load(config.read_text())
    second = tmp_path / "library2"
    make_mp3(second / "other.mp3", artist="Beta")
    data["matrix"].append(
        {
            "source_path": str(second),
            "destination_path": f"{out}/",
            "mp3_files": [{"artist": "Beta"}],
        }
    )
    config.write_text(yaml.safe_dump(data))
    result = CliRunner().invoke(cli, ["run", "--config", str(config), "--prune"])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in out.iterdir()) == ["other.mp3", "song.mp3"]
