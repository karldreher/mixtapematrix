"""Shared builders for the list and describe tests."""

import yaml
from eyed3.id3 import Tag


def make_mp3(path, **tags):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    if tags:
        tag = Tag()
        for key, value in tags.items():
            setattr(tag, key, value)
        tag.save(str(path))


def write_config(tmp_path, sources, cache=True):
    data = {
        "matrix": [
            {
                "source_path": str(source),
                "destination_path": str(tmp_path / f"out{i}"),
                "mp3_files": [{"artist": "nobody"}],  # list ignores matrix filters
            }
            for i, source in enumerate(sources)
        ]
    }
    for i in range(len(sources)):
        (tmp_path / f"out{i}").mkdir(exist_ok=True)
    if cache:
        data["cache"] = {"ttl": "1d"}
    config = tmp_path / "matrix.yaml"
    config.write_text(yaml.safe_dump(data))
    return config
