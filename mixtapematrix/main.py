from .routers.mp3_router import TagRouter
from .config import ConfigFile
import yaml


class MixtapeMatrix:
    def __init__(self, config: str):
        self.config = config
        self.config_data = self.load_config()

    def load_config(self) -> ConfigFile:
        with open(self.config, "r") as f:
            return ConfigFile.model_validate(yaml.safe_load(f))

    def run(self):
        for matrix_config in self.config_data.matrix:
            router = TagRouter.source(matrix_config)
            for file in set(router):
                # TODO Debug log this thing
                # print(f"Copying {file.path} to {destination_file.path}")
                # TODO: not terribly optimized and could be invalid based on
                # attribute decisions at class level
                TagRouter.deeply_copy(
                    file, matrix_config.source, matrix_config.destination
                )


def main():
    # TODO obviously get this from the command line, but default to CWD
    matrix = MixtapeMatrix("matrix.yaml")
    matrix.run()
