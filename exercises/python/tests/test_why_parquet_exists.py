"""Grades ch01's problems. Run with::

python3 -m pytest exercises/python/tests/test_why_parquet_exists.py --problems
"""

import pytest
from parquet_lab.layout import Encoded, Layout, Query, Table, encode, ranges
from why_parquet_exists import reads_for


def every_query() -> list[Query]:
    """Every query over the sales table: each non-empty set of columns, with every row or one
    row."""
    t = Table.sales()
    out = []
    for mask in range(1, 1 << len(t.columns)):
        columns = [c for c in range(len(t.columns)) if mask & (1 << c)]
        out.append(Query(columns, list(range(len(t.rows)))))
        out += [Query(columns, [r]) for r in range(len(t.rows))]
    return out


def value_spans(enc: Encoded, q: Query) -> list[tuple[int, int]]:
    spans = [(enc.cells[r][c].start, enc.cells[r][c].end) for r in q.rows for c in q.columns]
    # Hand them over in reverse, so a solution that forgets to sort is caught.
    return spans[::-1]


@pytest.mark.problem("1.1")
def test_problem_1_1_reads_match_the_planner_for_every_query():
    t = Table.sales()
    for layout in Layout:
        enc = encode(t, layout)
        for q in every_query():
            expected = [(s.start, s.end) for s in ranges(enc, q)]
            yours = [tuple(r) for r in reads_for(value_spans(enc, q))]
            assert yours == expected, (
                f"{layout.value} layout, columns {q.columns}, rows {q.rows}: if you have more "
                "reads than expected, check that touching ranges are merged; if fewer, check that "
                "you do not merge across a gap"
            )


@pytest.mark.problem("1.1")
def test_problem_1_1_gaps_are_never_merged():
    assert [tuple(r) for r in reads_for([(10, 20), (21, 30)])] == [(10, 20), (21, 30)]
    assert [tuple(r) for r in reads_for([(21, 30), (10, 21)])] == [(10, 30)]
    assert list(reads_for([])) == []


def test_the_queries_include_both_layouts_winning():
    """Scaffolding, not a problem: the cases differ, so matching them is not luck."""
    t = Table.sales()
    rows, cols = encode(t, Layout.ROWS), encode(t, Layout.COLUMNS)
    qs = every_query()
    assert any(len(ranges(rows, q)) < len(ranges(cols, q)) for q in qs)
    assert any(len(ranges(rows, q)) > len(ranges(cols, q)) for q in qs)
