import subprocess
from collections.abc import Iterator
from functools import cached_property

import click
import yaml

from .cache import TAG_FIELDS, TagCache, Tags, clean_cache, parse_ttl
from .config import ConfigFile, MatrixConfig
from .describe import TREE_FIELDS, Node, build_tree, render_children, render_roots
from .lock import LockError, single_instance
from .progress import TerminalProgress, no_progress
from .routers.files import destination_path, paths_overlap, prune_destination
from .routers.mp3_router import TagRouter, _tag_matches, configure_tag_logging


def _format_bytes(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


class MixtapeMatrix:
    def __init__(
        self,
        config: str,
        debug: bool = False,
        use_cache: bool = True,
        prune: bool = False,
        verbose: bool = False,
    ):
        self.config = config
        self.use_cache = use_cache
        self.prune = prune
        self.verbose = verbose
        self.logger = click.echo
        self.debug = self.logger if debug else lambda x: None
        # Log lines would tear an active bar, so verbose and debug runs show none.
        self.progress = no_progress if (verbose or debug) else TerminalProgress()

    @cached_property
    def config_data(self) -> ConfigFile:
        try:
            with open(self.config) as f:
                return ConfigFile.model_validate(yaml.safe_load(f))
        except FileNotFoundError:
            raise click.ClickException(
                f"Config file not found: {self.config}. "
                "Create one with `mixtape init` or pass --config."
            ) from None

    def tag_cache(self, matrix_config: MatrixConfig) -> TagCache | None:
        """The tag cache for a matrix, or None when caching is off for this run."""
        cache_config = self.config_data.cache
        if not (self.use_cache and cache_config):
            return None
        return TagCache(
            self.config,
            matrix_config.source.path,
            parse_ttl(cache_config.ttl),
            log=self.logger,
            debug=self.debug,
        )

    def _check_destinations_safe(self):
        """Sources are read-only: no destination may be, or sit inside, any source."""
        for matrix_config in self.config_data.matrix:
            destination = matrix_config.destination.path
            for other in self.config_data.matrix:
                if paths_overlap(destination, other.source.path):
                    raise click.ClickException(
                        f"Refusing to run: destination {destination} overlaps "
                        f"source {other.source.path}."
                    )

    def _entries(self, where: list[tuple[str, str]]) -> Iterator[tuple[str, Tags]]:
        """
        (path, tags) of every tagged MP3 in every matrix source, ignoring the matrix
        mp3_files filters. `where` pairs tag names with values; only files matching
        every pair (case-insensitive) are yielded.
        """
        configure_tag_logging(self.verbose)
        for matrix_config in self.config_data.matrix:
            router = TagRouter(
                matrix_config,
                cache=self.tag_cache(matrix_config),
                progress=self.progress,
            )
            for path, tags in router.entries():
                if all(_tag_matches(tags, k, v) for k, v in where):
                    yield path, tags

    def list_tag(self, field: str, where: dict[str, str] | None = None) -> list[str]:
        """
        Distinct values of a tag across every matrix source, sorted. `where` maps
        tag names to values; only files matching every one (case-insensitive) count.
        """
        index = TAG_FIELDS.index(field)
        spellings: dict[str, set[str]] = {}  # casefolded -> every spelling seen
        for _, tags in self._entries(list((where or {}).items())):
            if value := tags[index]:
                spellings.setdefault(value.casefold(), set()).add(value)
        # min() picks the same spelling whatever order the filesystem lists files in.
        return [min(spellings[key]) for key in sorted(spellings)]

    def describe_tag(
        self,
        field: str,
        value: str | None = None,
        where: dict[str, str] | None = None,
    ) -> list[str]:
        """
        An artist > album > song tree, always in that shape. FIELD either narrows it
        or groups it:
          - artist or album are levels of the tree, so FIELD=VALUE keeps only the
            matching branches (no VALUE keeps everything).
          - any other tag (genre, album_artist) is not a level, so the tree is split
            into one section per value of FIELD, headed by that value; VALUE keeps
            one section.
        """
        pairs = list((where or {}).items())
        if value is not None:
            pairs.append((field, value))
        rows = list(self._entries(pairs))
        if field in TREE_FIELDS:
            return list(render_roots(build_tree(rows)))

        index = TAG_FIELDS.index(field)
        sections: dict[str, tuple[set[str], list[tuple[str, Tags]]]] = {}
        for path, tags in rows:
            if heading := tags[index]:
                names, members = sections.setdefault(heading.casefold(), (set(), []))
                names.add(heading)
                members.append((path, tags))
        lines: list[str] = []
        for key in sorted(sections):
            names, members = sections[key]
            lines.append(min(names))
            section: Node = build_tree(members)
            lines.extend(render_children(section))
        return lines

    def run(self):
        configure_tag_logging(self.verbose)
        self._check_destinations_safe()
        # Destinations can be shared between matrices, so pruning waits until
        # every matrix has copied: a file is kept if any matrix put it there.
        keep: dict[str, set[str]] = {}
        for matrix_config in self.config_data.matrix:
            router = TagRouter(
                matrix_config,
                cache=self.tag_cache(matrix_config),
                progress=self.progress,
            )
            kept = keep.setdefault(matrix_config.destination.path, set())
            # Listing first runs tag discovery (and its bar) to completion, and
            # gives the copy bar a total.
            files = list(router.source)
            label = f"Copying files from {matrix_config.source.path}"
            with self.progress(label, len(files)) as bar:
                for file in files:
                    self.debug(
                        f"Copying {file.path} to {matrix_config.destination.path}"
                    )
                    # TODO: not terribly optimized and could be invalid based on
                    # attribute decisions at class level
                    TagRouter.deeply_copy(
                        file, matrix_config.source, matrix_config.destination
                    )
                    kept.add(
                        destination_path(
                            file, matrix_config.source, matrix_config.destination
                        )
                    )
                    bar.update(1)
        if self.prune:
            for root, kept in keep.items():
                for path in prune_destination(root, kept):
                    self.logger(f"Pruned {path}")
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
    # Every subcommand holds the lock until it finishes. A second instance is
    # warned about, not blocked: concurrent runs are discouraged, not forbidden.
    try:
        ctx.with_resource(single_instance())
    except LockError as e:
        click.echo(f"Warning: {e} Continuing anyway.", err=True)


@cli.command()
@click.option("--config", default="matrix.yaml", help="The YAML configuration file")
@click.option("--debug", help="Enable debug logging", is_flag=True)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show ID3 tag warnings (non-standard genres, invalid dates, ...)",
)
@click.option("--no-cache", is_flag=True, help="Ignore the tag cache for this run")
@click.option(
    "--prune",
    is_flag=True,
    help="Delete destination files that no matrix copied (off by default)",
)
def run(config, debug, verbose, no_cache, prune):
    """Run the matrix described by a configuration file."""
    MixtapeMatrix(
        config=config,
        debug=debug,
        verbose=verbose,
        use_cache=not no_cache,
        prune=prune,
    ).run()


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


def _filter_options(func):
    """Adds one --<tag> filter option per tag field, e.g. --artist, --album-artist."""
    for name in reversed(TAG_FIELDS):
        flags = {f"--{name.replace('_', '-')}", f"--{name}"}
        func = click.option(
            *sorted(flags, reverse=True),
            f"filter_{name}",
            help=f"Only count files whose {name} matches (case-insensitive)",
        )(func)
    return func


def _library_options(func):
    """The options every command that reads the library shares."""
    for option in reversed(
        [
            click.option(
                "--config", default="matrix.yaml", help="The YAML configuration file"
            ),
            click.option("--debug", help="Enable debug logging", is_flag=True),
            click.option(
                "--verbose",
                is_flag=True,
                help="Show ID3 tag warnings (non-standard genres, invalid dates, ...)",
            ),
            click.option(
                "--no-cache", is_flag=True, help="Ignore the tag cache for this run"
            ),
        ]
    ):
        func = option(func)
    return func


def _filters(options: dict) -> dict[str, str]:
    """The --<tag> filters that were given, keyed by tag name."""
    return {
        name: options[f"filter_{name}"]
        for name in TAG_FIELDS
        if options[f"filter_{name}"] is not None
    }


@list_group.command(name="tag")
@click.argument("field", type=click.Choice(TAG_FIELDS))
@_filter_options
@_library_options
def list_tag(field, config, debug, verbose, no_cache, **options):
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

    Tags come from the tag cache when it is valid. Files that are missing from
    the cache or have changed are read and the cache is updated for the next
    run. Use --no-cache to read every file instead. Progress is shown on stderr,
    so output can be piped.

    \b
    Examples:
      mixtape list tag artist
      mixtape list tag album --artist Alpha
      mixtape list tag artist --genre funk --album-artist Alpha
      mixtape list tag genre --config other.yaml
      mixtape list tag album_artist --no-cache
    """
    values = MixtapeMatrix(
        config=config, debug=debug, verbose=verbose, use_cache=not no_cache
    ).list_tag(field, where=_filters(options))
    for value in values:
        click.echo(value)


@cli.group(name="describe")
def describe_group():
    """Show library contents as an artist > album > song tree."""


@describe_group.command(name="tag")
@click.argument("field", type=click.Choice(TAG_FIELDS))
@click.argument("value", required=False)
@_filter_options
@_library_options
def describe_tag(field, value, config, debug, verbose, no_cache, **options):
    """Show an artist > album > song tree, narrowed or grouped by a tag.

    The tree always has the same shape: artists, then their albums, then the
    songs (file names without .mp3). FIELD decides what that tree is limited
    to, or split by:

    \b
      artist, album  Levels of the tree. FIELD VALUE keeps only the matching
                     branches; without VALUE the whole tree is shown.
      genre,         Not levels of the tree. The tree is split into one
      album_artist   section per value of FIELD, headed by that value; VALUE
                     shows one section.

    Matching is exact and case-insensitive, like mp3_files. The --artist,
    --album, --genre and --album-artist filters work as in list tag and narrow
    which files are described. Names that differ only by case share one node,
    shown with the spelling that sorts first. Files with no ID3 tag are skipped,
    and a missing artist or album appears as (unknown artist) or (unknown
    album). The matrix mp3_files filters are ignored.

    Tags come from the tag cache as in list tag, and progress is shown on
    stderr, so output can be piped.

    \b
    Examples:
      mixtape describe tag artist              every artist/album/song
      mixtape describe tag artist Alpha        only Alpha's albums and songs
      mixtape describe tag album "First"       albums named First, with artists
      mixtape describe tag genre               one section per genre
      mixtape describe tag genre funk          only the funk section
      mixtape describe tag genre --artist Alpha
    """
    lines = MixtapeMatrix(
        config=config, debug=debug, verbose=verbose, use_cache=not no_cache
    ).describe_tag(field, value, where=_filters(options))
    for line in lines:
        click.echo(line)


@cli.group(name="cache")
def cache_group():
    """Manage the tag cache."""


@cache_group.command()
@click.option(
    "--all", "all_files", is_flag=True, help="Delete every cache file, not only stale"
)
def clean(all_files):
    """Delete stale tag caches (expired, orphaned, or unreadable)."""
    removed = clean_cache(all_files=all_files)
    for item in removed:
        click.echo(f"Removed {item.name} ({item.reason}, {_format_bytes(item.size)})")
    freed = _format_bytes(sum(item.size for item in removed))
    click.echo(f"Removed {len(removed)} cache file(s), freed {freed}")
