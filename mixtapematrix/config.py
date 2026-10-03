import json
import sys
from pathlib import Path

import click
import yaml
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from .cache import TTL_PATTERN, parse_ttl
from .routers.files import File

CONFIG_FILENAME = "matrix.yaml"
SCHEMA_FILENAME = "matrix.schema.json"

_STRICT = ConfigDict(extra="forbid", use_attribute_docstrings=True)


class Mp3Match(BaseModel):
    """A set of ID3 tags to match. A file is copied when any listed tag matches."""

    model_config = _STRICT

    artist: str | None = None
    """Match files whose artist tag equals this value (case-insensitive)."""
    album: str | None = None
    """Match files whose album tag equals this value (case-insensitive)."""
    genre: str | None = None
    """Match files whose genre tag equals this value (case-insensitive)."""
    album_artist: str | None = None
    """Match files whose album artist tag equals this value (case-insensitive)."""


class MatrixConfig(BaseModel):
    model_config = _STRICT

    """
    MatrixConfig is the configuration for a single matrix.
    It contains the source path, exclude path, destination path, and mp3 files to copy.
    The files are a list of dictionaries, each containing the artist, album, genre, and album_artist.
    """

    source_path: str
    """Source path is the directory to copy files from."""
    exclude_path: str | None = None
    """Exclude path is the directory to exclude files from copying."""
    destination_path: str
    """Destination path is the directory to copy files to."""

    # While the input source_path, destination_.., and exclude_.. are strings,
    # the properties source, destination, and exclude are File objects
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
    def exclude(self) -> File | None:
        return File(path=self.exclude_path) if self.exclude_path else None

    mp3_files: list[Mp3Match]
    """Tag matches; a file is copied when it matches any entry."""


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
                    "exclude_path": "/path/to/exclude",
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
