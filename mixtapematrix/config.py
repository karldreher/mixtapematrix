from typing import List, Dict, Literal
from pydantic import BaseModel, computed_field
from pathlib import Path
import click
import sys
from .routers.files import File


class MatrixConfig(BaseModel):
    source_path: str
    exclude_path: str = None
    destination_path: str

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
