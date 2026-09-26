"""The page index (ch09): each column chunk's ColumnIndex and OffsetIndex.

Reading what they say, and skipping pages with them, arrives with ch09. The structure view needs
only to find and decode them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span
from .metadata import ColumnChunk
from .thrift import Node, Struct, read_struct


class PageIndexError(ValueError):
    pass


@dataclass
class IndexTree:
    """A decoded ColumnIndex or OffsetIndex, and where it is."""

    span: Span
    tree: Node


def _read_at(file: bytes, span: Span, what: str) -> Node:
    if span.end > len(file):
        raise PageIndexError(f"the {what} at {span} is past the end of the file")
    r = ByteReader(file[span.start : span.end], span.start)
    try:
        node = read_struct(r)
    except ValueError as e:
        raise PageIndexError(f"{what} at {span}: {e}") from e
    if not r.is_at_end():
        raise PageIndexError(f"the {what} at {span} is shorter than the footer says")
    return node


def column_index(file: bytes, chunk: ColumnChunk) -> IndexTree | None:
    if chunk.column_index is None:
        return None
    return IndexTree(chunk.column_index, _read_at(file, chunk.column_index, "ColumnIndex"))


def offset_index(file: bytes, chunk: ColumnChunk) -> IndexTree | None:
    if chunk.offset_index is None:
        return None
    tree = _read_at(file, chunk.offset_index, "OffsetIndex")
    locations = tree.value.field(1)
    for n in locations.node.value if locations and type(locations.node.value) is list else []:
        p = n.value
        if not isinstance(p, Struct):
            raise PageIndexError(f"expected a struct at {n.span}")
        for id in (1, 2, 3):
            f = p.field(id)
            if f is None or type(f.node.value) is not int:
                raise PageIndexError(f"PageLocation at {n.span} has no field {id}")
    return IndexTree(chunk.offset_index, tree)
