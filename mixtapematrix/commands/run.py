import click

from mixtapematrix.config import ConfigFile
from mixtapematrix.options import library_options


@click.command()
@library_options()
@click.option(
    "--prune",
    is_flag=True,
    help="Delete destination files that no matrix copied (off by default)",
)
def run(matrix):
    """Run the matrix described by a configuration file."""
    matrix.run()


@click.command()
@click.option("--force", is_flag=True, help="Overwrite an existing matrix.yaml")
@click.option(
    "--no-json-schema",
    is_flag=True,
    help="Skip writing matrix.schema.json and the schema modeline",
)
def init(no_json_schema, force):
    """Create a default matrix.yaml and matrix.schema.json in the current directory."""
    ConfigFile.create_default_config(json_schema=not no_json_schema, force=force)
