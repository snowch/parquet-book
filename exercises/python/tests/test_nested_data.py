"""Grades ch04's problems. Run with::

python3 -m pytest exercises/python/tests/test_nested_data.py --problems
"""

import json

import pytest
from parquet_lab import rle
from parquet_lab.column import Triple, read_column
from parquet_lab.nested import assemble, path_fields
from parquet_lab.report import open_bytes
from parquet_lab.schema import build, leaves

from fixtures import FIXTURES, Rng, stub

problems = stub("nested_data")
decode_hybrid = problems.decode_hybrid
list_from_levels = problems.list_from_levels


def nested():
    return (FIXTURES / "nested.parquet").read_bytes(), json.loads((FIXTURES / "nested.json").read_text())


def tags(data: bytes):
    root = build(open_bytes(data).schema)
    return root, next(leaf for leaf in leaves(root) if leaf.dotted_path() == "tags.list.element")


def uleb(v: int) -> bytes:
    out = bytearray()
    while True:
        b, v = v & 0x7F, v >> 7
        if v == 0:
            out.append(b)
            return bytes(out)
        out.append(b | 0x80)


def encode(values: list[int], width: int, rng: Rng) -> bytes:
    """Write a hybrid stream the way a writer might: runs of repeats as RLE, the rest bit-packed.
    Encoding is not the problem; decoding is."""
    out = bytearray()
    i = 0
    while i < len(values):
        if rng.next(2) == 0:
            n = 1
            while i + n < len(values) and values[i + n] == values[i] and n < 300:
                n += 1
            out += uleb(n << 1) + values[i].to_bytes(4, "little")[: (width + 7) // 8]
            i += n
        else:
            groups = 1 + rng.next(3)
            chunk = [values[i + k] if i + k < len(values) else 0 for k in range(groups * 8)]
            bits = bytearray(groups * width)
            for k, v in enumerate(chunk):
                for b in range(width):
                    if v >> b & 1:
                        at = k * width + b
                        bits[at // 8] |= 1 << (at % 8)
            out += uleb((groups << 1) | 1) + bits
            i += groups * 8
    return bytes(out)


@pytest.mark.problem("4.1")
def test_problem_4_1_decodes_the_fixture_levels():
    data, _ = nested()
    md = open_bytes(data)
    for leaf in leaves(build(md.schema)):
        for page in read_column(data, md.row_groups[0].columns[leaf.column], leaf).pages:
            for stream, top in (
                (page.rep_levels, leaf.max_repetition_level),
                (page.def_levels, leaf.max_definition_level),
            ):
                if stream is None:
                    continue
                span, runs = stream
                # Skip the four-byte length: the problem is the runs after it.
                body = data[span.start + 4 : span.end]
                expected = rle.values(runs)
                assert list(decode_hybrid(body, rle.bit_width(top), len(expected))) == expected, (
                    f"{leaf.dotted_path()} levels {body.hex(' ')}"
                )


@pytest.mark.problem("4.1")
def test_problem_4_1_decodes_generated_streams():
    rng = Rng(0xDEAD_BEEF_CAFE_F00D)
    for _ in range(1000):
        width = 1 + rng.next(12)
        n = 1 + rng.next(60)
        values = [0 if rng.next(3) == 0 else rng.next(1 << width) for _ in range(n)]
        data = encode(values, width, rng)
        assert list(decode_hybrid(data, width, n)) == values, (
            f"width {width}, bytes {data.hex(' ')}: check the header's low bit, the RLE value's "
            "byte count, and that bits are read least significant first"
        )


def reader_answer(root, leaf, rep, definition, values):
    found = iter(values)
    triples = [
        Triple(r, d, next(found).encode() if d == 3 else None, None, [], 0)
        for r, d in zip(rep, definition, strict=True)
    ]
    return assemble(path_fields(root, leaf), leaf, triples)


def as_records(lists):
    return [{"tags": None if r is None else list(r)} for r in lists]


@pytest.mark.problem("4.2")
def test_problem_4_2_rebuilds_the_fixture_tags_like_pyarrow():
    data, manifest = nested()
    _, leaf = tags(data)
    triples = read_column(data, open_bytes(data).row_groups[0].columns[leaf.column], leaf).triples
    rep = [t.rep for t in triples]
    definition = [t.definition for t in triples]
    values = [t.value.decode() for t in triples if t.value is not None]
    mine = as_records(list_from_levels(rep, definition, values))
    assert mine == [{"tags": row.get("tags")} for row in manifest["rows"]]


@pytest.mark.problem("4.2")
def test_problem_4_2_agrees_with_the_reader_on_generated_levels():
    data, _ = nested()
    root, leaf = tags(data)
    rng = Rng(0x0123_4567_89AB_CDEF)
    for _ in range(500):
        # Random levels that a writer could produce for this column: each record starts at r = 0,
        # and continues at r = 1 only after a d that shows the list has elements.
        rep, definition, values = [], [], []
        for _ in range(1 + rng.next(6)):
            d = rng.next(4)
            rep.append(0)
            definition.append(d)
            if d == 3:
                values.append(f"v{len(values)}")
            if d >= 2:
                for _ in range(rng.next(4)):
                    d = 2 + rng.next(2)
                    rep.append(1)
                    definition.append(d)
                    if d == 3:
                        values.append(f"v{len(values)}")
        expected = reader_answer(root, leaf, rep, definition, values)
        assert as_records(list_from_levels(rep, definition, values)) == expected, (
            f"rep {rep} def {definition}: d = 0 is a null list, 1 an empty list, 2 a null element, 3 a value"
        )


def test_the_fixture_tags_cover_every_case():
    """Scaffolding, not a problem: the fixture's tag column has every case problem 4.2 names."""
    data, _ = nested()
    _, leaf = tags(data)
    triples = read_column(data, open_bytes(data).row_groups[0].columns[leaf.column], leaf).triples
    assert sorted({t.definition for t in triples}) == [0, 1, 2, 3]
