"""Grades ch13's problems. Run with::

python3 -m pytest exercises/python/tests/test_modular_encryption.py --problems
"""

import json

import pytest
from parquet_lab import crypto
from parquet_lab.report import open_bytes

from fixtures import FIXTURES, stub

problems = stub("modular_encryption")
FooterMode = problems.FooterMode
footer_mode = problems.footer_mode
modules = problems.modules


def every_fixture():
    """Every fixture, the encrypted ones included, with its manifest."""
    return [
        (p.name, p.read_bytes(), json.loads(p.with_suffix(".json").read_text()))
        for p in sorted(FIXTURES.glob("*.parquet"))
    ]


@pytest.mark.problem("13.1")
def test_problem_13_1_finds_the_modules_the_reader_finds():
    data = (FIXTURES / "plaintext-footer.parquet").read_bytes()
    md = open_bytes(data)
    checked = 0
    for c in md.row_groups[0].columns:
        if c.crypto is None:
            continue
        r = c.byte_range()
        expected = [(m.span.start - r.start, m.span.length) for m in crypto.chunk_modules(data, r)]
        assert [tuple(m) for m in modules(data[r.start : r.end])] == expected, c.dotted_path()
        checked += 1
    assert checked == 2
    # Generated runs of modules of every size from the smallest possible.
    chunk, expected = bytearray(), []
    for n in range(28, 60):
        expected.append((len(chunk), 4 + n))
        chunk += n.to_bytes(4, "little") + bytes([0xAB]) * n
    assert [tuple(m) for m in modules(bytes(chunk))] == expected


@pytest.mark.problem("13.2")
def test_problem_13_2_tells_the_three_modes_apart():
    for name, data, manifest in every_fixture():
        e = manifest["generator"].get("encryption")
        if e is None:
            expected = FooterMode.NOT_ENCRYPTED
        elif e.get("plaintext_footer") is True:
            expected = FooterMode.PLAINTEXT_FOOTER
        else:
            expected = FooterMode.ENCRYPTED_FOOTER
        assert footer_mode(data) == expected, name


def test_the_fixtures_have_all_three_modes():
    """Scaffolding, not a problem: every mode has a fixture."""
    modes = set()
    for _, _, manifest in every_fixture():
        e = manifest["generator"].get("encryption")
        modes.add("none" if e is None else "plaintext" if e.get("plaintext_footer") is True else "encrypted")
    assert modes == {"none", "plaintext", "encrypted"}
