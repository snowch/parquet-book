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
