"""Grades ch05's problems. Run with::

python3 -m pytest exercises/python/tests/test_encodings.py --problems
"""

import pytest
from parquet_lab import plain
from parquet_lab.column import read_column
from parquet_lab.encoding import json_text
from parquet_lab.report import open_bytes
from parquet_lab.schema import build, leaves

from fixtures import FIXTURES, Rng, stub

problems = stub("encodings")
apply_prefixes = problems.apply_prefixes
decode_delta_binary_packed = problems.decode_delta_binary_packed
dictionary_values = problems.dictionary_values

MASK = 2**64 - 1


def wrap(v: int) -> int:
    return (v + 2**63) % 2**64 - 2**63


def columns(name: str):
    """A column as the book's reader read it: its path, its values section's bytes, its values,
    and its dictionary when it has one."""
    data = (FIXTURES / name).read_bytes()
    md = open_bytes(data)
    out = []
    for leaf in leaves(build(md.schema)):
        col = read_column(data, md.row_groups[0].columns[leaf.column], leaf)
        page = col.pages[0]
        values = [t.value for t in col.triples if t.value is not None]
        dictionary = [v for v, _ in col.dictionary.entries] if col.dictionary else None
        out.append((leaf.dotted_path(), data[page.values.start : page.values.end], values, dictionary))
    return out


def text(v) -> str:
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else json_text(plain.to_json(v))


def uleb(v: int) -> bytes:
    out = bytearray()
    while True:
        b, v = v & 0x7F, v >> 7
        if v == 0:
            out.append(b)
            return bytes(out)
        out.append(b | 0x80)


def encode_delta(values: list[int], block: int, miniblocks: int) -> bytes:
    """A DELTA_BINARY_PACKED writer, so the decoder meets block sizes and widths the fixtures
    lack."""

    def zz(v: int) -> int:
        return ((v << 1) ^ (v >> 63)) & MASK

    out = bytearray(uleb(block) + uleb(miniblocks) + uleb(len(values)) + uleb(zz(values[0] if values else 0)))
    deltas = [wrap(b - a) for a, b in zip(values, values[1:], strict=False)]
    per = block // miniblocks
    for c in range(0, len(deltas), block):
        chunk = deltas[c : c + block]
        low = min(chunk)
        out += uleb(zz(low))
        adjusted = [(d - low) & MASK for d in chunk]
        mbs = [adjusted[k : k + per] for k in range(0, len(adjusted), per)]
        widths = [max(mbs[m]).bit_length() if m < len(mbs) else 0 for m in range(miniblocks)]
        out += bytes(widths)
        for m, mb in enumerate(mbs):
            w = widths[m]
            bits = bytearray(per * w // 8)
            for i, v in enumerate(mb):
                for b in range(w):
                    if v >> b & 1:
                        bits[(i * w + b) // 8] |= 1 << ((i * w + b) % 8)
            out += bits
    return bytes(out)


@pytest.mark.problem("5.1")
def test_problem_5_1_decodes_the_fixture_columns():
    for path, section, values, _ in columns("encodings.parquet"):
        if path in ("order_id", "ordered_at"):
            assert list(decode_delta_binary_packed(section)) == values, path


@pytest.mark.problem("5.1")
def test_problem_5_1_decodes_generated_blocks():
    rng = Rng(0x5EED_1234_ABCD_0001)
    for _ in range(300):
        n = 1 + rng.next(700)
        v = []
        x = rng.next(1 << 40) - (1 << 39)
        for _ in range(n):
            v.append(x)
            step = rng.next(4)
            if step == 0:
                x = wrap(x + 1)
            elif step == 1:
                x = wrap(x + rng.next(1000) - 500)
            elif step == 2:
                x = wrap(x - rng.next(1 << 30))
            else:
                x = wrap(x + rng.next(8))
        block, mbs = [(128, 4), (256, 8), (128, 1), (256, 4)][rng.next(4)]
        data = encode_delta(v, block, mbs)
        assert list(decode_delta_binary_packed(data)) == v, (
            f"{n} values, blocks of {block} in {mbs} miniblocks: check that deltas add to the "
            "block's min delta, and that unneeded miniblocks take no bytes"
        )


@pytest.mark.problem("5.2")
def test_problem_5_2_rebuilds_urls_and_generated_strings():
    rng = Rng(0x0DD_BA11_C0FF_EE00)
    urls = [text(v).encode() for v in next(c for c in columns("encodings.parquet") if c[0] == "url")[2]]
    cases = [urls]
    for _ in range(300):
        words = [bytes(ord("a") + rng.next(3) for _ in range(rng.next(12))) for _ in range(1 + rng.next(30))]
        cases.append(sorted(words))
    for values in cases:
        prefixes, suffixes, prev = [], [], b""
        for v in values:
            p = 0
            while p < min(len(prev), len(v)) and prev[p] == v[p]:
                p += 1
            prefixes.append(p)
            suffixes.append(v[p:])
            prev = v
        assert [bytes(x) for x in apply_prefixes(prefixes, suffixes)] == values


@pytest.mark.problem("5.3")
def test_problem_5_3_reads_the_fixture_dictionary_pages():
    for path, section, values, dictionary in columns("dictionary.parquet"):
        expected = [text(v) for v in values]
        assert list(dictionary_values(section, len(expected), [text(v) for v in dictionary])) == expected, (
            path
        )


def test_generated_deltas_need_many_widths():
    """Scaffolding, not a problem: the generated blocks reach widths and miniblocks the fixtures
    do not, so problem 5.1 cannot pass on the fixtures' shapes alone."""
    assert len(encode_delta([0, 1, 1_000_000, 3, 3, 3, -7], 128, 4)) > 8
    assert any(c[0] == "order_id" for c in columns("encodings.parquet"))
