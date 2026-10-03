import sys
from pathlib import Path

import click
from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from .routers.files import File

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

    @staticmethod
    def create_default_config():
        if Path("matrix.yaml").exists():
            click.echo("Configuration file already exists at matrix.yaml.")
            sys.exit(1)
        with open("matrix.yaml", "w") as f:
            # Right now, statically defined strings is the best way to do this.
            # Programatically we might need a different BaseModel.
            f.write(
                """matrix:
  - source_path: /path/to/source
      exclude_path: /path/to/exclude
      destination_path: /path/to/destination
      mp3_files:
      # All fields are optional.  You can pick and choose which fields to search for.
      # Delete any that are not needed.
      - artist: Artist Name
      - album: Album Name
      - genre: Genre Name
      - album_artist: Album Artist Name
# transform: 
  # Optional transform configuration to run shell commands after copying files.
  # - ls -la
    """
            )
        click.echo("Default configuration file created at matrix.yaml")
        sys.exit(0)
