import click
from pydantic import ValidationError

from mixtapematrix.commands.cache import cache_group
from mixtapematrix.commands.describe import describe_group
from mixtapematrix.options import filter_options, filters, library_options
from mixtapematrix.service import MixtapeMatrix

from .cache import (
    TAG_FIELDS,
)
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


@cli.group(name="list")
def list_group():
    """List information about the music library."""


@list_group.command(name="tag")
@click.argument("field", type=click.Choice(TAG_FIELDS))
@filter_options
@library_options(refresh=True)
def list_tag(field, matrix, **options):
    """List distinct values of a tag.

    FIELD is one of artist, album, genre or album_artist. Prints each distinct
    value found in every matrix source in the config, one per line, sorted
    case-insensitively. Values that differ only by case are listed once, using
    the spelling that sorts first (uppercase before lowercase). Files with no
    ID3 tag, or with no value for FIELD, are skipped. The matrix mp3_files
    filters are ignored, so the whole library is listed.

    Narrow the result with --artist, --album, --genre or --album-artist. Each
    matches case-insensitively and exactly, like mp3_files, and several filters
    must all match. Any tag may filter any other, e.g. albums by one artist.

    Tags are read from the tag cache as is, without scanning the library, so
    files added, deleted or retagged since the cache was written are not seen.
    Use --refresh to rescan: files that are missing from the cache or have
    changed are read and the cache is updated. Without a valid cache the library
    is scanned and the cache is filled. Use --no-cache to read every file and
    leave the cache alone. Progress is shown on stderr, so output can be piped.

    \b
    Examples:
      mixtape list tag artist
      mixtape list tag artist --refresh
      mixtape list tag album --artist Alpha
      mixtape list tag artist --genre funk --album-artist Alpha
      mixtape list tag genre --config other.yaml
      mixtape list tag album_artist --no-cache
    """
    for value in matrix.list_tag(field, where=filters(options)):
        click.echo(value)


cli.add_command(cache_group)
cli.add_command(describe_group)
