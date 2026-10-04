import subprocess
from functools import cached_property

import click
import yaml

from .cache import TagCache, clean_cache, parse_ttl
from .config import ConfigFile, MatrixConfig
from .lock import LockError, single_instance
from .progress import TerminalProgress, no_progress
from .routers.files import destination_path, paths_overlap, prune_destination
from .routers.mp3_router import TagRouter, configure_tag_logging


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
        with open(self.config) as f:
            return ConfigFile.model_validate(yaml.safe_load(f))

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
