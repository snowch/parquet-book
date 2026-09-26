"""Decoding a page's values, whatever their encoding, with a record of how (ch05).

Every encoding turns bytes into values differently, but a reader wants the same thing from each:
the values, which bytes produced each one, and, for the book, the steps in between. This module
is that common shape, and the dispatch from an encoding's name to its decoder.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import plain, rle
from .bytes import Span
from .encoding import json_text
from .plain import PlainValue


@dataclass
class Step:
    """One step of a decode: a labelled range of bytes and what the decoder read from it."""

    label: str
    span: Span
    detail: str


@dataclass
class DecodedValue:
    value: PlainValue
    span: Span
    """The bytes that hold the value itself: its PLAIN bytes, its dictionary entry, its suffix."""
    extra: list[Span] = field(default_factory=list)
    """Other bytes it needed: an index run, a length, a prefix length, scattered stream bytes."""


@dataclass
class Decoded:
    values: list[DecodedValue]
    steps: list[Step]
    end: int
    """The first byte after the encoded values."""


Dictionary = list[tuple[PlainValue, Span]]
"""A decoded dictionary page: its values, each with the bytes it came from."""


class DecodeError(ValueError):
    def __init__(self, offset: int, what: str) -> None:
        super().__init__(f"offset {offset}: {what}")


def values(
    encoding: str,
    physical: int,
    type_length: int | None,
    data: bytes,
    base: int,
    count: int,
    dictionary: Dictionary | None,
) -> Decoded:
    """Decode ``count`` values of a column's physical type, encoded with ``encoding``."""
    from . import delta

    if encoding == "PLAIN":
        found = plain.decode(physical, type_length, data, base, count)
        steps = [Step(f"value {i}", s, json_text(plain.to_json(v))) for i, (v, s) in enumerate(found)]
        end = found[-1][1].end if found else base
        return Decoded([DecodedValue(v, s) for v, s in found], steps, end)

    if encoding in ("RLE_DICTIONARY", "PLAIN_DICTIONARY"):
        if dictionary is None:
            raise DecodeError(base, "dictionary indices, but no dictionary page came first")
        # One byte of bit width, then the indices as an RLE / bit-packing hybrid with no length.
        if not data:
            raise DecodeError(base, "an empty page where the index bit width should be")
        width = data[0]
        runs = rle.decode(data[1:], base + 1, width, count)
        steps = [
            Step(
                "bit width",
                Span(base, base + 1),
                f"{width} bits per index: enough for {len(dictionary)} dictionary entries",
            )
        ]
        found = []
        for n, run in enumerate(runs):
            steps.append(
                Step(
                    f"run {n}",
                    Span(run.header.start, run.body.end),
                    f"{run.kind}: indices {run.values}",
                )
            )
            for i in run.values:
                if i >= len(dictionary):
                    raise DecodeError(
                        run.body.start, f"index {i} is past the dictionary's {len(dictionary)} entries"
                    )
                v, s = dictionary[i]
                found.append(DecodedValue(v, s, [run.body]))
        end = runs[-1].body.end if runs else base + 1
        return Decoded(found, steps, end)

    if encoding == "DELTA_BINARY_PACKED":
        ints = delta.binary_packed(data, base)
        if len(ints.values) != count:
            raise DecodeError(base, f"the header counts {len(ints.values)} values, the page {count}")
        # An INT32 column's deltas wrap at 32 bits.
        wrap = (lambda v: (v + 2**31) % 2**32 - 2**31) if physical == 1 else (lambda v: v)
        return Decoded([DecodedValue(wrap(v), s) for v, s in ints.values], ints.steps, ints.end)

    if encoding == "DELTA_LENGTH_BYTE_ARRAY":
        return delta.length_byte_array(data, base)
    if encoding == "DELTA_BYTE_ARRAY":
        return delta.byte_array(data, base)

    if encoding == "BYTE_STREAM_SPLIT":
        widths = {1: 4, 4: 4, 2: 8, 5: 8}
        if physical in widths:
            width = widths[physical]
        elif physical == 7:
            width = max(type_length or 0, 0)
        else:
            raise DecodeError(base, "BYTE_STREAM_SPLIT on a type it does not apply to")
        split = delta.byte_stream_split(data, base, width, count)
        steps = [
            Step(f"stream {k}", Span(base + k * count, base + k * count + count), f"byte {k} of every value")
            for k in range(width)
        ]
        formats = {(4, 4): "<f", (5, 8): "<d", (1, 4): "<i", (2, 8): "<q"}
        found = []
        for raw, spans in split:
            f = formats.get((physical, len(raw)))
            value = struct.unpack(f, raw)[0] if f else raw
            found.append(DecodedValue(value, spans[0], spans[1:]))
        return Decoded(found, steps, base + width * count)

    raise DecodeError(base, f"the {encoding} encoding is not implemented by this reader")
