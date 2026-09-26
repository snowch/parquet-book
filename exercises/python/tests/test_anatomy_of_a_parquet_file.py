"""Grades ch02's problems. Run with::

python3 -m pytest exercises/python/tests/test_anatomy_of_a_parquet_file.py --problems
"""

import json
from pathlib import Path

import pytest
from anatomy_of_a_parquet_file import footer_length, footer_range, gets_to_open
from parquet_lab.object_store import MemoryStore, NetworkModel, TracingStore
from parquet_lab.reader import FooterOptions, Known, read_footer

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def fixtures():
    """The fixtures, each with what pyarrow said about it when it wrote it."""
    out = []
    for path in sorted(FIXTURES.glob("*.parquet")):
        manifest = json.loads(path.with_suffix(".json").read_text())
        # ch13's encrypted fixtures need keys for most of what these problems read.
        if "encryption" not in manifest["generator"]:
            out.append((path.name, path.read_bytes(), manifest))
    assert out
    return out


def samples() -> list[int]:
    """A spread of 32-bit values that exercises every byte position, generated rather than
    listed."""
    x = 0x9E3779B9
    v = [0, 1, 255, 256, 65_535, 65_536, 2**32 - 1]
    for _ in range(200):
        x ^= (x << 13) & 0xFFFF_FFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFF_FFFF
        v.append(x)
    return v


@pytest.mark.problem("2.1")
def test_problem_2_1_footer_length_agrees_with_pyarrow():
    for name, data, manifest in fixtures():
        assert footer_length(data[-8:]) == manifest["footer_length"], name


@pytest.mark.problem("2.1")
def test_problem_2_1_every_byte_position_counts():
    for v in samples():
        b = v.to_bytes(4, "little")
        assert footer_length(b + b"PAR1") == v, (
            f"bytes {b.hex(' ')}: if you got {int.from_bytes(b, 'big'):#x}, you read them most "
            "significant first"
        )


@pytest.mark.problem("2.2")
def test_problem_2_2_footer_range_matches_the_fixtures():
    for name, data, manifest in fixtures():
        size, n = len(data), manifest["footer_length"]
        start, end = footer_range(size, n)
        assert end == size - 8, f"{name}: the footer ends where the trailer starts"
        assert end - start == n, f"{name}: the range is footer_length long"


@pytest.mark.problem("2.2")
def test_problem_2_2_impossible_footers_are_refused():
    # The largest footer a 100-byte file can hold runs from byte 4 to byte 92.
    assert tuple(footer_range(100, 88)) == (4, 92)
    assert footer_range(100, 89) is None, "overlaps the opening magic"
    assert tuple(footer_range(12, 0)) == (4, 4)
    assert footer_range(11, 0) is None, "too small for magic and trailer"
    assert footer_range(0, 0) is None
    assert footer_range(20, 2**32 - 1) is None


def traced_gets(data: bytes, prefetch: int) -> tuple[int, int]:
    """Open ``data`` with the book's reader; return the GETs it made and the footer's length."""
    store = MemoryStore()
    store.put("f", data)
    traced = TracingStore(store, NetworkModel())
    read = read_footer(traced, "f", FooterOptions(Known(len(data)), prefetch))
    return sum(r.method == "GET" for r in traced.requests), read.footer.length


@pytest.mark.problem("2.3")
def test_problem_2_3_gets_match_the_traced_reader():
    for name, data, manifest in fixtures():
        # Every prefetch near the boundary, where the answer changes, and a spread elsewhere.
        edge = manifest["footer_length"] + 8
        spread = range(0, len(data) + 17, max(7, len(data) // 40))
        for prefetch in sorted({*range(max(edge - 20, 0), edge + 20), *spread, 8, 64 * 1024}):
            gets, footer = traced_gets(data, prefetch)
            assert gets_to_open(footer, prefetch) == gets, (
                f"{name} with prefetch {prefetch}: the footer is {footer} bytes"
            )


def test_prefetch_cases_include_one_and_two_gets():
    """Scaffolding, not a problem: problem 2.3's cases include both answers."""
    _, data, _ = fixtures()[0]
    assert traced_gets(data, 8)[0] == 2
    assert traced_gets(data, 1 << 16)[0] == 1
