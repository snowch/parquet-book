"""Grades ch10's problems. Run with::

python3 -m pytest exercises/python/tests/test_how_readers_read.py --problems
"""

import pytest
from parquet_lab import scan
from parquet_lab.bytes import Span
from parquet_lab.object_store import Bounded, MemoryStore, NetworkModel, TracingStore

from fixtures import Lcg, stub

problems = stub("how_readers_read")
coalesce = problems.coalesce
finish_time = problems.finish_time


@pytest.mark.problem("10.1")
def test_problem_10_1_merges_as_the_reader_does():
    rng = Lcg(7)
    for case in range(2000):
        ranges = []
        for _ in range(1 + rng.next(12)):
            start = rng.next(1000)
            ranges.append((start, start + 1 + rng.next(80)))
        for gap in [None, 0, 1, 10, 100]:
            expected = [(s.start, s.end) for s in scan.coalesce([Span(a, b) for a, b in ranges], gap)]
            got = [tuple(r) for r in coalesce(list(ranges), gap)]
            assert got == expected, f"case {case}: {ranges} with gap {gap}"


@pytest.mark.problem("10.2")
def test_problem_10_2_matches_the_simulated_store():
    # With no latency and a byte per microsecond, a request takes as long as it has bytes, so
    # the store's clock can time any list of durations.
    model = NetworkModel(latency_us=0, bandwidth_bytes_per_sec=1_000_000)
    rng = Lcg(11)
    for case in range(500):
        phases = [[1 + rng.next(900) for _ in range(1 + rng.next(9))] for _ in range(1 + rng.next(4))]
        for connections in [1, 2, 3, 8]:
            obj = MemoryStore()
            obj.put("f", bytes(10_000))
            store = TracingStore(obj, model, connections)
            for i, phase in enumerate(phases):
                if i > 0:
                    store.next_phase()
                for d in phase:
                    store.get("f", Bounded(Span(0, d)), "")
            assert finish_time([list(p) for p in phases], connections) == store.elapsed_us(), (
                f"case {case}: {phases} on {connections}"
            )


def test_more_connections_are_never_slower_in_the_store():
    """Scaffolding, not a problem: the store the test times against behaves as the chapter says."""
    model = NetworkModel(latency_us=0, bandwidth_bytes_per_sec=1_000_000)
    obj = MemoryStore()
    obj.put("f", bytes(1000))
    times = []
    for connections in [1, 2, 4]:
        store = TracingStore(obj, model, connections)
        for d in [300, 200, 100, 400]:
            store.get("f", Bounded(Span(0, d)), "")
        times.append(store.elapsed_us())
    assert times[0] == 1000 and times[0] > times[1] > times[2] == 400
