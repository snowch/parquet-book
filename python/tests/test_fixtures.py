"""The Python reader against the files pyarrow wrote, and what pyarrow said about them.

These check the reader on its own terms, not by comparison with the Rust reader:
``tests/test_python.py`` does that. Both kinds are needed. Two readers that agree can still both
be wrong; a reader that matches pyarrow can still disagree with the one the page shows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from parquet_lab import report
from parquet_lab.bytes import Span
from parquet_lab.format import MAGIC, footer_span, parse_trailer
from parquet_lab.object_store import MemoryStore, NetworkModel, TracingStore
from parquet_lab.reader import FooterOptions, SuffixRange, read_footer

ROOT = Path(__file__).resolve().parents[2]


def fixtures():
    out = []
    for path in sorted((ROOT / "fixtures").glob("*.parquet")):
        manifest = json.loads(path.with_suffix(".json").read_text())
        # The encrypted fixtures (ch13) have tests of their own: most of these need keys.
        if "encryption" not in manifest["generator"]:
            out.append((path.name, path.read_bytes(), manifest))
    assert len(out) > 2
    return out


FIXTURES = fixtures()
IDS = [f[0] for f in FIXTURES]


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_every_fixture_starts_and_ends_with_the_magic(name, data, manifest):
    assert len(data) == manifest["file_size"]
    assert data[:4] == MAGIC and data[-4:] == MAGIC


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_the_footer_length_agrees_with_pyarrow(name, data, manifest):
    assert parse_trailer(data[-8:], len(data)).footer_length == manifest["footer_length"]


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_the_footer_decodes_to_what_pyarrow_wrote(name, data, manifest):
    md = report.open_bytes(data)
    assert md.num_rows == manifest["num_rows"]
    assert len(md.row_groups) == manifest["num_row_groups"]
    assert md.created_by == manifest["created_by"]
    assert [e.physical_type.name for e in md.leaves()] == [
        leaf["physical_type"] for leaf in manifest["leaves"]
    ]


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_every_column_chunk_is_where_pyarrow_says_it_is(name, data, manifest):
    md = report.open_bytes(data)
    for rg, expected in zip(md.row_groups, manifest["row_groups"], strict=True):
        assert rg.num_rows == expected["num_rows"]
        for c, e in zip(rg.columns, expected["columns"], strict=True):
            assert c.dotted_path() == e["path"]
            assert c.data_page_offset == e["data_page_offset"]
            assert c.total_compressed_size == e["total_compressed_size"]
            assert c.num_values == e["num_values"]
            assert c.physical_type.name == e["physical_type"]
            # pyarrow calls codec 7 "LZ4"; parquet.thrift calls it LZ4_RAW.
            assert c.codec == {"LZ4": "LZ4_RAW"}.get(e["compression"], e["compression"])
            assert sorted(c.encodings) == e["encodings"]


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_column_chunks_indexes_and_the_footer_tile_the_file(name, data, manifest):
    from parquet_lab import bloom

    md = report.open_bytes(data)
    at = 4
    for rg in md.row_groups:
        for c in rg.columns:
            assert c.byte_range().start == at, c.dotted_path()
            at = c.byte_range().end
    extra = []
    for rg in md.row_groups:
        for c in rg.columns:
            b = bloom.read(data, c)
            if b is not None:
                extra.append(Span(b.header_span.start, b.bitset_span.end))
            extra += [s for s in (c.column_index, c.offset_index) if s is not None]
    for span in sorted(extra):
        assert span.start == at
        at = span.end
    footer = footer_span(len(data), parse_trailer(data[-8:], len(data)).footer_length)
    assert footer.start == at


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_the_exact_procedure_makes_three_requests_and_reads_only_the_tail(name, data, manifest):
    store = MemoryStore()
    store.put(name, data)
    traced = TracingStore(store, NetworkModel())
    read = read_footer(traced, name, FooterOptions())
    assert [r.method for r in traced.requests] == ["HEAD", "GET", "GET"]
    assert traced.bytes_returned() == 8 + manifest["footer_length"]
    assert not read.footer_was_prefetched


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_a_large_enough_prefetch_saves_a_request(name, data, manifest):
    footer = manifest["footer_length"]

    def run(prefetch):
        store = MemoryStore()
        store.put(name, data)
        traced = TracingStore(store, NetworkModel())
        read = read_footer(traced, name, FooterOptions(SuffixRange(), prefetch))
        return len(traced.requests), read.footer_was_prefetched

    assert run(footer + 8) == (1, True)
    assert run(footer + 7) == (2, False)
    assert run(64 * 1024) == (1, True)


@pytest.mark.parametrize("name, data, manifest", FIXTURES, ids=IDS)
def test_the_structure_view_and_the_footer_lab_report_success(name, data, manifest):
    assert report.structure(data)["ok"]
    assert report.footer_lab(data, name, FooterOptions(), NetworkModel())["ok"]


def test_the_eight_orders_file_holds_the_layouts_table():
    """ch01 stores Table.sales() by hand, then shows pyarrow's Parquet file of the same orders."""
    from parquet_lab.layout import Table, show_cell

    table = Table.sales()
    manifest = json.loads((ROOT / "fixtures" / "eight-orders.json").read_text())
    names = [name for name, _ in table.columns]
    assert [leaf["path"] for leaf in manifest["leaves"]] == names
    expected = [
        {name: show_cell(v, kind) for (name, kind), v in zip(table.columns, row, strict=True)}
        for row in table.rows
    ]
    assert [{k: str(v) for k, v in r.items()} for r in manifest["rows"]] == expected


# ---- ch15: a changing table -------------------------------------------------------------------


def _changes():
    listing = json.loads((ROOT / "fixtures" / "changes.json").read_text())
    store = MemoryStore()
    for o in listing["objects"]:
        store.put(o["key"], (ROOT / "fixtures" / o["key"]).read_bytes())
    return listing, store


def test_every_snapshot_scans_to_what_pyarrow_counts():
    from parquet_lab.changes import scan_table

    listing, store = _changes()
    for id, expected in listing["snapshots"].items():
        s = scan_table(store, "changes/", id, 4, NetworkModel())
        assert (s.live_rows, s.sum_amount_cents) == (expected["live_rows"], expected["sum_amount_cents"]), id
        assert len(s.requests) == len(s.snapshot.data_files) + len(s.snapshot.delete_files) + 1, id


def test_a_lookup_finds_every_live_order_and_no_deleted_one():
    from parquet_lab.changes import lookup

    listing, store = _changes()
    deleted = listing["deleted"]
    for id, gone in (
        ("written", []),
        ("copy-on-write", deleted[:1]),
        ("merge-on-read-2", deleted[:2]),
        ("after-a-day", deleted),
        ("compacted", deleted),
    ):
        last = 960 if id in ("after-a-day", "compacted") else 800
        for key in [*range(1, last + 2, 23), *deleted]:
            r = lookup(store, "changes/", id, key, 0, 1, NetworkModel())
            live = key <= last and key not in gone
            assert bool(r.row) == live, (id, key)
            if live:
                assert r.row[0] == ("order_id", key)
            if key in gone and (id.startswith("merge") or id == "after-a-day"):
                assert r.found is not None and r.deleted_by is not None, (id, key)


def test_the_compaction_planner_rewrites_what_the_compacted_snapshot_replaced():
    from parquet_lab.changes import compaction_cost, plan_compaction, read_snapshots

    snapshots = {
        s.id: s for s in read_snapshots((ROOT / "fixtures" / "changes" / "_snapshots.json").read_text())
    }
    plan = plan_compaction(snapshots["after-a-day"], 200, 100)
    assert len(plan) == 3
    cost = compaction_cost(snapshots["after-a-day"], snapshots["compacted"], plan, NetworkModel())
    assert len(cost.outputs) == 3
    assert plan_compaction(snapshots["compacted"], 200, 100) == []


def test_a_position_delete_file_names_the_order_it_deletes():
    from parquet_lab import engine
    from parquet_lab.changes import read_position_deletes

    listing, _ = _changes()
    for n, order in enumerate(listing["deleted"]):
        rows = read_position_deletes(
            (ROOT / "fixtures" / "changes" / "deletes" / f"delete-{n:02d}.parquet").read_bytes()
        )
        assert len(rows) == 1
        path, pos = rows[0]
        data = (ROOT / "fixtures" / "changes" / path).read_bytes()
        assert engine.run(data, "SELECT order_id FROM orders").rows[pos][0] == order
