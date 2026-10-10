import os
import subprocess
from collections.abc import Iterator
from functools import cached_property

import click
import yaml

from mixtapematrix.cache import TAG_INDEX, TagCache, TagField, Tags
from mixtapematrix.config import ConfigFile, MatrixConfig
from mixtapematrix.describe import describe
from mixtapematrix.progress import TerminalProgress, no_progress
from mixtapematrix.routers.files import copy_file, prune_destination
from mixtapematrix.routers.mp3_router import (
    TagRouter,
    _tag_matches,
    configure_tag_logging,
)


class MixtapeMatrix:
    def __init__(
        self,
        config: str,
        debug: bool = False,
        use_cache: bool = True,
        prune: bool = False,
        verbose: bool = False,
        refresh: bool = False,
    ):
        self.config = config
        self.use_cache = use_cache
        self.prune = prune
        self.verbose = verbose
        self.refresh = refresh
        self.logger = click.echo
        self.debug = self.logger if debug else lambda x: None
        # Log lines would tear an active bar, so verbose and debug runs show none.
        self.progress = no_progress if (verbose or debug) else TerminalProgress()

    @cached_property
    def config_data(self) -> ConfigFile:
        try:
            with open(self.config) as f:
                config = ConfigFile.model_validate(yaml.safe_load(f))
        except FileNotFoundError:
            raise click.ClickException(
                f"Config file not found: {self.config}. "
                "Create one with `mixtape init` or pass --config."
            ) from None
        config.check_paths()
        return config

    def _routers(self) -> Iterator[tuple[MatrixConfig, TagRouter]]:
        """A router per matrix, with the tag cache on unless this run turns it off."""
        configure_tag_logging(self.verbose)
        cache_config = self.config_data.cache
        for matrix_config in self.config_data.matrix:
            cache = None
            if self.use_cache and cache_config:
                cache = TagCache(
                    self.config,
                    matrix_config.source_path,
                    cache_config.ttl,
                    log=self.logger,
                    debug=self.debug,
                )
            yield (
                matrix_config,
                TagRouter(matrix_config, cache=cache, progress=self.progress),
            )

    def _entries(self, where: list[tuple[TagField, str]]) -> Iterator[tuple[str, Tags]]:
        """
        (path, tags) of every tagged MP3 in every matrix source, ignoring the matrix
        mp3_files filters. `where` pairs tag names with values; only files matching
        every pair (case-insensitive) are yielded.
        """
        for _, router in self._routers():
            for path, tags in router.entries(refresh=self.refresh):
                if all(_tag_matches(tags, k, v) for k, v in where):
                    yield path, tags

    def list_tag(
        self, field: TagField, where: dict[TagField, str] | None = None
    ) -> list[str]:
        """
        Distinct values of a tag across every matrix source, sorted. `where` maps
        tag names to values; only files matching every one (case-insensitive) count.
        """
        index = TAG_INDEX[field]
        spellings: dict[str, set[str]] = {}  # casefolded -> every spelling seen
        for _, tags in self._entries(list((where or {}).items())):
            if value := tags[index]:
                spellings.setdefault(value.casefold(), set()).add(value)
        # min() picks the same spelling whatever order the filesystem lists files in.
        return [min(spellings[key]) for key in sorted(spellings)]

    def describe_tag(
        self,
        field: TagField,
        value: str | None = None,
        where: dict[TagField, str] | None = None,
    ) -> list[str]:
        """
        Sections headed by each value of FIELD (or just VALUE), with the rest of
        artist > album > song beneath. See describe.py for the shape per tag.
        """
        pairs = list((where or {}).items())
        if value is not None:
            pairs.append((field, value))
        return list(describe(self._entries(pairs), field))

    def describe_untagged(self) -> list[str]:
        """Every MP3 with no readable ID3 tag across the matrix sources, sorted."""
        found: set[str] = set()
        for _, router in self._routers():
            found.update(router.untagged())
        return sorted(found, key=str.casefold)

    def run(self):
        # Destinations can be shared between matrices, so pruning waits until
        # every matrix has copied: a file is kept if any matrix put it there.
        keep: dict[str, set[str]] = {}
        for matrix_config, router in self._routers():
            # Normalized so "out" and "out/" are one destination, pruned once.
            destination = os.path.normpath(matrix_config.destination_path)
            kept = keep.setdefault(destination, set())
            # Listing first runs tag discovery (and its bar) to completion, and
            # gives the copy bar a total.
            files = list(router.source)
            source, destination = (
                matrix_config.source_path,
                matrix_config.destination_path,
            )
            label = f"Copying files from {source}"
            with self.progress(label, len(files)) as bar:
                for file in files:
                    self.debug(f"Copying {file} to {destination}")
                    kept.add(copy_file(file, source, destination))
                    bar.update(1)
        if self.prune:
            for root, kept in keep.items():
                for path in prune_destination(root, kept):
                    self.logger(f"Pruned {path}")
        if self.config_data.transform:
            for command in self.config_data.transform.commands:
                self.debug(f"Running command: {command}")
                subprocess.run(command, shell=True, check=True)
