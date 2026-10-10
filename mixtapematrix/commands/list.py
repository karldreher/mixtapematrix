import click

from mixtapematrix.cache import TAG_FIELDS
from mixtapematrix.options import filter_options, filters, library_options


@click.group(name="list")
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
