from mixtapematrix.main import MixtapeMatrix


def test_config(mkdirs):
    matrix = MixtapeMatrix("test/matrix.yaml")
    config = matrix.load_config()
    # This actually gets pretty far, because the ConfigFile model is highly validated.
    assert config
    assert config.matrix[0].source.path == "test/source"
    assert config.matrix[0].destination.path == "test/output"
