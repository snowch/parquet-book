"""ch08 to ch14: statistics and sort orders, skipping, the read path, the engine, encryption and
the table. The Rust modules of the same names carry the same tests."""

from __future__ import annotations

import json
import struct

from parquet_lab import bloom, crypto, engine, page_index, plain, report
from parquet_lab.bytes import ByteReader, Span
from parquet_lab.column import first_rows, read_column
from parquet_lab.format import parse_trailer
from parquet_lab.logical import value_json
from parquet_lab.object_store import MemoryStore, NetworkModel
from parquet_lab.prune import ALL, NONE, Mechanisms, Op, Predicate, _merge, plan
from parquet_lab.reader import FooterOptions, Head, SuffixRange
from parquet_lab.scan import Query, Strategy, coalesce, scan
from parquet_lab.schema import build, leaves
from parquet_lab.stats import DEPRECATED, MIN_MAX_VALUE, Comparator, bounds
from parquet_lab.table import LOG, Discovery, partition_values, read_log
from parquet_lab.table import query as table_query
from test_fixtures import FIXTURES, ROOT
from test_values import manifest_rows


def test_unsigned_and_signed_disagree_above_two_to_the_31():
    big, small = struct.pack("<I", 3_000_000_000), struct.pack("<I", 7)
    assert Comparator.U32.compare(big, small) == 1
    assert Comparator.I32.compare(big, small) == -1


def test_strings_sort_by_unsigned_bytes():
    lodz = "Łódź".encode()
    assert Comparator.BYTES.compare(b"Leeds", lodz) == -1
    assert Comparator.SIGNED_BYTES.compare(b"Leeds", lodz) == 1
    assert Comparator.BYTES.compare(b"Oslo", b"Os") == 1


def test_decimals_compare_by_value_and_nan_has_no_place():
    minus, plus = struct.pack(">i", -500), struct.pack(">i", 1999)
    assert Comparator.BIG_ENDIAN_SIGNED.compare(minus, plus) == -1
    assert Comparator.BYTES.compare(minus, plus) == 1
    nan = struct.pack("<d", float("nan"))
    assert Comparator.F64.compare(nan, struct.pack("<d", 1.0)) is None
    lo, hi = Comparator.F64.min_max([nan, struct.pack("<d", 2.0), struct.pack("<d", -1.0)])
    assert (struct.unpack("<d", lo)[0], struct.unpack("<d", hi)[0]) == (-1.0, 2.0)


def test_xxh64_matches_its_reference_values():
    assert bloom.xxh64(b"", 0) == 0xEF46DB3751D8E999
    assert bloom.xxh64(b"a", 0) == 0xD24EC4F1A98C6E5B
    assert bloom.xxh64(b"abc", 0) == 0x44BC2CF5AD770999


def test_ranges_merge_when_they_touch():
    assert _merge([(10, 20), (0, 10), (30, 40), (35, 50)]) == [(0, 20), (30, 50)]


def test_close_ranges_merge_and_distant_ones_do_not():
    spans = [Span(100, 200), Span(0, 50), Span(205, 300)]
    assert coalesce(spans, 0) == [Span(0, 50), Span(100, 200), Span(205, 300)]
    assert coalesce(spans, 10) == [Span(0, 50), Span(100, 300)]
    touching = [Span(0, 10), Span(10, 20)]
    assert coalesce(touching, 0) == [Span(0, 20)]
    assert coalesce(touching, None) == touching


def test_the_engine_parses_the_whole_language():
    q = engine.parse(
        "SELECT country, count(*), sum(x) FROM t WHERE a >= 3 AND b IS NOT NULL "
        "GROUP BY country ORDER BY country DESC LIMIT 3"
    )
    assert len(q.items) == 3 and q.items[1].name() == "count(*)"
    assert q.conditions[1].op is Op.IS_NOT_NULL
    assert q.order_by == [("country", True)] and q.limit == 3
    for bad in ("select from t", "select a from t where b = "):
        try:
            engine.parse(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_a_module_is_its_length_then_nonce_ciphertext_and_tag():
    data = struct.pack("<I", 40) + bytes(40)
    m = crypto.read_module(ByteReader(data, 100))
    assert (m.span, m.nonce, m.ciphertext, m.tag) == (
        Span(100, 144),
        Span(104, 116),
        Span(116, 128),
        Span(128, 144),
    )


def chunk_values(data: bytes):
    """Each column chunk's path, row group, the reader's comparator for it, its values as PLAIN
    bytes, and its statistics."""
    md = report.open_bytes(data)
    out = []
    for leaf in leaves(build(md.schema)):
        comparator = Comparator.for_leaf(leaf, md.schema[leaf.element].converted_type)
        for g, rg in enumerate(md.row_groups):
            chunk = rg.columns[leaf.column]
            try:
                triples = read_column(data, chunk, leaf).triples
            except ValueError:
                continue  # a codec the reader does not decode
            values = [
                plain.to_plain_bytes(t.value, leaf.physical_type) for t in triples if t.value is not None
            ]
            out.append((leaf.dotted_path(), g, comparator, values, chunk.statistics))
    return out


def test_the_readers_sort_orders_reproduce_pyarrows_statistics():
    checked = 0
    for name, data, _ in FIXTURES:
        assert report.open_bytes(data).column_orders is not None, name
        for path, g, comparator, values, stats in chunk_values(data):
            if stats is None or stats.min_value is None or stats.max_value is None:
                continue
            lo, hi = comparator.min_max(values)
            # Equal in the column's order: -0.0 and +0.0 are the same number.
            assert comparator.compare(lo, stats.min_value) == 0, f"{name} {path} {g}"
            assert comparator.compare(hi, stats.max_value) == 0, f"{name} {path} {g}"
            assert bounds(stats, comparator, True).source == MIN_MAX_VALUE
            checked += 1
    assert checked > 60


def test_the_statistics_fixture_catches_every_mistaken_order():
    _, data, _ = next(f for f in FIXTURES if f[0] == "statistics.parquet")
    caught = set()
    for path, _, comparator, values, stats in chunk_values(data):
        mistake = comparator.mistake()
        if mistake is None or stats is None or stats.min_value is None:
            continue
        got = mistake[0].min_max(values)
        if got != (stats.min_value, stats.max_value):
            caught.add(path)
    assert sorted(caught) == ["amount", "city", "customer_id", "delta", "temp_c"]


def test_deprecated_fields_are_used_only_where_signed_order_is_right():
    _, data, _ = next(f for f in FIXTURES if f[0] == "statistics.parquet")
    for path, _, comparator, _, stats in chunk_values(data):
        if stats is None or stats.min_value is None:
            continue
        # Pretend the file is old: only min and max, holding what min_value and max_value hold.
        stats.min, stats.max = stats.min_value, stats.max_value
        stats.min_value = stats.max_value = None
        try:
            usable = bounds(stats, comparator, True).source == DEPRECATED
        except ValueError:
            usable = False
        assert usable == (comparator in (Comparator.I32, Comparator.I64, Comparator.F64)), path


def test_the_page_index_agrees_with_the_pages():
    pages_checked = 0
    for name, data, _ in FIXTURES:
        md = report.open_bytes(data)
        for leaf in leaves(build(md.schema)):
            cmp = Comparator.for_leaf(leaf, md.schema[leaf.element].converted_type)
            for rg in md.row_groups:
                chunk = rg.columns[leaf.column]
                oi = page_index.offset_index(data, chunk)
                if oi is None:
                    continue
                d = read_column(data, chunk, leaf)
                assert [p.span() for p in oi.pages] == [p.page.span() for p in d.pages], name
                first = 1 if d.dictionary else 0
                reps = [[t.rep for t in d.triples if t.page == i + first] for i in range(len(d.pages))]
                assert [p.first_row_index for p in oi.pages] == first_rows(reps), name
                ci = page_index.column_index(data, chunk)
                for i in range(len(d.pages)):
                    mine = [t for t in d.triples if t.page == i + first]
                    values = [
                        plain.to_plain_bytes(t.value, leaf.physical_type) for t in mine if t.value is not None
                    ]
                    assert ci.null_counts[i] == sum(1 for t in mine if t.value is None)
                    found = cmp.min_max(values)
                    if found is None:
                        assert ci.null_pages[i]
                    else:
                        assert not ci.null_pages[i]
                        assert cmp.compare(found[0], ci.min_values[i]) == 0
                        assert cmp.compare(found[1], ci.max_values[i]) == 0
                    pages_checked += 1
    assert pages_checked > 100


def test_bloom_filters_hold_every_value_and_few_others():
    present = absent = false_positives = 0
    for _, data, _ in FIXTURES:
        md = report.open_bytes(data)
        for leaf in leaves(build(md.schema)):
            for rg in md.row_groups:
                chunk = rg.columns[leaf.column]
                f = bloom.read(data, chunk)
                if f is None:
                    continue
                d = read_column(data, chunk, leaf)
                values = {
                    plain.to_plain_bytes(t.value, leaf.physical_type)
                    for t in d.triples
                    if t.value is not None
                }
                for v in values:
                    assert f.probe(v).may_contain
                    present += 1
                for candidate in range(100_000, 1_000_000, 997):
                    b = struct.pack("<q", candidate)
                    if b not in values:
                        absent += 1
                        false_positives += f.probe(b).may_contain
    assert present >= 400
    assert false_positives / absent < 0.15


def test_skipping_never_loses_a_matching_row():
    plans = skipped_something = 0
    for name, data, _ in FIXTURES:
        if not (name.startswith("pruning") or name in ("statistics.parquet", "tiny.parquet")):
            continue
        md = report.open_bytes(data)
        flat = [leaf for leaf in leaves(build(md.schema)) if leaf.max_repetition_level == 0]
        projection = [leaf.column for leaf in flat]
        for leaf in flat:
            converted = md.schema[leaf.element].converted_type
            first = read_column(data, md.row_groups[0].columns[leaf.column], leaf)
            texts = []
            for t in [t for t in first.triples if t.value is not None][::7][:6]:
                v = plain.to_json(t.value)
                texts.append(v if isinstance(v, str) else json.dumps(v))
            texts.append("0")
            decoded = [read_column(data, rg.columns[leaf.column], leaf).triples for rg in md.row_groups]
            for op in Op:
                for text in texts:
                    try:
                        p = Predicate.new(leaf, converted, op, text)
                    except ValueError:
                        continue
                    pl = plan(data, md, leaf, p, projection, ALL)
                    plans += 1
                    for g, rg in enumerate(md.row_groups):
                        gp = pl.row_groups[g]
                        if gp.skipped or gp.rows != [(0, rg.num_rows)]:
                            skipped_something += 1
                        for row, t in enumerate(decoded[g]):
                            v = None if t.value is None else plain.to_plain_bytes(t.value, leaf.physical_type)
                            if p.row_matches(v):
                                assert any(a <= row < b for a, b in gp.rows), (
                                    f"{name} {leaf.dotted_path()} {op.symbol} {text}: row {row} lost"
                                )
    assert plans > 200 and skipped_something > 50


def test_every_strategy_returns_the_rows_a_full_read_finds():
    strategies = [
        Strategy(FooterOptions(), 1, None, True, NONE),
        Strategy(FooterOptions(SuffixRange(), 8192), 1, 0, False, ALL),
        Strategy(FooterOptions(), 4, 1024, False, ALL),
        Strategy(FooterOptions(SuffixRange(), 1 << 20), 2, None, False, ALL),
    ]
    scans = 0
    for name, data, _ in FIXTURES:
        if not (name.startswith("pruning") or name in ("statistics.parquet", "tiny.parquet")):
            continue
        md = report.open_bytes(data)
        flat = [leaf for leaf in leaves(build(md.schema)) if leaf.max_repetition_level == 0]
        columns = [leaf.column for leaf in flat]
        conditions = [None] + [
            (leaf.column, op, v)
            for leaf in flat
            for op, v in ((Op.EQ, "431"), (Op.GT, "100"), (Op.IS_NULL, ""), (Op.EQ, "SE"))
        ]
        for condition in conditions:
            if condition is None:
                expected = list(range(md.num_rows))
            else:
                c, op, v = condition
                leaf = next(leaf for leaf in flat if leaf.column == c)
                try:
                    p = Predicate.new(leaf, md.schema[leaf.element].converted_type, op, v)
                except ValueError:
                    continue
                expected, row = [], 0
                for rg in md.row_groups:
                    for t in read_column(data, rg.columns[c], leaf).triples:
                        raw = None if t.value is None else plain.to_plain_bytes(t.value, leaf.physical_type)
                        if p.row_matches(raw):
                            expected.append(row)
                        row += 1
            for s in strategies:
                r = scan(data, "data.parquet", Query(columns, condition), s, NetworkModel())
                assert r.matches == expected, f"{name} {condition} {s}"
                got = sorted(q.returned for q in r.requests if q.returned is not None)
                assert all(a.end <= b.start for a, b in zip(got, got[1:], strict=False)), (
                    "a byte fetched twice"
                )
                assert r.bytes_fetched <= len(data)
                scans += 1
    assert scans > 50


def test_the_engine_answers_as_pyarrow_does():
    checked = 0
    for q in json.loads((ROOT / "fixtures" / "queries.json").read_text()):
        if q["file"] == "table":
            continue
        a = engine.run((ROOT / "fixtures" / q["file"]).read_bytes(), q["sql"])
        assert a.columns == q["columns"], q["sql"]
        assert len(a.rows) == len(q["rows"]), q["sql"]
        for mine, theirs in zip(a.rows, q["rows"], strict=True):
            for m, t in zip(mine, theirs, strict=True):
                if isinstance(m, float):
                    assert abs(m - t) < 1e-9, q["sql"]
                else:
                    assert report.jsonable(m) == t, q["sql"]
        checked += 1
    assert checked >= 10


def encrypted_fixture(name: str):
    path = ROOT / "fixtures" / name
    return path.read_bytes(), json.loads(path.with_suffix(".json").read_text())


def key_id(key_metadata: bytes) -> str:
    # pyarrow's key material is JSON naming the master key; it never holds the key itself.
    return json.loads(key_metadata)["masterKeyID"]


def test_an_encrypted_footer_shows_only_its_crypto_metadata():
    data, manifest = encrypted_fixture("encrypted-footer.parquet")
    try:
        report.open_bytes(data)
        raise AssertionError("an encrypted footer opened")
    except ValueError as e:
        assert "encrypted" in str(e)
    f = crypto.encrypted_footer(data)
    assert f.algorithm == "AES_GCM_V1" and key_id(f.key_metadata) == "footer"
    # The crypto metadata, then one module, fill the footer exactly.
    assert f.crypto_metadata.span.start == f.footer.start
    assert f.crypto_metadata.span.end == f.module.span.start
    assert f.module.span.end == f.footer.end
    assert f.module.span.length == manifest["footer_length"]
    at = 4
    for c in manifest["row_groups"][0]["columns"]:
        assert c["data_page_offset"] == at
        at += c["total_compressed_size"]
    assert at == f.footer.start


def test_a_plaintext_footer_shows_everything_but_the_encrypted_columns():
    data, manifest = encrypted_fixture("plaintext-footer.parquet")
    md = report.open_bytes(data)
    assert md.encryption_algorithm == "AES_GCM_V1"
    assert md.footer_signature.length == 28
    t = parse_trailer(data[-8:], len(data))
    # pyarrow's footer length leaves out the signature that follows the FileMetaData.
    assert t.footer_length - 28 == manifest["footer_length"]
    rows = manifest_rows(manifest)
    for leaf in leaves(build(md.schema)):
        chunk = md.row_groups[0].columns[leaf.column]
        path = leaf.dotted_path()
        if chunk.crypto is None:
            d = read_column(data, chunk, leaf)
            for tr, row in zip(d.triples, rows, strict=False):
                assert value_json(leaf.physical_type, leaf.logical_type, tr.value) == row[path]
            continue
        assert chunk.crypto.with_column_key
        assert key_id(chunk.crypto.key_metadata) == ("pii" if path == "email" else "finance")
        try:
            read_column(data, chunk, leaf)
            raise AssertionError("an encrypted column decoded")
        except ValueError as e:
            assert "encrypted" in str(e)
        assert chunk.statistics is None
        modules = crypto.chunk_modules(data, chunk.byte_range())
        assert len(modules) == 2
        assert modules[0].span.start == chunk.byte_range().start
        assert modules[1].span.end == chunk.byte_range().end


def table_store() -> MemoryStore:
    listing = json.loads((ROOT / "fixtures" / "table.json").read_text())
    store = MemoryStore()
    for o in listing["objects"]:
        store.put(o["key"], (ROOT / "fixtures" / o["key"]).read_bytes())
    return store


def test_the_table_answers_as_pyarrow_does_however_its_files_are_found():
    checked = 0
    for q in json.loads((ROOT / "fixtures" / "queries.json").read_text()):
        if q["file"] != "table":
            continue
        read = []
        for d in (Discovery.LIST, Discovery.LIST_AND_PRUNE, Discovery.LOG):
            a = table_query(table_store(), "table/", q["sql"], d, 4, NetworkModel())
            assert [report.jsonable(r) for r in a.answer.rows] == q["rows"], f"{q['sql']} {d}"
            read.append(sum(1 for f in a.files if f.read))
            checked += 1
        # Each way of finding files reads no more than the one before it.
        assert read[0] >= read[1] >= read[2], q["sql"]
    assert checked >= 15


def test_the_log_lists_exactly_the_files_a_listing_finds():
    files, columns = read_log((ROOT / "fixtures" / "table" / LOG).read_text())
    assert "country" in columns
    listed = [(k[len("table/") :], n) for k, n in table_store().list("table/", "") if k.endswith(".parquet")]
    assert [(f.key, f.size) for f in files] == listed
    for f in files:
        md = report.open_bytes((ROOT / "fixtures" / "table" / f.key).read_bytes())
        assert f.stats.num_records == md.num_rows
        assert f.partition == partition_values(f.key)


def test_paths_carry_partition_values():
    assert partition_values("country=UK/part-0.parquet") == [("country", "UK")]
    assert partition_values("year=2026/month=01/f.parquet") == [("year", "2026"), ("month", "01")]
    assert partition_values("city=S%C3%A3o%20Paulo/f.parquet")[0][1] == "São Paulo"
    assert partition_values("part-0.parquet") == []


def test_mechanisms_default_to_all():
    assert Mechanisms() == ALL and Head() == FooterOptions().size
