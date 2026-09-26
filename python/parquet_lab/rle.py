"""The RLE / bit-packing hybrid: how Parquet stores small integers (ch04, ch05).

Repetition levels, definition levels and dictionary indices are all small integers with a known
maximum, so they need only a few bits each. Parquet stores them as a sequence of runs, and each
run starts with a ULEB128 header whose lowest bit says what kind of run it is::

    header & 1 == 0   RLE run:         (header >> 1) copies of one value,
                                       stored in ceil(bit_width / 8) bytes, little-endian
    header & 1 == 1   bit-packed run:  (header >> 1) groups of eight values,
                                       each value bit_width bits, least significant bit first

A writer uses an RLE run where a value repeats and a bit-packed run where values vary. A column
with no nulls has definition levels that are all the maximum, and the whole page's levels become
one RLE run of a few bytes.

This decoder records every run with the bytes of its header and its body, so the browser can
show which bytes produced which levels.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span, UnexpectedEnd

RLE, BIT_PACKED = "RLE", "bit-packed"


def bit_width(max_value: int) -> int:
    """How many bits it take to store every integer from 0 to ``max_value``.

    ``bit_width(0)`` is 0: a column whose maximum level is 0 stores no levels at all.
    """
    return max_value.bit_length()


@dataclass
class Run:
    """One run, as decoded."""

    kind: str
    header: Span
    """The ULEB128 header."""
    body: Span
    """The bytes after the header that hold this run's values."""
    values: list[int]
    """The values this run contributed. A bit-packed run holds a multiple of eight values, and
    the last one in a stream may hold padding past the count; the padding is not included."""


def decode(data: bytes, base: int, width: int, count: int) -> list[Run]:
    """Decode ``count`` values of ``width`` bits from ``data``, which start at file offset
    ``base``."""
    r = ByteReader(data, base)
    runs = []
    produced = 0
    value_bytes = (width + 7) // 8
    while produced < count:
        header_start = r.offset()
        header = r.read_uleb128()
        header_span = Span(header_start, r.offset())
        wanted = count - produced
        if header & 1 == 0:
            # RLE: one value, repeated.
            raw, body = r.read_bytes(value_bytes)
            value = int.from_bytes(raw, "little")
            run = Run(RLE, header_span, body, [value] * min(header >> 1, wanted))
        else:
            # Bit-packed: groups of eight values, packed least significant bit first.
            groups = header >> 1
            raw, body = r.read_bytes(groups * width)
            n = min(groups * 8, wanted)
            run = Run(BIT_PACKED, header_span, body, [unpack(raw, i, width) for i in range(n)])
        if not run.values and run.body.length == 0:
            # A run that produces nothing and consumes nothing would loop forever.
            raise UnexpectedEnd(header_start, 1)
        produced += len(run.values)
        runs.append(run)
    return runs


def unpack(raw: bytes, i: int, width: int) -> int:
    """The ``i``\\ th value of ``width`` bits in a little-endian bit stream."""
    value = 0
    for bit in range(width):
        at = i * width + bit
        if raw[at // 8] >> (at % 8) & 1:
            value |= 1 << bit
    return value


def values(runs: list[Run]) -> list[int]:
    """All the values of a sequence of runs, in order."""
    return [v for run in runs for v in run.values]
