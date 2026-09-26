"""Grades ch08's problems. Run with::

python3 -m pytest exercises/python/tests/test_metadata_and_statistics.py --problems

Problem 8.1 is graded against pyarrow: the minimum and maximum your order finds among a column
chunk's values must be the ones pyarrow wrote in the footer.
"""

import dataclasses
import struct
from functools import reduce

import pytest
from parquet_lab import schema, stats
from parquet_lab.column import read_column
from parquet_lab.plain import to_plain_bytes
from parquet_lab.report import open_bytes
from parquet_lab.stats import Comparator

from fixtures import FIXTURES, stub

problems = stub("metadata_and_statistics")
Kind = problems.Kind
compare = problems.compare
usable_bounds = problems.usable_bounds

KIND_OF = {
    Comparator.I32: Kind.INT32,
    Comparator.U32: Kind.UINT32,
    Comparator.I64: Kind.INT64,
    Comparator.F64: Kind.DOUBLE,
    Comparator.BYTES: Kind.STRING,
    Comparator.BIG_ENDIAN_SIGNED: Kind.DECIMAL,
}


def chunks():
    """Every column chunk of the fixture whose kind the problems cover: its name, its kind, the
    comparator the book's reader uses, its values as PLAIN bytes, and its statistics."""
    data = (FIXTURES / "statistics.parquet").read_bytes()
    md = open_bytes(data)
    out = []
    for leaf in schema.leaves(schema.build(md.schema)):
        c = Comparator.for_leaf(leaf, md.schema[leaf.element].converted_type)
        kind = KIND_OF.get(c)
        if kind is None:
            continue
        for g, rg in enumerate(md.row_groups):
            chunk = rg.columns[leaf.column]
            values = [
                to_plain_bytes(t.value, leaf.physical_type)
                for t in read_column(data, chunk, leaf).triples
                if t.value is not None
            ]
            out.append((f"{leaf.dotted_path()} row group {g}", kind, c, values, chunk.statistics))
    return out


@pytest.mark.problem("8.1")
def test_problem_8_1_finds_the_footers_minimum_and_maximum():
    checked = 0
    for name, kind, _, values, s in chunks():
        if s is None or s.min_value is None or s.max_value is None:
            continue
        placed = [v for v in values if compare(kind, v, v) is not None]
        lo = reduce(lambda a, b: b if compare(kind, b, a) == -1 else a, placed)
        hi = reduce(lambda a, b: b if compare(kind, b, a) == 1 else a, placed)
        assert compare(kind, lo, s.min_value) == 0, f"{name}: minimum"
        assert compare(kind, hi, s.max_value) == 0, f"{name}: maximum"
        checked += 1
    assert checked >= 15


@pytest.mark.problem("8.1")
def test_problem_8_1_agrees_with_the_reader_on_every_pair():
    for name, kind, reader, values, _ in chunks():
        for a in values:
            for b in values:
                assert compare(kind, a, b) == reader.compare(a, b), f"{name}: {a!r} against {b!r}"


@pytest.mark.problem("8.2")
def test_problem_8_2_applies_the_rules():
    for name, kind, reader, _, s in chunks():
        if s is None:
            continue
        # The footer as it is, as if it had no column_orders, and as if it came from an old
        # writer that set only the deprecated fields.
        old = dataclasses.replace(s, min=s.min_value, max=s.max_value, min_value=None, max_value=None)
        nan = s
        if kind == Kind.DOUBLE:
            nan = dataclasses.replace(s, max_value=struct.pack("<d", float("nan")))
        for case, st, type_order in [
            ("as written", s, True),
            ("no column_orders", s, False),
            ("old writer", old, True),
            ("NaN maximum", nan, True),
        ]:
            try:
                b = stats.bounds(st, reader, type_order)
                expected = (b.min, b.max)
            except stats.Unusable:
                expected = None
            got = usable_bounds(st, kind, type_order)
            assert (None if got is None else tuple(bytes(x) for x in got)) == expected, f"{name}, {case}"


def test_the_fixture_has_every_kind():
    """Scaffolding, not a problem: statistics.parquet has a column of every kind."""
    assert {kind for _, kind, _, _, _ in chunks()} == set(Kind)
