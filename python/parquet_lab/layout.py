"""Row layout and column layout: the same table, stored two ways (ch01).

Not Parquet yet. This is the question Parquet answers, asked with the smallest possible
encoding: integers are eight bytes, little-endian; a date is a four-byte day number; a string is
a four-byte length and then its bytes. The two layouts use identical encodings and differ only
in order::

    row layout:     id₁ cust₁ country₁ amount₁ date₁ | id₂ cust₂ country₂ …
    column layout:  id₁ id₂ id₃ … | cust₁ cust₂ … | country₁ country₂ … | …

Every value's position is recorded, so a query can be turned into the exact byte ranges it
needs, and the ranges into requests.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum

from .bytes import Span
from .logical import date_from_days


class ColumnType(Enum):
    INT64 = "int64"
    """Eight bytes, little-endian."""
    DATE = "date"
    """Four bytes, little-endian: days since 1970-01-01."""
    TEXT = "text"
    """A four-byte little-endian length, then UTF-8 bytes."""


def encode_cell(value: int | str, kind: ColumnType) -> bytes:
    if kind is ColumnType.INT64:
        return struct.pack("<q", value)
    if kind is ColumnType.DATE:
        return struct.pack("<i", value)
    text = value.encode("utf-8")
    return struct.pack("<I", len(text)) + text


def show_cell(value: int | str, kind: ColumnType) -> str:
    """For display: a date as ``YYYY-MM-DD``, everything else as itself."""
    return date_from_days(value) if kind is ColumnType.DATE else str(value)


@dataclass
class Table:
    columns: list[tuple[str, ColumnType]]
    rows: list[list[int | str]]

    @staticmethod
    def sales() -> Table:
        """Eight orders. Small enough to see every byte, large enough that the layouts differ."""
        # Day numbers for 2026-01-03 onwards: 20456 is 2026-01-03.
        return Table(
            columns=[
                ("order_id", ColumnType.INT64),
                ("customer_id", ColumnType.INT64),
                ("country", ColumnType.TEXT),
                ("amount_cents", ColumnType.INT64),
                ("order_date", ColumnType.DATE),
            ],
            rows=[
                [1, 501, "UK", 1999, 20456],
                [2, 502, "SE", 500, 20456],
                [3, 501, "UK", 4210, 20457],
                [4, 503, "PL", 1250, 20457],
                [5, 504, "US", 875, 20458],
                [6, 502, "SE", 3000, 20458],
                [7, 505, "UK", 640, 20459],
                [8, 501, "UK", 2275, 20459],
            ],
        )


class Layout(Enum):
    ROWS = "rows"
    COLUMNS = "columns"


@dataclass
class Encoded:
    """A table encoded in one layout, with the position of every value."""

    layout: Layout
    data: bytes
    cells: list[list[Span]]
    """``cells[row][column]`` is the span that value occupies."""


def encode(table: Table, layout: Layout) -> Encoded:
    nrows, ncols = len(table.rows), len(table.columns)
    data = bytearray()
    cells = [[Span(0, 0)] * ncols for _ in range(nrows)]

    def put(r: int, c: int) -> None:
        start = len(data)
        data.extend(encode_cell(table.rows[r][c], table.columns[c][1]))
        cells[r][c] = Span(start, len(data))

    if layout is Layout.ROWS:
        for r in range(nrows):
            for c in range(ncols):
                put(r, c)
    else:
        for c in range(ncols):
            for r in range(nrows):
                put(r, c)
    return Encoded(layout, bytes(data), cells)


@dataclass
class Query:
    """What a query needs: some columns of some rows."""

    columns: list[int]
    rows: list[int]


def ranges(enc: Encoded, q: Query) -> list[Span]:
    """The byte ranges a query needs, with touching ranges merged: each is one read.

    Merging only ranges that touch is the most generous thing a reader can do without reading
    bytes it does not need. Chapter 10 lets it read small gaps too, and counts the cost.
    """
    spans = sorted(enc.cells[r][c] for r in q.rows for c in q.columns)
    merged: list[Span] = []
    for s in spans:
        if merged and merged[-1].end == s.start:
            merged[-1] = Span(merged[-1].start, s.end)
        else:
            merged.append(s)
    return merged
