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
import base64
import datetime
import decimal
import hashlib
import io
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyarrow.parquet.encryption as pe

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
    #: When the table holds the same rows as another fixture's, in some order: that fixture's
    #: name. The manifest then lists the rows' ``order_id`` in file order instead of the rows.
    rows_same_as: str | None = None
    #: Modular encryption (ch13): pyarrow's ``EncryptionConfiguration`` arguments.
    encryption: dict | None = None


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

#: Sixty orders, enough to fill several small pages. Every seventh country is null.
PAGES_TABLE = pa.table(
    {
        "order_id": pa.array(range(1, 61), pa.int64()),
        "country": pa.array(
            [["UK", "SE", "PL", "US"][(i * 5) % 4] if i % 7 else None for i in range(60)], pa.string()
        ),
        "amount_cents": pa.array([(i * 37) % 5000 for i in range(60)], pa.int64()),
    },
    schema=pa.schema(
        [
            pa.field("order_id", pa.int64(), nullable=False),
            pa.field("country", pa.string(), nullable=True),
            pa.field("amount_cents", pa.int64(), nullable=False),
        ]
    ),
)

#: Small pages: the writer starts a new page after a few values, so each column chunk has several.
SMALL_PAGES = {"data_page_size": 128, "write_batch_size": 16, "use_dictionary": ["country"]}


def _orders(n: int) -> pa.Table:
    """``n`` orders with the kinds of columns a compressor meets: a counter, short repeated
    strings, codes from a small set, random integers, decimal-looking floats, noisy floats, and
    free text that is mostly empty."""
    x = 12345
    amounts, weights, distances = [], [], []
    for _ in range(n):
        # A linear congruential generator: the same "random" values on every machine.
        x = (x * 1103515245 + 12345) % 2**31
        amounts.append(100 + x % 9900)
        weights.append(round(0.2 + (x >> 8) % 3000 / 100, 2))
        distances.append(0.5 + 40 * x / 2**31)
    notes = ["", "gift wrap", "leave at door", "", "", ""]
    return pa.table(
        {
            "order_id": pa.array(range(1, n + 1), pa.int64()),
            "country": pa.array([["UK", "SE", "PL", "US", "DE"][(i * 7) % 5] for i in range(n)]),
            "sku": pa.array([f"SKU-{(i * 13) % 40:04d}" for i in range(n)]),
            "amount_cents": pa.array(amounts, pa.int64()),
            "weight_kg": pa.array(weights, pa.float64()),
            "distance_km": pa.array(distances, pa.float64()),
            "note": pa.array([notes[(i * 5) % 6] for i in range(n)]),
        },
        schema=pa.schema(
            [
                pa.field("order_id", pa.int64(), nullable=False),
                pa.field("country", pa.string(), nullable=False),
                pa.field("sku", pa.string(), nullable=False),
                pa.field("amount_cents", pa.int64(), nullable=False),
                pa.field("weight_kg", pa.float64(), nullable=False),
                pa.field("distance_km", pa.float64(), nullable=False),
                pa.field("note", pa.string(), nullable=False),
            ]
        ),
    )


#: Twelve orders in three row groups, each column chosen for a way statistics are misread (ch08):
#: unsigned integers above 2^31, negative small integers, strings with bytes above 0x7f, floats
#: with NaN and both zeros, negative decimals, a column null throughout one row group, and one
#: written without statistics.
STATISTICS_TABLE = pa.table(
    {
        "order_id": pa.array(range(1, 13), pa.int64()),
        "customer_id": pa.array(
            [7, 3_000_000_000, 42, 2_147_483_648, 15, 99, 4_000_000_000, 8, 1, 2, 3, 2_500_000_000],
            pa.uint32(),
        ),
        "delta": pa.array([-5, 3, -120, 7, 0, 9, -1, 100, 12, -3, 4, 5], pa.int8()),
        "city": pa.array(
            [
                "Leeds",
                "Łódź",
                "Zürich",
                "Aarhus",
                "Oslo",
                "Århus",
                "Bergen",
                "Écija",
                "Malmö",
                "York",
                "Ängelholm",
                "Cork",
            ]
        ),
        "temp_c": pa.array(
            [12.5, float("nan"), -3.0, 3.0, 0.0, -0.0, 20.0, float("nan"), 7.5, 1.0, 2.0, 4.5],
            pa.float64(),
        ),
        "amount": pa.array(
            [
                decimal.Decimal(v)
                for v in (
                    "19.99",
                    "-5.00",
                    "42.10",
                    "-0.50",
                    "7.25",
                    "3.00",
                    "-19.99",
                    "0.01",
                    "12.00",
                    "-100.00",
                    "8.40",
                    "1.10",
                )
            ],
            pa.decimal128(9, 2),
        ),
        "coupon": pa.array(
            ["SPRING", None, "SPRING", "WELCOME", None, None, None, None, "SUMMER", None, "SUMMER", None],
            pa.string(),
        ),
        "note": pa.array(
            ["gift", None, "", "leave at door", None, "gift", "", "", None, "fragile", "", "gift"],
            pa.string(),
        ),
    }
)


def _pruning_rows(n: int) -> list[dict]:
    """``n`` orders in order_id order, with random customers and amounts, and a country that is
    null for every eleventh order (ch09)."""
    x = 12345
    rows = []
    countries = ["UK", "SE", "PL", "US", "DE", "FR"]
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2**31
        rows.append(
            {
                "order_id": i + 1,
                "customer_id": 100_000 + x % 900_000,
                "country": countries[(i * 7) % 6] if i % 11 else None,
                "amount_cents": 100 + (x >> 8) % 9900,
            }
        )
    return rows


def _shuffled(rows: list) -> list:
    """The same rows in a fixed pseudo-random order: a Fisher-Yates shuffle driven by the same
    generator, so every machine shuffles alike."""
    order = list(range(len(rows)))
    y = 777
    for i in range(len(order) - 1, 0, -1):
        y = (y * 1103515245 + 12345) % 2**31
        j = y % (i + 1)
        order[i], order[j] = order[j], order[i]
    return [rows[k] for k in order]


PRUNING_SCHEMA = pa.schema(
    [
        pa.field("order_id", pa.int64(), nullable=False),
        pa.field("customer_id", pa.int64(), nullable=False),
        pa.field("country", pa.string()),
        pa.field("amount_cents", pa.int64(), nullable=False),
    ]
)
PRUNING_ROWS = _pruning_rows(800)

#: Four row groups of small pages, a page index, a dictionary for country, and a Bloom filter
#: for customer_id, whose values are nearly all distinct.
PRUNING_OPTIONS = {
    "use_dictionary": ["country"],
    "row_group_size": 200,
    "max_rows_per_page": 40,
    "write_page_index": True,
    "bloom_filter_options": {"customer_id": {"ndv": 200, "fpp": 0.05}},
}


def _writing_rows(n: int) -> list[dict]:
    """``n`` orders for ch11: increasing ids and times, random customers and amounts, a country
    that is usually UK, and a status that is usually paid."""
    x = 4242
    countries = ["UK", "UK", "UK", "SE", "PL", "US", "DE", "FR"]
    statuses = ["paid"] * 18 + ["refunded", "cancelled"]
    start = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    rows = []
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2**31
        rows.append(
            {
                "order_id": i + 1,
                "ordered_at": start + datetime.timedelta(seconds=97 * i + x % 60),
                "customer_id": 100_000 + x % 900_000,
                "country": countries[(x >> 4) % 8],
                "status": statuses[(x >> 9) % 20],
                "amount_cents": 100 + (x >> 12) % 9900,
            }
        )
    return rows


WRITING_SCHEMA = pa.schema(
    [
        pa.field("order_id", pa.int64(), nullable=False),
        pa.field("ordered_at", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("customer_id", pa.int64(), nullable=False),
        pa.field("country", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        pa.field("amount_cents", pa.int64(), nullable=False),
    ]
)
WRITING_ROWS = _writing_rows(800)

#: What ch11's files share: Snappy, a page index, row groups of 200 and pages of 40 rows. Each
#: variant changes one thing.
WRITING_OPTIONS = {
    "compression": "snappy",
    "use_dictionary": True,
    "row_group_size": 200,
    "max_rows_per_page": 40,
    "write_page_index": True,
}


def _writing(name: str, why: str, rows: list, **options) -> Fixture:
    return Fixture(
        name=f"writing-{name}",
        why=why,
        table=pa.Table.from_pylist(rows, schema=WRITING_SCHEMA),
        options={**WRITING_OPTIONS, **options},
        rows_same_as=None if name == "baseline" else "writing-baseline",
    )


#: Twelve orders with a column of personal data and a column of amounts to encrypt (ch13).
ENCRYPTION_TABLE = pa.table(
    {
        "order_id": pa.array(range(1, 13), pa.int64()),
        "country": pa.array(["UK", "SE", "UK", "PL", "UK", "US", "SE", "UK", "UK", "PL", "UK", "SE"]),
        "email": pa.array([f"customer{i}@example.com" for i in range(1, 13)]),
        "amount_cents": pa.array(
            [1999, 500, 4210, 1250, 875, 3000, 640, 2275, 1999, 500, 1250, 875], pa.int64()
        ),
    },
    schema=pa.schema(
        [
            pa.field("order_id", pa.int64(), nullable=False),
            pa.field("country", pa.string(), nullable=False),
            pa.field("email", pa.string(), nullable=False),
            pa.field("amount_cents", pa.int64(), nullable=False),
        ]
    ),
)

#: The same orders under every codec the format defines that pyarrow writes (ch07).
ORDERS = _orders(256)
CODECS = ("none", "snappy", "gzip", "lz4", "zstd", "brotli")


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
    Fixture(
        name="pages",
        why=(
            "Sixty orders written in small pages, so every column chunk holds several data "
            "pages, and the country column has a dictionary page in front of them and nulls "
            "in them. Data page version 1."
        ),
        table=PAGES_TABLE,
        options=SMALL_PAGES,
    ),
    Fixture(
        name="pages-v2",
        why=(
            "The same sixty orders in data page version 2, with a CRC-32 checksum in every page "
            "header. Compare its pages with pages.parquet's: the levels move out of the "
            "compressible section and each header counts its rows and nulls."
        ),
        table=PAGES_TABLE,
        options={**SMALL_PAGES, "data_page_version": "2.0", "write_page_checksum": True},
    ),
    *(
        Fixture(
            name=f"codec-{codec}",
            why=(
                f"256 orders, PLAIN-encoded with no dictionary, compressed with {codec}. The "
                "codec-* files hold identical pages before compression, so any difference in "
                "their sizes is the codec's."
            )
            if codec != "none"
            else (
                "256 orders, PLAIN-encoded with no dictionary and not compressed: the baseline "
                "the other codec-* files are measured against."
            ),
            table=ORDERS,
            options={"compression": codec},
        )
        for codec in CODECS
    ),
    Fixture(
        name="statistics",
        why=(
            "Twelve orders in three row groups, with a column for each way a reader can misread "
            "statistics: unsigned integers above 2^31, negative small integers, strings with "
            "non-ASCII bytes, floats with NaN and signed zeros, negative decimals, a column that "
            "is null throughout one row group, and a column written without statistics. The "
            "row groups declare that they are sorted by order_id."
        ),
        table=STATISTICS_TABLE,
        options={
            "row_group_size": 4,
            "write_statistics": ["order_id", "customer_id", "delta", "city", "temp_c", "amount", "coupon"],
            "sorting_columns": [pq.SortingColumn(0)],
        },
    ),
    Fixture(
        name="pruning-sorted",
        why=(
            "800 orders written in order_id order: four row groups of 200, pages of 40 rows, a "
            "page index for every column, and a Bloom filter for customer_id. Because the rows "
            "are sorted, each row group and page covers a narrow range of order_id, and a reader "
            "can skip most of the file for a query on it."
        ),
        table=pa.Table.from_pylist(PRUNING_ROWS, schema=PRUNING_SCHEMA),
        options=PRUNING_OPTIONS,
    ),
    Fixture(
        name="pruning-shuffled",
        why=(
            "The same 800 orders as pruning-sorted.parquet, shuffled, and written the same way. "
            "Every row group and page now covers nearly the whole range of order_id, and the "
            "statistics can rule out almost nothing."
        ),
        table=pa.Table.from_pylist(_shuffled(PRUNING_ROWS), schema=PRUNING_SCHEMA),
        options=PRUNING_OPTIONS,
    ),
    _writing(
        "baseline",
        "800 orders in order_id order, written the way ch11 starts from: Snappy, dictionary "
        "encoding, four row groups of 200, pages of 40 rows, and a page index. Every other "
        "writing-* file changes one of these.",
        WRITING_ROWS,
    ),
    _writing(
        "one-group",
        "writing-baseline.parquet in one row group of 800 rows.",
        WRITING_ROWS,
        row_group_size=800,
    ),
    _writing(
        "small-groups",
        "writing-baseline.parquet in row groups of 40 rows: twenty row groups, each with its own "
        "column chunks, statistics and page index.",
        WRITING_ROWS,
        row_group_size=40,
    ),
    _writing(
        "by-country",
        "writing-baseline.parquet's rows sorted by country, then order_id.",
        sorted(WRITING_ROWS, key=lambda r: (r["country"], r["order_id"])),
    ),
    _writing(
        "shuffled",
        "writing-baseline.parquet's rows in a pseudo-random order.",
        _shuffled(WRITING_ROWS),
    ),
    _writing(
        "plain",
        "writing-baseline.parquet without dictionary encoding.",
        WRITING_ROWS,
        use_dictionary=False,
    ),
    _writing(
        "no-index",
        "writing-baseline.parquet without a page index. pyarrow then writes each page's "
        "statistics into its page header instead.",
        WRITING_ROWS,
        write_page_index=False,
    ),
    Fixture(
        name="encrypted-footer",
        why=(
            "Twelve orders with modular encryption and an encrypted footer: the file ends in PARE. "
            "email is encrypted with the pii key and amount_cents with the finance key; order_id "
            "and country are not encrypted, but the footer that would say where they are is. "
            "Written once, since encryption is never byte-for-byte reproducible; the check "
            "decrypts it with the published test keys."
        ),
        table=ENCRYPTION_TABLE,
        encryption={
            "footer_key": "footer",
            "column_keys": {"pii": ["email"], "finance": ["amount_cents"]},
            "plaintext_footer": False,
            "encryption_algorithm": "AES_GCM_V1",
        },
    ),
    Fixture(
        name="plaintext-footer",
        why=(
            "The same orders and keys with a plaintext footer: the file ends in PAR1, the footer is "
            "readable and signed, and only the two encrypted columns' pages and details are hidden."
        ),
        table=ENCRYPTION_TABLE,
        encryption={
            "footer_key": "footer",
            "column_keys": {"pii": ["email"], "finance": ["amount_cents"]},
            "plaintext_footer": True,
            "encryption_algorithm": "AES_GCM_V1",
        },
    ),
    Fixture(
        name="pages-v2-snappy",
        why=(
            "pages-v2.parquet compressed with Snappy. In data page version 2 only a page's values "
            "are compressed: its levels stay as they were, so a reader can count rows and nulls "
            "without decompressing anything."
        ),
        table=PAGES_TABLE,
        options={
            **SMALL_PAGES,
            "data_page_version": "2.0",
            "write_page_checksum": True,
            "compression": "snappy",
        },
    ),
    Fixture(
        name="codec-zstd-split",
        why=(
            "codec-zstd.parquet with its two float columns written BYTE_STREAM_SPLIT. Comparing "
            "the two files measures what splitting a float's bytes is worth to a compressor, "
            "for decimal-looking floats and for noisy ones."
        ),
        table=ORDERS,
        options={
            "compression": "zstd",
            "column_encoding": {"weight_kg": "BYTE_STREAM_SPLIT", "distance_km": "BYTE_STREAM_SPLIT"},
        },
    ),
)


#: Master keys for ch13's fixtures. They are published here on purpose: these files exist to
#: show what encryption hides from a reader without keys, not to hide anything.
TEST_MASTER_KEYS = {
    "footer": b"footer-key-16byt",
    "pii": b"pii-column-key16",
    "finance": b"finance-key-16by",
}


class ToyKms(pe.KmsClient):
    """A key management service for fixtures only. It "wraps" a data key by XOR with the master
    key, which protects nothing; a real KMS never lets the master key leave it."""

    def __init__(self, config):
        super().__init__()

    def wrap_key(self, key_bytes, master_key_identifier):
        mk = TEST_MASTER_KEYS[master_key_identifier]
        return base64.b64encode(bytes(a ^ b for a, b in zip(key_bytes, mk, strict=True)))

    def unwrap_key(self, wrapped_key, master_key_identifier):
        mk = TEST_MASTER_KEYS[master_key_identifier]
        return bytes(a ^ b for a, b in zip(base64.b64decode(wrapped_key), mk, strict=True))


def _crypto():
    return pe.CryptoFactory(ToyKms), pe.KmsConnectionConfig()


def decryption_properties():
    factory, kms = _crypto()
    return factory.file_decryption_properties(kms, pe.DecryptionConfiguration())


def write_encrypted(fixture: Fixture) -> bytes:
    """Encryption draws fresh data keys and nonces on every write, so an encrypted fixture cannot
    be reproduced byte for byte. It is written once. Later runs keep the committed bytes if they
    decrypt, with the test keys, to exactly the fixture's table, and write new ones otherwise."""
    path = HERE / f"{fixture.name}.parquet"
    if path.exists():
        data = path.read_bytes()
        try:
            got = pq.read_table(io.BytesIO(data), decryption_properties=decryption_properties())
            if got.equals(fixture.table):
                return data
        except (OSError, ValueError, pa.ArrowException):
            pass
    factory, kms = _crypto()
    config = pe.EncryptionConfiguration(**fixture.encryption, double_wrapping=False)
    props = factory.file_encryption_properties(kms, config)
    sink = io.BytesIO()
    pq.write_table(fixture.table, sink, encryption_properties=props, **{**BASE_OPTIONS, **fixture.options})
    return sink.getvalue()


def write(fixture: Fixture) -> bytes:
    if fixture.encryption:
        return write_encrypted(fixture)
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
    if isinstance(value, float) and not math.isfinite(value):
        # JSON has no NaN or infinity; the reader writes the same strings for them.
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, tuple):
        return [_stat(v) for v in value]
    if isinstance(value, pq.SortingColumn):
        return {
            "column_index": value.column_index,
            "descending": value.descending,
            "nulls_first": value.nulls_first,
        }
    return str(value)


def manifest(fixture: Fixture, data: bytes) -> dict:
    """What pyarrow reports about the bytes it wrote. Nothing here is computed by this book."""
    decrypt = {"decryption_properties": decryption_properties()} if fixture.encryption else {}
    md = pq.ParquetFile(io.BytesIO(data), **decrypt).metadata
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
            "options": _stat({**BASE_OPTIONS, **fixture.options}),
            **({"encryption": fixture.encryption} if fixture.encryption else {}),
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
        **(
            {
                "rows_same_as": fixture.rows_same_as,
                "row_order": fixture.table.column("order_id").to_pylist(),
            }
            if fixture.rows_same_as
            else {"rows": [{k: _stat(v) for k, v in row.items()} for row in fixture.table.to_pylist()]}
        ),
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


def _rows(table: pa.Table, columns: list[str], names: list[str] | None = None) -> dict:
    """A result: column names as the engine writes them, and rows as lists."""
    return {
        "columns": names or columns,
        "rows": [[_stat(r[c]) for c in columns] for r in table.select(columns).to_pylist()],
    }


def _grouped(t: pa.Table, key: str, aggs: list, names: list[str]) -> dict:
    g = t.group_by(key).aggregate(aggs).sort_by(key)
    out_cols = [key] + [c for c in g.column_names if c != key]
    return _rows(g, out_cols, [key] + names)


#: Queries for ch12's engine, each answered here by pyarrow's own compute functions. The engine
#: runs the SQL; the test compares its answer with pyarrow's. (file, SQL, how pyarrow answers.)
QUERIES = [
    (
        "writing-baseline",
        "SELECT count(*) FROM orders",
        lambda t: {"columns": ["count(*)"], "rows": [[t.num_rows]]},
    ),
    (
        "writing-baseline",
        "SELECT count(*) FROM orders WHERE country = 'UK'",
        lambda t: {"columns": ["count(*)"], "rows": [[t.filter(pc.equal(t["country"], "UK")).num_rows]]},
    ),
    (
        "writing-baseline",
        "SELECT country, count(*) FROM orders GROUP BY country ORDER BY country",
        lambda t: _grouped(t, "country", [([], "count_all")], ["count(*)"]),
    ),
    (
        "writing-baseline",
        "SELECT status, sum(amount_cents) FROM orders GROUP BY status ORDER BY status",
        lambda t: _grouped(t, "status", [("amount_cents", "sum")], ["sum(amount_cents)"]),
    ),
    (
        "writing-baseline",
        "SELECT min(amount_cents), max(amount_cents), avg(amount_cents) FROM orders WHERE country = 'SE'",
        lambda t: (
            lambda f: {
                "columns": ["min(amount_cents)", "max(amount_cents)", "avg(amount_cents)"],
                "rows": [
                    [
                        pc.min(f["amount_cents"]).as_py(),
                        pc.max(f["amount_cents"]).as_py(),
                        pc.mean(f["amount_cents"]).as_py(),
                    ]
                ],
            }
        )(t.filter(pc.equal(t["country"], "SE"))),
    ),
    (
        "writing-baseline",
        "SELECT order_id, amount_cents FROM orders WHERE amount_cents > 9800 "
        "ORDER BY amount_cents DESC, order_id LIMIT 5",
        lambda t: _rows(
            t.filter(pc.greater(t["amount_cents"], 9800))
            .sort_by([("amount_cents", "descending"), ("order_id", "ascending")])
            .slice(0, 5),
            ["order_id", "amount_cents"],
        ),
    ),
    (
        "writing-baseline",
        "SELECT order_id, customer_id FROM orders WHERE order_id >= 431 AND order_id < 436 ORDER BY order_id",
        lambda t: _rows(
            t.filter(pc.and_(pc.greater_equal(t["order_id"], 431), pc.less(t["order_id"], 436))).sort_by(
                "order_id"
            ),
            ["order_id", "customer_id"],
        ),
    ),
    (
        "writing-baseline",
        "SELECT country, max(order_id) FROM orders WHERE status = 'refunded' GROUP BY country ORDER BY country",
        lambda t: _grouped(
            t.filter(pc.equal(t["status"], "refunded")), "country", [("order_id", "max")], ["max(order_id)"]
        ),
    ),
    (
        "writing-baseline",
        "SELECT count(*) FROM orders WHERE country = 'FR' AND amount_cents < 1000",
        lambda t: {
            "columns": ["count(*)"],
            "rows": [
                [t.filter(pc.and_(pc.equal(t["country"], "FR"), pc.less(t["amount_cents"], 1000))).num_rows]
            ],
        },
    ),
    (
        "statistics",
        "SELECT count(*), count(coupon) FROM orders",
        lambda t: {
            "columns": ["count(*)", "count(coupon)"],
            "rows": [[t.num_rows, pc.count(t["coupon"]).as_py()]],
        },
    ),
    (
        "statistics",
        "SELECT coupon, count(*) FROM orders WHERE coupon IS NOT NULL GROUP BY coupon ORDER BY coupon",
        lambda t: _grouped(t.filter(pc.is_valid(t["coupon"])), "coupon", [([], "count_all")], ["count(*)"]),
    ),
    (
        "statistics",
        "SELECT city, delta FROM orders WHERE delta < 0 ORDER BY delta",
        lambda t: _rows(t.filter(pc.less(t["delta"], 0)).sort_by("delta"), ["city", "delta"]),
    ),
]


def query_answers(written: dict[str, bytes]) -> bytes:
    """queries.json: each query, and pyarrow's answer to it from the fixture's bytes."""
    out = []
    for name, sql, answer in QUERIES:
        table = pq.read_table(io.BytesIO(written[name]))
        out.append({"file": f"{name}.parquet", "sql": sql, **answer(table)})
    return (json.dumps(out, indent=2) + "\n").encode()


def dump_manifest(m: dict) -> str:
    """The manifest as indented JSON, except that each row is on one line: the rows are most of
    a manifest, and one line each keeps them readable and the file small."""
    rows = m.get("rows")
    if rows is None:
        return json.dumps(m, indent=2)
    placeholder = "@@ROWS@@"
    text = json.dumps({**m, "rows": placeholder}, indent=2)
    body = ",\n".join("    " + json.dumps(r) for r in rows)
    return text.replace(json.dumps(placeholder), "[\n" + body + "\n  ]" if rows else "[]")


def outputs() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    manifests = []
    for fixture in FIXTURES:
        data = write(fixture)
        m = manifest(fixture, data)
        manifests.append(m)
        files[HERE / m["file"]] = data
        files[HERE / f"{fixture.name}.json"] = (dump_manifest(m) + "\n").encode()
    files[HERE / "README.md"] = readme(manifests).encode()
    files[HERE / "queries.json"] = query_answers({m["name"]: files[HERE / m["file"]] for m in manifests})
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
