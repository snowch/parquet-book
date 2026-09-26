"""Grades ch09's problems. Run with::

python3 -m pytest exercises/python/tests/test_skipping_data.py --problems

Problem 9.1 is graded against the data: for every page of the pruning fixtures and many
conditions, a page you skip must hold no matching row, and you must skip every page the bounds
alone rule out.
"""

import pytest
from parquet_lab import bloom, schema
from parquet_lab.column import read_column
from parquet_lab.page_index import column_index
from parquet_lab.plain import to_plain_bytes
from parquet_lab.report import open_bytes

from fixtures import FIXTURES, stub

problems = stub("skipping_data")
Cmp = problems.Cmp
can_skip = problems.can_skip
may_contain = problems.may_contain

I64_MIN, I64_MAX = -(2**63), 2**63 - 1


def int64(b: bytes) -> int:
    return int.from_bytes(b, "little", signed=True)


def pages():
    """Every page of every INT64 column of the pruning fixtures: its values (None for null), and
    the bounds and null count its ColumnIndex records."""
    out = []
    for name in ["pruning-sorted.parquet", "pruning-shuffled.parquet"]:
        data = (FIXTURES / name).read_bytes()
        md = open_bytes(data)
        for leaf in schema.leaves(schema.build(md.schema)):
            if leaf.physical_type != 2:
                continue
            for rg in md.row_groups:
                chunk = rg.columns[leaf.column]
                ci = column_index(data, chunk)
                col = read_column(data, chunk, leaf)
                for i in range(len(col.pages)):
                    values = [
                        None if t.value is None else int64(to_plain_bytes(t.value, leaf.physical_type))
                        for t in col.triples
                        if t.page == i
                    ]
                    bounds = None if ci.null_pages[i] else (int64(ci.min_values[i]), int64(ci.max_values[i]))
                    out.append((values, bounds, ci.null_counts[i]))
    return out


def matches(cmp, value: int, v: int | None) -> bool:
    if cmp == Cmp.IS_NULL:
        return v is None
    if v is None:
        return False
    return {Cmp.EQ: v == value, Cmp.LT: v < value, Cmp.GT: v > value}[cmp]


def provable(cmp, value: int, bounds, nulls: int, n: int) -> bool:
    """What the metadata alone proves: then the answer must be skip."""
    if cmp == Cmp.IS_NULL:
        return nulls == 0
    if bounds is None:
        return nulls == n
    lo, hi = bounds
    return {Cmp.EQ: value < lo or value > hi, Cmp.LT: lo >= value, Cmp.GT: hi <= value}[cmp]


@pytest.mark.problem("9.1")
def test_problem_9_1_never_skips_a_match_and_skips_what_the_bounds_rule_out():
    checked = skipped = 0
    for values, bounds, nulls in pages():
        n = len(values)
        probes = [I64_MIN, 0, 1, 100, 431, 500, 5_000, 9_800, 424_242, 999_999, I64_MAX]
        own = [v for v in values if v is not None][::9]
        for value in probes + own:
            for cmp in Cmp:
                skip = bool(can_skip(cmp, value, bounds, nulls, n))
                if skip:
                    assert not any(matches(cmp, value, v) for v in values), (
                        f"{cmp.name} {value}: you skipped a page holding a match ({bounds}, {nulls} nulls)"
                    )
                assert skip == provable(cmp, value, bounds, nulls, n), (
                    f"{cmp.name} {value} against {bounds} with {nulls} of {n} null"
                )
                skipped += skip
                checked += 1
    assert checked > 1000 and skipped > 100


@pytest.mark.problem("9.2")
def test_problem_9_2_agrees_with_the_fixtures_filters():
    data = (FIXTURES / "pruning-shuffled.parquet").read_bytes()
    md = open_bytes(data)
    probes = 0
    for rg in md.row_groups:
        f = bloom.read(data, rg.columns[1])
        for candidate in range(100_000, 1_000_000, 311):
            h = bloom.xxh64(candidate.to_bytes(8, "little", signed=True), 0)
            assert may_contain(f.bitset, h) == f.probe_hash(h).may_contain, f"customer {candidate}"
            probes += 1
    assert probes > 10_000


def test_the_pages_are_many_and_narrow():
    """Scaffolding, not a problem: there are pages enough, and some cover a narrow range, so the
    bounds rule some out."""
    ps = pages()
    assert len(ps) > 20
    assert any(b is not None and b[1] - b[0] < 1000 for _, b, _ in ps)
