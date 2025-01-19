import taglib
import os
import sys
import json
from abc import ABC, abstractmethod
from pydantic import BaseModel, field_validator, computed_field
from typing import List, Dict, Any
import shutil


class File(BaseModel):
    path: str
    
    @computed_field
    @property
    def is_dir(self) -> bool:
        return os.path.isdir(self.path)
    @computed_field
    @property
    def is_file(self) -> bool:
        return os.path.isfile(self.path)
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, path):
        if not os.path.exists(path):
            # TODO Valid behavior, but needs nicer looking error, just a exit 1 would do.  No stacktrace needed.
            raise ValueError(f"File {path} does not exist")

        return path

class FileRouter(ABC):
    @abstractmethod
    # TODO: is file_path always a List of Files?
    def source(self, file_path: File):
        return file_path
    @classmethod
    def deeply_copy(cls, file_path: File, destination: str):
        try:
            if os.path.isdir(file_path.path):
                shutil.copytree(file_path.path, destination)
            else:
                shutil.copyfile(file_path.path, destination)
        except Exception as e:
            print(f"Error copying {file_path} to {destination}: {e}")
            sys.exit(1)
    

