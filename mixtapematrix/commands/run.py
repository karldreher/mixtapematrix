import click

from mixtapematrix.config import ConfigFile
from mixtapematrix.lock import locked
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
    help="Skip writing matrix.schema.json",
)
@click.option(
    "--schema-only",
    is_flag=True,
    help="Write only matrix.schema.json, leaving matrix.yaml untouched",
)
@locked
def init(no_json_schema, force, schema_only):
    """Create a default matrix.yaml and matrix.schema.json in the current directory."""
    if schema_only and (no_json_schema or force):
        raise click.UsageError(
            "--schema-only cannot be combined with --no-json-schema or --force."
        )
    ConfigFile.create_default_config(
        json_schema=not no_json_schema, force=force, schema_only=schema_only
    )
