"""A chapter's walkthrough steps (walkthroughs/) run, in both languages, and say what is true.

A walkthrough is a few lines the chapter asks you to run and change before it builds the reader:
reading a file's bytes by hand, and then reading the same facts with a library (pyarrow, and the
``parquet`` crate in ``walkthroughs/libraries``, a workspace of its own so that the book's reader
keeps no dependencies). Each Python step has a Rust twin of the same name. Both run
from the repository's root, and both must print what pyarrow's manifest says about the fixture.
They print in their own language's idiom (``b'PAR1'`` and ``"PAR1"``), so the check is on the
facts in the output, derived here from the manifest, never on the text.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "walkthroughs" / "python"
RUST = ROOT / "walkthroughs" / "src" / "bin"
LIBRARIES = ROOT / "walkthroughs" / "libraries"


def rust_step(step: str) -> Path:
    """A Rust step's source: the walkthroughs crate's, or the library workspace's."""
    by_hand = RUST / f"{step}.rs"
    return by_hand if by_hand.exists() else LIBRARIES / "src" / "bin" / f"{step}.rs"


def rust_binary(step: str) -> Path:
    target = ROOT if (RUST / f"{step}.rs").exists() else LIBRARIES
    return target / "target" / "debug" / step


STEPS = sorted((p.parent.name, p.stem) for p in PYTHON.glob("*/*.py"))


def tiny():
    data = (ROOT / "fixtures" / "tiny.parquet").read_bytes()
    return data, json.loads((ROOT / "fixtures" / "tiny.json").read_text())


def facts(chapter: str, step: str, language: str) -> list[str]:
    """What a step's output must contain, from the fixture and pyarrow's manifest. Where two
    libraries expose different things (pyarrow has no levels), a step's facts are given per
    language."""
    data, manifest = tiny()
    n, length = len(data), manifest["footer_length"]
    start = n - 8 - length
    damaged = bytearray(data)
    damaged[-7] = 0xFF
    damaged_length = int.from_bytes(damaged[-8:-4], "little")
    known = {
        ("anatomy_of_a_parquet_file", "first_bytes"): [f"{manifest['file_size']} bytes", "PAR1"],
        ("anatomy_of_a_parquet_file", "last_bytes"): ["PAR1", "true"],
        ("anatomy_of_a_parquet_file", "footer_length"): [data[-8:-4].hex(" "), str(length)],
        ("anatomy_of_a_parquet_file", "footer_start"): [
            f"byte {start}",
            f"{length} bytes long",
            data[start : start + 8].hex(" "),
        ],
        ("anatomy_of_a_parquet_file", "damaged_length"): [str(damaged_length), str(n - 8 - damaged_length)],
        ("anatomy_of_a_parquet_file", "open_with_the_reader"): [
            "HEAD",
            f"GET bytes={n - 8}-{n - 1} -> 8 bytes",
            f"GET bytes={start}-{n - 9} -> {length} bytes",
            f"footer length: {length} rows: {manifest['num_rows']}",
        ],
        ("anatomy_of_a_parquet_file", "the_reader_refuses"): [
            f"the reader refuses: the trailer claims a {damaged_length}-byte footer",
            "after 2 requests",
        ],
        ("anatomy_of_a_parquet_file", "footer_with_a_library"): [
            f"footer length: {length}",
            f"rows: {manifest['num_rows']} in {manifest['num_row_groups']} row group",
            *(
                f"column chunk {c['path']}: bytes {start} to {start + c['total_compressed_size']}"
                for c in manifest["row_groups"][0]["columns"]
                for start in [c["dictionary_page_offset"] or c["data_page_offset"]]
            ),
        ],
    }
    known.update(changes_facts())
    known.update(formats_facts())
    known.update(types_facts())
    known.update(nested_facts())
    known.update(encodings_facts())
    known.update(pages_facts())
    known.update(compression_facts())
    known.update(statistics_facts())
    known.update(skipping_facts())
    known.update(readers_facts())
    known.update(writing_facts())
    assert (chapter, step) in known, f"add what {chapter}/{step} must print to tests/test_walkthroughs.py"
    found = known[(chapter, step)]
    return found[language] if isinstance(found, dict) else found


def formats_facts() -> dict:
    """What ch01's steps must print, from pyarrow's reading of the CSV and Parquet files."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    formats = ROOT / "fixtures" / "formats"
    orders = pq.read_table(formats / "orders.parquet")
    uk = pc.sum(orders.filter(pc.equal(orders["country"], "UK"))["amount_cents"]).as_py()
    csv_size = (formats / "orders.csv").stat().st_size
    parquet_size = (formats / "orders.parquet").stat().st_size
    import csv

    header, *rows = list(csv.reader((formats / "eight-orders.csv").open()))
    mark = ["#" if name in ("country", "amount_cents") else "." for name in header]
    by_rows = "".join(mark * len(rows))
    by_columns = "".join(m * len(rows) for m in mark)
    return {
        ("why_parquet_exists", "two_layouts"): [
            f"by rows, {len(rows)} runs:\n{by_rows}\n",
            f"by columns, 1 run:\n{by_columns}\n",
        ],
        ("why_parquet_exists", "read_a_csv"): [
            f"read {csv_size} of {csv_size} bytes",
            f"amount_cents in the UK: {uk}",
        ],
        ("why_parquet_exists", "columns_with_a_library"): [
            f"of {parquet_size} bytes",
            f"amount_cents in the UK: {uk}",
        ],
    }


def types_facts() -> dict:
    """What ch03's steps must print, from pyarrow's reading of types.parquet's schema and
    statistics."""
    from datetime import date

    import pyarrow.parquet as pq

    md = pq.read_metadata(ROOT / "fixtures" / "types.parquet")
    arrow = md.schema.to_arrow_schema()
    columns = [md.schema.column(i) for i in range(md.num_columns)]

    def field(path: str):
        f, *rest = path.split(".")
        f = arrow.field(f)
        for name in rest:
            f = f.type.field(name)
        return f

    def repetition(f) -> str:
        return "OPTIONAL" if f.nullable else "REQUIRED"

    # pyarrow names the integer logical type INT, where the format and the book say INTEGER.
    logical = {
        c.path: {"NONE": "", "INT": "INTEGER"}.get(t, t) for c in columns for t in [c.logical_type.type]
    }
    groups = [f for f in arrow if f.type.num_fields]
    stats = {c.path: md.row_group(0).column(i).statistics for i, c in enumerate(columns)}
    day = stats["order_date"].min
    amount, scale = stats["amount"], next(c.scale for c in columns if c.path == "amount")
    paid = stats["paid_at"].min
    return {
        ("the_type_system", "schema_as_stored"): [
            f"schema {len(arrow)} children REQUIRED",
            *(f"{f.name} {f.type.num_fields} children {repetition(f)}" for f in groups),
            *(
                f"{c.name} {repetition(field(c.path))} {c.physical_type} {logical[c.path]}".rstrip()
                for c in columns
            ),
        ],
        ("the_type_system", "rebuild_the_tree"): [
            *(
                f"\n{'  ' * (c.path.count('.') + 1)}{c.name}  max levels: "
                f"definition {c.max_definition_level}, repetition {c.max_repetition_level}\n"
                for c in columns
            ),
            f"the reader's build finds {md.num_columns} columns",
        ],
        ("the_type_system", "same_bytes_two_ways"): [
            f"order_date {stats['order_date'].min_raw.to_bytes(4, 'little').hex(' ')} -> "
            f"{(day - date(1970, 1, 1)).days} -> {day.isoformat()}",
            f"-> {paid.date().isoformat()}",
            paid.strftime("%H:%M:%S"),
            f"amount {amount.min_raw.hex(' ')} -> {int(amount.min.scaleb(scale))} -> {amount.min}",
        ],
        ("the_type_system", "schema_with_a_library"): [
            f"{c.path}: max levels {c.max_definition_level} {c.max_repetition_level}, {c.physical_type}, min"
            for c in columns
        ],
    }


def encodings_facts() -> dict:
    """What ch05's steps must print: deltas, prefixes and dictionary indices computed here from
    the values pyarrow reads back, and the encodings and offsets pyarrow reports."""
    import pyarrow.parquet as pq

    fixtures = ROOT / "fixtures"
    rows = pq.read_table(fixtures / "encodings.parquet").to_pylist()
    times = [row["ordered_at"] for row in rows]
    deltas = [b - a for a, b in zip(times, times[1:], strict=False)]
    width = (max(deltas) - min(deltas)).bit_length()

    urls = [row["url"].encode() for row in rows]
    shared = [0] + [len(os.path.commonprefix([a, b])) for a, b in zip(urls, urls[1:], strict=False)]
    suffixes = b"".join(url[n:] for url, n in zip(urls, shared, strict=False))
    values = " ".join(json.dumps(row["url"]) for row in rows[:4])

    countries = [row["country"] for row in pq.read_table(fixtures / "dictionary.parquet").to_pylist()]
    entries = list(dict.fromkeys(countries))  # in order of first appearance, as a writer adds them
    indices = [entries.index(c) for c in countries]
    md = pq.read_metadata(fixtures / "dictionary.parquet").row_group(0).column(1)
    kind = next(e for e in md.encodings if e.endswith("_DICTIONARY"))
    plain = next(e for e in md.encodings if e not in (kind, "RLE"))  # the dictionary page's
    strings = {"python": repr, "rust": lambda v: json.dumps(v, separators=(", ", ": "))}
    chunks = pq.read_metadata(fixtures / "encodings.parquet").row_group(0)
    chunks = [chunks.column(i) for i in range(chunks.num_columns)]
    return {
        ("encodings", "delta_header"): [
            f"{len(times)} values, first {times[0]}",
            f"min delta {min(deltas)}; widths [{width}, ",
            f"first deltas: {deltas[:8]}",
        ],
        ("encodings", "dictionary_by_hand"): {
            language: [
                f"DICTIONARY_PAGE {plain} {show(entries)}\n",
                f"{kind}: ",
                f"width {(len(entries) - 1).bit_length()}",
                f"indices: {indices}",
                f"values: {show(countries)}",
            ]
            for language, show in strings.items()
        },
        ("encodings", "decode_a_column"): [
            f"{next(c for c in chunks if c.path_in_schema == 'url').encodings[-1]} page",
            f"{len(urls)} values; the first is {shared[0]}\n",
            f"{len(urls)} values; the first is {len(urls[0]) - shared[0]}\n",
            f"bytes: {suffixes[:8].hex(' ')} … ({len(suffixes)} bytes)",
            f"values: {values} …",
        ],
        ("encodings", "encodings_with_a_library"): {
            "python": [
                *(f"{c.path_in_schema} {c.encodings}" for c in chunks),
                f"dictionary: {entries}",
                f"indices: {indices}",
            ],
            "rust": [
                *(f"{c.path_in_schema} [{', '.join(c.encodings)}]" for c in chunks),
                f"country: dictionary page at Some({md.dictionary_page_offset})",
                f"DICTIONARY_PAGE {plain} {len(entries)}",
                f"DATA_PAGE {kind} {len(countries)}",
            ],
        },
    }


def pages_facts() -> dict:
    """What ch06's steps must print: where country's column chunk and pages start, from pyarrow's
    metadata; how many values each data page holds, from the batch size the manifest says the
    writer was given; and the row pyarrow reads differently once the damaged bit is flipped."""
    import io

    import pyarrow.parquet as pq

    def chunk(name: str):
        path = ROOT / "fixtures" / name
        md = pq.read_metadata(path).row_group(0).column(1)
        manifest = json.loads(path.with_suffix(".json").read_text())
        batch = manifest["generator"]["options"]["write_batch_size"]
        rows = [row["country"] for row in manifest["rows"]]
        return path, md, [rows[i : i + batch] for i in range(0, len(rows), batch)]

    path, md, batches = chunk("pages.parquet")
    distinct = len({c for batch in batches for c in batch} - {None})  # the dictionary's entries
    walk = [
        f"country: bytes {md.dictionary_page_offset} to "
        f"{md.dictionary_page_offset + md.total_compressed_size}\n",
        f"DICTIONARY_PAGE at {md.dictionary_page_offset}: ",
        f"-byte body, {distinct} values\n",
        f"DATA_PAGE at {md.data_page_offset}: ",
        *(f"-byte body, {len(b)} values\n" for b in batches),
    ]

    path, md, batches = chunk("pages-v2.parquet")
    end = md.dictionary_page_offset + md.total_compressed_size
    data = bytearray(path.read_bytes())
    data[end - 2] ^= 1  # the bit the steps flip
    before = pq.read_table(path, columns=["country"])["country"].to_pylist()
    after = pq.read_table(io.BytesIO(data), columns=["country"])["country"].to_pylist()
    row = next(i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b)
    walked = [True] * len(batches)  # the dictionary page and every data page but the last
    return {
        ("pages", "walk_the_pages"): walk,
        ("pages", "damage_a_page"): {
            "python": [
                "DATA_PAGE_V2 at ",
                "matches the header: True\n",
                "matches the header: False\n",
                f"the reader's walk: {[*walked, False]}",
            ],
            "rust": [
                "DATA_PAGE_V2 at ",
                "matches the header: true\n",
                "matches the header: false\n",
                f"the reader's walk: [{', '.join(['Some(true)'] * len(walked))}, Some(false)]",
            ],
        },
        ("pages", "pages_with_a_library"): {
            "python": [
                f"country: bytes {md.dictionary_page_offset} to {end}",
                f"the dictionary page at {md.dictionary_page_offset}, "
                f"the first data page at {md.data_page_offset}",
                f"unchecked, row {row} reads {after[row]!r}, not {before[row]!r}",
                "checked, it refuses: ",
                "CRC checksum verification failed",
            ],
            "rust": [
                f"country: bytes {md.dictionary_page_offset} to {end}",
                *(f"DATA_PAGE_V2: {len(b)} rows, {b.count(None)} nulls, " for b in batches),
                "one bit flipped:",
                "refused: ",
                "CRC checksum mismatch",
            ],
        },
    }


def compression_facts() -> dict:
    """What ch07's steps must print: the country page's PLAIN bytes, built from the manifest's
    rows; the first literal and copy a compressor must make of them; each codec's compressed page,
    from the two sizes pyarrow reports for the chunk, which count the same page header; and the
    codec names pyarrow and the crate give."""
    import pyarrow.parquet as pq

    def chunk(name: str):
        return pq.read_metadata(ROOT / "fixtures" / f"codec-{name}.parquet").row_group(0).column(1)

    rows = json.loads((ROOT / "fixtures" / "codec-none.json").read_text())["rows"]
    plain = b"".join(len(v).to_bytes(4, "little") + v for v in (r["country"].encode() for r in rows))
    # Snappy's shortest copy is four bytes, so the page is a literal up to the first four bytes
    # seen before, then a copy of them that runs as long as the bytes keep matching.
    at = next(i for i in range(1, len(plain)) if plain[i : i + 4] in plain[: i + 3])
    back = at - plain.index(plain[at : at + 4])
    n = next(k for k in range(4, len(plain) - at) if plain[at + k] != plain[at + k - back])
    # pyarrow calls the file's LZ4_RAW LZ4, as the book's fixture tests note.
    in_the_file = {"SNAPPY": "SNAPPY", "LZ4": "LZ4_RAW", "GZIP": "GZIP"}
    lines, library, setting = [], [], {"GZIP": "GZIP(GzipLevel(6))"}
    for name in ["snappy", "lz4", "gzip"]:
        c = chunk(name)
        codec = in_the_file[c.compression]
        # Both totals count the page's one header, so they differ by what the codec saved.
        body = len(plain) - (c.total_uncompressed_size - c.total_compressed_size)
        lines.append(f"{codec}: {body} bytes become {len(plain)} in ")
        sizes = f"{c.total_compressed_size} of {c.total_uncompressed_size} bytes"
        library.append((f"country: {c.compression}, {sizes}", f"country: {codec}, {sizes}"))
        library.append((None, f"as a writer's setting: {setting.get(codec, codec)}\n"))
    return {
        ("compression", "snappy_by_hand"): [
            f"the varint says {len(plain)} will come out",
            f"literal {at} bytes\ncopy {n} from {back} back\n",
            f"wrote {len(plain)} bytes; the page header says {len(plain)}",
        ],
        ("compression", "every_codec_one_page"): [*lines, "the same: true"],
        ("compression", "compression_with_a_library"): {
            "python": [py for py, _ in library if py],
            "rust": [rs for _, rs in library],
        },
    }


def statistics_facts() -> dict:
    """What ch08's steps must print: every column chunk's bounds as pyarrow reads them, through
    the logical type and raw; the order each column's type gives it; and four of the fixture's
    cities sorted by their bytes, unsigned and signed."""
    import pyarrow.parquet as pq

    path = ROOT / "fixtures" / "statistics.parquet"
    md = pq.read_metadata(path)
    columns = [md.schema.column(i) for i in range(md.num_columns)]
    groups = [md.row_group(g) for g in range(md.num_row_groups)]
    stats = [[rg.column(i).statistics for rg in groups] for i in range(md.num_columns)]

    # The format's order for each column, from its type as pyarrow reports it.
    def order(c) -> tuple[str, str]:
        t, lt = c.physical_type, json.loads(c.logical_type.to_json())
        if lt["Type"] == "Int" and not lt["isSigned"]:
            return "UNSIGNED", "unsigned integers"
        if lt["Type"] == "Decimal":
            return "SIGNED", "signed big-endian integers"
        if t in ("BYTE_ARRAY", "FIXED_LEN_BYTE_ARRAY"):
            return "UNSIGNED", "unsigned bytes"
        if t in ("FLOAT", "DOUBLE"):
            return "SIGNED", "floating-point values"
        return "SIGNED", "signed integers"

    def shown(v) -> str:  # as the book's reader displays a value
        if isinstance(v, str):
            return json.dumps(v, ensure_ascii=False)
        return repr(v).removesuffix(".0") if isinstance(v, float) else str(v)

    customer = next(i for i, c in enumerate(columns) if c.path == "customer_id")
    lt = json.loads(columns[customer].logical_type.to_json())
    kind = f"INTEGER({lt['bitWidth']}, {'signed' if lt['isSigned'] else 'unsigned'})"
    signed = []
    for g, s in enumerate(stats[customer]):
        high = s.max.to_bytes(4, "little")
        both = f"unsigned [{s.min}, {s.max}], signed [{s.min_raw}, {s.max_raw}]"
        signed.append(
            (
                f"row group {g}: max {high.hex(' ')}; {both}",
                f"row group {g}: max [{', '.join(f'{b:02x}' for b in high)}]; {both}",
            )
        )

    cities = ["Zürich", "Łódź", "Aarhus", "Århus"]  # the step's four, all in the fixture
    rows = json.loads(path.with_suffix(".json").read_text())["rows"]
    assert set(cities) <= {row["city"] for row in rows}
    by_bytes = sorted(cities, key=str.encode)
    by_signed = sorted(cities, key=lambda c: [b - 256 if b > 127 else b for b in c.encode()])

    def decides(source: str) -> list[str]:
        out = []
        for c, chunks in zip(columns, stats, strict=True):
            out.append(f"{c.path}, compared as {order(c)[1]}")
            for g, s in enumerate(chunks):
                if s is None:
                    out.append(f"  row group {g}: no statistics\n")
                elif not s.has_min_max:
                    out.append(f"  row group {g}: refused, ")
                    out.append(f"; null count {s.null_count}\n")
                else:
                    out.append(f"  row group {g}: {shown(s.min)} to {shown(s.max)}, from {source}\n")
        return out

    first = [(c, s[0]) for c, s in zip(columns, stats, strict=True)]
    sorting = groups[0].sorting_columns
    rust_sorting = ", ".join(
        f"SortingColumn {{ column_idx: {x.column_index}, descending: {str(x.descending).lower()}, "
        f"nulls_first: {str(x.nulls_first).lower()} }}"
        for x in sorting
    )
    return {
        ("metadata_and_statistics", "signed_or_unsigned"): {
            "python": [f"customer_id {columns[customer].physical_type} {kind}\n", *(p for p, _ in signed)],
            "rust": [f"customer_id {columns[customer].physical_type} {kind}\n", *(r for _, r in signed)],
        },
        ("metadata_and_statistics", "byte_order"): {
            "python": [
                *(f"{c} {c.encode().hex(' ')}\n" for c in cities),
                f"unsigned bytes: {', '.join(by_bytes)}\n",
                f"signed bytes:   {', '.join(by_signed)}\n",
                f"Python's sort:  {', '.join(sorted(cities))}\n",
            ],
            "rust": [
                *(f"{c} [{', '.join(f'{b:02x}' for b in c.encode())}]\n" for c in cities),
                f"unsigned bytes: {json.dumps(by_bytes, ensure_ascii=False, separators=(', ', ': '))}",
                f"signed bytes:   {json.dumps(by_signed, ensure_ascii=False, separators=(', ', ': '))}",
            ],
        },
        ("metadata_and_statistics", "the_reader_decides"): {
            "python": decides("min_value and max_value"),
            "rust": decides("MinMaxValue"),
        },
        ("metadata_and_statistics", "statistics_with_a_library"): {
            "python": [
                f"the footer: {md.serialized_size} bytes; sorted by {sorting}\n",
                *(
                    f"{c.path}: no statistics\n"
                    if s is None
                    else f"{c.path}: {s.min!r} to {s.max!r}, null count {s.null_count}\n"
                    for c, s in first
                ),
                f"  raw, as INT32: {stats[customer][0].min_raw} to {stats[customer][0].max_raw}\n",
            ],
            "rust": [
                f"sorted by Some([{rust_sorting}])\n",
                *(
                    f"{c.path}: TYPE_DEFINED_ORDER({order(c)[0]})"
                    + (", no statistics\n" if s is None else ", exact ")
                    for c, s in first
                ),
                f"customer_id: Some({stats[customer][0].min_raw}) to Some({stats[customer][0].max_raw})",
            ],
        },
    }


def xxh64_of_eight(data: bytes) -> int:
    """xxHash64 with seed 0 of exactly eight bytes, as its specification computes it: one lane,
    then the final mixing. Written here so that the Bloom filter steps are checked against a hash
    the book's reader did not compute."""
    mask, p1, p2, p3, p4, p5 = (
        2**64 - 1, 0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9,
        0x85EBCA77C2B2AE63, 0x27D4EB2F165667C5,
    )  # fmt: skip

    def rotl(x: int, r: int) -> int:
        return ((x << r) | (x >> (64 - r))) & mask

    assert len(data) == 8
    h = (p5 + 8) & mask
    h ^= rotl(int.from_bytes(data, "little") * p2 & mask, 31) * p1 & mask
    h = (rotl(h, 27) * p1 + p4) & mask
    for shift, prime in ((33, p2), (29, p3)):
        h = (h ^ (h >> shift)) * prime & mask
    return h ^ (h >> 32)


def skipping_facts() -> dict:
    """What ch09's steps must print: each row group's range of order_id, from pyarrow's
    statistics; the pages of row group 2, from the rows the manifest lists and the page size the
    writer was given; and each Bloom filter's answer for customer 424242, probed here with the
    format's hash and salts on the bytes pyarrow says the filter occupies."""
    import pyarrow.parquet as pq

    sorted_path = ROOT / "fixtures" / "pruning-sorted.parquet"
    shuffled_path = ROOT / "fixtures" / "pruning-shuffled.parquet"
    md = pq.read_metadata(sorted_path)
    manifest = json.loads(sorted_path.with_suffix(".json").read_text())
    options = manifest["generator"]["options"]
    group, page = options["row_group_size"], options["max_rows_per_page"]
    wanted = 431

    bounds = []
    for g in range(md.num_row_groups):
        s = md.row_group(g).column(0).statistics
        bounds.append((s.min, s.max, "read" if s.min <= wanted <= s.max else "skip"))
    kept = [g for g, (_, _, verdict) in enumerate(bounds) if verdict == "read"]

    # Row group 2's pages, from the rows the manifest lists in file order.
    ids = [row["order_id"] for row in manifest["rows"]][2 * group : 3 * group]
    pages = [ids[i : i + page] for i in range(0, len(ids), page)]
    first = md.row_group(2).column(0)
    end = first.data_page_offset + first.total_compressed_size
    # ASCENDING, as the format defines it: the minimums in order, and the maximums in order.
    ascending = all(min(a) <= min(b) and max(a) <= max(b) for a, b in zip(pages, pages[1:], strict=False))
    walk = [
        f"{len(pages)} pages, boundary order {'ASCENDING' if ascending else 'UNORDERED'}\n",
        *(
            f"page {i}: order_id {min(p)} to {max(p)}, "
            f"{'read' if min(p) <= wanted <= max(p) else 'skip'}; rows from {i * page}, bytes "
            for i, p in enumerate(pages)
        ),
        f"bytes {first.data_page_offset} to ",
        f" to {end}\n",
    ]
    matching = next(i for i, x in enumerate(ids) if x == wanted) // page * page

    # Customer 424242 against each row group's filter in the shuffled file.
    data = shuffled_path.read_bytes()
    shuffled = pq.read_metadata(shuffled_path)
    customers = {
        row["customer_id"] for row in json.loads(shuffled_path.with_suffix(".json").read_text())["rows"]
    }
    assert 424242 not in customers
    value = (424242).to_bytes(8, "little", signed=True)
    h = xxh64_of_eight(value)
    salts = [0x47B6137B, 0x44974D91, 0x8824AD5B, 0xA2B7289D, 0x705495C7, 0x2DF1424B, 0x9EFC4947, 0x5C6BFB31]
    probes = []
    for g in range(shuffled.num_row_groups):
        c = shuffled.row_group(g).column(1)
        end = c.bloom_filter_offset + c.bloom_filter_length
        blocks = c.bloom_filter_length // 32  # the Thrift header before the bitset is shorter
        bitset = data[end - 32 * blocks : end]
        block = ((h >> 32) * blocks) >> 32
        bits = []
        for w, salt in enumerate(salts):
            at = ((h & 0xFFFFFFFF) * salt & 0xFFFFFFFF) >> 27
            word = int.from_bytes(bitset[32 * block + 4 * w : 32 * block + 4 * w + 4], "little")
            bits.append((at, bool(word >> at & 1)))
        # Printed as Python writes a list of tuples, and as Rust's Debug writes an array of them.
        probes.append((f"row group {g}: block {block} of {blocks}, bits {bits}\n", all(on for _, on in bits)))

    plan = []
    for g, (_, high, verdict) in enumerate(bounds):
        if verdict == "skip":
            above = wanted > high
            plan.append(f"row group {g}: skip\n")
            plan.append(
                f"  statistics: skip, the value is {'above the maximum' if above else 'below the minimum'}\n"
            )
        else:
            plan.append(f"row group {g}: read rows [({matching}, {matching + page})]\n")
            plan.append("  statistics: read, the range may hold a match\n")
            plan.append(f"  page index: read, 1 of {len(pages)} pages may hold a match\n")

    c = shuffled.row_group(0).column(1)
    in_range = [
        g
        for g in range(shuffled.num_row_groups)
        if (s := shuffled.row_group(g).column(1).statistics).min <= 424242 <= s.max
    ]
    return {
        ("skipping_data", "row_group_bounds"): [
            f"row group {g}: order_id {low} to {high}, {verdict}\n"
            for g, (low, high, verdict) in enumerate(bounds)
        ],
        ("skipping_data", "pages_of_one_group"): walk,
        ("skipping_data", "probe_a_bloom_filter"): {
            "python": [f": {h:016x}\n", *(x for line, may in probes for x in (line, f"it: {may}\n"))],
            "rust": [
                f": {h:016x}\n",
                *(
                    x
                    for line, may in probes
                    for x in (
                        line.replace("True", "true").replace("False", "false"),
                        f"it: {str(may).lower()}\n",
                    )
                ),
            ],
        },
        ("skipping_data", "plan_a_read"): [*plan, " bytes of column chunks, "],
        ("skipping_data", "skipping_with_a_library"): {
            "python": [
                f"order_id = {wanted}: kept row groups {kept}\n",
                f"customer_id = 424242: kept row groups {in_range}\n",
                f"a column index: {c.has_column_index}; an offset index: {c.has_offset_index}\n",
            ],
            "rust": [
                *(f"order_id = {wanted}: kept row group Some({g})\n" for g in kept),
                f"  pages in {'ASCENDING' if ascending else 'UNORDERED'} order: "
                f"[{', '.join(str(min(p)) for p in pages)}] to [{', '.join(str(max(p)) for p in pages)}]\n",
                *(
                    f"customer_id = 424242: row group {g}, may contain it: Some({str(a).lower()})\n"
                    for g, (_, a) in enumerate(probes)
                ),
            ],
        },
    }


def readers_facts() -> dict:
    """What ch10's steps must print: the requests the reader makes for order_id = 431, from where
    pyarrow says the footer and row group 2's column chunks are, and the indexes it says they
    have; the reads pyarrow makes of the same file; and the tails the parquet crate asks for,
    from the footer length in the manifest."""
    import pyarrow.parquet as pq

    path = ROOT / "fixtures" / "pruning-sorted.parquet"
    md = pq.read_metadata(path)
    manifest = json.loads(path.with_suffix(".json").read_text())
    n, length = manifest["file_size"], manifest["footer_length"]
    wanted = 431
    kept = [
        g
        for g in range(md.num_row_groups)
        if (s := md.row_group(g).column(0).statistics).min <= wanted <= s.max
    ]
    assert kept == [2], "the steps and the prose follow one row group"
    group = md.row_group(2)
    chunks = [group.column(c) for c in range(group.num_columns)]
    # The first page of row group 2 holds order_id 431, so each column's first data page is read,
    # and its dictionary page before it.
    ids = [row["order_id"] for row in manifest["rows"]]
    per_group, per_page = (
        manifest["generator"]["options"][k] for k in ("row_group_size", "max_rows_per_page")
    )
    assert (ids.index(wanted) - 2 * per_group) // per_page == 0
    starts = [s for c in chunks for s in (c.dictionary_page_offset, c.data_page_offset) if s is not None]
    indexes = int(chunks[0].has_column_index) + sum(c.has_offset_index for c in chunks)
    requests = 3 + indexes + len(starts)

    tail = min(n, 64 * 1024)
    each = "".join(
        f"  read {c.total_compressed_size} bytes at {c.dictionary_page_offset or c.data_page_offset}\n"
        for c in chunks
    )
    first = chunks[0].dictionary_page_offset or chunks[0].data_page_offset
    whole = sum(c.total_compressed_size for c in chunks)
    return {
        ("how_readers_read", "read_with_a_strategy"): [
            "on 1: HEAD",
            f"on 1: GET bytes={n - 8}-{n - 1} read the trailer\n",
            f"on 1: GET bytes={n - 8 - length}-{n - 9} read the footer",
            *(f"on 1: GET bytes={s}-" for s in starts),
            "read the indexes the plan needs\n",
            f"{requests} requests, ",
            f"rows matching: [{ids.index(wanted)}]\n",
        ],
        ("how_readers_read", "reads_with_a_library"): {
            "python": [
                f"open, pre_buffer=False:\n  read {tail} bytes at {n - tail}\nread row group 2:\n{each}"
                f"{group.num_rows} rows\n",
                f"open, pre_buffer=True:\n  read {tail} bytes at {n - tail}\nread row group 2:\n"
                f"  read {whole} bytes at {first}\n{group.num_rows} rows\n",
            ],
            "rust": [
                f"read the last 8 bytes\n  NeedMoreData({8 + length})\nread the last {8 + length} bytes\n",
                f"{md.num_row_groups} row groups; the page index read: true\n",
            ],
        },
    }


WRITING = ["baseline", "one-group", "small-groups", "by-country", "shuffled", "plain", "no-index"]


def writing_facts() -> dict:
    """What ch11's steps must print: each file's footer length from its manifest and the row
    groups whose order_id statistics hold 431, from pyarrow's; the rows that match it, and what a
    file without a page index reads for it, its whole row group; and the files pyarrow
    writes from the baseline's rows, which are the fixtures to the byte."""
    import pyarrow.parquet as pq

    wanted = 431
    lookups, queries, crate, files = [], [], [], {}
    for name in WRITING:
        path = ROOT / "fixtures" / f"writing-{name}.parquet"
        md, manifest = pq.read_metadata(path), json.loads(path.with_suffix(".json").read_text())
        files[name] = (md, manifest)
        holding = [
            g
            for g in range(md.num_row_groups)
            if (s := md.row_group(g).column(0).statistics).min <= wanted <= s.max
        ]
        lookups.append(
            f"writing-{name}: footer {manifest['footer_length']} bytes, "
            f"{len(holding)} of {md.num_row_groups} row groups may hold it\n"
        )
        ids = pq.read_table(path, columns=["order_id"]).column(0).to_pylist()
        matching = f"{ids.count(wanted)} rows matching\n"
        if name == "no-index":
            # Without a page index the reader reads the whole row group, in one merged request.
            (g,) = holding
            whole = sum(md.row_group(g).column(c).total_compressed_size for c in range(md.num_columns))
            queries.append(f"writing-{name}: {whole} bytes in 1 requests, {matching}")
        else:
            queries.append(f"writing-{name}: ")
            queries.append(f" requests, {matching}")
        c = md.row_group(0).column(0)
        crate.append(f"writing-{name}: {md.num_row_groups} row groups, {c.compression}\n")
        crate.append(
            f"  dictionary {str(c.has_dictionary_page).lower()}, "
            f"column index {str(c.has_column_index).lower()}, sorted by None\n"
        )
        assert md.row_group(0).sorting_columns == (), "the fixtures do not declare their sort"

    def rewritten(change: str, name: str, sorted_by: str = "()") -> list[str]:
        md, manifest = files[name]
        c = md.row_group(0).column(0)
        return [
            f"{change}: {manifest['file_size']} bytes, footer {manifest['footer_length']}, "
            f"{md.num_row_groups} row groups\n",
            f"  dictionary {c.has_dictionary_page}, column index {c.has_column_index}, sorted by {sorted_by}\n",
        ]

    declared = pq.SortingColumn(0)
    return {
        ("writing_parquet_well", "row_groups_per_lookup"): lookups,
        ("writing_parquet_well", "query_every_file"): queries,
        ("writing_parquet_well", "writing_with_a_library"): {
            "python": [
                *rewritten("the baseline", "baseline"),
                *rewritten("row groups of 40", "small-groups"),
                *rewritten("no dictionary", "plain"),
                *rewritten("no page index", "no-index"),
                f"sorted by ({declared!r},)\n",
            ],
            "rust": crate,
        },
    }


def shred(value, steps: list[str], r: int = 0, d: int = 0, rep: int = 0):
    """Dremel's (r, d, value) for one optional field's value, computed from pyarrow's reading of
    the record rather than from the file's levels. ``steps`` walks down from the field: ``"[]"``
    for a standard three-level list (its optional group, repeated ``list`` and optional element)
    and a name for an optional field of a struct."""
    if value is None:
        yield r, d, None
        return
    d += 1
    if not steps:
        yield r, d, value
    elif steps[0] == "[]":
        if not value:
            yield r, d, None
        for i, element in enumerate(value):
            yield from shred(element, steps[1:], r if i == 0 else rep + 1, d + 1, rep + 1)
    else:
        yield from shred(value[steps[0]], steps[1:], r, d, rep)


def nested_facts() -> dict:
    """What ch04's steps must print: the levels of tags[] and items[].discounts[], shredded here
    from pyarrow's reading of nested.parquet's records, and the Arrow arrays pyarrow reads them
    into, computed from the same records."""
    import pyarrow.parquet as pq

    path = ROOT / "fixtures" / "nested.parquet"
    md, rows = pq.read_metadata(path), pq.read_table(path).to_pylist()
    columns = {md.schema.column(i).path: md.schema.column(i) for i in range(md.num_columns)}
    tags = [t for row in rows for t in shred(row["tags"], ["[]"])]
    discounts = [t for row in rows for t in shred(row["items"], ["[]", "discounts", "[]"])]

    def unpacked(name: str, levels: list[int], most: int) -> str:
        groups, width = -(-len(levels) // 8), most.bit_length()
        header = f"{1 + groups * width} bytes, header {groups << 1 | 1:02x}"
        packed = " ".join(map(str, levels))
        return f"{name}: {header}, bit-packed, {groups} group: {packed} (+{8 * groups - len(levels)} padding)"

    deep = columns["items.list.element.discounts.list.element"]
    leaf = columns["tags.list.element"]
    most = f"definition {leaf.max_definition_level}, repetition {leaf.max_repetition_level}"
    records = [{"tags": row["tags"]} for row in rows]
    values = [v for row in rows for v in row["tags"] or []]
    offsets = [0]
    for row in rows:
        offsets.append(offsets[-1] + len(row["tags"] or []))
    return {
        ("nested_data", "unpack_the_levels"): [
            unpacked("rep", [r for r, _, _ in discounts], deep.max_repetition_level),
            unpacked("def", [d for _, d, _ in discounts], deep.max_definition_level),
        ],
        ("nested_data", "levels_of_a_column"): {
            language: [
                f"tags[]  max levels: {most}\nr d value\n",
                *(f"\n{r} {d} {json.dumps(v)}\n" for r, d, v in tags),
                *(json.dumps(record, separators=separators) for record in records),
            ]
            for language, separators in [("python", None), ("rust", (",", ":"))]
        },
        ("nested_data", "levels_with_a_library"): {
            "python": [
                f"offsets: {offsets}",
                f"null lists: {[row['tags'] is None for row in rows]}",
                f"values: {values}",
            ],
            "rust": [
                f"{len(rows)} records",
                f"rep: {[r for r, _, _ in tags]}",
                f"def: {[d for _, d, _ in tags]}",
                f"values: {json.dumps([v for v in values if v is not None], separators=(', ', ': '))}",
            ],
        },
    }


def the_least_a_parquet_reader_reads() -> int:
    """The trailer, the footer and the two columns' chunks, from pyarrow's own metadata."""
    import pyarrow.parquet as pq

    md = pq.read_metadata(ROOT / "fixtures" / "formats" / "orders.parquet")
    chunks = [md.row_group(g).column(c) for g in range(md.num_row_groups) for c in range(md.num_columns)]
    wanted = [c for c in chunks if c.path_in_schema in ("country", "amount_cents")]
    return 8 + md.serialized_size + sum(c.total_compressed_size for c in wanted)


def test_parquet_reads_less_than_the_csv_and_the_crate_reads_the_least(built):
    """ch01's point, measured: a row-at-a-time CSV reader reads every byte; pyarrow reads less of
    the Parquet file, including a prefetched tail; the Rust crate reads only what it needs."""
    py = run_python("why_parquet_exists", "columns_with_a_library")
    rs = run_rust("columns_with_a_library")
    csv_size = (ROOT / "fixtures" / "formats" / "orders.csv").stat().st_size
    read = lambda out: int(re.search(r"read (\d+) of", out).group(1))  # noqa: E731
    assert the_least_a_parquet_reader_reads() <= read(py) < csv_size
    assert read(rs) == the_least_a_parquet_reader_reads()


def changes_facts() -> dict:
    """What ch15's steps must print, from the snapshots the generator wrote and pyarrow's reading
    of the files."""
    import pyarrow.parquet as pq

    table = ROOT / "fixtures" / "changes"
    snapshots = json.loads((table / "_snapshots.json").read_text())["snapshots"]
    day = next(s for s in snapshots if s["id"] == "after-a-day")
    deleted = json.loads((ROOT / "fixtures" / "changes.json").read_text())["deleted"]
    part = next(f for f in day["data_files"] if f["order_id"][0] <= 300 <= f["order_id"][1])
    names = [d for d in day["delete_files"] if d["data_file"] == part["path"]]
    first = pq.read_table(table / day["delete_files"][0]["path"]).to_pylist()[0]
    ids = pq.read_table(table / first["file_path"])["order_id"].to_pylist()
    gone = [p for d in names for p in pq.read_table(table / d["path"])["pos"].to_pylist()]
    amounts = pq.read_table(table / part["path"])["amount_cents"].to_pylist()
    live = [a for i, a in enumerate(amounts) if i not in gone]
    return {
        ("changing_a_table", "table_files"): [
            f"{len(day['data_files'])} data files and {len(day['delete_files'])} delete files",
            *(
                f"{f['path']}: {f['record_count']} rows in {f['file_size']} bytes, "
                f"{f['file_size'] // f['record_count']} bytes a row"
                for f in day["data_files"]
            ),
        ],
        ("changing_a_table", "find_the_file"): [
            f"order 300 can only be in {part['path']}",
            "may remove it: " + ", ".join(d["path"] for d in names),
        ],
        ("changing_a_table", "read_a_delete_file"): [
            f"row {first['pos']} of {first['file_path']} is deleted: order {ids[first['pos']]}",
            f"order {deleted[0]}",
        ],
        ("changing_a_table", "deletes_with_a_library"): [
            f"{part['path']} holds {len(amounts)} rows; {len(gone)} are deleted; {len(live)} are live",
            f"their amounts sum to {sum(live)}",
        ],
    }


def run_python(chapter: str, step: str) -> str:
    return subprocess.run(
        [sys.executable, str(PYTHON / chapter / f"{step}.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def run_rust(step: str) -> str:
    return subprocess.run(
        [str(rust_binary(step))], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture(scope="module")
def built():
    subprocess.run(["cargo", "build", "--quiet", "-p", "walkthroughs"], cwd=ROOT, check=True)
    subprocess.run(["cargo", "build", "--quiet"], cwd=LIBRARIES, check=True)


def test_every_step_has_a_twin():
    python = {step for _, step in STEPS}
    rust = {p.stem for p in [*RUST.glob("*.rs"), *(LIBRARIES / "src" / "bin").glob("*.rs")]}
    assert python == rust, f"only in Python: {python - rust}; only in Rust: {rust - python}"


@pytest.mark.parametrize(("chapter", "step"), STEPS, ids=[f"{c}/{s}" for c, s in STEPS])
def test_a_step_prints_the_same_facts_in_both_languages(built, chapter, step):
    py, rs = run_python(chapter, step), run_rust(step)
    for fact in facts(chapter, step, "python"):
        # Python prints True where Rust prints true; the shared facts are written Rust's way.
        found = fact.replace("True", "true") in py.replace("True", "true")
        assert found, f"Python {step} should print {fact!r}:\n{py}"
    for fact in facts(chapter, step, "rust"):
        assert fact in rs, f"Rust {step} should print {fact!r}:\n{rs}"


@pytest.mark.parametrize(("chapter", "step"), STEPS, ids=[f"{c}/{s}" for c, s in STEPS])
def test_a_step_is_in_its_chapter_in_both_languages(chapter, step):
    text = (ROOT / "chapters" / f"{chapter}.md").read_text()
    python = f"```{{literalinclude}} ../walkthroughs/python/{chapter}/{step}.py"
    rust = f"```{{literalinclude}} ../{rust_step(step).relative_to(ROOT)}"
    assert python in text and rust in text, f"quote {step} in both languages in chapters/{chapter}.md"
    # The two sit in one tab set, Python first.
    between = text[text.index(python) : text.index(rust)]
    assert ":sync: rust" in between and "::::" not in between.replace("::::{tab-set}", "")
    assert re.search(r"::::\{tab-set\}\s*:::\{tab-item\} Python", text[: text.index(python)][-200:])
