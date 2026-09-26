"""Binary primitives: the handful of ways Parquet turns bytes into numbers.

Everything else in this package is built from these. A Parquet file uses three integer
encodings, and this module has one function for each:

- fixed-width little-endian integers, for the footer length and PLAIN values;
- ULEB128 variable-length integers ("varints"), for Thrift lengths and sizes;
- zigzag, which maps signed integers onto unsigned ones so small negatives stay small.

Every read reports *where* it read from, as a :class:`Span` of absolute file offsets. The
browser uses those spans to answer the question the book keeps asking: which bytes caused this
value?
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Span:
    """A half-open range of absolute file offsets: ``start`` is included, ``end`` is not.

    Half-open because lengths then fall out as ``end - start``, and two adjacent spans share an
    endpoint instead of overlapping by one.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"a span cannot end before it starts: {self.start}..{self.end}")

    @property
    def length(self) -> int:
        return self.end - self.start

    def contains(self, other: Span) -> bool:
        return self.start <= other.start and other.end <= self.end

    def http_range(self) -> str:
        """The HTTP ``Range`` header for these bytes. HTTP ranges are inclusive at both ends, so
        the last byte is ``end - 1``. Getting this wrong by one is the classic range-request bug.
        """
        return f"bytes={self.start}-{self.end - 1}"

    def __str__(self) -> str:
        return f"[{self.start}, {self.end})"


class BytesError(ValueError):
    """What went wrong while reading bytes, and where."""


class UnexpectedEnd(BytesError):
    """Asked for ``wanted`` bytes at ``offset``, but the buffer ends first."""

    def __init__(self, offset: int, wanted: int) -> None:
        super().__init__(f"needed {wanted} more byte(s) at offset {offset}, but the data ends")
        self.offset, self.wanted = offset, wanted


class VarintTooLong(BytesError):
    """A varint ran past the width of the integer it encodes."""

    def __init__(self, offset: int) -> None:
        super().__init__(f"varint starting at offset {offset} is longer than 10 bytes")
        self.offset = offset


def read_le_u32(data: bytes) -> int:
    """Read four bytes as an unsigned little-endian integer: the first byte is the least
    significant.

    ``7c 01 00 00`` is ``0x7c + 0x01 × 256 = 380``.
    """
    return data[0] | data[1] << 8 | data[2] << 16 | data[3] << 24


def le_terms(data: bytes) -> list[tuple[int, int]]:
    """Each byte of a little-endian integer with the weight it is multiplied by.

    The sum of ``byte × weight`` over the terms is the value. The browser prints this so the
    arithmetic behind a decoded length is on the screen, not only its answer.
    """
    return [(b, 1 << (8 * i)) for i, b in enumerate(data)]


def zigzag_decode(n: int) -> int:
    """Map an unsigned zigzag value back to the signed integer it encodes.

    Zigzag interleaves the signed integers: 0, -1, 1, -2, 2 … become 0, 1, 2, 3, 4 …. A small
    negative number therefore stays a small varint instead of becoming a huge two's-complement
    one.
    """
    return (n >> 1) ^ -(n & 1)


def crc32(data: bytes) -> int:
    """The CRC-32 checksum of ``data``: the IEEE polynomial, as zlib and Ethernet compute it.

    Parquet page headers may carry one over the page body, so a reader can tell a damaged page
    from a page whose values happen to look odd. Computed a bit at a time: slower than a table,
    and short enough to read.
    """
    crc = 0xFFFF_FFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB8_8320 if crc & 1 else 0)
    return crc ^ 0xFFFF_FFFF


class ByteReader:
    """A cursor over bytes that knows the absolute file offset of its first byte.

    The footer arrives as a separate buffer from the rest of the file, but every span this
    reader reports is an offset into the *file*. ``base`` is what makes those agree.
    """

    def __init__(self, data: bytes, base: int) -> None:
        self.data, self.base, self.pos = data, base, 0

    def offset(self) -> int:
        """The absolute file offset of the next byte to be read."""
        return self.base + self.pos

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def is_at_end(self) -> bool:
        return self.pos == len(self.data)

    def read_u8(self) -> int:
        if self.pos >= len(self.data):
            raise UnexpectedEnd(self.offset(), 1)
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_bytes(self, n: int) -> tuple[bytes, Span]:
        """Take the next ``n`` bytes, and the span they came from."""
        if self.remaining() < n:
            raise UnexpectedEnd(self.offset(), n)
        start = self.offset()
        chunk = bytes(self.data[self.pos : self.pos + n])
        self.pos += n
        return chunk, Span(start, start + n)

    def read_le_u32(self) -> int:
        return read_le_u32(self.read_bytes(4)[0])

    def read_le_u64(self) -> int:
        return int.from_bytes(self.read_bytes(8)[0], "little")

    def read_uleb128(self) -> int:
        """Read an unsigned LEB128 varint: seven bits of value per byte, least significant group
        first, and the high bit set on every byte except the last.

        ``96 01`` is ``0x16 + (0x01 << 7) = 150``.
        """
        start = self.offset()
        value = 0
        for i in range(10):
            byte = self.read_u8()
            value |= (byte & 0x7F) << (7 * i)
            if byte & 0x80 == 0:
                return value & 0xFFFF_FFFF_FFFF_FFFF
        raise VarintTooLong(start)

    def read_zigzag(self) -> int:
        """A zigzag varint: how Thrift's compact protocol writes every signed integer."""
        return zigzag_decode(self.read_uleb128())
