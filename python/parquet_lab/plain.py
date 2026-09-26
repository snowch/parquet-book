"""PLAIN encoding: values written back to back (ch04, ch05).

The simplest encoding, and the one every other encoding falls back to:

- fixed-width numbers (``INT32``, ``INT64``, ``FLOAT``, ``DOUBLE``) are little-endian, in full;
- ``FIXED_LEN_BYTE_ARRAY`` values are their bytes, each the length the schema declares;
- ``BYTE_ARRAY`` values are a four-byte little-endian length, then the bytes;
- ``BOOLEAN`` values are bit-packed, one bit each, least significant bit first.

Only non-null values are stored. A null has a definition level and nothing here.

A decoded value, before any logical type is applied, is a Python ``bool``, ``int``, ``float``
or ``bytes``.
"""

from __future__ import annotations

import struct

from .bytes import ByteReader, Span, UnexpectedEnd
from .encoding import hex

PlainValue = bool | int | float | bytes


def to_plain_bytes(value: PlainValue, physical: int) -> bytes:
    """The value's PLAIN bytes for a column of physical type ``physical``, without the length
    prefix a byte array has in a page. Statistics store values this way (ch08)."""
    if isinstance(value, bool):
        return bytes([int(value)])
    if isinstance(value, int):
        return struct.pack("<i", _wrap32(value)) if physical == 1 else struct.pack("<q", value)
    if isinstance(value, float):
        return struct.pack("<f", value) if physical == 4 else struct.pack("<d", value)
    return bytes(value)


def _wrap32(v: int) -> int:
    return (v + 2**31) % 2**32 - 2**31


def to_json(value: PlainValue) -> object:
    """As JSON: text for bytes that are UTF-8, and a hex string for bytes that are not."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return hex(value)
    return value


def decode(
    physical: int, type_length: int | None, data: bytes, base: int, count: int
) -> list[tuple[PlainValue, Span]]:
    """Decode ``count`` PLAIN values of a physical type from ``data``, which starts at ``base``.
    Each value comes back with the span it occupied."""
    r = ByteReader(data, base)
    out: list[tuple[PlainValue, Span]] = []
    if physical == 0:
        # BOOLEAN: one bit per value. A value's span is the byte its bit sits in.
        raw, span = r.read_bytes((count + 7) // 8)
        for i in range(count):
            byte = span.start + i // 8
            out.append((raw[i // 8] >> (i % 8) & 1 == 1, Span(byte, byte + 1)))
        return out
    for _ in range(count):
        start = r.offset()
        if physical == 1:
            value: PlainValue = struct.unpack("<i", r.read_bytes(4)[0])[0]
        elif physical == 2:
            value = struct.unpack("<q", r.read_bytes(8)[0])[0]
        elif physical == 3:
            value = r.read_bytes(12)[0]
        elif physical == 4:
            value = struct.unpack("<f", r.read_bytes(4)[0])[0]
        elif physical == 5:
            value = struct.unpack("<d", r.read_bytes(8)[0])[0]
        elif physical == 6:
            value = r.read_bytes(r.read_le_u32())[0]
        elif physical == 7:
            value = r.read_bytes(max(type_length or 0, 0))[0]
        else:
            raise UnexpectedEnd(start, 0)
        out.append((value, Span(start, r.offset())))
    return out
