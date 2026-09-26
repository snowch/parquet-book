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

EXPERIMENTS = ("layouts", "footer", "anatomy", "schema", "levels", "encodings", "pages", "compression")
"""The labs this engine can run so far. The rest arrive as their chapters are ported."""


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
