"""What the reader found, as JSON: the one format the browser, the tests and the book all read.

Nothing here decides anything. Every function runs the reader and writes down what it did, so a
page that shows a footer length, a byte range or a request is showing a value this package
computed. The Rust reader has a module of the same name that writes the same JSON, and
``tests/test_python.py`` holds the two to it, call by call.
"""

from __future__ import annotations

import json
import math
import struct

from . import bloom, crypto, page_index
from .bytes import ByteReader, Span, le_terms, zigzag_decode
from .encoding import hex, plain_scalar, quote
from .format import MIN_FILE_LEN, TRAILER_LEN, check_header, footer_span, parse_trailer
from .layout import Layout, Query, Table, encode, ranges, show_cell
from .metadata import ColumnChunk, FileMetaData, decode_file_metadata
from .object_store import Bounded, MemoryStore, NetworkModel, Request, StoreError, TracingStore
from .pages import walk_pages
from .parquet_thrift import Kind, enum_value_name, field_def
from .reader import FooterOptions, Head, Known, SuffixRange, read_footer
from .thrift import Map, Node, Struct, WireType

MAX_SAFE = 2**53 - 1
"""The largest integer a JavaScript number holds exactly."""


def plain(value: object) -> object:
    """A report as plain JSON values: spans as ``[start, end]``, and the two things JSON cannot
    hold written as strings, as the Rust reader writes them. An integer beyond 2^53 would be
    rounded by the browser, and JSON has no NaN or infinity."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, Span):
        return [value.start, value.end]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > MAX_SAFE else value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    raise TypeError(f"cannot write {type(value).__name__} as JSON")


def dumps(value: object) -> str:
    return json.dumps(plain(value), ensure_ascii=False, separators=(",", ":"))


def footer_lab(file: bytes, key: str, options: FooterOptions, model: NetworkModel) -> dict:
    """Open ``file`` through a simulated object store, and report every step and every request.

    The file is put in a :class:`MemoryStore` under ``key``, and the reader sees it only through
    a :class:`TracingStore`. It gets no other access to the bytes. What it reports as fetched is
    therefore exactly what it asked for.
    """
    store = MemoryStore()
    store.put(key, file)
    traced = TracingStore(store, model)
    try:
        read, error = read_footer(traced, key, options), None
    except (ValueError, StoreError) as e:
        read, error = None, str(e)
    out = {
        "key": key,
        "options": _options(options, model),
        "requests": requests_json(traced.requests),
        "totals": {
            "requests": len(traced.requests),
            "bytes_returned": traced.bytes_returned(),
            "elapsed_us": traced.elapsed_us(),
        },
        "fetched": [r.returned for r in traced.requests if r.returned is not None],
    }
    if read is None:
        return {**out, "ok": False, "error": error}
    t = read.trailer
    useful = TRAILER_LEN + read.footer.length
    return {
        **out,
        "ok": True,
        "file_size": read.file_size,
        "tail": read.tail,
        "trailer": {
            "span": t.span,
            "bytes": list(t.data),
            "length_span": t.length_span(),
            "magic_span": t.magic_span(),
            "magic": t.magic.decode("utf-8", "replace"),
            "footer_length": t.footer_length,
            "terms": [{"byte": b, "weight": w, "product": b * w} for b, w in t.length_terms()],
        },
        "footer": {
            "span": read.footer,
            "length": read.footer.length,
            "prefetched": read.footer_was_prefetched,
        },
        "useful_bytes": useful,
        "overfetch_bytes": max(traced.bytes_returned() - useful, 0),
        "metadata": _metadata_summary(read.metadata),
    }


def _options(o: FooterOptions, m: NetworkModel) -> dict:
    match o.size:
        case Head():
            size, known = "head", None
        case Known(n):
            size, known = "known", n
        case SuffixRange():
            size, known = "suffix", None
    return {
        "size_source": size,
        "known_size": known,
        "prefetch": o.prefetch,
        "latency_us": m.latency_us,
        "bandwidth_bytes_per_sec": m.bandwidth_bytes_per_sec,
    }


def requests_json(requests: list[Request]) -> list[dict]:
    return [
        {
            "seq": r.seq,
            "method": r.method,
            "key": r.key,
            "range": r.range,
            "why": r.why,
            "status": r.status,
            "returned": r.returned,
            "bytes": r.bytes_returned,
            "start_us": r.start_us,
            "end_us": r.end_us,
            "connection": r.connection,
            "phase": r.phase,
        }
        for r in requests
    ]


def _metadata_summary(m: FileMetaData) -> dict:
    return {
        "version": m.version,
        "num_rows": m.num_rows,
        "created_by": m.created_by,
        "num_row_groups": len(m.row_groups),
        "columns": [
            {
                "name": e.name,
                "physical_type": e.physical_type.name if e.physical_type is not None else None,
                "repetition": e.repetition,
                "logical_type": str(e.logical_type) if e.logical_type else None,
            }
            for e in m.leaves()
        ],
        "key_value_metadata": len(m.key_value_metadata),
    }


def structure(file: bytes) -> dict:
    """The whole file, parsed into the regions the structure view draws.

    Unlike :func:`footer_lab` this reads the bytes directly rather than through a store: it is a
    map of the file, not a record of how a reader got there. Every node has a ``span``, so
    selecting it can highlight its bytes, and a ``label`` and ``value`` for the tree.
    """
    try:
        return {"ok": True, "file_size": len(file), "tree": _structure(file)}
    except ValueError as e:
        return {"ok": False, "file_size": len(file), "error": str(e)}


def region(label: str, kind: str, span: Span, value: object, children: list) -> dict:
    return {"label": label, "kind": kind, "span": span, "value": value, "children": children}


def _module_region(label: str, m: crypto.Module) -> dict:
    """A module's parts, as structure regions."""
    return region(
        label,
        "encrypted",
        m.span,
        f"{m.span.length} bytes, encrypted",
        [
            region("Length", "module_length", m.length, f"{m.span.length - 4} (u32, little-endian)", []),
            region("Nonce", "nonce", m.nonce, "12 bytes, used once", []),
            region("Ciphertext", "ciphertext", m.ciphertext, None, []),
            region("Tag", "tag", m.tag, "16 bytes: AES-GCM's check", []),
        ],
    )


def _trailer_region(last: Span, length: str, magic: str) -> dict:
    return region(
        "Trailer",
        "trailer",
        last,
        None,
        [
            region("Footer length", "footer_length", Span(last.start, last.start + 4), length, []),
            region("Magic", "magic", Span(last.start + 4, last.end), magic, []),
        ],
    )


def _encrypted_structure(file: bytes) -> dict:
    """An encrypted-footer file, as far as a reader without the footer key can see it (ch13)."""
    size = len(file)
    e = crypto.encrypted_footer(file)
    return region(
        "Parquet file",
        "file",
        Span(0, size),
        f"{size} bytes",
        [
            region("Header", "magic", Span(0, 4), "PARE", []),
            region(
                "Data",
                "encrypted",
                Span(4, e.footer.start),
                "row groups the reader cannot locate without the footer",
                [],
            ),
            region(
                "Footer",
                "footer",
                e.footer,
                "FileCryptoMetaData, then the encrypted FileMetaData",
                [
                    annotate(e.crypto_metadata, "FileCryptoMetaData", "FileCryptoMetaData"),
                    _module_region("Encrypted FileMetaData", e.module),
                ],
            ),
            _trailer_region(
                Span(size - TRAILER_LEN, size), f"{e.footer.length} (u32, little-endian)", "PARE"
            ),
        ],
    )


def _structure(file: bytes) -> dict:
    size = len(file)
    if size < MIN_FILE_LEN:
        raise ValueError(f"{size} bytes is too short to be a Parquet file")
    if file[:4] == crypto.MAGIC_ENCRYPTED:
        return _encrypted_structure(file)
    header = check_header(file[:4])
    trailer = parse_trailer(file[-8:], size)
    footer = footer_span(size, trailer.footer_length)
    md = decode_file_metadata(file[footer.start : footer.end], footer.start)

    top = [region("Header", "magic", header, "PAR1", [])]
    for i, rg in enumerate(md.row_groups):
        chunks = [_chunk_region(file, c) for c in rg.columns]
        spans = [c.byte_range() for c in rg.columns]
        span = (
            Span(min(s.start for s in spans), max(s.end for s in spans))
            if spans
            else Span(header.end, header.end)
        )
        top.append(region(f"Row group {i}", "row_group", span, f"{rg.num_rows} rows", chunks))

    # Bloom filters and the page index (ch09), between the last row group and the footer.
    extra: list[tuple[Span, dict]] = []
    for g, rg in enumerate(md.row_groups):
        for c in rg.columns:
            name = f"{c.dotted_path()} (row group {g})"
            b = _quietly(bloom.read, file, c)
            if b is not None:
                span = Span(b.header_span.start, b.bitset_span.end)
                bitset = region(
                    "Bitset",
                    "bloom_bitset",
                    b.bitset_span,
                    f"{b.num_blocks()} blocks of 32 bytes",
                    [],
                )
                head = annotate(b.header, "BloomFilterHeader", "BloomFilterHeader")
                extra.append((span, region(f"Bloom filter {name}", "bloom", span, None, [head, bitset])))
            ci = _quietly(page_index.column_index, file, c)
            if ci is not None:
                tree = annotate(ci.tree, "ColumnIndex", "ColumnIndex", c)
                extra.append((ci.span, region(f"Column index {name}", "column_index", ci.span, None, [tree])))
            oi = _quietly(page_index.offset_index, file, c)
            if oi is not None:
                tree = annotate(oi.tree, "OffsetIndex", "OffsetIndex")
                extra.append((oi.span, region(f"Offset index {name}", "offset_index", oi.span, None, [tree])))
    extra.sort(key=lambda e: e[0])
    if extra:
        span = Span(extra[0][0].start, extra[-1][0].end)
        top.append(
            region(
                "Indexes and filters",
                "indexes",
                span,
                f"{len(extra)} structures",
                [j for _, j in extra],
            )
        )
    footer_children = [annotate(md.tree, "FileMetaData", "FileMetaData")]
    sig = md.footer_signature
    if sig is not None:
        footer_children.append(
            region(
                "Signature",
                "signature",
                sig,
                "a nonce and an AES-GCM tag made with the footer key",
                [
                    region("Nonce", "nonce", Span(sig.start, sig.start + 12), None, []),
                    region("Tag", "tag", Span(sig.start + 12, sig.end), None, []),
                ],
            )
        )
    top.append(region("Footer", "footer", footer, "FileMetaData", footer_children))
    top.append(_trailer_region(trailer.span, f"{trailer.footer_length} (u32, little-endian)", "PAR1"))
    return region("Parquet file", "file", Span(0, size), f"{size} bytes", top)


def _quietly(read, *args):
    """The structure view shows an index or a filter only when it reads cleanly."""
    try:
        return read(*args)
    except ValueError:
        return None


def _chunk_region(file: bytes, c: ColumnChunk) -> dict:
    r = c.byte_range()
    if r.end > len(file):
        raise ValueError(f"column chunk {c.dotted_path()} claims bytes {r}, past the end of the file")
    if c.crypto is not None:
        # Encrypted pages cannot be walked by their headers; their modules can, by length.
        try:
            modules = crypto.chunk_modules(file, r)
        except ValueError as e:
            raise ValueError(f"column chunk {c.dotted_path()}: {e}") from e
        key = "its own key" if c.crypto.with_column_key else "the footer key"
        return region(
            f"Column chunk {c.dotted_path()}",
            "column_chunk",
            r,
            f"{c.physical_type.name} · encrypted with {key} · {len(modules)} modules",
            [
                _module_region("Encrypted page header" if i % 2 == 0 else "Encrypted page", m)
                for i, m in enumerate(modules)
            ],
        )
    try:
        pages = walk_pages(file[r.start : r.end], r.start)
    except ValueError as e:
        raise ValueError(f"column chunk {c.dotted_path()}: {e}") from e
    children = []
    for i, p in enumerate(pages):
        detail = f"{p.compressed_page_size} bytes, {p.num_values or 0} values"
        if p.encoding is not None:
            detail += f", {p.encoding}"
        children.append(
            region(
                f"Page {i}: {p.page_type}",
                "page",
                p.span(),
                detail,
                [
                    region(
                        "Page header",
                        "page_header",
                        p.header_span,
                        "PageHeader",
                        [annotate(p.header, "PageHeader", "PageHeader", c)],
                    ),
                    region("Page body", "page_body", p.body_span, "values", []),
                ],
            )
        )
    value = f"{c.physical_type.name} · {', '.join(c.encodings)} · {c.codec}"
    s = c.statistics
    if s is not None and s.min_value is not None and s.max_value is not None:
        lo = plain_scalar(c.physical_type, s.min_value) or hex(s.min_value)
        hi = plain_scalar(c.physical_type, s.max_value) or hex(s.max_value)
        value += f" · min {lo} max {hi}"
    return region(f"Column chunk {c.dotted_path()}", "column_chunk", r, value, children)


def annotate(node: Node, type_name: str, label: str, column: ColumnChunk | None = None) -> dict:
    """A decoded Thrift node with Parquet's names attached, for the structure view.

    ``column`` is the column chunk a page header belongs to, when there is one, so statistics
    can be shown as values rather than bytes.
    """
    return _annotate(node, Kind("struct", type_name), label, node.span, column)


def _annotate(node: Node, kind: Kind, label: str, span: Span, column: ColumnChunk | None) -> dict:
    v = node.value
    children: list = []
    if isinstance(v, Struct):
        struct_name = kind.of if kind.tag == "struct" else ""
        for f in v.fields:
            d = field_def(struct_name, f.id)
            child = _annotate(
                f.node,
                d.kind if d else Kind("int"),
                d.name if d else f"field {f.id}",
                f.span(),
                column,
            )
            children.append({**child, "field_id": f.id, "header": f.header})
        type_name, value = struct_name or "struct", None
    elif isinstance(v, Map):
        type_name, value = "map", f"{len(v)} entries"
    elif isinstance(v, list):
        inner = kind.of if kind.tag == "list" else Kind("int")
        children = [_annotate(n, inner, f"[{i}]", n.span, column) for i, n in enumerate(v)]
        type_name, value = f"list<{_kind_name(inner)}>", f"{len(v)} item{'' if len(v) == 1 else 's'}"
    elif isinstance(v, bool):
        type_name, value = "bool", v
    elif isinstance(v, int) and kind.tag == "enum":
        name = enum_value_name(kind.of, v)
        type_name, value = "enum", f"{v} → {name}" if name is not None else f"{v}"
    elif isinstance(v, int):
        type_name, value = "int", v
    elif isinstance(v, float):
        type_name, value = "double", v
    elif kind.tag == "str":
        type_name, value = "string", quote(v.decode("utf-8", "replace"))
    else:
        shown = None
        if column is not None and label in ("min_value", "max_value", "min", "max"):
            scalar = plain_scalar(column.physical_type, v)
            shown = f"{hex(v)} → {scalar}" if scalar is not None else None
        type_name, value = "binary", shown if shown is not None else hex(v)
    return {
        "label": label,
        "kind": "thrift",
        "type": type_name,
        "span": span,
        "value": value,
        "children": children,
    }


def _kind_name(k: Kind) -> str:
    if k.tag in ("int", "bool"):
        return k.tag
    if k.tag == "str":
        return "string"
    if k.tag == "bytes":
        return "binary"
    if k.tag == "list":
        return f"list<{_kind_name(k.of)}>"
    return k.of


def interpret(file: bytes, offset: int) -> dict:
    """Every reasonable reading of the bytes starting at ``offset``: the byte inspector.

    A byte means nothing on its own. It is a value only once you decide how many bytes belong to
    it and in which order, and this lists the choices side by side, all computed here.
    """
    if offset >= len(file):
        return {"ok": False, "error": f"offset {offset} is past the end"}
    rest = file[offset:]
    b = rest[0]
    out: dict = {
        "ok": True,
        "offset": offset,
        "byte": b,
        "hex": f"{b:02x}",
        "binary": f"{b:08b}",
        "i8": b - 256 if b >= 128 else b,
        "ascii": chr(b) if 0x20 <= b <= 0x7E else None,
    }
    if len(rest) >= 2:
        out["u16_le"] = int.from_bytes(rest[:2], "little")
    if len(rest) >= 4:
        four = rest[:4]
        out["u32_le"] = int.from_bytes(four, "little")
        out["i32_le"] = int.from_bytes(four, "little", signed=True)
        out["f32_le"] = struct.unpack("<f", four)[0]
        out["u32_le_terms"] = [{"byte": x, "weight": w} for x, w in le_terms(four)]
    if len(rest) >= 8:
        eight = rest[:8]
        out["u64_le"] = int.from_bytes(eight, "little")
        out["i64_le"] = int.from_bytes(eight, "little", signed=True)
        out["f64_le"] = struct.unpack("<d", eight)[0]
    r = ByteReader(rest, offset)
    try:
        v = r.read_uleb128()
        out["uleb128"] = {"value": v, "length": r.offset() - offset, "zigzag": zigzag_decode(v)}
    except ValueError:
        pass
    wire = WireType.from_nibble(b & 0x0F)
    out["thrift_field_header"] = {
        "delta": b >> 4,
        "type_nibble": b & 0x0F,
        "type": wire.type_name if wire else None,
    }
    return out


def open_bytes(file: bytes) -> FileMetaData:
    """Parse ``file`` fully and return its metadata. For the tests and the problems."""
    store = MemoryStore()
    store.put("file", file)
    return read_footer(store, "file", FooterOptions()).metadata


def layouts(column_mask: int, row: int | None, model: NetworkModel) -> dict:
    """Ch01's experiment: one query against the same table in both layouts, read through the
    simulated object store.

    ``column_mask`` has bit ``c`` set for each column the query projects. ``row`` is one row to
    fetch, or ``None`` for every row. Each layout is stored as an object and read twice: once
    range by range, asking only for the bytes the query needs, and once as a single whole-object
    ``GET``. Both reads are real requests against the store, and their traces are returned.
    """
    table = Table.sales()
    columns = [c for c in range(len(table.columns)) if column_mask & (1 << c)]
    rows = [row] if row is not None and row < len(table.rows) else list(range(len(table.rows)))
    query = Query(columns, rows)

    def layout_json(layout: Layout, key: str) -> dict:
        enc = encode(table, layout)
        needed = ranges(enc, query)
        store = MemoryStore()
        store.put(key, enc.data)
        by_range = TracingStore(store, model)
        for i, span in enumerate(needed):
            by_range.get(key, Bounded(span), f"range {i + 1} of {len(needed)}: the query's values")
        whole = TracingStore(store, model)
        if needed:
            whole.get(
                key,
                Bounded(Span(0, len(enc.data))),
                "the whole object, to pick the values out locally",
            )
        return {
            "layout": layout.value,
            "key": key,
            "bytes": list(enc.data),
            "cells": enc.cells,
            "needed": needed,
            "needed_bytes": sum(s.length for s in needed),
            "total_bytes": len(enc.data),
            "by_range": {
                "requests": requests_json(by_range.requests),
                "bytes": by_range.bytes_returned(),
                "elapsed_us": by_range.elapsed_us(),
            },
            "whole": {
                "requests": requests_json(whole.requests),
                "bytes": whole.bytes_returned(),
                "elapsed_us": whole.elapsed_us(),
            },
        }

    return {
        "ok": True,
        "columns": [name for name, _ in table.columns],
        "rows": [[show_cell(v, t) for v, (_, t) in zip(r, table.columns, strict=True)] for r in table.rows],
        "query": {"columns": query.columns, "rows": query.rows},
        "model": {
            "latency_us": model.latency_us,
            "bandwidth_bytes_per_sec": model.bandwidth_bytes_per_sec,
        },
        "rows_layout": layout_json(Layout.ROWS, "sales.rows"),
        "columns_layout": layout_json(Layout.COLUMNS, "sales.columns"),
    }
