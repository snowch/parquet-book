"""Grades ch12's problems. Run with::

python3 -m pytest exercises/python/tests/test_a_tiny_query_engine.py --problems

Each problem is graded against pyarrow's answer to the same question about the ch11 baseline
file, from ``fixtures/queries.json``, and against many generated cases.
"""

import json

import pytest
from parquet_lab import schema
from parquet_lab.column import read_column
from parquet_lab.plain import to_json
from parquet_lab.report import open_bytes

from fixtures import FIXTURES, Lcg, stub

problems = stub("a_tiny_query_engine")
sum_by_key = problems.sum_by_key
top_n = problems.top_n


def answer(sql: str) -> list[list]:
    """pyarrow's answer to the query that starts with ``sql``."""
    queries = json.loads((FIXTURES / "queries.json").read_text())
    return next(q for q in queries if q["sql"].startswith(sql))["rows"]


def column(name: str) -> list:
    """The baseline file's column, decoded by the book's reader."""
    data = (FIXTURES / "writing-baseline.parquet").read_bytes()
    md = open_bytes(data)
    leaf = next(x for x in schema.leaves(schema.build(md.schema)) if x.dotted_path() == name)
    return [
        to_json(t.value)
        for rg in md.row_groups
        for t in read_column(data, rg.columns[leaf.column], leaf).triples
    ]


def pairs(rows) -> list[tuple]:
    return [tuple(r) for r in rows]


@pytest.mark.problem("12.1")
def test_problem_12_1_matches_pyarrows_group_by():
    expected = pairs(answer("SELECT status, sum(amount_cents)"))
    assert pairs(sum_by_key(column("status"), column("amount_cents"))) == expected
    rng = Lcg(3)
    names = ["a", "b", "ab", "Z", "é", ""]
    for case in range(500):
        n = rng.next(40)
        keys = [names[rng.next(6)] for _ in range(n)]
        values = [rng.next(1000) - 500 for _ in range(n)]
        sums: dict[str, int] = {}
        for k, v in zip(keys, values, strict=True):
            sums[k] = sums.get(k, 0) + v
        expected = sorted(sums.items(), key=lambda kv: kv[0].encode())
        assert pairs(sum_by_key(keys, values)) == expected, f"case {case}"


@pytest.mark.problem("12.2")
def test_problem_12_2_matches_pyarrows_sort():
    rows = [(i, a) for i, a in zip(column("order_id"), column("amount_cents"), strict=True) if a > 9800]
    expected = pairs(answer("SELECT order_id, amount_cents FROM orders WHERE amount_cents > 9800"))
    assert pairs(top_n(rows, 5)) == expected
    rng = Lcg(5)
    for case in range(500):
        rows = [(i, rng.next(20)) for i in range(rng.next(60))]
        n = rng.next(10)
        expected = sorted(rows, key=lambda r: (-r[1], r[0]))[:n]
        assert pairs(top_n(list(rows), n)) == expected, f"case {case}"


def test_pyarrows_answers_are_there():
    """Scaffolding, not a problem: the answers the problems are graded against exist, and the
    columns decode to as many values as each other."""
    assert answer("SELECT status, sum(amount_cents)")
    assert len(answer("SELECT order_id, amount_cents FROM orders WHERE amount_cents > 9800")) == 5
    assert len(column("status")) == len(column("amount_cents")) == len(column("order_id"))
