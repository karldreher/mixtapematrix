import functools

import click

from mixtapematrix.cache import TAG_FIELDS, TagField
from mixtapematrix.service import MixtapeMatrix


def library_options(refresh: bool = False):
    """
    The options every command that reads the library shares, plus --refresh when
    asked. The command receives a MixtapeMatrix built from them as `matrix`.
    """

    def decorate(func):
        @functools.wraps(func)
        def command(*, config, debug, verbose, no_cache, refresh=False, **kwargs):
            prune = kwargs.pop("prune", False)
            matrix = MixtapeMatrix(
                config=config,
                debug=debug,
                verbose=verbose,
                use_cache=not no_cache,
                prune=prune,
                refresh=refresh,
            )
            return func(matrix=matrix, **kwargs)

        options = [
            click.option(
                "--config",
                default="matrix.yaml",
                type=click.Path(dir_okay=False),
                help="The YAML configuration file",
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
        if refresh:
            options.insert(
                0,
                click.option(
                    "--refresh",
                    is_flag=True,
                    help="Rescan the library and rewrite the tag cache, instead of "
                    "reading the cache as is",
                ),
            )
        for option in reversed(options):
            command = option(command)
        return command

    return decorate


def filter_options(func):
    """Adds one --<tag> filter option per tag field, e.g. --artist, --album-artist."""
    for name in reversed(TAG_FIELDS):
        flags = {f"--{name.replace('_', '-')}", f"--{name}"}
        func = click.option(
            *sorted(flags, reverse=True),
            f"filter_{name}",
            help=f"Only count files whose {name} matches (case-insensitive)",
        )(func)
    return func


def filters(options: dict) -> dict[TagField, str]:
    """The --<tag> filters that were given, keyed by tag name."""
    return {
        name: options[f"filter_{name}"]
        for name in TAG_FIELDS
        if options[f"filter_{name}"] is not None
    }
