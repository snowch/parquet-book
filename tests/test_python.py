"""The Python reader and the Rust reader give identical answers.

The book shows both, and the browser can run either, so they must never disagree. Every call the
pages make to the Python engine is made here twice: through ``python/parquet_lab`` and natively
through ``pqlab``. The JSON must match, key order included. Damaged copies of the fixtures are
included, because a reader's errors are part of what the page shows.

Calls join this list as their chapters are ported; ``browser.EXPERIMENTS`` names the labs the
Python engine runs so far.
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
