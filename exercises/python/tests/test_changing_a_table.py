"""Grades ch15's problems. Run with::

python3 -m pytest exercises/python/tests/test_changing_a_table.py --problems
"""

import pytest
from parquet_lab import changes
from parquet_lab.changes import DataFile, DeleteFile, Snapshot, read_snapshots
from parquet_lab.object_store import NetworkModel

from fixtures import FIXTURES, stub

problems = stub("changing_a_table")
files_to_open = problems.files_to_open
plan_compaction = problems.plan_compaction


def snapshots() -> list[Snapshot]:
    """Every snapshot of ch15's table, as pyarrow's generator recorded them."""
    return read_snapshots((FIXTURES / "changes" / "_snapshots.json").read_text())


def made_up() -> list[Snapshot]:
    """Snapshots the fixture does not have: ranges that overlap, files that are all small,
    deletes on every file, and an empty table."""

    def file(path, rows, lo, hi):
        return DataFile(path, rows, 40 * rows + 900, lo, hi)

    def delete(path, rows, of):
        return DeleteFile(path, rows, 1000, of)

    return [
        Snapshot(
            "made-up",
            "",
            [
                file("late.parquet", 50, 500, 600),
                file("wide.parquet", 300, 1, 1000),
                file("early.parquet", 20, 1, 40),
                file("tiny.parquet", 5, 41, 45),
            ],
            [
                delete("d1.parquet", 3, "wide.parquet"),
                delete("d2.parquet", 1, "late.parquet"),
                delete("d3.parquet", 2, "wide.parquet"),
            ],
        ),
        Snapshot(
            "made-up",
            "",
            [file(f"s{i:02d}.parquet", 10 + i, 100 * i, 100 * i + 9 + i) for i in range(12)],
            [],
        ),
        Snapshot(
            "made-up",
            "",
            [file("a.parquet", 100, 1, 100), file("b.parquet", 100, 101, 200)],
            [delete("x.parquet", 100, "a.parquet"), delete("y.parquet", 1, "b.parquet")],
        ),
        Snapshot("made-up", "", [], []),
    ]


@pytest.mark.problem("15.1")
def test_problem_15_1_opens_the_files_the_reader_opens():
    for s in snapshots() + made_up():
        for key in [*range(-1, 1002), 2000, -(2**63), 2**63 - 1]:
            data, deletes = changes.files_to_open(s, key)
            expected = ([f.path for f in data], [d.path for d in deletes])
            mine = files_to_open(s, key)
            assert (list(mine[0]), list(mine[1])) == expected, (s.id, key)


@pytest.mark.problem("15.2")
def test_problem_15_2_plans_what_the_reader_plans():
    for s in snapshots() + made_up():
        for target in (0, 1, 10, 50, 100, 196, 200, 250, 400, 1000):
            for small in (0, 1, 10, 20, 100, 200, 1000):
                expected = [g.data_files for g in changes.plan_compaction(s, target, small)]
                assert [list(g) for g in plan_compaction(s, target, small)] == expected, (s.id, target, small)


@pytest.mark.problem("15.2")
def test_problem_15_2_rewrites_what_the_compacted_snapshot_replaced():
    by_id = {s.id: s for s in snapshots()}
    planned = sorted(p for g in plan_compaction(by_id["after-a-day"], 200, 100) for p in g)
    kept = {f.path for f in by_id["compacted"].data_files}
    assert planned == sorted(f.path for f in by_id["after-a-day"].data_files if f.path not in kept)


# Scaffolding: the problems are answerable from what the snapshots record.


def test_every_snapshot_reads_and_the_readers_plan_matches_the_compacted_one():
    by_id = {s.id: s for s in snapshots()}
    assert len(by_id) > 4
    plan = changes.plan_compaction(by_id["after-a-day"], 200, 100)
    changes.compaction_cost(by_id["after-a-day"], by_id["compacted"], plan, NetworkModel())
    for s in made_up():
        for key in (0, 42, 550):
            changes.files_to_open(s, key)
