"""Skipping data: deciding, from metadata alone, what a query does not need to read (ch09).

A reader is given a condition on one column, such as ``order_id = 431`` or
``amount_cents > 9000``. Before it reads a page it asks three things, each cheaper than the
reading it may save:

1. **Row group statistics** (:mod:`parquet_lab.stats`), already in the footer: can any value in
   this column chunk's range satisfy the condition?
2. **The Bloom filter** (:mod:`parquet_lab.bloom`), for equality only: was this exact value ever
   added?
3. **The page index** (:mod:`parquet_lab.page_index`): the same question as the first, page by
   page, and then which rows those pages hold, and so which pages of the *other* columns to read.

Every answer is either "skip", which must be certain, or "read", which only means "cannot rule
it out". A wrong "skip" loses rows; a wrong "read" costs bytes. Each decision records why.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from enum import Enum

from . import bloom, page_index
from .bytes import Span
from .metadata import ColumnChunk, FileMetaData
from .schema import Leaf
from .stats import Comparator, bounds


class Op(Enum):
    EQ = "="
    NOT_EQ = "!="
    LT = "<"
    LT_EQ = "<="
    GT = ">"
    GT_EQ = ">="
    IS_NULL = "is null"
    IS_NOT_NULL = "is not null"

    @staticmethod
    def parse(s: str) -> Op:
        try:
            return Op(s)
        except ValueError:
            raise ValueError(f"unknown comparison {_debug(s)}") from None

    @property
    def symbol(self) -> str:
        return self.value

    def matches(self, ordering: int | None) -> bool:
        """Whether a value compares this way: ``ordering`` is -1, 0 or 1, or ``None`` when the
        value cannot be placed. Null matches nothing but ``is null``."""
        wanted = {
            Op.EQ: (0,),
            Op.NOT_EQ: (-1, 1),
            Op.LT: (-1,),
            Op.LT_EQ: (-1, 0),
            Op.GT: (1,),
            Op.GT_EQ: (1, 0),
        }.get(self, ())
        return ordering in wanted


def _debug(s: str) -> str:
    from .encoding import quote

    return quote(s)


@dataclass
class Predicate:
    """A condition on one column: ``column op value``."""

    column: int
    op: Op
    value: bytes | None
    """The value as PLAIN bytes, as statistics store it. ``None`` for ``is null`` and
    ``is not null``."""
    comparator: Comparator

    @staticmethod
    def new(leaf: Leaf, converted: str | None, op: Op, text: str) -> Predicate:
        """Parse a condition's value for ``leaf``: integers, floats and strings."""
        comparator = Comparator.for_leaf(leaf, converted)
        value = None if op in (Op.IS_NULL, Op.IS_NOT_NULL) else literal(comparator, text.strip())
        return Predicate(leaf.column, op, value, comparator)

    def row_matches(self, value: bytes | None) -> bool:
        """Whether one row's value satisfies the condition. ``None`` is null."""
        if self.op is Op.IS_NULL:
            return value is None
        if self.op is Op.IS_NOT_NULL:
            return value is not None
        if value is None or self.value is None:
            return False
        return self.op.matches(self.comparator.compare(value, self.value))


_INTEGER = re.compile(r"[+-]?[0-9]+")
_FLOAT = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[+-]?(?:inf|infinity|nan)", re.I)


def literal(c: Comparator, text: str) -> bytes:
    """A literal as PLAIN bytes for a column compared with ``c``."""
    bad = ValueError(f"{_debug(text)} is not a value of this column")
    ints = {Comparator.I32: ("<i", -(2**31), 2**31), Comparator.U32: ("<I", 0, 2**32),
            Comparator.I64: ("<q", -(2**63), 2**63), Comparator.U64: ("<Q", 0, 2**64)}  # fmt: skip
    if c in ints:
        f, low, high = ints[c]
        if not _INTEGER.fullmatch(text) or not low <= int(text) < high:
            raise bad
        return struct.pack(f, int(text))
    if c in (Comparator.F32, Comparator.F64):
        if not _FLOAT.fullmatch(text):
            raise bad
        v = float(text)
        if c is Comparator.F32:
            # Out of a 32-bit float's range, the value is infinite, as parsing one would make it.
            if math.isfinite(v) and abs(v) > 3.4028235677973366e38:
                v = math.copysign(math.inf, v)
            return struct.pack("<f", v)
        return struct.pack("<d", v)
    if c is Comparator.BYTES:
        return text.strip('"').encode()
    raise ValueError("this reader parses values only for integer, float and string columns")


@dataclass
class Decision:
    """A decision and the reason for it."""

    skip: bool
    why: str


def skip(why: str) -> Decision:
    return Decision(True, why)


def read(why: str) -> Decision:
    return Decision(False, why)


def against_bounds(
    p: Predicate, found: tuple[bytes, bytes] | None, null_count: int | None, num_values: int
) -> Decision:
    """Decide from a minimum and maximum (when usable), a null count, and a value count."""
    all_null = null_count == num_values and num_values > 0
    if p.op is Op.IS_NULL:
        return (
            skip("the null count is zero")
            if null_count == 0
            else read("the null count is not zero, or not recorded")
        )
    if p.op is Op.IS_NOT_NULL:
        return skip("every value is null") if all_null else read("some values are not null")
    if all_null:
        return skip("every value is null, and null satisfies no comparison")
    if p.value is None or found is None:
        return read("no usable minimum and maximum")
    low, high = found
    vs_min, vs_max = p.comparator.compare(p.value, low), p.comparator.compare(p.value, high)
    if vs_min is None or vs_max is None:
        return read("the value cannot be placed in the column's order")
    ruled_out = {
        Op.EQ: vs_min == -1 or vs_max == 1,
        Op.NOT_EQ: vs_min == 0 and vs_max == 0,
        Op.LT: vs_min != 1,  # min >= x
        Op.LT_EQ: vs_min == -1,  # min > x
        Op.GT: vs_max != -1,  # max <= x
        Op.GT_EQ: vs_max == 1,  # max < x
    }[p.op]
    if not ruled_out:
        return read("the range may hold a match")
    if p.op is Op.EQ:
        return skip("the value is below the minimum" if vs_min == -1 else "the value is above the maximum")
    if p.op is Op.NOT_EQ:
        return skip("every value equals it")
    if p.op in (Op.LT, Op.LT_EQ):
        return skip("the minimum is too large")
    return skip("the maximum is too small")


@dataclass(frozen=True)
class Mechanisms:
    """Which mechanisms a plan may use."""

    statistics: bool = True
    bloom: bool = True
    page_index: bool = True


ALL = Mechanisms()
NONE = Mechanisms(False, False, False)


@dataclass
class PagePlan:
    """One page of the condition's column, and whether its rows are kept."""

    span: Span
    rows: tuple[int, int]
    decision: Decision


@dataclass
class ColumnRead:
    """The bytes of one projected column a plan reads in one row group."""

    column: int
    spans: list[Span]
    pages_read: int
    """How many of the chunk's data pages those spans include, and how many it has."""
    pages_total: int


@dataclass
class RowGroupPlan:
    index: int
    num_rows: int
    steps: list[tuple[str, Decision]]
    """Each mechanism consulted, in order, and what it decided."""
    skipped: bool
    pages: list[PagePlan]
    rows: list[tuple[int, int]]
    """The rows still to read, as ``[start, end)`` ranges within the row group."""
    reads: list[ColumnRead]
    index_bytes: int
    """Bytes of Bloom filters and page indexes fetched to decide."""


@dataclass
class Plan:
    row_groups: list[RowGroupPlan] = field(default_factory=list)

    def bytes_read(self) -> int:
        return sum(s.length for g in self.row_groups for r in g.reads for s in r.spans)

    def index_bytes(self) -> int:
        return sum(g.index_bytes for g in self.row_groups)

    def rows_read(self) -> int:
        return sum(b - a for g in self.row_groups for a, b in g.rows)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge touching or overlapping ranges."""
    out: list[tuple[int, int]] = []
    for r in sorted(ranges):
        if out and r[0] <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], r[1]))
        else:
            out.append(r)
    return out


def _offset_index_quietly(file: bytes, chunk: ColumnChunk):
    try:
        return page_index.offset_index(file, chunk)
    except ValueError:
        return None


def column_read(
    file: bytes, chunk: ColumnChunk, column: int, rows: list[tuple[int, int]], num_rows: int, use_index: bool
) -> tuple[ColumnRead, int]:
    """The bytes of ``chunk`` needed for ``rows``: its dictionary page, if any, and the data pages
    whose rows overlap them. Without an offset index, the whole chunk."""
    whole = chunk.byte_range()
    oi = _offset_index_quietly(file, chunk) if use_index else None
    if oi is None:
        found = _offset_index_quietly(file, chunk)
        pages = len(found.pages) if found else 0
        return ColumnRead(column, [whole], pages, pages), 0
    spans = []
    # The dictionary page sits before the first data page; any page read needs it.
    first_data = oi.pages[0].offset if oi.pages else whole.end
    ranges = oi.row_ranges(num_rows)
    wanted = [i for i in range(len(oi.pages)) if any(_overlaps(ranges[i], r) for r in rows)]
    if wanted and first_data > whole.start:
        spans.append(Span(whole.start, first_data))
    spans += [oi.pages[i].span() for i in wanted]
    return ColumnRead(column, spans, len(wanted), len(oi.pages)), oi.span.length


def plan(
    file: bytes, md: FileMetaData, leaf: Leaf, p: Predicate, projection: list[int], use: Mechanisms
) -> Plan:
    """Plan a read of ``projection`` for rows satisfying ``p``."""
    orders = md.column_orders
    type_order = orders is not None and leaf.column < len(orders) and orders[leaf.column] == "TYPE_ORDER"
    out = Plan()
    for g, rg in enumerate(md.row_groups):
        chunk = rg.columns[leaf.column]
        steps: list[tuple[str, Decision]] = []
        index_bytes = 0
        skipped = False
        if use.statistics:
            if chunk.statistics is None:
                d = read("the column chunk has no statistics")
            else:
                try:
                    b = bounds(chunk.statistics, p.comparator, type_order)
                    found = (b.min, b.max)
                except ValueError:
                    found = None
                d = against_bounds(p, found, chunk.statistics.null_count, chunk.num_values)
            skipped |= d.skip
            steps.append(("statistics", d))
        if use.bloom and not skipped and p.op is Op.EQ:
            f = bloom.read(file, chunk)
            if f is not None and p.value is not None:
                index_bytes += f.bitset_span.end - f.header_span.start
                d = (
                    read("every bit the value's hash chose is set")
                    if f.probe(p.value).may_contain
                    else skip("a bit the value's hash chose is clear")
                )
                skipped |= d.skip
                steps.append(("Bloom filter", d))
        pages: list[PagePlan] = []
        rows = [] if skipped else [(0, rg.num_rows)]
        # Page rows equal page values only when the column does not repeat; for a repeated column
        # the reader would need the level histograms, and this one does not use them.
        use_pages = use.page_index and not skipped and leaf.max_repetition_level == 0
        if use_pages:
            ci = page_index.column_index(file, chunk)
            oi = page_index.offset_index(file, chunk)
            if ci is not None and oi is not None:
                index_bytes += ci.span.length
                ranges = oi.row_ranges(rg.num_rows)
                for i, loc in enumerate(oi.pages):
                    page_rows = ranges[i][1] - ranges[i][0]
                    found = None
                    if not ci.null_pages[i] and type_order:
                        low, high = ci.min_values[i], ci.max_values[i]
                        if (
                            p.comparator.compare(low, low) is not None
                            and p.comparator.compare(high, high) is not None
                        ):
                            found = (low, high)
                    nulls = (
                        page_rows
                        if ci.null_pages[i]
                        else (ci.null_counts[i] if ci.null_counts is not None else None)
                    )
                    pages.append(PagePlan(loc.span(), ranges[i], against_bounds(p, found, nulls, page_rows)))
                rows = _merge([q.rows for q in pages if not q.decision.skip])
                kept = sum(1 for q in pages if not q.decision.skip)
                steps.append(
                    (
                        "page index",
                        skip("every page's bounds rule it out")
                        if not rows
                        else read(f"{kept} of {len(pages)} pages may hold a match"),
                    )
                )
                skipped |= not rows
        reads = []
        if not skipped:
            for column in projection:
                r, oi_bytes = column_read(file, rg.columns[column], column, rows, rg.num_rows, use_pages)
                index_bytes += oi_bytes
                reads.append(r)
        out.row_groups.append(
            RowGroupPlan(g, rg.num_rows, steps, skipped, pages, [] if skipped else rows, reads, index_bytes)
        )
    return out
