"""The Python reader and the Rust reader give identical answers.

The book shows both, and the browser can run either, so they must never disagree. Every call the
pages make to the Python engine is made here twice: through ``python/parquet_lab`` and natively
through ``pqlab``. The JSON must match, key order included. Damaged copies of the fixtures are
included, because a reader's errors are part of what the page shows.

``browser.EXPERIMENTS`` names the labs the Python engine runs, which is every lab in the book.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from parquet_lab import report  # noqa: E402
from parquet_lab.object_store import NetworkModel  # noqa: E402
from parquet_lab.reader import FooterOptions, Head, Known, SuffixRange  # noqa: E402

PQLAB = ROOT / "target" / "debug" / "pqlab"
FIXTURES = sorted((ROOT / "fixtures").glob("*.parquet"))


@pytest.fixture(scope="module", autouse=True)
def built_pqlab():
    subprocess.run(["cargo", "build", "--quiet", "-p", "pqlab"], cwd=ROOT, check=True)


def rust(*args: str) -> object:
    out = subprocess.run([str(PQLAB), *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    return json.loads(out.stdout, object_pairs_hook=list)


def python(value: dict) -> object:
    return json.loads(report.dumps(value), object_pairs_hook=list)


def damaged(tmp_path: Path) -> list[Path]:
    """Copies of a fixture with one byte changed: in the trailer, the footer and a page."""
    data = (ROOT / "fixtures" / "tiny.parquet").read_bytes()
    size = len(data)
    footer_length = int.from_bytes(data[-8:-4], "little")
    footer_start = size - 8 - footer_length
    out = []
    for offset, value in (
        (0, 0x51),
        (size - 1, 0x45),
        (size - 2, 0x00),
        (size - 8, 0xFF),
        (size - 5, 0x01),
        (footer_start, 0x00),
        (footer_start + 1, 0xFF),
        (footer_start + footer_length // 2, 0x07),
        (footer_start + footer_length - 1, 0x19),
        (4, 0x99),
        (10, 0x00),
    ):
        bad = bytearray(data)
        bad[offset] = value
        path = tmp_path / f"damaged-{offset}-{value}.parquet"
        path.write_bytes(bytes(bad))
        out.append(path)
    short = tmp_path / "short.parquet"
    short.write_bytes(data[-10:])
    out.append(short)
    return out


def files(tmp_path: Path) -> list[Path]:
    return FIXTURES + damaged(tmp_path)


def test_the_footer_lab_matches(tmp_path):
    models = ((20000, 100_000_000), (0, 0), (150000, 1_000_000))
    for path in files(tmp_path):
        data = path.read_bytes()
        for mode, size in (("head", Head()), ("known", Known(len(data))), ("suffix", SuffixRange())):
            for prefetch in (8, 300, 65536):
                for latency, bandwidth in models:
                    mine = report.footer_lab(
                        data,
                        path.name,
                        FooterOptions(size, prefetch),
                        NetworkModel(latency, bandwidth),
                    )
                    theirs = rust(
                        "footer", path, "--size", mode, "--prefetch", prefetch,
                        "--latency-us", latency, "--bandwidth", bandwidth, "--json",
                    )  # fmt: skip
                    assert python(mine) == theirs, f"footer {path.name} {mode} {prefetch}"


def test_the_structure_view_matches(tmp_path):
    for path in files(tmp_path):
        assert python(report.structure(path.read_bytes())) == rust("structure", path), path.name


def test_the_schema_lab_matches(tmp_path):
    for path in files(tmp_path):
        assert python(report.schema(path.read_bytes())) == rust("schema", path), path.name


@pytest.mark.parametrize("name", ["levels", "encodings", "pages", "compression"])
def test_the_column_labs_match(tmp_path, name):
    """ch04 to ch07: every column of every fixture, and the damaged copies."""
    call = getattr(report, name)
    for path in files(tmp_path):
        data = path.read_bytes()
        for column in range(12):
            mine = python(call(data, column, None) if name == "compression" else call(data, column))
            assert mine == rust(name, path, column), f"{name} {path.name} column {column}"


def test_the_compression_lab_matches_on_every_page(tmp_path):
    for path in files(tmp_path):
        data = path.read_bytes()
        for page in range(4):
            mine = python(report.compression(data, 1, page))
            assert mine == rust("compression", path, 1, page), f"{path.name} page {page}"


def test_the_statistics_lab_matches(tmp_path):
    """ch08: every column of the first row groups of every fixture, and the damaged copies."""
    for path in files(tmp_path):
        data = path.read_bytes()
        for row_group in range(3):
            for column in range(12):
                mine = python(report.statistics(data, row_group, column))
                assert mine == rust("statistics", path, row_group, column), (
                    f"{path.name} {row_group} {column}"
                )


SKIPPING = [
    (0, "=", "431", 7),
    (0, ">", "700", 1),
    (1, "=", "424242", 3),
    (1, "=", "7", 7),
    (2, "is null", "", 7),
    (2, "=", "SE", 5),
    (3, "<=", "150", 4),
    (0, "!=", "5", 0),
    (0, "<", "not a number", 1),
    (0, "~", "5", 1),
    (9, "=", "1", 7),
    (2, ">=", '"UK"', 7),
    (3, ">", "-1e400", 1),
]


def test_the_skipping_lab_matches(tmp_path):
    """ch09: conditions of every kind, with each mechanism, on every fixture."""
    for path in files(tmp_path):
        data = path.read_bytes()
        for column, op, value, mechanisms in SKIPPING:
            flags = ",".join(
                n for bit, n in ((1, "statistics"), (2, "bloom"), (4, "page-index")) if mechanisms & bit
            )
            mine = python(report.skipping(data, column, op, value, mechanisms))
            theirs = rust("skipping", path, column, op, value, "--use", flags)
            assert mine == theirs, f"{path.name}: {column} {op} {value!r} with {mechanisms}"


def test_the_scan_lab_matches(tmp_path):
    """ch10 and ch11: strategies of every kind, with and without a condition."""
    from parquet_lab.prune import Mechanisms, Op
    from parquet_lab.scan import Query, Strategy

    cases = [
        (None, "head", 8, 1, None, 7, False, []),
        ((0, "=", "431"), "suffix", 8192, 4, 1024, 7, False, []),
        ((2, "is null", ""), "head", 8, 2, None, 7, False, []),
        ((0, ">=", "700"), "head", 65536, 8, 0, 5, False, []),
        ((1, "=", "424242"), "suffix", 8, 1, 4096, 3, True, []),
        ((0, "<", "10"), "head", 8, 4, None, 0, False, [0, 3]),
        ((3, "=", "not a number"), "head", 8, 1, None, 7, False, []),
        ((0, "=", "5"), "head", 8, 1, None, 7, False, [99]),
    ]
    for path in files(tmp_path):
        data = path.read_bytes()
        try:
            flat = report.flat_columns(data)
        except ValueError:
            continue  # pqlab refuses a file it cannot open before it scans
        for where, size, prefetch, connections, gap, flags, chunks, columns in cases:
            footer = FooterOptions(SuffixRange() if size == "suffix" else Head(), prefetch)
            mechanisms = Mechanisms(bool(flags & 1), bool(flags & 2), bool(flags & 4))
            strategy = Strategy(footer, connections, gap, chunks, mechanisms)
            condition = (where[0], Op.parse(where[1]), where[2]) if where else None
            query = Query(columns or flat, condition)
            mine = python(report.scan(data, query, strategy, NetworkModel()))
            args = ["scan", path, "--size", size, "--prefetch", prefetch, "--connections", connections]
            if columns:
                args += ["--columns", ",".join(map(str, columns))]
            if gap is not None:
                args += ["--gap", gap]
            if chunks:
                args.append("--chunks")
            args += [
                "--use",
                ",".join(n for bit, n in ((1, "statistics"), (2, "bloom"), (4, "page-index")) if flags & bit),
            ]
            if where:
                args += ["--where", where[0], where[1]] + ([where[2]] if where[2] else [])
            assert mine == rust(*args), f"{path.name} {where} {size} {prefetch} {connections} {gap} {flags}"


QUERIES = [
    "SELECT count(*) FROM orders",
    "SELECT * FROM orders LIMIT 3",
    "SELECT country, count(*), sum(amount_cents), min(amount_cents), max(amount_cents), avg(amount_cents) "
    "FROM orders GROUP BY country ORDER BY country",
    "SELECT order_id, amount_cents FROM orders WHERE amount_cents > 9000 AND country = 'UK' ORDER BY amount_cents DESC, order_id LIMIT 7",
    "SELECT order_id FROM orders WHERE order_id >= 431 AND order_id < 436",
    "SELECT count(email) FROM orders WHERE email IS NULL",
    "SELECT status, count(*) FROM orders WHERE status <> 'paid' GROUP BY status",
    "SELECT min(ordered_at), max(ordered_at) FROM orders",
    "SELECT nonsense FROM",
    "SELECT * FROM orders WHERE country = 'UK",
    "SELECT order_id FROM orders LIMIT 2.5",
    "SELECT order_id FROM orders WHERE order_id ~ 5",
    "SELECT order_id, count(*) FROM orders",
    "SELECT * FROM orders GROUP BY country",
    "SELECT order_id FROM orders ORDER BY country",
    "SELECT order_id FROM orders WHERE order_id ( 5",
]


def test_the_engine_matches(tmp_path):
    """ch12: pyarrow's queries on their fixtures, and a spread of queries and mistakes on every
    fixture."""
    for q in json.loads((ROOT / "fixtures" / "queries.json").read_text()):
        if q["file"] == "table":
            continue
        path = ROOT / "fixtures" / q["file"]
        mine = python(report.query(path.read_bytes(), q["sql"]))
        assert mine == rust("query", path, q["sql"]), q["sql"]
    for path in files(tmp_path):
        data = path.read_bytes()
        for sql in QUERIES:
            assert python(report.query(data, sql)) == rust("query", path, sql), f"{path.name}: {sql}"


def test_the_encryption_lab_matches(tmp_path):
    for path in files(tmp_path):
        assert python(report.encryption(path.read_bytes())) == rust("encryption", path), path.name


def test_the_table_lab_matches():
    """ch14: every table query, with the files found each way, over one to eight connections."""
    from parquet_lab.table import Discovery

    listing = json.loads((ROOT / "fixtures" / "table.json").read_text())
    objects = [(o["key"], (ROOT / "fixtures" / o["key"]).read_bytes()) for o in listing["objects"]]
    queries = [
        q["sql"] for q in json.loads((ROOT / "fixtures" / "queries.json").read_text()) if q["file"] == "table"
    ]
    queries += [
        "SELECT * FROM orders WHERE country = 'XX'",
        "SELECT count(*) FROM orders WHERE order_id > 5000",
        "SELECT country, max(amount_cents) FROM orders WHERE status IS NULL GROUP BY country",
        "SELECT FROM",
    ]
    for sql in queries:
        for discovery, flag in (
            (Discovery.LIST, "list"),
            (Discovery.LIST_AND_PRUNE, "prune"),
            (Discovery.LOG, "log"),
        ):
            for connections in (1, 8):
                mine = python(report.table(objects, sql, discovery, connections, NetworkModel()))
                theirs = rust(
                    "table", "fixtures/table.json", sql, "--discovery", flag, "--connections", connections
                )
                assert mine == theirs, f"{sql} by {flag} over {connections}"


def test_the_changes_lab_matches():
    """ch15: every snapshot scanned, orders looked up with and without a prefetched tail, and
    compactions planned with several targets."""
    listing = json.loads((ROOT / "fixtures" / "changes.json").read_text())
    objects = [(o["key"], (ROOT / "fixtures" / o["key"]).read_bytes()) for o in listing["objects"]]
    cases = []
    for snapshot in [*listing["snapshots"], "no-such-snapshot"]:
        cases.append((snapshot, ("scan",), 0, 4, []))
        for key in (1, 250, 300, 450, 805, 960, 2000):
            for prefetch, connections in ((0, 1), (65536, 4)):
                cases.append(
                    (
                        snapshot,
                        ("lookup", key),
                        prefetch,
                        connections,
                        ["--lookup", key, "--prefetch", prefetch],
                    )
                )
        for target, small in ((200, 100), (400, 150), (50, 10)):
            cases.append(
                (
                    snapshot,
                    ("compact", target, small),
                    0,
                    4,
                    ["--compact", "--target-rows", target, "--small-rows", small],
                )
            )
    for snapshot, op, prefetch, connections, flags in cases:
        mine = python(report.changes(objects, snapshot, op, prefetch, connections, NetworkModel()))
        theirs = rust(
            "changes", "fixtures/changes.json", "--snapshot", snapshot, *flags, "--connections", connections
        )
        assert mine == theirs, f"{snapshot} {op} {prefetch} {connections}"


def test_the_byte_inspector_matches(tmp_path):
    for path in files(tmp_path):
        data = path.read_bytes()
        size = len(data)
        for offset in sorted(
            {0, 1, 4, 5, size // 3, size // 2, size - 9, size - 8, size - 4, size - 1, size}
        ):
            if offset < 0:
                continue
            mine = python(report.interpret(data, offset))
            assert mine == rust("interpret", path, offset), f"{path.name} at {offset}"


def test_every_byte_of_the_smallest_file_reads_the_same():
    path = ROOT / "fixtures" / "tiny.parquet"
    data = path.read_bytes()
    for offset in range(len(data)):
        assert python(report.interpret(data, offset)) == rust("interpret", path, offset), offset


@pytest.mark.parametrize(
    "columns, row",
    [([2, 3], None), ([3], None), ([0, 1, 2, 3, 4], 3), ([0, 4], None), ([], None), ([1], 7), ([2], 99)],
)
def test_the_layouts_lab_matches(columns, row):
    mask = sum(1 << c for c in columns)
    for latency, bandwidth in ((20000, 100_000_000), (0, 0), (5000, 1000)):
        args = ["layouts", "--columns", ",".join(map(str, columns))]
        if row is not None:
            args += ["--row", row]
        args += ["--latency-us", latency, "--bandwidth", bandwidth]
        mine = python(report.layouts(mask, row, NetworkModel(latency, bandwidth)))
        assert mine == rust(*args)


CLI = [
    ["structure", "fixtures/tiny.parquet"],
    ["footer", "fixtures/tiny.parquet", "--size", "suffix", "--prefetch", "65536", "--json"],
    ["interpret", "fixtures/tiny.parquet", "629"],
    ["schema", "fixtures/types.parquet"],
    ["layouts", "--columns", "2,3", "--row", "1"],
    ["levels", "fixtures/nested.parquet", "1"],
    ["encodings", "fixtures/dictionary.parquet", "1"],
    ["pages", "fixtures/pages.parquet", "1"],
    ["compression", "fixtures/codec-snappy.parquet", "1", "0"],
    ["statistics", "fixtures/statistics.parquet", "0", "2"],
    ["skipping", "fixtures/pruning-shuffled.parquet", "1", "=", "424242"],
    ["skipping", "fixtures/pruning-sorted.parquet", "0", "<", "500", "--use", "statistics"],
    ["scan", "fixtures/writing-baseline.parquet", "--where", "0", "=", "431"],
    ["scan", "fixtures/writing-baseline.parquet", "--where", "0", "=", "431", "--connections", "4", "--gap",
     "100", "--latency-us", "5000", "--bandwidth", "50000000"],
    ["scan", "fixtures/writing-baseline.parquet", "--where", "3", "is null", "--columns", "0,1", "--chunks",
     "--use", "statistics", "--size", "suffix", "--prefetch", "65536"],
    ["query", "fixtures/writing-baseline.parquet", "SELECT status, sum(amount_cents) FROM orders GROUP BY status"],
    ["encryption", "fixtures/plaintext-footer.parquet"],
    ["table", "fixtures/table.json", "SELECT count(*) FROM orders WHERE country = 'UK'", "--discovery", "prune",
     "--connections", "2"],
]  # fmt: skip


@pytest.mark.parametrize("args", CLI, ids=lambda a: " ".join(a[:2]))
def test_the_command_lines_print_the_same(args):
    """The book tells you to run either reader's command line on your own files; both print the
    same JSON."""
    out = subprocess.run(
        [sys.executable, "-m", "parquet_lab", *args],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "python"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(out.stdout, object_pairs_hook=list) == rust(*args)
