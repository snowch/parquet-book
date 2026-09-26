"""The calls the book's pages make when a lab runs on the Python engine.

The page holds its files here and calls these functions through Pyodide, the way it calls the
Rust reader's exports through WebAssembly (``crates/parquet-lab-wasm``). Each returns the same
JSON text as its Rust counterpart, so ``web/lab`` draws either without knowing which ran.
"""

from __future__ import annotations

from . import report
from .object_store import NetworkModel
from .reader import FooterOptions, Head, Known, SuffixRange

FILES: list[tuple[str, bytearray]] = []

EXPERIMENTS = (
    "layouts",
    "footer",
    "anatomy",
    "schema",
    "levels",
    "encodings",
    "pages",
    "compression",
    "statistics",
    "skipping",
    "scan",
    "writing",
    "engine",
    "encryption",
    "table",
    "changes",
)
"""The labs this engine can run: every lab in the book."""


def load(name: str, data: bytes) -> int:
    # From the page, ``data`` is a JavaScript Uint8Array, which Pyodide hands over as a proxy.
    if hasattr(data, "to_bytes"):
        data = data.to_bytes()
    FILES.append((name, bytearray(data)))
    return len(FILES) - 1


def _file(id: int) -> bytes | None:
    return bytes(FILES[id][1]) if 0 <= id < len(FILES) else None


def _no_such_file(id: int) -> str:
    return report.dumps({"ok": False, "error": f"no file with id {id}"})


def file_bytes(id: int) -> bytes:
    return _file(id) or b""


def set_byte(id: int, offset: int, value: int) -> int:
    """Change one byte of a loaded file. Returns the byte that was there, or -1."""
    if not (0 <= id < len(FILES)) or not (0 <= offset < len(FILES[id][1])):
        return -1
    old = FILES[id][1][offset]
    FILES[id][1][offset] = value & 0xFF
    return old


def footer_lab(id: int, size_source: int, prefetch: int, latency_us: int, bandwidth: int) -> str:
    if not (0 <= id < len(FILES)):
        return _no_such_file(id)
    name, data = FILES[id]
    size = [Head(), Known(len(data)), SuffixRange()][min(size_source, 2)]
    model = NetworkModel(int(latency_us), int(bandwidth))
    return report.dumps(report.footer_lab(bytes(data), name, FooterOptions(size, int(prefetch)), model))


def structure(id: int) -> str:
    data = _file(id)
    return _no_such_file(id) if data is None else report.dumps(report.structure(data))


def interpret(id: int, offset: int) -> str:
    data = _file(id)
    return _no_such_file(id) if data is None else report.dumps(report.interpret(data, int(offset)))


def layouts(column_mask: int, row: int, latency_us: int, bandwidth: int) -> str:
    model = NetworkModel(int(latency_us), int(bandwidth))
    return report.dumps(report.layouts(column_mask, row if row >= 0 else None, model))


def schema(id: int) -> str:
    data = _file(id)
    return _no_such_file(id) if data is None else report.dumps(report.schema(data))


def _per_column(report_fn):
    def call(id: int, column: int, *rest) -> str:
        data = _file(id)
        if data is None:
            return _no_such_file(id)
        return report.dumps(report_fn(data, int(column), *rest))

    return call


levels = _per_column(report.levels)
encodings = _per_column(report.encodings)
pages = _per_column(report.pages)


def compression(id: int, column: int, page: int) -> str:
    """``page`` above 2^32 - 2 means the first data page, as in the Rust export."""
    data = _file(id)
    if data is None:
        return _no_such_file(id)
    chosen = None if page >= 0xFFFF_FFFF else int(page)
    return report.dumps(report.compression(data, int(column), chosen))


def statistics(id: int, row_group: int, column: int) -> str:
    data = _file(id)
    return (
        _no_such_file(id)
        if data is None
        else report.dumps(report.statistics(data, int(row_group), int(column)))
    )


def skipping(id: int, column: int, op: int, value: str, mechanisms: int) -> str:
    """``op`` is an index into ``report.OPS``, as in the Rust export."""
    data = _file(id)
    if data is None:
        return _no_such_file(id)
    name = report.OPS[op] if 0 <= op < len(report.OPS) else "?"
    return report.dumps(report.skipping(data, int(column), name, value, int(mechanisms)))


def scan(
    id, columns, where_column, op, text, footer, prefetch, connections, gap, flags, latency_us, bandwidth
) -> str:
    """The arguments of the Rust export ``pl_scan``: a column bit mask (0 for all), a condition's
    column (2^32 - 1 for none), an index into ``report.OPS``, its text, the footer strategy (1 for a
    suffix read), the prefetch, the connections, the coalescing gap (2^32 - 1 never merges), the
    mechanisms and whole chunks as bit flags, and the network."""
    from .prune import Mechanisms, Op
    from .reader import FooterOptions, Head, SuffixRange
    from .scan import Query, Strategy

    data = _file(id)
    if data is None:
        return _no_such_file(id)
    condition = None
    if where_column != 0xFFFF_FFFF:
        name = report.OPS[op] if 0 <= op < len(report.OPS) else "?"
        try:
            condition = (int(where_column), Op.parse(name), text)
        except ValueError as e:
            return report.dumps({"ok": False, "error": str(e)})
    strategy = Strategy(
        footer=FooterOptions(SuffixRange() if footer == 1 else Head(), int(prefetch)),
        connections=max(int(connections), 1),
        coalesce_gap=None if gap == 0xFFFF_FFFF else int(gap),
        whole_chunks=bool(flags & 8),
        mechanisms=Mechanisms(bool(flags & 1), bool(flags & 2), bool(flags & 4)),
    )
    try:
        cols = [c for c in report.flat_columns(data) if columns == 0 or (c < 32 and columns & (1 << c))]
    except ValueError as e:
        return report.dumps({"ok": False, "error": str(e)})
    model = NetworkModel(int(latency_us), int(bandwidth))
    return report.dumps(report.scan(data, Query(cols, condition), strategy, model))


def query(id: int, sql: str) -> str:
    data = _file(id)
    return _no_such_file(id) if data is None else report.dumps(report.query(data, sql))


def encryption(id: int) -> str:
    data = _file(id)
    return _no_such_file(id) if data is None else report.dumps(report.encryption(data))


def table(ids, sql: str, discovery: int, connections: int, latency_us: int, bandwidth: int) -> str:
    """``ids`` are loaded files named by their object keys; ``discovery`` is 0 to list, 1 to list
    and prune, 2 to read the log."""
    from .table import Discovery

    objects = [(FILES[i][0], bytes(FILES[i][1])) for i in ids if 0 <= i < len(FILES)]
    kind = [Discovery.LIST, Discovery.LIST_AND_PRUNE, Discovery.LOG][min(int(discovery), 2)]
    model = NetworkModel(int(latency_us), int(bandwidth))
    return report.dumps(report.table(objects, sql, kind, max(int(connections), 1), model))


def changes(
    ids,
    snapshot: str,
    op: int,
    key: int,
    target_rows: int,
    small_rows: int,
    prefetch: int,
    connections: int,
    latency_us: int,
    bandwidth: int,
) -> str:
    """``ids`` are loaded files named by their object keys; ``op`` is 0 to scan, 1 to look up
    ``key``, 2 to plan a compaction, as in the Rust export ``pl_changes``."""
    objects = [(FILES[i][0], bytes(FILES[i][1])) for i in ids if 0 <= i < len(FILES)]
    how = {1: ("lookup", int(key)), 2: ("compact", int(target_rows), int(small_rows))}.get(int(op), ("scan",))
    model = NetworkModel(int(latency_us), int(bandwidth))
    return report.dumps(
        report.changes(objects, snapshot, how, int(prefetch), max(int(connections), 1), model)
    )
