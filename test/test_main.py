from mixtapematrix.main import MixtapeMatrix, cli
import click

def test_config(mkdirs):
    matrix = MixtapeMatrix("test/matrix.yaml")
    config = matrix.load_config()
    # This actually gets pretty far, because the ConfigFile model is highly validated.
    assert config
    assert config.matrix[0].source.path == "test/source"
    assert config.matrix[0].destination.path == "test/output"

def test_cli():
    assert type(cli) == click.core.Command
