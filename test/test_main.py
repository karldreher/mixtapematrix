from mixtapematrix.main import MixtapeMatrix


def test_config():
    matrix = MixtapeMatrix("test/router.yaml")
    assert matrix.config == "test/router.yaml"
    assert matrix.config_data.get("sources")[0].get("source_path") == "test/source"
    assert matrix.config_data.get("sources")[0].get("destination_path") == "test/output"
