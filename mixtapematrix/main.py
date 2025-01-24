from .routers.mp3_router import TagRouter
from .config import ConfigFile, create_default_config
import yaml
import click


class MixtapeMatrix:
    def __init__(self, config: str, debug: bool = False):
        self.config = config
        self.config_data = self.load_config()
        self.logger = click.echo
        self.debug = self.logger if debug else lambda x: None

    def load_config(self) -> ConfigFile:
        with open(self.config, "r") as f:
            return ConfigFile.model_validate(yaml.safe_load(f))

    def run(self):
        for matrix_config in self.config_data.matrix:
            router = TagRouter(matrix_config)
            for file in router.source:
                self.debug(f"Copying {file.path} to {matrix_config.destination.path}")
                # TODO: not terribly optimized and could be invalid based on
                # attribute decisions at class level
                TagRouter.deeply_copy(
                    file, matrix_config.source, matrix_config.destination
                )


@click.command()
@click.option("--config", default="matrix.yaml", help="The YAML configuration file")
@click.option("--create-config", help="Create a default configuration file", is_flag=True)
@click.option("--debug", default=False, help="Enable debug logging")
def cli(config, create_config, debug):
    if create_config:
        create_default_config()
    matrix = MixtapeMatrix(config=config, debug=debug)
    matrix.run()
