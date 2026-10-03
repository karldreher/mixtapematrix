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
