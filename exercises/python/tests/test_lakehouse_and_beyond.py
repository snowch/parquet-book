"""Grades ch14's problems. Run with::

python3 -m pytest exercises/python/tests/test_lakehouse_and_beyond.py --problems
"""

import json

import pytest
from parquet_lab import engine, table
from parquet_lab.object_store import MemoryStore, NetworkModel
from parquet_lab.table import LOG, Discovery

from fixtures import FIXTURES, stub

problems = stub("lakehouse_and_beyond")
files_to_read = problems.files_to_read
partition_values = problems.partition_values


def objects() -> list[tuple[str, bytes]]:
    """The table's objects, by key, from the listing pyarrow's generator wrote."""
    listing = json.loads((FIXTURES / "table.json").read_text())
    return [(o["key"], (FIXTURES / o["key"]).read_bytes()) for o in listing["objects"]]


@pytest.mark.problem("14.1")
def test_problem_14_1_reads_the_paths_the_reader_reads():
    paths = [k[len("table/") :] for k, _ in objects()] + [
        "part-0.parquet",
        "year=2026/month=01/day=31/part-0.parquet",
        "country=UK/not-a-partition/part-0.parquet",
        "country=UK/status=a=b/part-0.parquet",
        "country=/part-0.parquet",
        "country=UK/x=y.parquet",
        "city=S%C3%A3o%20Paulo/part-0.parquet",
        "path=a%2Fb%3Dc/part-0.parquet",
        "odd%3Dname=1/part-0.parquet",
        "pct=100%25/part-0.parquet",
        "broken=%zz%4/part-0.parquet",
        "country=__HIVE_DEFAULT_PARTITION__/part-0.parquet",
    ]
    for p in paths:
        assert [tuple(x) for x in partition_values(p)] == [tuple(x) for x in table.partition_values(p)], p


RANGES = [
    (1, 801),
    (431, 436),
    (0, 1),
    (1, 2),
    (272, 274),
    (271, 272),
    (533, 536),
    (790, 801),
    (799, 900),
    (800, 801),
    (-5, 0),
    (500, 400),
]


@pytest.mark.problem("14.2")
def test_problem_14_2_keeps_exactly_the_files_the_reader_keeps():
    objs = objects()
    log = next(v for k, v in objs if k.endswith(LOG)).decode()
    for lo, hi in RANGES:
        sql = f"SELECT count(*) FROM orders WHERE order_id >= {lo} AND order_id < {hi}"
        store = MemoryStore()
        for k, v in objs:
            store.put(k, v)
        a = table.query(store, "table/", sql, Discovery.LOG, 4, NetworkModel())
        expected = [f.key for f in a.files if f.read]
        mine = list(files_to_read(log, lo, hi))
        assert mine == expected, sql
        # Never lose a row: every file with a matching row is kept.
        for f in a.files:
            data = dict(objs)[f"table/{f.key}"]
            n = engine.run(data, sql).rows[0][0]
            if n != 0:
                assert f.key in mine, f"{sql}: {f.key} holds {n} rows"


@pytest.mark.problem("14.2")
def test_problem_14_2_follows_removes_and_keeps_files_without_statistics():
    def add(path: str, stats: tuple[int, int] | None) -> str:
        action = {"path": path, "partitionValues": {}, "size": 1}
        if stats:
            lo, hi = stats
            action["stats"] = json.dumps(
                {"numRecords": 10, "minValues": {"order_id": lo}, "maxValues": {"order_id": hi}}
            )
        return json.dumps({"add": action})

    log = "\n".join(
        [
            '{"protocol": {"minReaderVersion": 1, "minWriterVersion": 2}}',
            add("a.parquet", (1, 100)),
            add("b.parquet", (101, 200)),
            add("c.parquet", None),
            add("d.parquet", (150, 250)),
            '{"remove": {"path": "b.parquet", "dataChange": true}}',
            add("e.parquet", (101, 120)),
        ]
    )
    assert list(files_to_read(log, 50, 60)) == ["a.parquet", "c.parquet"]
    assert list(files_to_read(log, 100, 160)) == ["a.parquet", "c.parquet", "d.parquet", "e.parquet"]
    assert list(files_to_read(log, 121, 150)) == ["c.parquet"]
    assert list(files_to_read(log, 250, 251)) == ["c.parquet", "d.parquet"]


def test_the_log_lists_what_a_listing_finds():
    """Scaffolding, not a problem: the log and the directory agree, so a plan from the log loses
    no file."""
    keys = {k[len("table/") :] for k, _ in objects() if k.endswith(".parquet")}
    log = next(v for k, v in objects() if k.endswith(LOG)).decode()
    assert {f.key for f in table.read_log(log)[0]} == keys
