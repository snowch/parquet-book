#!/usr/bin/env python3
"""Write the book's Parquet fixtures, and the manifest that describes each one.

    python3 fixtures/generate.py            # write every fixture, manifest and README.md
    python3 fixtures/generate.py --check    # fail if a committed file differs from a fresh write

Every fixture is written by a production implementation (pyarrow, pinned in
``requirements.txt``), never by this repository's own code. That is the point of a fixture: the
book's reader is tested against files it did not write.

Each fixture has two committed companions:

- ``<name>.json``, the **manifest**. What pyarrow says about the file it wrote: sizes, offsets,
  encodings, statistics, and the footer length. The Rust tests compare the teaching
  implementation against it, so the manifest is an oracle that owes nothing to the code it
  checks.
- a section of ``README.md``, generated from the same table, so the documentation of a fixture
  cannot drift from the fixture.

Writes are deterministic for a given pyarrow version: the same table and the same options give
the same bytes. ``--check`` relies on that. A different pyarrow version writes a different
``created_by`` string and so different bytes, which is why the version is pinned and why the
check refuses to run under any other version rather than reporting a false difference.
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import hashlib
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent

#: The pyarrow version the committed bytes were written by. A fixture's bytes depend on it.
PINNED_PYARROW = "25.0.1"

SALES = pa.schema(
    [
        pa.field("order_id", pa.int64(), nullable=False),
        pa.field("country", pa.string(), nullable=False),
        pa.field("amount_cents", pa.int64(), nullable=False),
    ]
)


@dataclass(frozen=True)
class Fixture:
    name: str
    why: str
    table: pa.Table
    #: Passed to ``pyarrow.parquet.write_table`` as written, and printed in the README.
    options: dict = field(default_factory=dict)


#: Options every fixture starts from. Each is chosen to keep a file small enough to read byte by
#: byte, and each fixture that needs something else says so in its own ``options``.
BASE_OPTIONS = {
    "compression": "none",
    "use_dictionary": False,
    "write_statistics": True,
    # Without this pyarrow adds an ``ARROW:schema`` key-value entry: a base64 Arrow schema that
    # is larger than everything else in a tiny footer put together.
    "store_schema": False,
    "data_page_version": "1.0",
    "write_page_index": False,
}

#: One column for each physical type the book discusses, and the common logical types on top of
#: them. Two columns are nullable and one is a group, so the schema has all three repetitions'
#: effects on levels and a path with a dot in it.
TYPES = pa.schema(
    [
        pa.field("is_paid", pa.bool_(), nullable=False),
        pa.field("quantity", pa.int8(), nullable=False),
        pa.field("store_id", pa.uint16(), nullable=False),
        pa.field("order_id", pa.int64(), nullable=False),
        pa.field("weight_kg", pa.float32(), nullable=False),
        pa.field("amount", pa.decimal128(9, 2), nullable=False),
        pa.field("country", pa.string(), nullable=True),
        pa.field("order_date", pa.date32(), nullable=False),
        pa.field("paid_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field(
            "shipping",
            pa.struct([pa.field("city", pa.string()), pa.field("postcode", pa.string())]),
            nullable=True,
        ),
    ]
)

#: Orders with a nullable string, a list of strings, and a list of structs that each hold a list:
#: the shape the Dremel paper's levels were designed for.
NESTED = pa.schema(
    [
        pa.field("order_id", pa.int64(), nullable=False),
        pa.field("email", pa.string()),
        pa.field("tags", pa.list_(pa.string())),
        pa.field(
            "items",
            pa.list_(pa.struct([pa.field("sku", pa.string()), pa.field("discounts", pa.list_(pa.int32()))])),
        ),
    ]
)

FIXTURES = (
    Fixture(
        name="tiny",
        why=(
            "The smallest useful file: four rows of a sales table, one row group, no "
            "compression, no dictionary, every column required so no levels are stored. "
            "Small enough to read completely by eye. The footer laboratory starts here."
        ),
        table=pa.table(
            {
                "order_id": [1, 2, 3, 4],
                "country": ["UK", "SE", "UK", "PL"],
                "amount_cents": [1999, 500, 4210, 1250],
            },
            schema=SALES,
        ),
    ),
    Fixture(
        name="multiple-row-groups",
        why=(
            "The same sales schema split into row groups of two rows. The footer now "
            "describes several row groups, each with its own column chunks and statistics, "
            "so the structure view has more than one branch."
        ),
        table=pa.table(
            {
                "order_id": [1, 2, 3, 4, 5, 6],
                "country": ["UK", "SE", "UK", "PL", "SE", "UK"],
                "amount_cents": [1999, 500, 4210, 1250, 875, 3000],
            },
            schema=SALES,
        ),
        options={"row_group_size": 2},
    ),
    Fixture(
        name="types",
        why=(
            "Three orders with a column for each physical type and the common logical types: "
            "a signed and an unsigned small integer, a decimal, a date, a UTC timestamp, a "
            "nullable string and an optional group. The same bytes mean different values "
            "depending on the logical type the schema gives them, which is ch03's subject."
        ),
        table=pa.table(
            {
                "is_paid": [True, False, True],
                "quantity": [1, 3, 2],
                "store_id": [7, 65000, 12],
                "order_id": [1, 2, 3],
                "weight_kg": [0.5, 1.25, 2.0],
                "amount": [decimal.Decimal("19.99"), decimal.Decimal("5.00"), decimal.Decimal("42.10")],
                "country": ["UK", None, "PL"],
                "order_date": [
                    datetime.date(2026, 1, 3),
                    datetime.date(2026, 1, 4),
                    datetime.date(2026, 1, 5),
                ],
                "paid_at": [
                    datetime.datetime(2026, 1, 3, 9, 30, tzinfo=datetime.UTC),
                    datetime.datetime(2026, 1, 4, 17, 5, tzinfo=datetime.UTC),
                    datetime.datetime(2026, 1, 5, 0, 0, tzinfo=datetime.UTC),
                ],
                "shipping": [
                    {"city": "Leeds", "postcode": "LS1"},
                    None,
                    {"city": "Kraków", "postcode": None},
                ],
            },
            schema=TYPES,
        ),
    ),
    Fixture(
        name="nested",
        why=(
            "Four orders whose fields are missing in every way a nested value can be: a null "
            "string, a null list, an empty list, a list holding a null, and a list of structs "
            "each holding a list of its own. Every column stores repetition and definition "
            "levels, which is ch04's subject."
        ),
        table=pa.Table.from_pylist(
            [
                {
                    "order_id": 1,
                    "email": "ann@example.com",
                    "tags": ["gift", "express"],
                    "items": [{"sku": "A1", "discounts": [5, 10]}, {"sku": "B2", "discounts": []}],
                },
                {"order_id": 2, "email": None, "tags": [], "items": []},
                {
                    "order_id": 3,
                    "email": "cat@example.com",
                    "tags": None,
                    "items": [{"sku": "C3", "discounts": [7]}],
                },
                {"order_id": 4, "email": "dan@example.com", "tags": ["sale", None], "items": None},
            ],
            schema=NESTED,
        ),
    ),
    Fixture(
        name="dictionary",
        why=(
            "Twelve orders written with dictionary encoding, the writer's default. Each column "
            "chunk starts with a dictionary page of its distinct values, and its data page "
            "holds small indices into it, packed with the RLE / bit-packing hybrid."
        ),
        table=pa.table(
            {
                "order_id": list(range(1, 13)),
                "country": ["UK", "SE", "UK", "PL", "UK", "US", "SE", "UK", "UK", "PL", "UK", "SE"],
                "amount_cents": [1999, 500, 4210, 1250, 875, 3000, 640, 2275, 1999, 500, 1250, 875],
            },
            schema=SALES,
        ),
        options={"use_dictionary": True},
    ),
    Fixture(
        name="encodings",
        why=(
            "Forty orders with one column per encoding a writer uses instead of a dictionary: "
            "DELTA_BINARY_PACKED for increasing integers, DELTA_LENGTH_BYTE_ARRAY and "
            "DELTA_BYTE_ARRAY for strings, and BYTE_STREAM_SPLIT for floats. Each column's "
            "values were chosen to suit its encoding."
        ),
        table=pa.table(
            {
                "order_id": pa.array(range(1001, 1041), pa.int64()),
                "ordered_at": pa.array([1767432600 + 60 * i + (i % 3) for i in range(40)], pa.int64()),
                "sku": pa.array([f"SKU-{(i * 7) % 13:03d}" for i in range(40)], pa.string()),
                "url": pa.array([f"https://shop.example/p/{100 + i}" for i in range(40)], pa.string()),
                "weight_kg": pa.array([round(0.25 + 0.05 * i, 2) for i in range(40)], pa.float32()),
            },
            schema=pa.schema(
                [
                    pa.field("order_id", pa.int64(), nullable=False),
                    pa.field("ordered_at", pa.int64(), nullable=False),
                    pa.field("sku", pa.string(), nullable=False),
                    pa.field("url", pa.string(), nullable=False),
                    pa.field("weight_kg", pa.float32(), nullable=False),
                ]
            ),
        ),
        options={
            "column_encoding": {
                "order_id": "DELTA_BINARY_PACKED",
                "ordered_at": "DELTA_BINARY_PACKED",
                "sku": "DELTA_LENGTH_BYTE_ARRAY",
                "url": "DELTA_BYTE_ARRAY",
                "weight_kg": "BYTE_STREAM_SPLIT",
            }
        },
    ),
)


def write(fixture: Fixture) -> bytes:
    sink = io.BytesIO()
    pq.write_table(fixture.table, sink, **{**BASE_OPTIONS, **fixture.options})
    return sink.getvalue()


def _stat(value):
    """A value pyarrow returned, as JSON can hold it: text for anything that is not a number."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {k: _stat(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stat(v) for v in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def manifest(fixture: Fixture, data: bytes) -> dict:
    """What pyarrow reports about the bytes it wrote. Nothing here is computed by this book."""
    md = pq.ParquetFile(io.BytesIO(data)).metadata
    row_groups = []
    for i in range(md.num_row_groups):
        rg = md.row_group(i)
        columns = []
        for j in range(rg.num_columns):
            c = rg.column(j)
            stats = c.statistics
            columns.append(
                {
                    "path": c.path_in_schema,
                    "physical_type": c.physical_type,
                    "compression": c.compression,
                    "encodings": sorted(c.encodings),
                    "num_values": c.num_values,
                    "data_page_offset": c.data_page_offset,
                    "dictionary_page_offset": c.dictionary_page_offset,
                    "total_compressed_size": c.total_compressed_size,
                    "total_uncompressed_size": c.total_uncompressed_size,
                    "statistics": None
                    if stats is None
                    else {
                        "min": _stat(stats.min),
                        "max": _stat(stats.max),
                        "null_count": stats.null_count,
                    },
                }
            )
        row_groups.append(
            {"num_rows": rg.num_rows, "total_byte_size": rg.total_byte_size, "columns": columns}
        )
    return {
        "name": fixture.name,
        "file": f"{fixture.name}.parquet",
        "why": fixture.why,
        "generator": {
            "script": "fixtures/generate.py",
            "writer": f"pyarrow {pa.__version__}",
            "options": {**BASE_OPTIONS, **fixture.options},
        },
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "footer_length": md.serialized_size,
        "created_by": md.created_by,
        "format_version": md.format_version,
        "num_rows": md.num_rows,
        "num_columns": md.num_columns,
        "num_row_groups": md.num_row_groups,
        "schema": [
            {"name": f.name, "type": str(f.type), "nullable": f.nullable} for f in fixture.table.schema
        ],
        # pyarrow's own reading of the Parquet schema: one entry per leaf column.
        "leaves": [
            {
                "path": md.schema.column(i).path,
                "physical_type": md.schema.column(i).physical_type,
                "logical_type": str(md.schema.column(i).logical_type),
                "converted_type": md.schema.column(i).converted_type,
                "max_definition_level": md.schema.column(i).max_definition_level,
                "max_repetition_level": md.schema.column(i).max_repetition_level,
            }
            for i in range(md.num_columns)
        ],
        "rows": [{k: _stat(v) for k, v in row.items()} for row in fixture.table.to_pylist()],
        "row_groups": row_groups,
    }


def readme(manifests: list[dict]) -> str:
    out = [
        "# Fixtures",
        "",
        "Generated by `fixtures/generate.py`. Do not edit this file or the fixtures by hand:",
        "change the generator and run `make fixtures`. `make check` fails if a committed file",
        "differs from what the generator writes.",
        "",
        "Every fixture is written by pyarrow, a production Parquet implementation, and never by",
        "this repository's own code. The `.json` beside each file is pyarrow's own description of",
        "it, and the Rust tests use it as an oracle.",
        "",
    ]
    for m in manifests:
        out += [f"## `{m['file']}`", "", m["why"], ""]
        out += [
            "| | |",
            "|---|---|",
            f"| Written by | {m['generator']['writer']} (`{m['generator']['script']}`) |",
            f"| Size | {m['file_size']} bytes |",
            f"| Rows | {m['num_rows']} |",
            f"| Row groups | {m['num_row_groups']} |",
            f"| Footer length | {m['footer_length']} bytes |",
            f"| SHA-256 | `{m['sha256'][:16]}…` |",
            "",
            "Leaf columns, as pyarrow reads the Parquet schema:",
            "",
            "| Column | Physical type | Logical type | Max def | Max rep | Encodings | Codec |",
            "|---|---|---|--:|--:|---|---|",
        ]
        first = m["row_groups"][0]["columns"]
        for leaf, c in zip(m["leaves"], first, strict=True):
            out.append(
                f"| `{leaf['path']}` | {leaf['physical_type']} | {leaf['logical_type']} | "
                f"{leaf['max_definition_level']} | {leaf['max_repetition_level']} | "
                f"{', '.join(c['encodings'])} | {c['compression']} |"
            )
        out += ["", "Writer options:", "", "```python"]
        out += [f"{k}={v!r}" for k, v in m["generator"]["options"].items()]
        out += ["```", ""]
    return "\n".join(out)


def outputs() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    manifests = []
    for fixture in FIXTURES:
        data = write(fixture)
        m = manifest(fixture, data)
        manifests.append(m)
        files[HERE / m["file"]] = data
        files[HERE / f"{fixture.name}.json"] = (json.dumps(m, indent=2) + "\n").encode()
    files[HERE / "README.md"] = readme(manifests).encode()
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args()
    if pa.__version__ != PINNED_PYARROW:
        print(
            f"pyarrow {pa.__version__} is installed; the fixtures were written by "
            f"{PINNED_PYARROW}. A different writer writes different bytes, so this refuses "
            "rather than report a difference that is only a version string.",
            file=sys.stderr,
        )
        return 2
    stale = []
    for path, data in outputs().items():
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                stale.append(path.relative_to(HERE.parent))
        else:
            path.write_bytes(data)
            print(f"wrote {path.relative_to(HERE.parent)} ({len(data)} bytes)")
    if stale:
        print("stale fixtures (run `make fixtures` and commit):", file=sys.stderr)
        for path in stale:
            print(f"  {path}", file=sys.stderr)
        return 1
    if args.check:
        print(f"  {len(FIXTURES)} fixtures match their generator")
    return 0


if __name__ == "__main__":
    sys.exit(main())
