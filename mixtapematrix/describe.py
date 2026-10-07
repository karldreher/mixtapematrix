"""
The trees behind `mixtape describe`.

Songs sit under albums, and albums under artists. The tag you describe is the top
level, and the tree below it is whatever remains of artist > album > song:

    artist  -> artist > album > song
    album   -> album > song
    genre   -> genre > artist > album > song     (genre is not in the chain, so
    album_artist -> album_artist > artist > ...   the whole chain sits below it)

Songs are shown as the full path of the file. Names that differ only by case share
one node, shown with the spelling that sorts first, so the output does not depend on
the order the filesystem lists files in.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .cache import TagField, Tags, tag_index

# The levels songs can be nested under, outermost first.
LEVELS: tuple[TagField, ...] = ("artist", "album")
UNKNOWN: dict[TagField, str] = {
    "artist": "(unknown artist)",
    "album": "(unknown album)",
}


def levels_below(field: TagField) -> tuple[TagField, ...]:
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


def build_tree(rows: Iterable[tuple[str, Tags]], levels: tuple[TagField, ...]) -> Node:
    """
    A tree of `levels` (outermost first) with songs at the bottom. A level with no
    value and no UNKNOWN placeholder leaves the row out.
    """
    steps = [(tag_index(level), UNKNOWN.get(level)) for level in levels]
    root = Node()
    for path, tags in rows:
        node = root
        for index, unknown in steps:
            if (name := tags[index] or unknown) is None:
                break
            node = node.child(name)
        else:
            node.songs.append(path)
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


def describe(rows: Iterable[tuple[str, Tags]], tag: TagField) -> Iterator[str]:
    """
    One section per distinct value of `tag`, sorted, each headed by that value with
    the rest of artist > album > song beneath it. Files with no value for `tag` are
    left out, except artist and album, which are grouped as (unknown ...).
    """
    root = build_tree(rows, (tag, *levels_below(tag)))
    for _, section in sorted(root.children.items()):
        yield section.label
        yield from render_children(section)
