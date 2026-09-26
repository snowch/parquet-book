"""Grades ch11's problems. Run with::

python3 -m pytest exercises/python/tests/test_writing_parquet_well.py --problems

Problem 11.1 is graded against the reader's own plans for the ch11 fixtures: for values in a
column, the number of row groups the reader keeps when asked for each. Problem 11.2 is graded
against the ranges the row groups' decoded values actually span.
"""

from functools import cache

import pytest
from parquet_lab import schema
from parquet_lab.column import read_column
from parquet_lab.plain import to_plain_bytes
from parquet_lab.prune import Mechanisms, Op, Predicate, plan
from parquet_lab.report import open_bytes

from fixtures import FIXTURES, stub

problems = stub("writing_parquet_well")
row_groups_for = problems.row_groups_for
mean_row_groups_per_lookup = problems.mean_row_groups_per_lookup

FILES = [
    "writing-baseline.parquet",
    "writing-one-group.parquet",
    "writing-small-groups.parquet",
    "writing-by-country.parquet",
    "writing-shuffled.parquet",
    "writing-plain.parquet",
    "writing-no-index.parquet",
]


@cache
def cases():
    """For each file and integer column: its values in file order, each row group's bounds, the
    row group size, and for each distinct value the row groups the reader keeps."""
    out = []
    only_stats = Mechanisms(statistics=True, bloom=False, page_index=False)
    for name in FILES:
        data = (FIXTURES / name).read_bytes()
        md = open_bytes(data)
        for leaf in schema.leaves(schema.build(md.schema)):
            if leaf.dotted_path() not in ("order_id", "customer_id"):
                continue
            values, bounds = [], []
            for rg in md.row_groups:
                col = read_column(data, rg.columns[leaf.column], leaf)
                vs = [
                    int.from_bytes(to_plain_bytes(t.value, leaf.physical_type), "little", signed=True)
                    for t in col.triples
                ]
                bounds.append((min(vs), max(vs)))
                values.extend(vs)
            kept = []
            for v in sorted(set(values))[::3]:
                p = Predicate.new(leaf, None, Op.EQ, str(v))
                pl = plan(data, md, leaf, p, [leaf.column], only_stats)
                kept.append((v, sum(1 for g in pl.row_groups if not g.skipped)))
            out.append((f"{name} {leaf.dotted_path()}", values, bounds, md.row_groups[0].num_rows, kept))
    return out


@pytest.mark.problem("11.1")
def test_problem_11_1_counts_what_the_reader_reads():
    for name, _, bounds, _, kept in cases():
        for v, n in kept:
            assert row_groups_for(list(bounds), v) == n, f"{name}: order {v}"


@pytest.mark.problem("11.2")
def test_problem_11_2_predicts_the_mean_from_the_values():
    for name, values, bounds, size, _ in cases():
        distinct = sorted(set(values))
        expected = sum(sum(1 for lo, hi in bounds if lo <= v <= hi) for v in distinct) / len(distinct)
        got = mean_row_groups_per_lookup(list(values), size)
        assert abs(got - expected) < 1e-9, f"{name}: {got} against {expected}"


def test_the_layouts_differ():
    """Scaffolding, not a problem: the files' layouts give lookups different costs."""
    means = {}
    for name, values, bounds, _, _ in cases():
        distinct = set(values)
        means[name] = sum(sum(1 for lo, hi in bounds if lo <= v <= hi) for v in distinct) / len(distinct)
    assert means["writing-baseline.parquet order_id"] < 1.5
    assert means["writing-shuffled.parquet order_id"] > 3
