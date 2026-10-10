import click
from pydantic import ValidationError

from mixtapematrix.commands.cache import cache_group
from mixtapematrix.commands.describe import describe_group
from mixtapematrix.commands.list import list_group
from mixtapematrix.options import library_options
from mixtapematrix.service import MixtapeMatrix

from .config import ConfigFile
from .lock import LockError, single_instance

__all__ = ["MixtapeMatrix", "cli"]


class MixtapeGroup(click.Group):
    def invoke(self, ctx: click.Context):
        """Report an invalid config as a one-line error instead of a traceback."""
        try:
            return super().invoke(ctx)
        except ValidationError as e:
            problems = []
            for error in e.errors():
                message = error["msg"].removeprefix("Value error, ")
                where = ".".join(map(str, error["loc"]))
                problems.append(f"{where}: {message}" if where else message)
            raise click.ClickException(
                f"Invalid config: {'; '.join(problems)}"
            ) from None


@click.group(cls=MixtapeGroup, invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Copy and transform music files according to a matrix YAML config."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(1)
    # Every subcommand holds the lock until it finishes. A second instance is
    # warned about, not blocked: concurrent runs are discouraged, not forbidden.
    try:
        ctx.with_resource(single_instance())
    except LockError as e:
        click.echo(f"Warning: {e} Continuing anyway.", err=True)


@cli.command()
@library_options()
@click.option(
    "--prune",
    is_flag=True,
    help="Delete destination files that no matrix copied (off by default)",
)
def run(matrix):
    """Run the matrix described by a configuration file."""
    matrix.run()


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite an existing matrix.yaml")
@click.option(
    "--no-json-schema",
    is_flag=True,
    help="Skip writing matrix.schema.json and the schema modeline",
)
def init(no_json_schema, force):
    """Create a default matrix.yaml and matrix.schema.json in the current directory."""
    ConfigFile.create_default_config(json_schema=not no_json_schema, force=force)


cli.add_command(cache_group)
cli.add_command(describe_group)
cli.add_command(list_group)
