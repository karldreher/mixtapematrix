from mixtapematrix.main import MixtapeMatrix, cli
from mixtapematrix.config import ConfigFile
import click
import pytest
import yaml


def test_config(mkdirs):
    matrix = MixtapeMatrix("test/matrix.yaml")
    config = matrix.load_config()
    # This actually gets pretty far, because the ConfigFile model is highly validated.
    assert config
    assert config.matrix[0].source.path == "test/source"
    assert config.matrix[0].destination.path == "test/output"


def test_invalid_config():
    with pytest.raises(ValueError):
        matrix = MixtapeMatrix("test/invalid.yaml")
    with pytest.raises(ValueError):
        with open("test/invalid.yaml", "r") as f:
            # same as above, but more directly catching the error we expect
            matrix = ConfigFile.model_validate(yaml.safe_load(f))


def test_cli():
    assert type(cli) == click.core.Command
