"""The page index: statistics and locations for every page, gathered in one place (ch09).

A column chunk's statistics describe all of its pages together. Page headers carry their own
statistics (:mod:`parquet_lab.pages`), but a reader has to walk the chunk to see them, which
costs the reads it was trying to avoid. The page index moves both into two structures written
after the row groups, which a reader fetches in one range per column chunk:

- a **ColumnIndex**: per page, whether it is all null, its minimum and maximum, and its null
  count, plus whether the pages' bounds are in ascending or descending order;
- an **OffsetIndex**: per page, its offset, its size, and the index of its first row.

With the OffsetIndex, a reader can fetch one page without reading the ones before it. With the
ColumnIndex it can decide which pages to fetch.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span
from .metadata import ColumnChunk, as_struct
from .parquet_thrift import enum_value_name
from .thrift import Node, Struct, read_struct


class PageIndexError(ValueError):
    pass


@dataclass
class ColumnIndex:
    null_pages: list[bool]
    min_values: list[bytes]
    max_values: list[bytes]
    boundary_order: str
    null_counts: list[int] | None
    span: Span
    tree: Node


@dataclass(frozen=True)
class PageLocation:
    offset: int
    compressed_page_size: int
    first_row_index: int

    def span(self) -> Span:
        return Span(self.offset, self.offset + self.compressed_page_size)


@dataclass
class OffsetIndex:
    pages: list[PageLocation]
    """Data pages only: a dictionary page, if any, comes before the first of them."""
    span: Span
    tree: Node

    def row_ranges(self, num_rows: int) -> list[tuple[int, int]]:
        """The rows each page holds, as ``[first, end)``, given the row group's row count."""
        return [
            (p.first_row_index, self.pages[i + 1].first_row_index if i + 1 < len(self.pages) else num_rows)
            for i, p in enumerate(self.pages)
        ]


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


def _list(s: Struct, id: int) -> list[Node]:
    f = s.field(id)
    return f.node.value if f and type(f.node.value) is list else []


def column_index(file: bytes, chunk: ColumnChunk) -> ColumnIndex | None:
    """Read a column chunk's ColumnIndex, if it has one."""
    span = chunk.column_index
    if span is None:
        return None
    tree = _read_at(file, span, "ColumnIndex")
    s = as_struct(tree)
    order = s.field(4)
    boundary = "UNKNOWN"
    if order and type(order.node.value) is int:
        boundary = enum_value_name("BoundaryOrder", order.node.value) or "UNKNOWN"
    return ColumnIndex(
        null_pages=[n.value is True for n in _list(s, 1)],
        min_values=[n.value if isinstance(n.value, bytes) else b"" for n in _list(s, 2)],
        max_values=[n.value if isinstance(n.value, bytes) else b"" for n in _list(s, 3)],
        boundary_order=boundary,
        null_counts=[n.value for n in _list(s, 5) if type(n.value) is int] if s.field(5) else None,
        span=span,
        tree=tree,
    )


def offset_index(file: bytes, chunk: ColumnChunk) -> OffsetIndex | None:
    """Read a column chunk's OffsetIndex, if it has one."""
    span = chunk.offset_index
    if span is None:
        return None
    tree = _read_at(file, span, "OffsetIndex")
    s = as_struct(tree)
    pages = []
    for n in _list(s, 1):
        p = as_struct(n)
        ints = []
        for id in (1, 2, 3):
            f = p.field(id)
            if f is None or type(f.node.value) is not int:
                raise PageIndexError(f"PageLocation at {n.span} has no field {id}")
            ints.append(f.node.value)
        pages.append(PageLocation(*ints))
    return OffsetIndex(pages, span, tree)
