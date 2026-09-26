"""Pages: walking a column chunk one page header at a time (ch06).

A column chunk is a run of pages laid end to end. Each page is a Thrift ``PageHeader`` followed
by ``compressed_page_size`` bytes of body. The header says how long the body is, and so where the
next header starts, which is how a reader walks a chunk without any index.

This module reads the headers, measures the bodies, and checks each body against the CRC its
header carries, when it carries one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span, crc32
from .metadata import Statistics, as_struct, opt_bool, opt_int, req_int, statistics
from .parquet_thrift import enum_value_name
from .thrift import Node, read_struct


@dataclass
class PageV2:
    """What a data page version 2 header adds (ch06)."""

    num_nulls: int
    num_rows: int
    definition_levels_byte_length: int
    """The level streams' lengths: in version 2 they are in the header, not the body."""
    repetition_levels_byte_length: int
    is_compressed: bool
    """Whether the values section is compressed. The levels never are."""


@dataclass
class Page:
    page_type: str
    header_span: Span
    """The Thrift header."""
    body_span: Span
    """The body that follows it: ``compressed_page_size`` bytes."""
    uncompressed_page_size: int
    compressed_page_size: int
    num_values: int | None
    encoding: str | None
    statistics: Statistics | None
    crc: int | None
    """The checksum the header carries, and whether the body still matches it."""
    crc_ok: bool | None
    v2: PageV2 | None
    """Data page version 2's extra fields."""
    header: Node

    def span(self) -> Span:
        return Span(self.header_span.start, self.body_span.end)


def walk_pages(chunk: bytes, base: int) -> list[Page]:
    """Walk the pages of a column chunk whose bytes are ``chunk``, starting at file offset
    ``base``.

    Stops at the end of the chunk. A page whose body would run past the end is an error: the
    chunk's size in the footer and the sizes in its page headers must agree.
    """
    r = ByteReader(chunk, base)
    pages = []
    while not r.is_at_end():
        pages.append(read_page(r))
    return pages


def read_page(r: ByteReader) -> Page:
    """Read one page: its header, and the body the header measures. The reader is left after
    it."""
    header = read_struct(r)
    h = as_struct(header)
    ph = "PageHeader"
    page_type = req_int(h, ph, 1, "type", header.span)
    uncompressed = req_int(h, ph, 2, "uncompressed_page_size", header.span)
    compressed = req_int(h, ph, 3, "compressed_page_size", header.span)
    # The sub-header that matches the page type: 5 for a v1 data page, 7 for a dictionary page,
    # 8 for a v2 data page. All three put num_values in field 1; the encoding is in field 2 for
    # v1 and dictionary pages and field 4 for v2.
    sub_field, encoding_field = {0: (5, 2), 2: (7, 2), 3: (8, 4)}.get(page_type, (None, 0))
    f = h.field(sub_field) if sub_field is not None else None
    sub = as_struct(f.node) if f else None
    stats_field = {0: 5, 3: 8}.get(page_type, 0)
    stats = sub.field(stats_field) if sub else None
    page_statistics = statistics(stats.node) if stats else None
    # A negative size cannot be read; asking for more bytes than exist reports where it failed.
    body, body_span = r.read_bytes(compressed if compressed >= 0 else 2**64 - 1)
    crc = opt_int(h, 4)
    # The header stores the CRC as a signed 32-bit integer.
    crc_ok = (crc & 0xFFFF_FFFF) == crc32(body) if crc is not None else None
    v2 = None
    if page_type == 3 and sub is not None:
        v2 = PageV2(
            num_nulls=opt_int(sub, 2) or 0,
            num_rows=opt_int(sub, 3) or 0,
            definition_levels_byte_length=opt_int(sub, 5) or 0,
            repetition_levels_byte_length=opt_int(sub, 6) or 0,
            is_compressed=True if opt_bool(sub, 7) is None else opt_bool(sub, 7),
        )
    encoding = opt_int(sub, encoding_field) if sub else None
    return Page(
        page_type=enum_value_name("PageType", page_type) or f"UNKNOWN({page_type})",
        header_span=header.span,
        body_span=body_span,
        uncompressed_page_size=uncompressed,
        compressed_page_size=compressed,
        num_values=opt_int(sub, 1) if sub else None,
        encoding=enum_value_name("Encoding", encoding) if encoding is not None else None,
        statistics=page_statistics,
        crc=crc,
        crc_ok=crc_ok,
        v2=v2,
        header=header,
    )
