"""
The artist > album > song tree behind `mixtape describe`.

The tree shape is fixed: artists contain albums, albums contain songs. Names that
differ only by case share one node, shown with the spelling that sorts first, so
the output does not depend on the order the filesystem lists files in.
"""

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .cache import TAG_FIELDS, Tags

# Tags that are levels of the tree. Any other tag (genre, album_artist) is not,
# so it can only group the tree into sections.
TREE_FIELDS = ("artist", "album")
UNKNOWN = {"artist": "(unknown artist)", "album": "(unknown album)"}


@dataclass
class Node:
    names: set[str] = field(default_factory=set)
    children: dict[str, "Node"] = field(default_factory=dict)
    songs: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return min(self.names)

    def child(self, name: str) -> "Node":
        node = self.children.setdefault(name.casefold(), Node())
        node.names.add(name)
        return node


def song_name(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def build_tree(rows: Iterable[tuple[str, Tags]]) -> Node:
    """An artist > album > song tree from (path, tags) rows."""
    root = Node()
    for path, tags in rows:
        artist = tags[TAG_FIELDS.index("artist")] or UNKNOWN["artist"]
        album = tags[TAG_FIELDS.index("album")] or UNKNOWN["album"]
        root.child(artist).child(album).songs.append(song_name(path))
    return root


def _children(node: Node) -> list[Node | str]:
    """Sub-nodes in case-insensitive order, then songs."""
    nodes = sorted(node.children.values(), key=lambda n: n.label.casefold())
    return [*nodes, *sorted(node.songs, key=str.casefold)]


def render_children(node: Node, prefix: str = "") -> Iterator[str]:
    """The tree below a node, drawn with box characters."""
    items = _children(node)
    for i, item in enumerate(items):
        last = i == len(items) - 1
        connector = "└── " if last else "├── "
        if isinstance(item, str):
            yield f"{prefix}{connector}{item}"
        else:
            yield f"{prefix}{connector}{item.label}"
            yield from render_children(item, prefix + ("    " if last else "│   "))


def render_roots(root: Node) -> Iterator[str]:
    """A tree whose top level (the artists) is flush left, with no connector."""
    for item in _children(root):
        assert isinstance(item, Node)  # artists only; songs sit under albums
        yield item.label
        yield from render_children(item)
