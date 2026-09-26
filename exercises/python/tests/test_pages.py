"""Grades ch06's problems. Run with::

python3 -m pytest exercises/python/tests/test_pages.py --problems
"""

import pytest
from parquet_lab.pages import walk_pages
from parquet_lab.report import open_bytes

from fixtures import fixtures, stub

problems = stub("pages")
crc_matches = problems.crc_matches
page_starts = problems.page_starts


@pytest.mark.problem("6.1")
def test_problem_6_1_finds_every_page_of_every_fixture():
    chunks = 0
    for name, data, _ in fixtures():
        for rg in open_bytes(data).row_groups:
            for c in rg.columns:
                r = c.byte_range()
                chunk = data[r.start : r.end]
                expected = [p.span().start for p in walk_pages(chunk, r.start)]
                assert list(page_starts(chunk, r.start)) == expected, (
                    f"{name} {c.dotted_path()}: each page is its header's length plus compressed_page_size"
                )
                chunks += 1
    assert chunks > 20


@pytest.mark.problem("6.2")
def test_problem_6_2_checks_the_standard_value():
    check = 0xCBF43926 - 2**32  # stored as a signed 32-bit integer
    assert crc_matches(b"123456789", check), 'the CRC-32 of "123456789" is 0xcbf43926'
    assert not crc_matches(b"123456780", check)


@pytest.mark.problem("6.2")
def test_problem_6_2_verifies_the_fixture_pages_and_catches_damage():
    _, data, _ = next(f for f in fixtures() if f[0] == "pages-v2.parquet")
    for c in open_bytes(data).row_groups[0].columns:
        r = c.byte_range()
        for p in walk_pages(data[r.start : r.end], r.start):
            body = bytearray(data[p.body_span.start : p.body_span.end])
            assert crc_matches(bytes(body), p.crc), f"page at {p.span().start}: the body is unchanged"
            for i in (0, len(body) // 2, len(body) - 1):
                body[i] ^= 0x10
                assert not crc_matches(bytes(body), p.crc), (
                    f"page at {p.span().start}: one flipped bit must fail"
                )
                body[i] ^= 0x10


def test_some_chunks_have_many_pages():
    """Scaffolding, not a problem: the fixtures include chunks with several pages and a
    dictionary page, so problem 6.1 cannot pass by reading one header."""
    _, data, _ = next(f for f in fixtures() if f[0] == "pages.parquet")
    r = open_bytes(data).row_groups[0].columns[1].byte_range()
    found = walk_pages(data[r.start : r.end], r.start)
    assert len(found) > 3 and found[0].page_type == "DICTIONARY_PAGE"
