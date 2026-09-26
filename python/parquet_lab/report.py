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
from functools import cmp_to_key

from . import bloom, crypto, engine, logical, page_index, plain
from .bytes import ByteReader, Span, le_terms, zigzag_decode
from .column import first_rows, read_column
from .compress import decompress, supported
from .encoding import hex, json_text, plain_scalar, quote
from .format import MIN_FILE_LEN, TRAILER_LEN, check_header, footer_span, parse_trailer
from .layout import Layout, Query, Table, encode, ranges, show_cell
from .metadata import ColumnChunk, FileMetaData, decode_file_metadata
from .nested import assemble, explain, path_fields
from .object_store import Bounded, MemoryStore, NetworkModel, Request, StoreError, TracingStore
from .pages import walk_pages
from .parquet_thrift import Kind, enum_value_name, field_def
from .prune import NONE as NO_MECHANISMS
from .prune import Mechanisms, Op, Predicate, plan
from .reader import FooterOptions, Head, Known, SuffixRange, read_footer
from .scan import Query as ScanQuery
from .scan import Strategy
from .scan import scan as run_scan
from .schema import SchemaNode, build, leaves, physical_word, to_text
from .stats import Comparator
from .stats import bounds as stats_bounds
from .table import query as table_query
from .thrift import Map, Node, Struct, WireType

MAX_SAFE = 2**53 - 1
"""The largest integer a JavaScript number holds exactly."""


def jsonable(value: object) -> object:
    """A report as plain JSON values: spans as ``[start, end]``, and the two things JSON cannot
    hold written as strings, as the Rust reader writes them. An integer beyond 2^53 would be
    rounded by the browser, and JSON has no NaN or infinity."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
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
    return json.dumps(jsonable(value), ensure_ascii=False, separators=(",", ":"))


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


def _open(file: bytes) -> FileMetaData | str:
    """The file's metadata, or why it could not be read, for the reports that start from it."""
    try:
        return open_bytes(file)
    except (ValueError, StoreError) as e:
        return str(e)


def schema(file: bytes) -> dict:
    """Ch03's experiment: the schema as the footer stores it, as the reader rebuilds it, and what
    each column's statistics mean once its logical type is applied."""
    md = _open(file)
    if isinstance(md, str):
        return {"ok": False, "error": md}
    try:
        root = build(md.schema)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    elements = [
        {
            "index": i,
            "name": e.name,
            "span": e.span,
            "num_children": e.num_children,
            "repetition": e.repetition,
            "physical_type": e.physical_type.name if e.physical_type is not None else None,
            "type_length": e.type_length,
            "logical_type": str(e.logical_type) if e.logical_type else None,
            "converted_type": e.converted_type,
        }
        for i, e in enumerate(md.schema)
    ]

    def reading(c: ColumnChunk, lt, data: bytes | None, span: Span | None):
        if data is None or span is None:
            return None
        return {
            "span": span,
            "hex": hex(data),
            "physical": plain_scalar(c.physical_type, data),
            "logical": logical.interpret(c.physical_type, lt, data) if lt else None,
        }

    first = md.row_groups[0] if md.row_groups else None
    out_leaves = []
    for leaf in leaves(root):
        chunk = first.columns[leaf.column] if first and leaf.column < len(first.columns) else None
        stats = None
        if chunk is not None and chunk.statistics is not None:
            s = chunk.statistics
            stats = {
                "span": s.span,
                "min": reading(chunk, leaf.logical_type, s.min_value, s.min_span),
                "max": reading(chunk, leaf.logical_type, s.max_value, s.max_span),
                "null_count": s.null_count,
            }
        out_leaves.append(
            {
                "column": leaf.column,
                "path": leaf.dotted_path(),
                "element": leaf.element,
                "repetitions": leaf.repetitions,
                "max_definition_level": leaf.max_definition_level,
                "max_repetition_level": leaf.max_repetition_level,
                "physical_type": leaf.physical_type.name,
                "logical_type": str(leaf.logical_type) if leaf.logical_type else None,
                "chunk": chunk.byte_range() if chunk else None,
                "statistics": stats,
            }
        )

    def tree(node: SchemaNode) -> dict:
        return {
            "name": node.name,
            "element": node.element,
            "span": node.span,
            "repetition": node.repetition,
            "children": [tree(c) for c in node.children],
        }

    return {
        "ok": True,
        "elements": elements,
        "tree": tree(root),
        "text": to_text(root),
        "leaves": out_leaves,
    }


def _leaf(file: bytes, column: int):
    """The metadata, the schema tree, its leaves and the chosen leaf, or an error report."""
    md = _open(file)
    if isinstance(md, str):
        return {"ok": False, "error": md}
    try:
        root = build(md.schema)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    found = leaves(root)
    if not 0 <= column < len(found):
        return {"ok": False, "error": f"the file has no column {column}"}
    return md, root, found, found[column]


def _runs(stream) -> dict | None:
    if stream is None:
        return None
    span, runs = stream
    return {
        "span": span,
        "runs": [{"kind": r.kind, "header": r.header, "body": r.body, "values": r.values} for r in runs],
    }


def levels(file: bytes, column: int) -> dict:
    """Ch04's experiment: one column's levels and values, what each triple means, and the
    records rebuilt from them."""
    md = _open(file)
    if isinstance(md, str):
        return {"ok": False, "error": md}
    try:
        root = build(md.schema)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    found = leaves(root)
    columns = []
    for leaf in found:
        fields = path_fields(root, leaf)
        columns.append(
            {
                "column": leaf.column,
                "path": leaf.dotted_path(),
                "label": fields[-1].label if fields else "",
                "max_definition_level": leaf.max_definition_level,
                "max_repetition_level": leaf.max_repetition_level,
            }
        )
    if not 0 <= column < len(found):
        return {"ok": False, "error": f"the file has no column {column}"}
    leaf = found[column]
    fields = path_fields(root, leaf)
    pages, triples = [], []
    for g, rg in enumerate(md.row_groups):
        try:
            data = read_column(file, rg.columns[leaf.column], leaf)
        except ValueError as e:
            return {"ok": False, "error": str(e), "columns": columns}
        for p in data.pages:
            pages.append(
                {
                    "row_group": g,
                    "span": p.page.span(),
                    "header": p.page.header_span,
                    "repetition_levels": _runs(p.rep_levels),
                    "definition_levels": _runs(p.def_levels),
                    "values": p.values,
                }
            )
        triples += data.triples
    records = assemble(fields, leaf, triples)
    return {
        "ok": True,
        "columns": columns,
        "column": column,
        "path": leaf.dotted_path(),
        "fields": [
            {
                "name": f.name,
                "label": f.label,
                "repetition": f.repetition,
                "definition_level": f.definition,
                "repetition_level": f.rep,
                "list": f.is_list,
            }
            for f in fields
        ],
        "max_definition_level": leaf.max_definition_level,
        "max_repetition_level": leaf.max_repetition_level,
        "pages": pages,
        "triples": [
            {
                "rep": t.rep,
                "def": t.definition,
                "value": None
                if t.value is None
                else logical.value_json(leaf.physical_type, leaf.logical_type, t.value),
                "value_span": t.value_span,
                "explain": explain(fields, t),
            }
            for t in triples
        ],
        "records": records,
    }


def _plain_size(physical: int, type_length: int | None, values: list) -> int:
    """What ``values`` would take as PLAIN: the size an encoding is saving against."""
    n = len(values)
    sizes = {0: (n + 7) // 8, 1: 4 * n, 4: 4 * n, 2: 8 * n, 5: 8 * n, 3: 12 * n}
    if physical in sizes:
        return sizes[physical]
    if physical == 7:
        return max(type_length or 0, 0) * n
    return sum(4 + len(v) for v in values if isinstance(v, bytes))


def encodings(file: bytes, column: int) -> dict:
    """Ch05's experiment: how one column's values are encoded, step by step, and what the
    encoding saves against PLAIN."""
    found = _leaf(file, column)
    if isinstance(found, dict):
        return found
    md, _, all_leaves, leaf = found
    first = md.row_groups[0] if md.row_groups else None
    columns = [
        {
            "column": other.column,
            "path": other.dotted_path(),
            "encodings": first.columns[i].encodings if first and i < len(first.columns) else None,
        }
        for i, other in enumerate(all_leaves)
    ]

    def show(v):
        return logical.value_json(leaf.physical_type, leaf.logical_type, v)

    data_all = []
    for rg in md.row_groups:
        try:
            data_all.append(read_column(file, rg.columns[leaf.column], leaf))
        except ValueError as e:
            return {"ok": False, "error": str(e), "columns": columns}
    pages, values, plain_values = [], [], []
    dictionary = None
    encoded = 0
    for data in data_all:
        if data.dictionary is not None:
            d = data.dictionary
            encoded += d.page.body_span.length
            dictionary = {
                "page": d.page.span(),
                "header": d.page.header_span,
                "body": d.page.body_span,
                "entries": [{"index": i, "value": show(v), "span": s} for i, (v, s) in enumerate(d.entries)],
            }
        for p in data.pages:
            encoded += p.values.length
            pages.append(
                {
                    "span": p.page.span(),
                    "encoding": p.encoding,
                    "values": p.values,
                    "steps": [{"label": s.label, "span": s.span, "detail": s.detail} for s in p.steps],
                }
            )
        for t in data.triples:
            if t.value is not None:
                plain_values.append(t.value)
                values.append({"value": show(t.value), "span": t.value_span, "extra": t.extra_spans})
    return {
        "ok": True,
        "columns": columns,
        "column": column,
        "path": leaf.dotted_path(),
        "physical_type": leaf.physical_type.name,
        "logical_type": str(leaf.logical_type) if leaf.logical_type else None,
        "dictionary": dictionary,
        "pages": pages,
        "values": values,
        "sizes": {
            "encoded": encoded,
            "plain": _plain_size(leaf.physical_type, leaf.type_length, plain_values),
            "count": len(plain_values),
        },
    }


def pages(file: bytes, column: int) -> dict:
    """Ch06's experiment: every page of one column chunk, what its header says, where its parts
    are, and which rows it holds."""
    found = _leaf(file, column)
    if isinstance(found, dict):
        return found
    md, _, all_leaves, leaf = found
    columns = [{"column": other.column, "path": other.dotted_path()} for other in all_leaves]

    def stat(c: ColumnChunk, b: bytes | None):
        if b is None:
            return None
        shown = logical.interpret(c.physical_type, leaf.logical_type, b) if leaf.logical_type else None
        return shown or plain_scalar(c.physical_type, b) or hex(b)

    out = []
    row = 0
    for g, rg in enumerate(md.row_groups):
        chunk = rg.columns[leaf.column]
        r = chunk.byte_range()
        if r.end > len(file):
            return {"ok": False, "error": f"column chunk {r} is past the end of the file"}
        try:
            walked = walk_pages(file[r.start : r.end], r.start)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        # Rows per page come from the decoded levels: a row starts wherever r is 0.
        try:
            decoded = read_column(file, chunk, leaf)
        except ValueError:
            decoded = None
        per_page = [
            [t.rep for t in decoded.triples if t.page == i] if decoded else [] for i in range(len(walked))
        ]
        firsts = first_rows(per_page)
        group_start = row
        for i, p in enumerate(walked):
            starts = sum(1 for x in per_page[i] if x == 0) if decoded else None
            data_page = (
                next((d for d in decoded.pages if d.page.header_span == p.header_span), None)
                if decoded
                else None
            )
            first_row = group_start + firsts[i]
            row += starts or 0
            s = p.statistics
            v = p.v2
            not_dictionary = p.page_type != "DICTIONARY_PAGE"
            out.append(
                {
                    "row_group": g,
                    "index": i,
                    "type": p.page_type,
                    "span": p.span(),
                    "header": p.header_span,
                    "body": p.body_span,
                    "compressed_page_size": p.compressed_page_size,
                    "uncompressed_page_size": p.uncompressed_page_size,
                    "num_values": p.num_values,
                    "encoding": p.encoding,
                    "statistics": {
                        "min": stat(chunk, s.min_value),
                        "max": stat(chunk, s.max_value),
                        "null_count": s.null_count,
                    }
                    if s
                    else None,
                    "crc": p.crc,
                    "crc_ok": p.crc_ok,
                    "v2": {
                        "num_nulls": v.num_nulls,
                        "num_rows": v.num_rows,
                        "definition_levels_byte_length": v.definition_levels_byte_length,
                        "repetition_levels_byte_length": v.repetition_levels_byte_length,
                        "is_compressed": v.is_compressed,
                    }
                    if v
                    else None,
                    "repetition_levels": data_page.rep_levels[0]
                    if data_page and data_page.rep_levels
                    else None,
                    "definition_levels": data_page.def_levels[0]
                    if data_page and data_page.def_levels
                    else None,
                    "values": data_page.values if data_page else None,
                    "first_row": first_row if starts is not None and not_dictionary else None,
                    "rows_started": starts if not_dictionary else None,
                }
            )
    return {"ok": True, "columns": columns, "column": column, "path": leaf.dotted_path(), "pages": out}


def compression(file: bytes, column: int, page: int | None) -> dict:
    """Ch07's experiment: what compression did to every column chunk, and how one page of one
    column was decompressed, token by token.

    The sizes come from the footer, so they are reported for every codec. The tokens need a
    decoder, so a page compressed with a codec :mod:`parquet_lab.compress` does not decode
    reports why instead of tokens.
    """
    found = _leaf(file, column)
    if isinstance(found, dict):
        return found
    md, _, all_leaves, leaf = found
    # Every column chunk's two sizes, summed over the row groups.
    chunks = []
    for other in all_leaves:
        cs = [rg.columns[other.column] for rg in md.row_groups]
        chunks.append(
            {
                "column": other.column,
                "path": other.dotted_path(),
                "codec": cs[0].codec if cs else None,
                "uncompressed": sum(c.total_uncompressed_size for c in cs),
                "compressed": sum(c.total_compressed_size for c in cs),
            }
        )
    if not md.row_groups:
        return {"ok": False, "error": "the file has no row groups"}
    chunk = md.row_groups[0].columns[leaf.column]
    r = chunk.byte_range()
    if r.end > len(file):
        return {"ok": False, "error": f"column chunk {r} is past the end of the file"}
    try:
        walked = walk_pages(file[r.start : r.end], r.start)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    # What the codec was given: the whole body, or in a version 2 data page only the values, and
    # only when the header says they are compressed.
    sections = []
    for p in walked:
        if p.v2:
            levels_len = p.v2.repetition_levels_byte_length + p.v2.definition_levels_byte_length
            levels_len = min(max(levels_len, 0), p.body_span.length)
            sections.append(
                (
                    Span(p.body_span.start + levels_len, p.body_span.end),
                    p.uncompressed_page_size - levels_len,
                    p.v2.is_compressed,
                )
            )
        else:
            sections.append((p.body_span, p.uncompressed_page_size, True))
    if page is None:
        page = next((i for i, p in enumerate(walked) if p.page_type != "DICTIONARY_PAGE"), 0)
    listed = [
        {
            "index": i,
            "type": p.page_type,
            "span": p.span(),
            "header": p.header_span,
            "compressed_section": section,
            "section_compressed": is_compressed,
            "compressed_page_size": p.compressed_page_size,
            "uncompressed_page_size": p.uncompressed_page_size,
            "section_uncompressed_size": size,
            "encoding": p.encoding,
        }
        for i, (p, (section, size, is_compressed)) in enumerate(zip(walked, sections, strict=True))
    ]
    if 0 <= page < len(walked):
        section, size, is_compressed = sections[page]
        codec = chunk.codec if is_compressed else "UNCOMPRESSED"
        try:
            d = decompress(codec, file[section.start : section.end], section.start, max(size, 0))
            decoded = {
                "ok": True,
                "codec": codec,
                "bytes": hex(d.data),
                "tokens": [
                    {
                        "kind": t.kind,
                        "label": t.label,
                        "input": t.input,
                        "output": t.output,
                        "distance": t.distance,
                        "detail": t.detail,
                    }
                    for t in d.tokens
                ],
            }
        except ValueError as e:
            decoded = {"ok": False, "codec": codec, "error": str(e)}
    else:
        decoded = {"ok": False, "error": f"the column chunk has no page {page}"}
    return {
        "ok": True,
        "file_size": len(file),
        "chunks": chunks,
        "column": column,
        "path": leaf.dotted_path(),
        "codec": chunk.codec,
        "supported": supported(chunk.codec),
        "pages": listed,
        "page": page,
        "decompressed": decoded,
    }


def _stat_display(leaf, data: bytes) -> str:
    shown = logical.interpret(leaf.physical_type, leaf.logical_type, data) if leaf.logical_type else None
    return shown or plain_scalar(leaf.physical_type, data) or hex(data)


def _all_null(reason: str, null_count: int | None, num_values: int) -> str:
    """A chunk whose every value is null has no minimum or maximum, and that is not a gap in the
    statistics: the null count says everything a reader needs."""
    if null_count is not None and null_count == num_values and null_count > 0:
        return (
            "every value is null, so there is no minimum or maximum; the null count alone rules the "
            "chunk out for any comparison with a value"
        )
    return reason


def statistics(file: bytes, row_group: int, column: int) -> dict:
    """Ch08's experiment: every column chunk's statistics, whether the reader may use them and
    why, and for one chunk every field, the values in the column's order, and what a mistaken
    order would have made of them."""
    md = _open(file)
    if isinstance(md, str):
        return {"ok": False, "error": md}
    try:
        root = build(md.schema)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    found = leaves(root)

    def comparator_of(leaf):
        return Comparator.for_leaf(leaf, md.schema[leaf.element].converted_type)

    def type_order(leaf) -> bool:
        o = md.column_orders
        return o is not None and leaf.column < len(o) and o[leaf.column] == "TYPE_ORDER"

    def verdict_of(c, cmp, leaf):
        if c.statistics is None:
            return "the column chunk has no statistics"
        try:
            return stats_bounds(c.statistics, cmp, type_order(leaf))
        except ValueError as e:
            return _all_null(str(e), c.statistics.null_count, c.num_values)

    columns = []
    for leaf in found:
        cmp = comparator_of(leaf)
        chunks = []
        for g, rg in enumerate(md.row_groups):
            c = rg.columns[leaf.column]
            null_count = c.statistics.null_count if c.statistics else None
            v = verdict_of(c, cmp, leaf)
            if isinstance(v, str):
                chunks.append(
                    {
                        "row_group": g,
                        "usable": False,
                        "reason": v,
                        "null_count": null_count,
                        "num_rows": rg.num_rows,
                    }
                )
            else:
                chunks.append(
                    {
                        "row_group": g,
                        "usable": True,
                        "min": _stat_display(leaf, v.min),
                        "max": _stat_display(leaf, v.max),
                        "source": v.source,
                        "null_count": null_count,
                        "num_rows": rg.num_rows,
                    }
                )
        lt = md.schema[leaf.element].logical_type
        columns.append(
            {
                "column": leaf.column,
                "path": leaf.dotted_path(),
                "type": physical_word(leaf.physical_type, leaf.type_length),
                "logical": str(lt) if lt else None,
                "order": cmp.order(),
                "comparator": cmp.description,
                "chunks": chunks,
            }
        )
    row_groups = [
        {
            "index": g,
            "num_rows": rg.num_rows,
            "total_byte_size": rg.total_byte_size,
            "sorting_columns": [
                {
                    "column": s.column,
                    "path": found[max(s.column, 0)].dotted_path() if max(s.column, 0) < len(found) else None,
                    "descending": s.descending,
                    "nulls_first": s.nulls_first,
                }
                for s in rg.sorting_columns
            ],
        }
        for g, rg in enumerate(md.row_groups)
    ]
    if not (0 <= column < len(found) and 0 <= row_group < len(md.row_groups)):
        return {"ok": False, "error": f"no column {column} in row group {row_group}"}
    leaf = found[column]
    chunk = md.row_groups[row_group].columns[leaf.column]
    cmp = comparator_of(leaf)
    # Every field of the Statistics struct the footer has, with the bytes that hold its value.
    fields = []
    s = chunk.statistics
    if s is not None:
        for name, data, span in (
            ("min_value", s.min_value, s.min_span),
            ("max_value", s.max_value, s.max_span),
            ("min", s.min, s.min_deprecated_span),
            ("max", s.max, s.max_deprecated_span),
        ):
            if data is not None and span is not None:
                fields.append(
                    {"name": name, "span": span, "hex": hex(data), "value": _stat_display(leaf, data)}
                )
        for name, v in (
            ("null_count", s.null_count),
            ("distinct_count", s.distinct_count),
            ("is_min_value_exact", s.is_min_value_exact),
            ("is_max_value_exact", s.is_max_value_exact),
        ):
            if v is not None:
                shown = str(v).lower() if isinstance(v, bool) else str(v)
                fields.append({"name": name, "span": s.span, "hex": None, "value": shown})
    verdict = verdict_of(chunk, cmp, leaf)
    # The values themselves, decoded, and what each order makes of them.
    try:
        triples = read_column(file, chunk, leaf).triples
        values = [plain.to_plain_bytes(t.value, leaf.physical_type) for t in triples if t.value is not None]
        nulls = sum(1 for t in triples if t.value is None)
    except ValueError:
        values, nulls = None, 0
    values_json = None
    if values is not None:
        placed = sorted(
            (v for v in values if cmp.compare(v, v) is not None),
            key=cmp_to_key(lambda a, b: cmp.compare(a, b) or 0),
        )

        def pair(c):
            found_pair = c.min_max(values)
            if found_pair is None:
                return None
            return {"min": _stat_display(leaf, found_pair[0]), "max": _stat_display(leaf, found_pair[1])}

        mistake = cmp.mistake()
        values_json = {
            "sorted": [_stat_display(leaf, v) for v in placed],
            "unplaced": len(values) - len(placed),
            "nulls": nulls,
            "observed": pair(cmp),
            "mistake": {"comparator": mistake[0].description, "what": mistake[1], "result": pair(mistake[0])}
            if mistake
            else None,
        }
    return {
        "ok": True,
        "created_by": md.created_by,
        "column_orders": md.column_orders is not None,
        "row_groups": row_groups,
        "columns": columns,
        "selected": {
            "row_group": row_group,
            "column": column,
            "path": leaf.dotted_path(),
            "order": cmp.order(),
            "comparator": cmp.description,
            "statistics_span": s.span if s else None,
            "fields": fields,
            "verdict": {"usable": False, "reason": verdict}
            if isinstance(verdict, str)
            else {
                "usable": True,
                "source": verdict.source,
                "min": _stat_display(leaf, verdict.min),
                "max": _stat_display(leaf, verdict.max),
                "min_exact": verdict.min_exact,
                "max_exact": verdict.max_exact,
            },
            "values": values_json,
        },
    }


OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"]
"""The comparisons :func:`skipping` accepts, in the order the browser numbers them."""


def skipping(file: bytes, column: int, op: str, value: str, mechanisms: int) -> dict:
    """Ch09's experiment: a condition on one column, and what the reader skips to answer
    ``SELECT *`` with it. ``mechanisms`` is a bit set: 1 row group statistics, 2 Bloom filters,
    4 the page index."""
    md = _open(file)
    if isinstance(md, str):
        return {"ok": False, "error": md}
    try:
        root = build(md.schema)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    found = leaves(root)
    flat = [leaf for leaf in found if leaf.max_repetition_level == 0]
    columns = [
        {
            "column": leaf.column,
            "path": leaf.dotted_path(),
            "type": physical_word(leaf.physical_type, leaf.type_length),
        }
        for leaf in flat
    ]

    def fail(e: str) -> dict:
        return {"ok": False, "error": e, "columns": columns}

    leaf = next((leaf for leaf in flat if leaf.column == column), None)
    if leaf is None:
        return fail(f"no column {column} that does not repeat")
    try:
        parsed = Op.parse(op)
        p = Predicate.new(leaf, md.schema[leaf.element].converted_type, parsed, value)
    except ValueError as e:
        return fail(str(e))
    use = Mechanisms(bool(mechanisms & 1), bool(mechanisms & 2), bool(mechanisms & 4))
    projection = [leaf.column for leaf in flat]
    try:
        pl = plan(file, md, leaf, p, projection, use)
        full = plan(file, md, leaf, p, projection, NO_MECHANISMS)
    except ValueError as e:
        return fail(str(e))
    # The answer, by reading everything: how many rows match, and in which row groups.
    matching = []
    for rg in md.row_groups:
        try:
            triples = read_column(file, rg.columns[leaf.column], leaf).triples
        except ValueError as e:
            return fail(str(e))
        matching.append(
            sum(
                1
                for t in triples
                if p.row_matches(
                    None if t.value is None else plain.to_plain_bytes(t.value, leaf.physical_type)
                )
            )
        )

    def path_of(c: int) -> str:
        return found[c].dotted_path() if 0 <= c < len(found) else ""

    groups = []
    for g in pl.row_groups:
        chunk = md.row_groups[g.index].columns[leaf.column]
        # For equality, the Bloom filter probe in full, whether or not it decided.
        probe = None
        if p.value is not None and p.op is Op.EQ and use.bloom:
            try:
                f = bloom.read(file, chunk)
            except ValueError:
                f = None
            if f is not None:
                pr = f.probe(p.value)
                probe = {
                    "hash": f"{pr.hash:016x}",
                    "block": pr.block,
                    "blocks": f.num_blocks(),
                    "block_span": f.block_span(pr.block),
                    "bits": [{"bit": b, "set": is_set} for b, is_set in pr.bits],
                    "may_contain": pr.may_contain,
                }
        groups.append(
            {
                "index": g.index,
                "num_rows": g.num_rows,
                "skipped": g.skipped,
                "matching": matching[g.index],
                "steps": [{"mechanism": m, "skip": d.skip, "why": d.why} for m, d in g.steps],
                "bloom": probe,
                "pages": [
                    {"span": q.span, "rows": list(q.rows), "skip": q.decision.skip, "why": q.decision.why}
                    for q in g.pages
                ],
                "rows": [list(r) for r in g.rows],
                "reads": [
                    {
                        "column": r.column,
                        "path": path_of(r.column),
                        "spans": r.spans,
                        "bytes": sum(s.length for s in r.spans),
                        "pages_read": r.pages_read,
                        "pages_total": r.pages_total,
                    }
                    for r in g.reads
                ],
                "index_bytes": g.index_bytes,
            }
        )
    condition = (
        f"{leaf.dotted_path()} {parsed.symbol} {value.strip()}"
        if p.value is not None
        else f"{leaf.dotted_path()} {parsed.symbol}"
    )
    return {
        "ok": True,
        "columns": columns,
        "column": column,
        "condition": condition,
        "mechanisms": {"statistics": use.statistics, "bloom": use.bloom, "page_index": use.page_index},
        "totals": {
            "rows": md.num_rows,
            "rows_read": pl.rows_read(),
            "rows_matching": sum(matching),
            "bytes_full_scan": full.bytes_read(),
            "bytes_read": pl.bytes_read(),
            "index_bytes": pl.index_bytes(),
        },
        "row_groups": groups,
    }


def flat_columns(file: bytes) -> list[int]:
    """The leaf columns that do not repeat: the ones ``scan`` can return."""
    md = open_bytes(file)
    return [leaf.column for leaf in leaves(build(md.schema)) if leaf.max_repetition_level == 0]


def scan(file: bytes, query: ScanQuery, strategy: Strategy, model: NetworkModel) -> dict:
    """Ch10's experiment: a query run against the file in the simulated object store, with every
    request, when it ran and on which connection, and the rows it returned."""
    try:
        md = open_bytes(file)
        columns = [
            {"column": leaf.column, "path": leaf.dotted_path()}
            for leaf in leaves(build(md.schema))
            if leaf.max_repetition_level == 0
        ]
    except (ValueError, StoreError) as e:
        return {"ok": False, "error": str(e)}
    try:
        r = run_scan(file, "data.parquet", query, strategy, model)
    except (ValueError, StoreError) as e:
        return {"ok": False, "error": str(e), "columns": columns}
    after = [q for q in r.requests if q.why.startswith(("read the indexes", "read the pages"))]
    try:
        footer_bytes = parse_trailer(file[-8:], len(file)).footer_length
        row_groups = len(md.row_groups)
    except ValueError:
        footer_bytes, row_groups = 0, 0
    return {
        "ok": True,
        "columns": columns,
        "file_size": len(file),
        "strategy": {
            "footer": _options(strategy.footer, model),
            "connections": strategy.connections,
            "coalesce_gap": strategy.coalesce_gap,
            "whole_chunks": strategy.whole_chunks,
            "statistics": strategy.mechanisms.statistics,
            "bloom": strategy.mechanisms.bloom,
            "page_index": strategy.mechanisms.page_index,
        },
        "totals": {
            "requests": len(r.requests),
            "elapsed_us": r.elapsed_us,
            "bytes_fetched": r.bytes_fetched,
            "bytes_planned": r.bytes_planned,
            "rows_decoded": r.rows_decoded,
            "rows_matching": len(r.matches),
            # What the query read once it had the footer: its indexes and pages.
            "requests_after_footer": len(after),
            "bytes_after_footer": sum(q.bytes_returned for q in after),
            "footer_bytes": footer_bytes,
            "row_groups": row_groups,
        },
        "requests": requests_json(r.requests),
        "result": {"columns": r.column_names, "rows": r.rows},
    }


def query(file: bytes, sql: str) -> dict:
    """Ch12's experiment: ``sql`` answered from ``file``, with every stage of the pipeline."""
    try:
        a = engine.run(file, sql)
    except (ValueError, StoreError) as e:
        return {"ok": False, "error": str(e)}
    return _answer_json(a)


def _answer_json(a) -> dict:
    return {
        "ok": True,
        "columns": a.columns,
        "rows": a.rows,
        "row_groups": a.row_groups,
        "row_groups_read": a.row_groups_read,
        "bytes_read": a.bytes_read,
        "stages": [
            {
                "name": s.name,
                "detail": s.detail,
                "rows_in": s.rows_in,
                "rows_out": s.rows_out,
                "columns": s.columns,
                "sample": s.sample,
            }
            for s in a.stages
        ],
    }


def _key_name(key_metadata: bytes) -> str:
    """The master key a key-metadata blob names, when it is JSON with a ``masterKeyID``, as
    pyarrow's is; otherwise its bytes as hex."""
    try:
        found = json.loads(key_metadata.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        found = None
    if isinstance(found, dict) and isinstance(found.get("masterKeyID"), str):
        return found["masterKeyID"]
    return hex(key_metadata)


def encryption(file: bytes) -> dict:
    """Ch13's experiment: what a reader without keys can see in a file, and what it cannot.
    Every "visible" item is something the reader decoded here; every "hidden" item is one it
    tried to read and could not."""

    def item(what: str, span: Span | None, value: str) -> dict:
        return {"what": what, "span": span, "value": value}

    visible, hidden, columns = [], [], []
    if len(file) >= 4 and file[:4] == crypto.MAGIC_ENCRYPTED:
        mode = "encrypted footer"
        try:
            f = crypto.encrypted_footer(file)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        visible.append(item("That it is Parquet, with an encrypted footer", Span(0, 4), "PARE"))
        visible.append(item("The encryption algorithm", f.crypto_metadata.span, f.algorithm))
        if f.key_metadata is not None:
            visible.append(item("The footer key's name", f.crypto_metadata.span, _key_name(f.key_metadata)))
        visible.append(item("The encrypted footer's size", f.module.span, f"{f.module.span.length} bytes"))
        for what in (
            "The schema",
            "The number of rows",
            "Where any column is",
            "Any statistics",
            "Any values, even of columns not encrypted",
        ):
            hidden.append(item(what, f.module.ciphertext, "inside the encrypted footer"))
    else:
        md = _open(file)
        if isinstance(md, str):
            return {"ok": False, "error": md}
        mode = "plaintext footer" if md.encryption_algorithm is not None else "not encrypted"
        if md.encryption_algorithm is not None:
            visible.append(item("The encryption algorithm", md.footer_signature, md.encryption_algorithm))
        if md.footer_signature is not None:
            visible.append(
                item(
                    "The footer's signature, which only the footer key can check",
                    md.footer_signature,
                    "28 bytes",
                )
            )
        try:
            found = leaves(build(md.schema))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        visible.append(item("The schema", None, ", ".join(leaf.dotted_path() for leaf in found)))
        visible.append(item("The number of rows", None, str(md.num_rows)))
        for leaf in found:
            chunks = [rg.columns[leaf.column] for rg in md.row_groups]
            if not chunks:
                continue
            first = chunks[0]
            path = leaf.dotted_path()
            key, sample, modules, error = None, [], 0, None
            if first.crypto is not None:
                c = first.crypto
                key = (
                    _key_name(c.key_metadata)
                    if c.key_metadata is not None and c.with_column_key
                    else "the footer key"
                )
                try:
                    modules = len(crypto.chunk_modules(file, first.byte_range()))
                except ValueError:
                    modules = 0
                try:
                    read_column(file, first, leaf)
                except ValueError as e:
                    error = str(e)
            else:
                try:
                    triples = read_column(file, first, leaf).triples[:4]
                    sample = [
                        None
                        if t.value is None
                        else logical.value_json(leaf.physical_type, leaf.logical_type, t.value)
                        for t in triples
                    ]
                except ValueError:
                    sample = []
            if key is None and md.encryption_algorithm is not None:
                shown = ", ".join(json_text(v) for v in sample)
                visible.append(item(f"The values of {path}", first.byte_range(), f"{shown}, …"))
                s = first.statistics
                if s is not None and s.min_value is not None and s.max_value is not None:
                    visible.append(
                        item(
                            f"The statistics of {path}",
                            s.span,
                            f"{_stat_display(leaf, s.min_value)} to {_stat_display(leaf, s.max_value)}",
                        )
                    )
            if key is not None:
                hidden.append(item(f"The values of {path}", first.byte_range(), error or ""))
                if first.statistics is None:
                    hidden.append(
                        item(
                            f"The statistics of {path}",
                            first.crypto.encrypted_metadata if first.crypto else None,
                            "withheld from the plaintext footer",
                        )
                    )
                visible.append(item(f"Which key protects {path}", None, key))
            columns.append(
                {
                    "path": path,
                    "encrypted": key is not None,
                    "key": key,
                    "span": first.byte_range(),
                    "statistics_visible": first.statistics is not None,
                    "modules": modules,
                    "sample": sample,
                }
            )
    return {"ok": True, "mode": mode, "visible": visible, "hidden": hidden, "columns": columns}


def table(
    objects: list[tuple[str, bytes]], sql: str, discovery, connections: int, model: NetworkModel
) -> dict:
    """Ch14's experiment: ``sql`` over the table under ``table/`` in a store holding ``objects``,
    with its files found by ``discovery``: every file considered, every request made, and the
    answer."""
    store = MemoryStore()
    for k, v in objects:
        store.put(k, v)
    try:
        a = table_query(store, "table/", sql, discovery, connections, model)
    except (ValueError, StoreError) as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "discovery": discovery.value,
        "files": [
            {
                "key": f.key,
                "partition": [f"{k}={v}" for k, v in f.partition],
                "size": f.size,
                "rows": f.stats.num_records if f.stats else None,
                "read": f.read,
                "why": f.why,
            }
            for f in a.files
        ],
        "requests": requests_json(a.requests),
        "totals": {
            "requests": len(a.requests),
            "elapsed_us": a.elapsed_us,
            "bytes_fetched": a.bytes_fetched,
            "files": len(a.files),
            "files_read": sum(1 for f in a.files if f.read),
        },
        "columns": a.answer.columns,
        "rows": a.answer.rows,
        "stages": [
            {"name": s.name, "detail": s.detail, "rows_in": s.rows_in, "rows_out": s.rows_out}
            for s in a.answer.stages
        ],
    }
