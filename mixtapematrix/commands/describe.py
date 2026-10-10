import click

from mixtapematrix.cache import TAG_FIELDS
from mixtapematrix.options import filter_options, filters, library_options


@click.group(name="describe")
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
