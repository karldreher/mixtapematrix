from typing import List, Dict, Literal
from pydantic import BaseModel, computed_field
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
