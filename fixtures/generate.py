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
)


def write(fixture: Fixture) -> bytes:
    sink = io.BytesIO()
    pq.write_table(fixture.table, sink, **{**BASE_OPTIONS, **fixture.options})
    return sink.getvalue()


def _stat(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


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
        "rows": fixture.table.to_pylist(),
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
            "Schema:",
            "",
            "| Column | Arrow type | Nullable | Parquet physical type | Encodings | Codec |",
            "|---|---|---|---|---|---|",
        ]
        first = m["row_groups"][0]["columns"]
        for s, c in zip(m["schema"], first, strict=True):
            out.append(
                f"| `{s['name']}` | {s['type']} | {s['nullable']} | {c['physical_type']} | "
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
