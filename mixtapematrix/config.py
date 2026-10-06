import json
import os
import sys
from pathlib import Path
from typing import Any

import click
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from .cache import TTL_PATTERN, parse_ttl
from .routers.files import GLOB_TAIL, File, is_glob

CONFIG_FILENAME = "matrix.yaml"
SCHEMA_FILENAME = "matrix.schema.json"

_STRICT = ConfigDict(extra="forbid", use_attribute_docstrings=True)


class Mp3Match(BaseModel):
    """
    A set of ID3 tags and a folder to match. A file is copied when any listed key
    matches, unless its exclude block matches.
    """

    model_config = _STRICT

    artist: str | None = None
    """Match files whose artist tag equals this value (case-insensitive)."""
    album: str | None = None
    """Match files whose album tag equals this value (case-insensitive)."""
    genre: str | None = None
    """Match files whose genre tag equals this value (case-insensitive)."""
    album_artist: str | None = None
    """Match files whose album artist tag equals this value (case-insensitive)."""
    folder: str | None = None
    """Match files beneath this absolute directory, which must be inside source_path.
    Matched on whole path components, so /music/rock does not match /music/rockabilly.
    Only tagged MP3s are copied, as with tags."""
    exclude: "Mp3Match | None" = None
    """Files this entry would match are skipped when any key listed here matches
    (tags case-insensitive). Takes the same keys as an entry, including a nested exclude."""

    @field_validator("folder")
    @classmethod
    def validate_folder(cls, folder: str | None) -> str | None:
        if folder is None:
            return None
        if not os.path.isabs(folder):
            raise ValueError(
                f"Folder '{folder}' must be an absolute path inside source_path."
            )
        return os.path.normpath(folder)

    @model_validator(mode="after")
    def validate_exclude_has_key(self) -> "Mp3Match":
        has_key = any(
            (self.artist, self.album, self.genre, self.album_artist, self.folder)
        )
        if self.exclude is not None and not has_key:
            raise ValueError(
                "An entry with an exclude block must also list at least one tag "
                "(artist, album, genre, or album_artist) or a folder to match; "
                "'everything except X' is not supported."
            )
        return self

    def folders(self) -> list[str]:
        """Every folder this entry names, including those in nested excludes."""
        own = [self.folder] if self.folder else []
        return own + (self.exclude.folders() if self.exclude else [])


class MatrixConfig(BaseModel):
    model_config = _STRICT

    """
    MatrixConfig is the configuration for a single matrix.
    It contains the source path, exclude paths, destination path, and mp3 files to copy.
    The files are a list of dictionaries, each containing the artist, album, genre, and album_artist.
    """

    source_path: str
    """Source path is the directory to copy files from."""
    exclude_paths: list[str] = []
    """Directories or files to leave out, with everything beneath them.
    A plain entry is a literal path matched on whole path components. An entry may end
    in ** to match by prefix: /music/rock** skips everything whose path starts with
    /music/rock, and /music/rock/** skips everything beneath /music/rock.
    No other wildcards are supported."""

    @field_validator("exclude_paths")
    @classmethod
    def validate_exclude_paths(cls, paths: list[str]) -> list[str]:
        for path in paths:
            body = path[: -len(GLOB_TAIL)] if is_glob(path) else path
            if any(char in body for char in "*?["):
                raise ValueError(
                    f"Exclude path '{path}' is not supported: wildcards are only "
                    "allowed as a trailing '**', e.g. /music/rock** or /music/rock/**."
                )
        return paths

    destination_path: str
    """Destination path is the directory to copy files to."""

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_exclude_path(cls, data: Any) -> Any:
        if isinstance(data, dict) and "exclude_path" in data:
            raise ValueError(
                "'exclude_path' was replaced by 'exclude_paths', a list. "
                f"Use:\n  exclude_paths:\n    - {data['exclude_path']}"
            )
        return data

    # While the input source_path, destination_.., and exclude_.. are strings,
    # the properties source, destination, and excluded_files are File objects
    @computed_field
    @property
    def source(self) -> File:
        return File(path=self.source_path)

    @computed_field
    @property
    def destination(self) -> File:
        return File(path=self.destination_path)

    @computed_field
    @property
    def excluded_files(self) -> list[File]:
        # Glob entries need not exist; only literal paths are checked.
        return [File(path=p) for p in self.exclude_paths if not is_glob(p)]

    mp3_files: list[Mp3Match]
    """Tag and folder matches; a file is copied when it matches any entry."""


class TransformConfig(BaseModel):
    model_config = _STRICT

    """
    TransformConfig represents a list of shell commands to run after files are copied.
    Each command is a string that will be executed in the shell.
    This is meant for advanced users who want to run custom commands
    after the files have been copied according to the matrix configuration.
    Exercise caution.
    """

    commands: list[str] = []

    @field_validator("commands")
    def validate_commands(cls, commands: list[str]):
        # Dangerous commands that should not be allowed.
        # update this list over time with anything that should not be allowed.
        DANGEROUS_COMMANDS = ["rm "]
        for command in commands:
            if any(dangerous in command for dangerous in DANGEROUS_COMMANDS):
                raise ValueError(
                    f"Command '{command}' is considered dangerous and is not allowed."
                )
        return commands


class CacheConfig(BaseModel):
    """
    CacheConfig enables the tag cache for every matrix in this config file.
    The cache belongs to this file: it is keyed by this file's path and each
    source_path, so moving or renaming the file starts a new cache.
    """

    model_config = _STRICT

    ttl: str = Field(
        json_schema_extra={"pattern": TTL_PATTERN, "examples": ["30m", "2d", "1w"]}
    )
    """How long the cache stays valid: a whole number plus m, h, d, w, or mo (30 days).
    The first run after it expires deletes the cache and rescans the library."""

    @field_validator("ttl")
    @classmethod
    def validate_ttl(cls, ttl: str) -> str:
        parse_ttl(ttl)
        return ttl


class ConfigFile(BaseModel):
    model_config = _STRICT

    matrix: list[MatrixConfig]
    """
    Matrix is a list of MatrixConfig objects, each representing a matrix configuration.
    This is the main configuration for the mixtape matrix."""
    transform: TransformConfig | None = None
    """
    Transform is an optional TransformConfig object that contains shell commands to run after copying files.
    This is useful for advanced users who want to run custom commands after the files have been copied.
    Exercise caution when using this feature, as it can run arbitrary shell commands.  
    Anything you can do in a shell, you can do here.
    Try not to rm -rf yourself.
    """
    cache: CacheConfig | None = None
    """
    Cache is an optional CacheConfig that stores discovered MP3 tags between runs,
    so repeat runs skip re-reading every file. Without it, no cache is read or written.
    """

    @staticmethod
    def json_schema() -> dict:
        """JSON Schema for editing a config file (validation mode, no computed fields)."""
        return ConfigFile.model_json_schema(mode="validation")

    @staticmethod
    def default_config_yaml(json_schema: bool = True) -> str:
        """The default config, built from plain data so it validates against the models."""
        default = {
            "matrix": [
                {
                    "source_path": "/path/to/source",
                    "exclude_paths": ["/path/to/exclude"],
                    "destination_path": "/path/to/destination",
                    "mp3_files": [
                        {"artist": "Artist Name"},
                        {"album": "Album Name"},
                        {"genre": "Genre Name"},
                        {"album_artist": "Album Artist Name"},
                    ],
                }
            ]
        }
        body = yaml.safe_dump(default, sort_keys=False)
        modeline = (
            f"# yaml-language-server: $schema=./{SCHEMA_FILENAME}\n"
            if json_schema
            else ""
        )
        return (
            f"{modeline}"
            "# Each mp3_files entry is optional; keep the tags you want to match.\n"
            "# A folder (absolute, inside source_path) matches every tagged MP3 beneath it.\n"
            "# exclude_paths removes locations; an entry's exclude: removes tags or a folder, e.g.\n"
            "#   - artist: Artist Name\n"
            "#     exclude:\n"
            "#       album: Album Name\n"
            "#   - folder: /path/to/source/Mixes\n"
            "#     exclude:\n"
            "#       genre: Podcast\n"
            f"{body}"
            "# Optional: shell commands to run after copying files.\n"
            "# transform:\n"
            "#   commands:\n"
            "#     - ls -la\n"
            "# Optional: cache discovered MP3 tags so repeat runs are faster.\n"
            "# The cache belongs to this config file: it is keyed by this file's path\n"
            "# and each source_path, so moving or renaming this file starts a new cache.\n"
            "# Run `mixtape cache clean` to remove stale caches.\n"
            "# ttl is a whole number plus m, h, d, w, or mo (30 days).\n"
            "# cache:\n"
            "#   ttl: 2d\n"
        )

    @staticmethod
    def create_default_config(json_schema: bool = True, force: bool = False):
        config_path, schema_path = Path(CONFIG_FILENAME), Path(SCHEMA_FILENAME)
        if config_path.exists() and not force:
            click.echo(
                f"Configuration file already exists at {CONFIG_FILENAME}. "
                "Use --force to overwrite it."
            )
            sys.exit(1)
        config_path.write_text(ConfigFile.default_config_yaml(json_schema))
        click.echo(f"Default configuration file created at {CONFIG_FILENAME}")
        if json_schema:
            # The schema is derived from the models, so it is always refreshed.
            schema_path.write_text(
                json.dumps(ConfigFile.json_schema(), indent=2) + "\n"
            )
            click.echo(f"JSON Schema written to {SCHEMA_FILENAME}")
        sys.exit(0)
