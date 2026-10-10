import click
from pydantic import ValidationError

from mixtapematrix.commands.cache import cache_group
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


@cli.group(name="describe")
def describe_group():
    """Show library contents as an artist > album > song tree."""


@describe_group.command(name="tag")
@click.argument("field", type=click.Choice(TAG_FIELDS))
@click.argument("value", required=False)
@filter_options
@library_options(refresh=True)
def describe_tag(field, value, matrix, **options):
    """Show a tag's values as a tree.

    The tag you choose is the top level. Below it comes whatever is left of
    artist > album > song (a song is shown as the full path of its file):

    \b
      artist         artist > album > song
      album          album > song
      genre          genre > artist > album > song
      album_artist   album_artist > artist > album > song

    There is one section per distinct value of FIELD, sorted case-insensitively.
    VALUE shows only that section. Matching is exact and case-insensitive, like
    mp3_files. The --artist, --album, --genre and --album-artist filters work as
    in list tag and narrow which files are described. Names that differ only by
    case share one node, shown with the spelling that sorts first. Files with no
    ID3 tag are skipped, as are files with no genre or album_artist when those
    are the top level. A missing artist or album appears as (unknown artist) or
    (unknown album). The matrix mp3_files filters are ignored.

    Tags are read from the tag cache as is, as in list tag, so the output can
    be stale until you pass --refresh to rescan. Progress is shown on stderr, so
    output can be piped.

    \b
    Examples:
      mixtape describe tag artist              every artist > album > song
      mixtape describe tag artist Alpha        only Alpha
      mixtape describe tag album               every album > song
      mixtape describe tag album "First"       only the album named First
      mixtape describe tag genre               every genre > artist > album > song
      mixtape describe tag genre funk          only the funk section
      mixtape describe tag genre --artist Alpha
    """
    for line in matrix.describe_tag(field, value, where=filters(options)):
        click.echo(line)


@describe_group.command(name="untagged")
@library_options()
def describe_untagged(matrix):
    """List MP3 files that have no ID3 tag.

    Prints the full path of every untagged MP3 in every matrix source in the
    config, one per line, sorted case-insensitively. Unlike the tag commands, it
    takes no tag filters, since an untagged file has no tags to filter on. The
    matrix mp3_files filters are ignored, and exclude_paths still apply.

    The tag cache is only used to skip files it already records as tagged and
    unchanged. Files the cache does not list, and files it lists as untagged, are
    read again, and the cache is never written. Use --no-cache to read every
    file. Progress is shown on stderr, so output can be piped.

    \b
    Examples:
      mixtape describe untagged
      mixtape describe untagged --config other.yaml
      mixtape describe untagged --no-cache
    """
    for path in matrix.describe_untagged():
        click.echo(path)


cli.add_command(cache_group)
