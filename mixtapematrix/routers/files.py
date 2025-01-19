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
    # Is it actually a Class Attribute rather than a method?
    def source(file_path: File):
        return file_path
    @classmethod
    # TODO is this a class method or a static method?
    def deeply_copy(cls, source: File, destination: File):
        try:
            # TODO : broken yet, not copying because destination is a dir ( which is what we want)
            if source.is_dir:
                if not os.path.exists(destination.path):
                    os.makedirs(destination.path)
                shutil.copytree(source.path, destination.path)
            elif source.is_file:
                if not os.path.exists(destination.path):
                    os.makedirs(destination.path)
                shutil.copyfile(source.path, destination.path)
        except Exception as e:
            print(f"Error copying {source.path} to {destination.path}: {e}")
            sys.exit(1)
    

