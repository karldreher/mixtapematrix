import json

import click
import pytest
import yaml
from click.testing import CliRunner
from jsonschema import Draft202012Validator

from mixtapematrix.config import ConfigFile
from mixtapematrix.main import MixtapeMatrix, cli


def test_config(mkdirs):
    matrix = MixtapeMatrix("test/matrix.yaml")
    # This actually gets pretty far, because the ConfigFile model is highly validated.
    assert matrix.config_data
    assert matrix.config_data.matrix[0].source.path == "test/source"
    assert matrix.config_data.matrix[0].destination.path == "test/output"


def test_invalid_config():
    with pytest.raises(ValueError):
        _ = MixtapeMatrix("test/invalid.yaml").config_data
    with pytest.raises(ValueError), open("test/invalid.yaml") as f:
        # same as above, but more directly catching the error we expect
        ConfigFile.model_validate(yaml.safe_load(f))


def test_valid_transform(mkdirs):
    matrix = MixtapeMatrix("test/matrix.yaml")
    assert matrix.config_data.transform.commands == ['echo "Files copied successfully"']


def test_dangerous_transform():
    with pytest.raises(ValueError):
        _ = MixtapeMatrix("test/dangerous_matrix.yaml").config_data
    with pytest.raises(ValueError), open("test/dangerous_matrix.yaml") as f:
        # same as above, but more directly catching the error we expect
        ConfigFile.model_validate(yaml.safe_load(f))


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
    assert result.exit_code != 0


def test_run_with_config(mkdirs):
    result = CliRunner().invoke(cli, ["run", "--config", "test/matrix.yaml"])
    assert result.exit_code == 0, result.output


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


def test_schema_excludes_computed_fields_and_forbids_extras():
    schema = ConfigFile.json_schema()
    matrix = schema["$defs"]["MatrixConfig"]
    assert not {"source", "destination", "exclude"} & set(matrix["properties"])
    assert all(d["additionalProperties"] is False for d in schema["$defs"].values())
    assert "File" not in schema["$defs"]
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


def write_cache_config(tmp_path, ttl="1d"):
    from eyed3.id3 import Tag

    source = tmp_path / "library"
    source.mkdir()
    (tmp_path / "out").mkdir()
    song = source / "song.mp3"
    song.touch()
    tag = Tag()
    tag.artist = "Alpha"
    tag.save(str(song))
    config = tmp_path / "matrix.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "matrix": [
                    {
                        "source_path": str(source),
                        "destination_path": str(tmp_path / "out"),
                        "mp3_files": [{"artist": "Alpha"}],
                    }
                ],
                "cache": {"ttl": ttl},
            }
        )
    )
    return config


def cache_files(tmp_path):
    directory = tmp_path / "xdg-cache" / "mixtapematrix"
    return sorted(directory.glob("*.mmcache")) if directory.exists() else []


def test_cache_block_accepted_and_in_schema():
    schema = ConfigFile.json_schema()
    assert "ttl" in schema["$defs"]["CacheConfig"]["properties"]
    assert "cache" in schema["properties"]
    config = ConfigFile.model_validate(
        {"matrix": [], "cache": {"ttl": "2d"}},
    )
    assert config.cache.ttl == "2d"
    assert ConfigFile.model_validate({"matrix": []}).cache is None


@pytest.mark.parametrize("ttl", ["0h", "1.5d", "1h30m", "2y", "1M", "abc", ""])
def test_invalid_ttl_rejected(ttl):
    with pytest.raises(ValueError, match="Invalid cache ttl"):
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
    assert cache_files(tmp_path) == []


def test_run_no_cache_flag_bypasses_cache(tmp_path):
    config = write_cache_config(tmp_path)
    args = ["run", "--config", str(config), "--no-cache"]
    assert CliRunner().invoke(cli, args).exit_code == 0
    assert cache_files(tmp_path) == []


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
    assert cache_files(tmp_path) == []


def test_cache_clean_with_no_cache_directory(tmp_path):
    result = CliRunner().invoke(cli, ["cache", "clean", "--all"])
    assert result.exit_code == 0
    assert "Removed 0 cache file(s)" in result.output


def prune_config(tmp_path, destinations=None):
    """write_cache_config plus stale files in the destination."""
    config = write_cache_config(tmp_path)
    out = tmp_path / "out"
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
    from eyed3.id3 import Tag

    (second / "other.mp3").touch()
    tag = Tag()
    tag.artist = "Beta"
    tag.save(str(second / "other.mp3"))
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
