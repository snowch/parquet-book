"""The Python reader on the command line: the same reports the labs draw, as JSON.

    PYTHONPATH=python python3 -m parquet_lab footer fixtures/tiny.parquet --size suffix --prefetch 65536
    PYTHONPATH=python python3 -m parquet_lab structure fixtures/tiny.parquet
    PYTHONPATH=python python3 -m parquet_lab interpret fixtures/tiny.parquet 629
    PYTHONPATH=python python3 -m parquet_lab schema fixtures/types.parquet
    PYTHONPATH=python python3 -m parquet_lab layouts --columns 2,3

``pqlab``, the Rust reader's command line, takes the same commands and prints the same JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import report
from .object_store import NetworkModel
from .reader import FooterOptions, Head, Known, SuffixRange


def main() -> None:
    parser = argparse.ArgumentParser(prog="python3 -m parquet_lab", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    footer = sub.add_parser("footer", help="open a file through the simulated object store")
    footer.add_argument("file", type=Path)
    footer.add_argument("--size", choices=("head", "known", "suffix"), default="head")
    footer.add_argument("--prefetch", type=int, default=8)
    for p in (footer, layouts := sub.add_parser("layouts", help="ch01's two layouts")):
        p.add_argument("--latency-us", type=int, default=NetworkModel().latency_us)
        p.add_argument("--bandwidth", type=int, default=NetworkModel().bandwidth_bytes_per_sec)
    layouts.add_argument("--columns", default="")
    layouts.add_argument("--row", type=int)
    sub.add_parser("structure", help="every region of a file").add_argument("file", type=Path)
    sub.add_parser("schema", help="the schema, flat and as a tree (ch03)").add_argument("file", type=Path)
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
    elif a.command == "interpret":
        out = report.interpret(a.file.read_bytes(), a.offset)
    else:
        mask = sum(1 << int(c) for c in a.columns.split(",") if c)
        out = report.layouts(mask, a.row, NetworkModel(a.latency_us, a.bandwidth))
    print(json.dumps(report.plain(out), indent=2, ensure_ascii=False))


main()
