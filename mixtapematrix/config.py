from typing import List, Dict, Literal
from pydantic import BaseModel, computed_field
from pathlib import Path
import click
import sys
from .routers.files import File


class MatrixConfig(BaseModel):
    """
    MatrixConfig is the configuration for a single matrix.
    It contains the source path, exclude path, destination path, and mp3 files to copy.
    The files are a list of dictionaries, each containing the artist, album, genre, and album_artist.
    """
    source_path: str
    """Source path is the directory to copy files from."""
    exclude_path: str = None
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
    def exclude(self) -> File:
        return File(path=self.exclude_path) if self.exclude_path else None

    # TODO album_artist is probably wrong, check later
    mp3_files: List[Dict[Literal["artist", "album", "genre", "album_artist"], str]]


class TransformConfig(BaseModel):
    """
    TransformConfig represents a list of shell commands to run after files are copied.
    Each command is a string that will be executed in the shell.
    This is meant for advanced users who want to run custom commands
    after the files have been copied according to the matrix configuration.
    Exercise caution.  
    """
    commands: List[str] = []

class ConfigFile(BaseModel):
    matrix: List[MatrixConfig]


def create_default_config():
    if Path("matrix.yaml").exists():
        click.echo("Configuration file already exists at matrix.yaml.")
        sys.exit(1)
    with open("matrix.yaml", "w") as f:
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
"""
        )
    click.echo("Default configuration file created at matrix.yaml")
    sys.exit(0)
