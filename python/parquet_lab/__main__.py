"""The Python reader on the command line: the same reports the labs draw, as JSON.

    PYTHONPATH=python python3 -m parquet_lab footer fixtures/tiny.parquet --size suffix --prefetch 65536
    PYTHONPATH=python python3 -m parquet_lab structure fixtures/tiny.parquet
    PYTHONPATH=python python3 -m parquet_lab interpret fixtures/tiny.parquet 629
    PYTHONPATH=python python3 -m parquet_lab schema fixtures/types.parquet
    PYTHONPATH=python python3 -m parquet_lab layouts --columns 2,3
    PYTHONPATH=python python3 -m parquet_lab scan fixtures/writing-baseline.parquet --where 0 = 431
    PYTHONPATH=python python3 -m parquet_lab query fixtures/writing-baseline.parquet "SELECT count(*) FROM orders"
    PYTHONPATH=python python3 -m parquet_lab table fixtures/table.json "SELECT count(*) FROM orders"

``pqlab``, the Rust reader's command line, takes the same commands and prints the same JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import report
from .object_store import NetworkModel
from .prune import Mechanisms, Op
from .reader import FooterOptions, Head, Known, SuffixRange
from .scan import Query, Strategy
from .table import Discovery

MECHANISMS = {"statistics": 1, "bloom": 2, "page-index": 4}


def mechanisms(text: str) -> int:
    """``statistics,bloom,page-index``, or any of them, as the bit set the reports take."""
    bits = 0
    for m in filter(None, text.split(",")):
        if m not in MECHANISMS:
            raise SystemExit(f"unknown mechanism {m}")
        bits |= MECHANISMS[m]
    return bits


def main() -> None:
    parser = argparse.ArgumentParser(prog="python3 -m parquet_lab", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    footer = sub.add_parser("footer", help="open a file through the simulated object store")
    footer.add_argument("file", type=Path)
    footer.add_argument("--size", choices=("head", "known", "suffix"), default="head")
    footer.add_argument("--prefetch", type=int, default=8)
    footer.add_argument(
        "--json", action="store_true", help="accepted for pqlab's sake; the output is always JSON"
    )
    scan = sub.add_parser("scan", help="a query through the simulated object store (ch10)")
    for p in (footer, layouts := sub.add_parser("layouts", help="ch01's two layouts"), scan):
        p.add_argument("--latency-us", type=int, default=NetworkModel().latency_us)
        p.add_argument("--bandwidth", type=int, default=NetworkModel().bandwidth_bytes_per_sec)
    layouts.add_argument("--columns", default="")
    layouts.add_argument("--row", type=int)
    sub.add_parser("structure", help="every region of a file").add_argument("file", type=Path)
    sub.add_parser("schema", help="the schema, flat and as a tree (ch03)").add_argument("file", type=Path)
    for name, what in (
        ("levels", "a column's levels, values and records (ch04)"),
        ("encodings", "how a column's values are encoded, step by step (ch05)"),
        ("pages", "every page of a column chunk (ch06)"),
        ("compression", "a column's pages decompressed, token by token (ch07)"),
    ):
        p = sub.add_parser(name, help=what)
        p.add_argument("file", type=Path)
        p.add_argument("column", type=int)
        if name == "compression":
            p.add_argument("page", type=int, nargs="?")
    stats = sub.add_parser(
        "statistics", help="a column chunk's statistics, and whether they are usable (ch08)"
    )
    stats.add_argument("file", type=Path)
    stats.add_argument("row_group", type=int)
    stats.add_argument("column", type=int)
    skip = sub.add_parser("skipping", help="what a condition lets the reader skip (ch09)")
    skip.add_argument("file", type=Path)
    skip.add_argument("column", type=int)
    skip.add_argument("op", help='a comparison, such as = or "is null"')
    skip.add_argument("value", nargs="?", default="")
    skip.add_argument("--use", default="statistics,bloom,page-index")
    scan.add_argument("file", type=Path)
    scan.add_argument("--where", nargs="+", metavar="COLUMN OP VALUE")
    scan.add_argument("--columns")
    scan.add_argument("--size", choices=("head", "suffix"), default="head")
    scan.add_argument("--prefetch", type=int, default=FooterOptions().prefetch)
    scan.add_argument("--connections", type=int, default=1)
    scan.add_argument("--gap", type=int)
    scan.add_argument("--chunks", action="store_true", help="read whole column chunks")
    scan.add_argument("--use", default="statistics,bloom,page-index")
    q = sub.add_parser("query", help="SQL answered by the tiny engine (ch12)")
    q.add_argument("file", type=Path)
    q.add_argument("sql")
    sub.add_parser("encryption", help="what a reader without keys can see (ch13)").add_argument(
        "file", type=Path
    )
    t = sub.add_parser("table", help="SQL over a table of files (ch14)")
    t.add_argument("listing", type=Path, help="the table's listing, such as fixtures/table.json")
    t.add_argument("sql")
    t.add_argument("--discovery", choices=("list", "prune", "log"), default="log")
    t.add_argument("--connections", type=int, default=4)
    c = sub.add_parser("changes", help="a changing table: scan, look up, or plan a compaction (ch15)")
    c.add_argument("listing", type=Path, help="the table's listing, such as fixtures/changes.json")
    c.add_argument("--snapshot", default="written")
    how = c.add_mutually_exclusive_group()
    how.add_argument("--lookup", type=int, metavar="ORDER_ID")
    how.add_argument("--compact", action="store_true")
    c.add_argument("--target-rows", type=int, default=200)
    c.add_argument("--small-rows", type=int, default=100)
    c.add_argument("--prefetch", type=int, default=0)
    c.add_argument("--connections", type=int, default=4)
    inspect = sub.add_parser("interpret", help="every reading of the bytes at an offset")
    inspect.add_argument("file", type=Path)
    inspect.add_argument("offset", type=int)
    a = parser.parse_args()

    if a.command == "footer":
        data = a.file.read_bytes()
        size = {"head": Head(), "known": Known(len(data)), "suffix": SuffixRange()}[a.size]
        model = NetworkModel(a.latency_us, a.bandwidth)
        out = report.footer_lab(data, a.file.name, FooterOptions(size, a.prefetch), model)
    elif a.command == "structure":
        out = report.structure(a.file.read_bytes())
    elif a.command == "schema":
        out = report.schema(a.file.read_bytes())
    elif a.command == "compression":
        out = report.compression(a.file.read_bytes(), a.column, a.page)
    elif a.command in ("levels", "encodings", "pages"):
        out = getattr(report, a.command)(a.file.read_bytes(), a.column)
    elif a.command == "statistics":
        out = report.statistics(a.file.read_bytes(), a.row_group, a.column)
    elif a.command == "skipping":
        out = report.skipping(a.file.read_bytes(), a.column, a.op, a.value, mechanisms(a.use))
    elif a.command == "scan":
        data = a.file.read_bytes()
        columns = [int(c) for c in a.columns.split(",")] if a.columns else report.flat_columns(data)
        condition = None
        if a.where:
            column, op, *value = a.where
            condition = (int(column), Op.parse(op), " ".join(value))
        bits = mechanisms(a.use)
        strategy = Strategy(
            FooterOptions(SuffixRange() if a.size == "suffix" else Head(), a.prefetch),
            a.connections,
            a.gap,
            a.chunks,
            Mechanisms(bool(bits & 1), bool(bits & 2), bool(bits & 4)),
        )
        model = NetworkModel(a.latency_us, a.bandwidth)
        out = report.scan(data, Query(columns, condition), strategy, model)
    elif a.command == "query":
        out = report.query(a.file.read_bytes(), a.sql)
    elif a.command == "encryption":
        out = report.encryption(a.file.read_bytes())
    elif a.command == "table":
        listing = json.loads(a.listing.read_text())
        objects = [(o["key"], (a.listing.parent / o["key"]).read_bytes()) for o in listing["objects"]]
        discovery = {"list": Discovery.LIST, "prune": Discovery.LIST_AND_PRUNE, "log": Discovery.LOG}[
            a.discovery
        ]
        out = report.table(objects, a.sql, discovery, a.connections, NetworkModel())
    elif a.command == "changes":
        listing = json.loads(a.listing.read_text())
        objects = [(o["key"], (a.listing.parent / o["key"]).read_bytes()) for o in listing["objects"]]
        if a.lookup is not None:
            op = ("lookup", a.lookup)
        elif a.compact:
            op = ("compact", a.target_rows, a.small_rows)
        else:
            op = ("scan",)
        out = report.changes(objects, a.snapshot, op, a.prefetch, a.connections, NetworkModel())
    elif a.command == "interpret":
        out = report.interpret(a.file.read_bytes(), a.offset)
    else:
        mask = sum(1 << int(c) for c in a.columns.split(",") if c)
        out = report.layouts(mask, a.row, NetworkModel(a.latency_us, a.bandwidth))
    print(json.dumps(report.jsonable(out), indent=2, ensure_ascii=False))


main()
