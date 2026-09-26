"""The read path: a query turned into requests, and requests into rows (ch10).

Everything before this chapter decided *what* to read. This module decides *how*: in which
order, in how many requests, over how many connections. It runs a query,
``SELECT columns WHERE condition``, against a file in an object store, in three phases:

1. **The footer** (:mod:`parquet_lab.reader`), with whatever tail prefetch the strategy asks for.
2. **The indexes the plan needs**: Bloom filters and page indexes (:mod:`parquet_lab.prune`),
   unless the prefetched tail already holds them.
3. **The data**: the byte ranges the plan chose.

In phases 2 and 3 the ranges are sorted, and two ranges whose gap is at most the strategy's
``coalesce_gap`` become one request. That reads the gap too, which is waste, and saves a request,
which is time. With more than one connection, the requests of a phase overlap.

The reader decodes only from bytes it fetched. It keeps a copy of the file that starts empty and
fills in each response, so a range it forgot to request reads as zeros and fails its decode; the
tests check every result against a full read.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import page_index, plain, prune, stats
from .bytes import Span
from .column import read_column, read_column_pages
from .logical import value_json
from .object_store import Bounded, MemoryStore, NetworkModel, ObjectStore, Request, TracingStore
from .prune import Mechanisms, Op, Predicate
from .reader import FooterOptions, read_footer
from .schema import build, leaves


@dataclass(frozen=True)
class Strategy:
    """How to issue requests."""

    footer: FooterOptions = FooterOptions()
    connections: int = 1
    coalesce_gap: int | None = None
    """Two ranges this close or closer become one request: ``0`` merges ranges that touch.
    ``None`` never merges, so every range is its own request."""
    whole_chunks: bool = False
    """Read whole column chunks, even when the page index would allow single pages."""
    mechanisms: Mechanisms = Mechanisms()


@dataclass
class Query:
    """A query: the columns to return, and at most one condition, as ``(column, op, text)``."""

    columns: list[int]
    condition: tuple[int, Op, str] | None = None


@dataclass
class ScanResult:
    requests: list[Request]
    elapsed_us: int
    bytes_fetched: int
    bytes_planned: int
    """Bytes the reader planned to use: fetched bytes minus the gaps coalescing read."""
    rows_decoded: int
    matches: list[int]
    """Row numbers in the file, counting from 0, of the rows that satisfy the condition."""
    rows: list[list[object]]
    """The first matching rows, column by column, as JSON values."""
    column_names: list[str]


class Fetched:
    """The file as the reader has it: the bytes it has fetched, and zeros elsewhere."""

    def __init__(self, size: int) -> None:
        self.data = bytearray(size)
        self.have: list[Span] = []

    def add(self, span: Span, data: bytes) -> None:
        self.data[span.start : span.end] = data
        self.have.append(span)

    def missing(self, s: Span) -> list[Span]:
        """The parts of ``s`` not yet fetched."""
        parts = [s]
        for h in self.have:
            out = []
            for p in parts:
                if p.start < min(h.start, p.end):
                    out.append(Span(p.start, min(h.start, p.end)))
                if max(h.end, p.start) < p.end:
                    out.append(Span(max(h.end, p.start), p.end))
            parts = out
        return parts


def coalesce(spans: list[Span], gap: int | None) -> list[Span]:
    """Sort ranges and merge those whose gap is at most ``gap`` bytes. With no gap, only ranges
    that overlap are merged, since fetching the same byte twice is never useful."""
    out: list[Span] = []
    for s in sorted(spans):
        if out and (s.start <= out[-1].end + gap if gap is not None else s.start < out[-1].end):
            out[-1] = Span(out[-1].start, max(out[-1].end, s.end))
        else:
            out.append(s)
    return out


def fetch(store: ObjectStore, key: str, have: Fetched, wanted: list[Span], gap: int | None, why: str) -> int:
    """Fetch every range the reader does not already have, coalesced, as one phase."""
    # Only the bytes not already held: a merged request must not fetch the tail again.
    missing = [part for s in wanted for part in have.missing(s)]
    planned = sum(s.length for s in coalesce(missing, 0))
    requests = [part for r in coalesce(missing, gap) for part in have.missing(r)]
    if not requests:
        return 0
    store.next_phase()
    for r in requests:
        got = store.get(key, Bounded(r), why)
        have.add(got.span, got.data)
    return planned


class ScanError(ValueError):
    pass


def scan(obj: bytes, key: str, query: Query, strategy: Strategy, model: NetworkModel) -> ScanResult:
    """Run ``query`` against ``obj``, stored under ``key``, with ``strategy``, over ``model``."""
    inner = MemoryStore()
    inner.put(key, obj)
    store = TracingStore(inner, model, strategy.connections)
    return scan_in(store, obj, key, query, strategy)


def scan_in(store: TracingStore, obj: bytes, key: str, query: Query, strategy: Strategy) -> ScanResult:
    """:func:`scan`, in a store that other requests share: a table's reader opens one of its
    files (ch15). ``obj`` is the file's bytes, which the store holds under ``key``; the result's
    requests and totals are the whole store's."""
    have = Fetched(len(obj))

    # Phase 1: the footer. Every byte the footer read returned is now the reader's.
    before = len(store.requests)
    try:
        footer = read_footer(store, key, strategy.footer)
    except Exception as e:  # a store error or a format error, reported as text
        raise ScanError(str(e)) from e
    for r in store.requests[before:]:
        if r.key == key and r.returned is not None:
            have.add(r.returned, obj[r.returned.start : r.returned.end])
    md = footer.metadata
    flat = [leaf for leaf in leaves(build(md.schema)) if leaf.max_repetition_level == 0]

    def leaf_of(c: int):
        found = next((leaf for leaf in flat if leaf.column == c), None)
        if found is None:
            raise ScanError(f"no column {c} that does not repeat")
        return found

    columns = [leaf_of(c) for c in query.columns]
    predicate = None
    if query.condition is not None:
        c, op, text = query.condition
        leaf = leaf_of(c)
        predicate = (leaf, Predicate.new(leaf, md.schema[leaf.element].converted_type, op, text))
    # Every column the query touches: the condition's too, since it must be read to test rows.
    touched = list(query.columns)
    if predicate is not None and predicate[0].column not in touched:
        touched.append(predicate[0].column)

    # Phase 2: the indexes the plan will consult. Which ones depends on the footer alone.
    planned = 0
    if predicate is not None:
        leaf, p = predicate
        orders = md.column_orders
        type_order = orders is not None and leaf.column < len(orders) and orders[leaf.column] == "TYPE_ORDER"
        wanted = []
        for rg in md.row_groups:
            chunk = rg.columns[leaf.column]
            # A row group the footer's statistics already rule out needs no index.
            if strategy.mechanisms.statistics and chunk.statistics is not None:
                st = chunk.statistics
                try:
                    b = stats.bounds(st, p.comparator, type_order)
                    found = (b.min, b.max)
                except ValueError:
                    found = None
                if prune.against_bounds(p, found, st.null_count, chunk.num_values).skip:
                    continue
            if strategy.mechanisms.bloom and p.op is Op.EQ:
                o, n = chunk.bloom_filter_offset, chunk.bloom_filter_length
                if o is not None and n is not None:
                    wanted.append(Span(o, o + n))
            if strategy.mechanisms.page_index and not strategy.whole_chunks:
                if chunk.column_index is not None:
                    wanted.append(chunk.column_index)
                wanted += [rg.columns[c].offset_index for c in touched if rg.columns[c].offset_index]
        planned += fetch(store, key, have, wanted, strategy.coalesce_gap, "read the indexes the plan needs")

    # Phase 3: the data. The plan runs on the fetched copy, so it sees only fetched indexes.
    use = strategy.mechanisms
    if strategy.whole_chunks:
        use = Mechanisms(use.statistics, use.bloom, False)
    # A Bloom filter without a recorded length could not be fetched in one request; this reader
    # does not consult it.
    if predicate is not None and any(
        rg.columns[predicate[0].column].bloom_filter_offset is not None
        and rg.columns[predicate[0].column].bloom_filter_length is None
        for rg in md.row_groups
    ):
        use = Mechanisms(use.statistics, False, use.page_index)
    # For each row group read: its index, the rows kept, and the byte ranges to fetch.
    if predicate is not None:
        fetched_view = bytes(have.data)
        pl = prune.plan(fetched_view, md, predicate[0], predicate[1], touched, use)
        groups = [
            (g.index, g.rows, [s for r in g.reads for s in r.spans]) for g in pl.row_groups if not g.skipped
        ]
    else:
        groups = [
            (i, [(0, rg.num_rows)], [rg.columns[c].byte_range() for c in touched])
            for i, rg in enumerate(md.row_groups)
        ]
    wanted = [s for g in groups for s in g[2]]
    planned += fetch(store, key, have, wanted, strategy.coalesce_gap, "read the pages the plan kept")

    # Decode what was fetched, and keep the rows that satisfy the condition.
    data = bytes(have.data)
    matches: list[int] = []
    rows: list[list[object]] = []
    rows_decoded = 0
    group_starts, first_row = [], 0
    for rg in md.row_groups:
        group_starts.append(first_row)
        first_row += rg.num_rows
    for g, ranges, spans in groups:
        rg = md.row_groups[g]
        # Each touched column's values by row number within the row group: PLAIN bytes (None for
        # null), and the value to show. The first value a row number gets is the one kept.
        by_column: dict[int, dict[int, tuple[bytes | None, object]]] = {}
        for c in touched:
            leaf = leaf_of(c)
            chunk = rg.columns[c]
            try:
                oi = page_index.offset_index(data, chunk)
            except ValueError:
                oi = None
            firsts = None
            if oi is not None and not strategy.whole_chunks and use.page_index:
                offsets = [p.offset for p in oi.pages if any(s.contains(p.span()) for s in spans)]
                firsts = [p.first_row_index for p in oi.pages if p.offset in offsets]
                d = read_column_pages(data, chunk, leaf, offsets)
            else:
                d = read_column(data, chunk, leaf)
            dictionary = 1 if d.dictionary is not None else 0
            values: dict[int, tuple[bytes | None, object]] = {}
            count = 0
            row_in_page, last_page = 0, None
            for t in d.triples:
                if t.page != last_page:
                    last_page, row_in_page = t.page, 0
                row = firsts[t.page - dictionary] + row_in_page if firsts is not None else count
                row_in_page += 1
                count += 1
                raw = None if t.value is None else plain.to_plain_bytes(t.value, leaf.physical_type)
                shown = (
                    None if t.value is None else value_json(leaf.physical_type, leaf.logical_type, t.value)
                )
                values.setdefault(row, (raw, shown))
            by_column[c] = values
        for a, b in ranges:
            for row in range(a, b):
                rows_decoded += 1
                keep = True
                if predicate is not None:
                    v = by_column[predicate[0].column].get(row)
                    if v is None:
                        raise ScanError(f"row {row} of row group {g} was not decoded")
                    keep = predicate[1].row_matches(v[0])
                if keep:
                    matches.append(group_starts[g] + row)
                    if len(rows) < 20:
                        rows.append([by_column[c].get(row, (None, None))[1] for c in query.columns])
    return ScanResult(
        requests=list(store.requests),
        elapsed_us=store.elapsed_us(),
        bytes_fetched=store.bytes_returned(),
        bytes_planned=planned,
        rows_decoded=rows_decoded,
        matches=matches,
        rows=rows,
        column_names=[leaf.dotted_path() for leaf in columns],
    )
