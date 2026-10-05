"""
The trees behind `mixtape describe`.

Songs sit under albums, and albums under artists. The tag you describe is the top
level, and the tree below it is whatever remains of artist > album > song:

    artist  -> artist > album > song
    album   -> album > song
    genre   -> genre > artist > album > song     (genre is not in the chain, so
    album_artist -> album_artist > artist > ...   the whole chain sits below it)

Names that differ only by case share one node, shown with the spelling that sorts
first, so the output does not depend on the order the filesystem lists files in.
"""

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .cache import TAG_FIELDS, Tags

# The levels songs can be nested under, outermost first.
LEVELS = ("artist", "album")
UNKNOWN = {"artist": "(unknown artist)", "album": "(unknown album)"}


def levels_below(field: str) -> tuple[str, ...]:
    """The levels between FIELD and the songs: the rest of the chain after FIELD."""
    return LEVELS[LEVELS.index(field) + 1 :] if field in LEVELS else LEVELS


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


def build_tree(rows: Iterable[tuple[str, Tags]], levels: tuple[str, ...]) -> Node:
    """A tree of `levels` (outermost first) with songs at the bottom."""
    root = Node()
    for path, tags in rows:
        node = root
        for level in levels:
            node = node.child(tags[TAG_FIELDS.index(level)] or UNKNOWN[level])
        node.songs.append(song_name(path))
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


def describe(rows: Iterable[tuple[str, Tags]], tag: str) -> Iterator[str]:
    """
    One section per distinct value of `tag`, sorted, each headed by that value with
    the rest of artist > album > song beneath it. Files with no value for `tag` are
    left out, except artist and album, which are grouped as (unknown ...).
    """
    index = TAG_FIELDS.index(tag)
    sections: dict[str, tuple[set[str], list[tuple[str, Tags]]]] = {}
    for path, tags in rows:
        heading = tags[index] or UNKNOWN.get(tag)
        if heading:
            names, members = sections.setdefault(heading.casefold(), (set(), []))
            names.add(heading)
            members.append((path, tags))
    levels = levels_below(tag)
    for key in sorted(sections):
        names, members = sections[key]
        yield min(names)
        yield from render_children(build_tree(members, levels))
