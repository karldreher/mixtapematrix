import subprocess
from functools import cached_property

import click
import yaml

from .config import ConfigFile
from .routers.mp3_router import TagRouter


class MixtapeMatrix:
    def __init__(self, config: str, debug: bool = False):
        self.config = config
        self.logger = click.echo
        self.debug = self.logger if debug else lambda x: None

    @cached_property
    def config_data(self) -> ConfigFile:
        with open(self.config) as f:
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
        if self.config_data.transform:
            for command in self.config_data.transform.commands:
                self.debug(f"Running command: {command}")
                subprocess.run(command, shell=True, check=True)
                self.debug(f"Command executed: {command}")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Copy and transform music files according to a matrix YAML config."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(1)


@cli.command()
@click.option("--config", default="matrix.yaml", help="The YAML configuration file")
@click.option("--debug", help="Enable debug logging", is_flag=True)
def run(config, debug):
    """Run the matrix described by a configuration file."""
    MixtapeMatrix(config=config, debug=debug).run()


@cli.command()
def init():
    """Create a default matrix.yaml and matrix.schema.json in the current directory."""
    ConfigFile.create_default_config()
