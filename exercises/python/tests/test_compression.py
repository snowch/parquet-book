"""Grades ch07's problems. Run with::

python3 -m pytest exercises/python/tests/test_compression.py --problems
"""

import pytest
from parquet_lab import compress
from parquet_lab.pages import walk_pages
from parquet_lab.report import open_bytes

from fixtures import FIXTURES, stub

problems = stub("compression")
lz4_raw_decompress = problems.lz4_raw_decompress
snappy_decompress = problems.snappy_decompress


def pages(name: str):
    """Every page body of every column chunk, with its uncompressed size."""
    data = (FIXTURES / name).read_bytes()
    out = []
    for c in open_bytes(data).row_groups[0].columns:
        r = c.byte_range()
        for p in walk_pages(data[r.start : r.end], r.start):
            out.append(
                (f"{name} {c.dotted_path()} page at {p.span().start}", data[p.body_span.start : p.body_span.end],
                 p.uncompressed_page_size)
            )  # fmt: skip
    return out


def check(codec_file: str, decompress) -> None:
    expected = pages("codec-none.parquet")
    compressed = pages(codec_file)
    assert len(expected) == len(compressed)
    for (_, want, _), (label, body, size) in zip(expected, compressed, strict=True):
        got = bytes(decompress(body, size))
        assert len(got) == len(want), f"{label}: output length"
        assert got == want, f"{label}: the bytes differ from the uncompressed file's page"


@pytest.mark.problem("7.1")
def test_problem_7_1_small_cases():
    # "abababab": a two-byte literal, then six bytes copied from two back, overlapping.
    assert bytes(snappy_decompress(bytes([8, 0x04, *b"ab", 0x09, 2]))) == b"abababab"
    # A 100-byte literal, whose length needs the extra byte (tag 60 << 2).
    assert bytes(snappy_decompress(bytes([100, 60 << 2, 99, *range(100)]))) == bytes(range(100))
    # A copy with a two-byte offset: "xyz", then 3 bytes from 3 back.
    assert bytes(snappy_decompress(bytes([6, 0x08, *b"xyz", (2 << 2) | 0b10, 3, 0]))) == b"xyzxyz"


@pytest.mark.problem("7.1")
def test_problem_7_1_decompresses_every_snappy_page():
    check("codec-snappy.parquet", lambda b, _: snappy_decompress(b))


@pytest.mark.problem("7.2")
def test_problem_7_2_small_cases():
    # "abcabcabcX": three literals, a match of six from three back, then one last literal.
    assert bytes(lz4_raw_decompress(bytes([0x32, *b"abc", 3, 0, 0x10, *b"X"]), 10)) == b"abcabcabcX"
    # A match of 4 + 15 + 255 + 10 = 284 bytes: its length continues over two extra bytes.
    out = bytes(lz4_raw_decompress(bytes([0x1F, *b"z", 1, 0, 255, 10, 0x10, *b"!"]), 286))
    assert len(out) == 286 and out[:285] == b"z" * 285 and out[285:] == b"!"


@pytest.mark.problem("7.2")
def test_problem_7_2_decompresses_every_lz4_page():
    check("codec-lz4.parquet", lz4_raw_decompress)


def test_the_fixtures_use_long_literals_and_long_matches():
    """Scaffolding, not a problem: the fixtures exercise the long forms, so the problems cannot
    pass with only the short ones."""
    assert any(
        t.label == "literal" and t.output.length > 60
        for _, body, _ in pages("codec-snappy.parquet")
        for t in compress.snappy(body, 0).tokens
    )
    assert any(
        t.label == "match" and t.output.length > 19 + 255
        for _, body, size in pages("codec-lz4.parquet")
        for t in compress.lz4_raw(body, 0, size).tokens
    )
