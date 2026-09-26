"""The reader's small pieces, each checked on a case worked by hand. The Rust modules of the same
names carry the same tests."""

from __future__ import annotations

import pytest
from parquet_lab.bytes import (
    ByteReader,
    Span,
    UnexpectedEnd,
    VarintTooLong,
    crc32,
    le_terms,
    read_le_u32,
    zigzag_decode,
)
from parquet_lab.format import (
    BadMagic,
    EncryptedFooter,
    FooterLengthTooLarge,
    TooShort,
    footer_span,
    parse_trailer,
)
from parquet_lab.layout import Layout, Query, Table, encode, ranges
from parquet_lab.object_store import (
    Bounded,
    MemoryStore,
    NetworkModel,
    RangeNotSatisfiable,
    Suffix,
    TracingStore,
)
from parquet_lab.thrift import Struct, TooDeep, read_struct


def test_little_endian_puts_the_least_significant_byte_first():
    assert read_le_u32(bytes([0x7C, 0x01, 0x00, 0x00])) == 380
    assert read_le_u32(bytes([0x00, 0x00, 0x00, 0x01])) == 1 << 24


def test_le_terms_sum_to_the_value():
    data = bytes([0x7C, 0x01, 0x00, 0x00])
    assert sum(b * w for b, w in le_terms(data)) == read_le_u32(data)


def test_zigzag_interleaves_the_signed_integers():
    assert [zigzag_decode(n) for n in range(6)] == [0, -1, 1, -2, 2, -3]
    assert zigzag_decode(2**64 - 1) == -(2**63)


def test_uleb128_reads_seven_bits_per_byte():
    r = ByteReader(bytes([0x96, 0x01, 0x05]), 100)
    assert r.read_uleb128() == 150
    assert r.offset() == 102
    assert r.read_uleb128() == 5
    assert r.is_at_end()


def test_a_varint_that_never_ends_is_an_error_not_a_crash():
    with pytest.raises(VarintTooLong, match="offset 0"):
        ByteReader(bytes([0xFF] * 11), 0).read_uleb128()
    with pytest.raises(UnexpectedEnd, match="at offset 9"):
        ByteReader(bytes([0x80, 0x80]), 7).read_uleb128()


def test_crc32_matches_the_standard_check_value():
    assert crc32(b"123456789") == 0xCBF43926
    assert crc32(b"") == 0


def test_spans_are_absolute_file_offsets():
    r = ByteReader(b"abcdef", 1000)
    r.read_u8()
    data, span = r.read_bytes(3)
    assert data == b"bcd"
    assert span == Span(1001, 1004)
    assert span.http_range() == "bytes=1001-1003"


def test_the_trailer_is_a_length_and_the_magic():
    t = parse_trailer(bytes([0x7C, 0x01, 0, 0]) + b"PAR1", 1000)
    assert t.footer_length == 380
    assert t.span == Span(992, 1000)
    assert footer_span(1000, 380) == Span(612, 992)


def test_a_lying_trailer_is_refused():
    with pytest.raises(TooShort):
        parse_trailer(b"\0\0\0\0PAR1", 11)
    with pytest.raises(BadMagic, match="found 50 41 52 32"):
        parse_trailer(b"\0\0\0\0PAR2", 100)
    with pytest.raises(EncryptedFooter):
        parse_trailer(b"\0\0\0\0PARE", 100)
    with pytest.raises(FooterLengthTooLarge, match="only 88 bytes"):
        footer_span(100, 89)


def test_a_struct_decodes_field_by_field():
    # Field 1, i32 zigzag 150 (varint 0xac 0x02 is 300, zigzag 150); field 2, true; stop.
    node = read_struct(ByteReader(bytes([0x15, 0xAC, 0x02, 0x11, 0x00]), 50))
    s = node.value
    assert isinstance(s, Struct)
    assert s.field(1).node.value == 150
    assert s.field(2).node.value is True
    assert s.field(2).node.span == s.field(2).header
    assert node.span == Span(50, 55)


def test_nesting_has_a_limit():
    # A struct whose field 1 is a struct whose field 1 is a struct, and so on.
    with pytest.raises(TooDeep):
        read_struct(ByteReader(bytes([0x1C] * 200), 0))


def test_ranges_merge_only_when_they_touch():
    table = Table.sales()
    by_rows = encode(table, Layout.ROWS)
    by_columns = encode(table, Layout.COLUMNS)
    everything = Query(list(range(5)), list(range(8)))
    assert ranges(by_rows, everything) == [Span(0, len(by_rows.data))]
    one_column = Query([3], list(range(8)))
    assert len(ranges(by_columns, one_column)) == 1
    assert len(ranges(by_rows, one_column)) == 8


def test_the_store_serves_ranges_as_s3_does():
    store = MemoryStore()
    store.put("f", bytes(range(10)))
    assert store.get("f", Bounded(Span(8, 20)), "").data == bytes([8, 9])
    assert store.get("f", Suffix(100), "").span == Span(0, 10)
    with pytest.raises(RangeNotSatisfiable):
        store.get("f", Bounded(Span(10, 12)), "")


def test_connections_overlap_requests_and_phases_wait():
    store = MemoryStore()
    store.put("f", bytes(1000))
    traced = TracingStore(store, NetworkModel(1000, 0), connections=2)
    for _ in range(3):
        traced.get("f", Bounded(Span(0, 10)), "")
    assert [(r.start_us, r.connection) for r in traced.requests] == [(0, 0), (0, 1), (1000, 0)]
    traced.next_phase()
    traced.get("f", Bounded(Span(0, 10)), "")
    assert traced.requests[-1].start_us == 2000
