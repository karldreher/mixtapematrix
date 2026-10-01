import click
import pytest
import yaml

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
        matrix = MixtapeMatrix("test/invalid.yaml").config_data
    with pytest.raises(ValueError):
        with open("test/invalid.yaml") as f:
            # same as above, but more directly catching the error we expect
            matrix = ConfigFile.model_validate(yaml.safe_load(f))


def test_valid_transform(mkdirs):
    matrix = MixtapeMatrix("test/matrix.yaml")
    assert matrix.config_data.transform.commands == ['echo "Files copied successfully"']


def test_dangerous_transform():
    with pytest.raises(ValueError):
        matrix = MixtapeMatrix("test/dangerous_matrix.yaml").config_data
    with pytest.raises(ValueError):
        with open("test/dangerous_matrix.yaml") as f:
            # same as above, but more directly catching the error we expect
            matrix = ConfigFile.model_validate(yaml.safe_load(f))


def test_cli():
    assert type(cli) == click.core.Command
