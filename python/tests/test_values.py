"""ch04 to ch07: levels, PLAIN, the delta encodings, the decompressors, and records rebuilt from
a column. The Rust modules of the same names carry the same tests."""

from __future__ import annotations

import json
import struct

import pytest
from parquet_lab import compress, report
from parquet_lab.bytes import Span, UnexpectedEnd
from parquet_lab.column import read_column
from parquet_lab.delta import binary_packed, byte_stream_split
from parquet_lab.nested import assemble, path_fields
from parquet_lab.pages import walk_pages
from parquet_lab.plain import decode as plain_decode
from parquet_lab.rle import BIT_PACKED, RLE, bit_width, values
from parquet_lab.rle import decode as rle_decode
from parquet_lab.schema import build, leaves
from test_fixtures import FIXTURES, ROOT


def test_bit_width_is_the_bits_needed_for_the_maximum():
    assert [bit_width(m) for m in (0, 1, 2, 3, 4, 7, 8, 255, 256)] == [0, 1, 2, 2, 3, 3, 4, 8, 9]


def test_an_rle_run_repeats_one_value():
    # header 0x08: RLE (low bit 0), count 4; value 0x01 in one byte.
    runs = rle_decode(bytes([0x08, 0x01]), 100, 1, 4)
    assert len(runs) == 1 and runs[0].kind == RLE
    assert runs[0].values == [1, 1, 1, 1]
    assert runs[0].header == Span(100, 101) and runs[0].body == Span(101, 102)


def test_a_bit_packed_run_packs_least_significant_bit_first():
    # header 0x03: bit-packed, one group of eight. Width 3: values 0..8 are the example in the
    # Parquet specification, packed into 0x88 0xc6 0xfa.
    runs = rle_decode(bytes([0x03, 0x88, 0xC6, 0xFA]), 0, 3, 8)
    assert runs[0].kind == BIT_PACKED and runs[0].values == list(range(8))


def test_padding_past_the_count_is_dropped():
    assert values(rle_decode(bytes([0x03, 0x88, 0xC6, 0xFA]), 0, 3, 5)) == [0, 1, 2, 3, 4]


def test_runs_follow_one_another():
    # RLE: three 2s at width 2, then bit-packed: 1, 0, 3, 2, 0, 0, 0, 0.
    runs = rle_decode(bytes([0x06, 0x02, 0x03, 0b1100_0001, 0b0000_0010]), 0, 2, 7)
    assert values(runs) == [2, 2, 2, 1, 0, 0, 3]


def test_a_stream_that_ends_early_is_an_error():
    with pytest.raises(UnexpectedEnd):
        rle_decode(bytes([0x03, 0x88]), 0, 3, 8)
    with pytest.raises(UnexpectedEnd):
        rle_decode(b"", 0, 1, 1)


def test_byte_arrays_are_a_length_then_bytes():
    v = plain_decode(6, None, bytes([2, 0, 0, 0, ord("U"), ord("K"), 0, 0, 0, 0]), 10, 2)
    assert v == [(b"UK", Span(10, 16)), (b"", Span(16, 20))]


def test_booleans_are_one_bit_each():
    assert [b for b, _ in plain_decode(0, None, bytes([0b101]), 0, 3)] == [True, False, True]


def test_integers_are_little_endian_and_signed():
    data = struct.pack("<iq", -3, 7)
    assert plain_decode(1, None, data[:4], 0, 1)[0][0] == -3
    assert plain_decode(2, None, data[4:], 4, 1)[0][1] == Span(4, 12)


def test_a_constant_step_packs_into_nothing():
    # Block of 128 in 4 miniblocks, 5 values, first 7 (zigzag 14). One block: min delta 1
    # (zigzag 2), widths 0,0,0,0, and no miniblock bytes at all.
    d = binary_packed(bytes([0x80, 0x01, 0x04, 0x05, 0x0E, 0x02, 0, 0, 0, 0]), 0)
    assert [v for v, _ in d.values] == [7, 8, 9, 10, 11]
    assert d.end == 10


def test_deltas_above_the_minimum_are_bit_packed():
    # Values 1, 3, 4, 8: deltas 2, 1, 4; min 1; adjusted 1, 0, 3 at 2 bits. A miniblock of 32
    # values at 2 bits is 8 bytes, the first holding 1 | 0<<2 | 3<<4 = 0x31.
    d = binary_packed(bytes([0x80, 0x01, 0x04, 0x04, 0x02, 0x02, 2, 0, 0, 0, 0x31] + [0] * 7), 0)
    assert [v for v, _ in d.values] == [1, 3, 4, 8]
    assert any("deltas [2, 1, 4]" in s.detail for s in d.steps)


def test_byte_stream_split_interleaves_by_byte_position():
    v = byte_stream_split(bytes([1, 2, 10, 20]), 0, 2, 2)
    assert v[0][0] == bytes([1, 10]) and v[1][0] == bytes([2, 20])
    assert v[1][1] == [Span(1, 2), Span(3, 4)]


def test_snappy_literal_then_overlapping_copy():
    # Output "abababab": length 8, a two-byte literal, then a copy of six bytes from two back,
    # which overlaps the bytes it writes.
    d = compress.snappy(bytes([8, 0b0000_0100, ord("a"), ord("b"), 0b0000_1001, 2]), 100)
    assert d.data == b"abababab"
    assert (d.tokens[2].kind, d.tokens[2].distance) == (compress.COPY, 2)
    assert d.tokens[2].input == Span(104, 106)


def test_lz4_sequence_and_last_literals():
    # "abcabcabcX": three literals then a match of six from three back, then one literal.
    d = compress.lz4_raw(bytes([0x32, *b"abc", 3, 0, 0x10, *b"X"]), 0, 10)
    assert d.data == b"abcabcabcX"


def test_inflate_stored_and_fixed_blocks():
    # A stored final block holding "hi".
    assert compress.inflate(bytes([0x01, 0x02, 0x00, 0xFD, 0xFF, *b"hi"]), 0, [])[0] == b"hi"
    # zlib's fixed-code encoding of "aaaaaaaaaa": a literal and a copy of nine from one back.
    assert compress.inflate(bytes([0x4B, 0x4C, 0x84, 0x01, 0x00]), 0, [])[0] == b"a" * 10


def test_unsupported_codecs_say_so():
    with pytest.raises(compress.CompressError, match="does not decompress ZSTD"):
        compress.decompress("ZSTD", b"", 0, 0)


def manifest_rows(manifest: dict) -> list:
    if "rows" in manifest:
        return manifest["rows"]
    base = json.loads((ROOT / "fixtures" / f"{manifest['rows_same_as']}.json").read_text())["rows"]
    by_id = {r["order_id"]: r for r in base}
    return [by_id[i] for i in manifest["row_order"]]


def project(value, keys: list[str]):
    """A pyarrow row, cut down to one column's path."""
    if value is None:
        return None
    if isinstance(value, list):
        return [project(v, keys) for v in value]
    if isinstance(value, dict) and keys:
        return {keys[0]: project(value.get(keys[0]), keys[1:])}
    # pyarrow prints a UTC timestamp with a space and "+00:00"; the reader uses ISO 8601.
    if isinstance(value, str) and value.endswith("+00:00"):
        return value.replace(" ", "T", 1).replace("+00:00", "Z")
    return value


def test_records_rebuilt_from_levels_match_pyarrows_rows():
    checked = 0
    for name, data, manifest in FIXTURES:
        md = report.open_bytes(data)
        root = build(md.schema)
        rows = manifest_rows(manifest)
        for leaf in leaves(root):
            fields = path_fields(root, leaf)
            # The keys a pyarrow row uses: a LIST's repeated group and its element are not keys.
            keys = [
                f.name
                for i, f in enumerate(fields)
                if not (i > 0 and fields[i - 1].is_list) and not (i > 1 and fields[i - 2].is_list)
            ]
            records = []
            for rg in md.row_groups:
                chunk = rg.columns[leaf.column]
                if not compress.supported(chunk.codec):
                    # ZSTD and BROTLI: the reader must say it cannot, not return anything.
                    with pytest.raises(ValueError, match="does not decompress"):
                        read_column(data, chunk, leaf)
                    continue
                records += assemble(fields, leaf, read_column(data, chunk, leaf).triples)
            if (
                not records
                and md.row_groups
                and not compress.supported(md.row_groups[0].columns[leaf.column].codec)
            ):
                continue
            assert len(records) == len(rows), f"{name} {leaf.dotted_path()}: one record per row"
            for i, (mine, row) in enumerate(zip(records, rows, strict=True)):
                assert report.plain(mine) == project(row, keys), f"{name} {leaf.dotted_path()} record {i}"
                checked += 1
    assert checked > 40


def test_page_checksums_verify_and_catch_damage():
    name, data, _ = next(f for f in FIXTURES if f[0] == "pages-v2.parquet")
    checked = 0
    for rg in report.open_bytes(data).row_groups:
        for c in rg.columns:
            r = c.byte_range()
            pages = walk_pages(data[r.start : r.end], r.start)
            for p in pages:
                assert p.crc_ok is True, f"{name} {c.dotted_path()} page at {p.span()}"
                checked += 1
            # Flip one bit in the first page's body: its checksum must now fail.
            damaged = bytearray(data[r.start : r.end])
            damaged[pages[0].body_span.start - r.start] ^= 1
            assert walk_pages(bytes(damaged), r.start)[0].crc_ok is False
    assert checked > 8


def test_every_codec_decompresses_to_the_same_pages():
    # The codec-* fixtures differ only in their codec, so every page, decompressed, must be the
    # uncompressed file's page byte for byte.
    def bodies(data: bytes, column: int):
        c = report.open_bytes(data).row_groups[0].columns[column]
        r = c.byte_range()
        out = []
        for p in walk_pages(data[r.start : r.end], r.start):
            body = data[p.body_span.start : p.body_span.end]
            d = compress.decompress(c.codec, body, p.body_span.start, p.uncompressed_page_size)
            out.append((c.codec, d.data))
        return out

    files = {f[0]: f[1] for f in FIXTURES}
    checked = 0
    for codec in ("snappy", "gzip", "lz4"):
        for column in range(7):
            expected = bodies(files["codec-none.parquet"], column)
            got = bodies(files[f"codec-{codec}.parquet"], column)
            assert len(expected) == len(got)
            for (_, e), (c, g) in zip(expected, got, strict=True):
                assert c != "UNCOMPRESSED"
                assert e == g, f"codec-{codec} column {column}"
                checked += 1
    assert checked >= 21
