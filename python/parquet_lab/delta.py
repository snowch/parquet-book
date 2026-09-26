"""The delta encodings, and BYTE_STREAM_SPLIT (ch05).

**DELTA_BINARY_PACKED** stores integers as differences. Sorted or slowly changing values (ids,
timestamps, counters) have small differences, and small differences pack into few bits::

    header:  block size · miniblocks per block · value count · first value (zigzag)
    block:   min delta (zigzag) · one bit width per miniblock · the miniblocks, bit-packed

Each block subtracts its smallest delta from every delta, so all of them are zero or more, and
each miniblock packs its adjusted deltas in the fewest bits that hold its largest. A run of values
one apart has every adjusted delta zero, and bit width zero: the miniblock takes no bytes at all.

**DELTA_LENGTH_BYTE_ARRAY** stores every string's length first, delta-packed, then all the bytes
back to back. **DELTA_BYTE_ARRAY** stores, for each string, how many leading bytes it shares with
the previous one, then only the rest: sorted keys, paths and URLs shrink.

**BYTE_STREAM_SPLIT** does not shrink anything. It writes every value's first byte, then every
value's second byte, and so on, which puts the slowly varying bytes of floats together for a
compressor to find (ch07).
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span, UnexpectedEnd
from .decode import Decoded, DecodedValue, Step


def _i64(v: int) -> int:
    """Wrap to a signed 64-bit integer, as the deltas' arithmetic does."""
    return (v + 2**63) % 2**64 - 2**63


def _size(n: int) -> int:
    """A length as an unsigned size: a negative one cannot be read, and asks for too much."""
    return n if n >= 0 else n % 2**64


@dataclass
class Integers:
    """What DELTA_BINARY_PACKED decodes to: integers with the bytes of their miniblock, the steps
    that produced them, and the first byte after the encoding."""

    values: list[tuple[int, Span]]
    steps: list[Step]
    end: int


def binary_packed(data: bytes, base: int) -> Integers:
    """Integers from DELTA_BINARY_PACKED, with the steps that produced them."""
    r = ByteReader(data, base)
    steps = []
    start = r.offset()
    block_size = r.read_uleb128()
    miniblocks = max(r.read_uleb128(), 1)
    total = r.read_uleb128()
    first = r.read_zigzag()
    steps.append(
        Step(
            "header",
            Span(start, r.offset()),
            f"blocks of {block_size} values in {miniblocks} miniblocks; {total} values; the first is {first}",
        )
    )
    per_miniblock = block_size // miniblocks
    out: list[tuple[int, Span]] = []
    if total == 0:
        return Integers(out, steps, r.offset())
    out.append((first, Span(start, r.offset())))
    prev = first
    block = 0
    while len(out) < total:
        block_start = r.offset()
        min_delta = r.read_zigzag()
        widths = list(r.read_bytes(miniblocks)[0])
        steps.append(
            Step(
                f"block {block}",
                Span(block_start, r.offset()),
                f"smallest delta {min_delta}; bit widths {widths}",
            )
        )
        for m, w in enumerate(widths):
            if len(out) >= total:
                break  # Unneeded miniblocks have a width byte and no body.
            raw, span = r.read_bytes(per_miniblock * w // 8)
            deltas = []
            for i in range(per_miniblock):
                if len(out) >= total:
                    break
                packed = 0
                for bit in range(w):
                    at = i * w + bit
                    if raw[at // 8] >> (at % 8) & 1:
                        packed |= 1 << (bit % 64)
                delta = _i64(min_delta + _i64(packed))
                prev = _i64(prev + delta)
                deltas.append(delta)
                out.append((prev, span))
            steps.append(Step(f"block {block}, miniblock {m}", span, f"{w} bits per delta; deltas {deltas}"))
        block += 1
    return Integers(out, steps, r.offset())


def length_byte_array(data: bytes, base: int) -> Decoded:
    """DELTA_LENGTH_BYTE_ARRAY: delta-packed lengths, then the bytes of every value in one run."""
    lengths = binary_packed(data, base)
    steps = [Step(f"lengths: {s.label}", s.span, s.detail) for s in lengths.steps]
    r = ByteReader(data[lengths.end - base :], lengths.end)
    values = []
    data_start = r.offset()
    for n, n_span in lengths.values:
        value, span = r.read_bytes(_size(n))
        values.append(DecodedValue(value, span, [n_span]))
    steps.append(Step("bytes", Span(data_start, r.offset()), f"{len(values)} values' bytes, back to back"))
    return Decoded(values, steps, r.offset())


def byte_array(data: bytes, base: int) -> Decoded:
    """DELTA_BYTE_ARRAY: shared-prefix lengths, then the suffixes as DELTA_LENGTH_BYTE_ARRAY."""
    prefixes = binary_packed(data, base)
    steps = [Step(f"prefix lengths: {s.label}", s.span, s.detail) for s in prefixes.steps]
    suffixes = length_byte_array(data[prefixes.end - base :], prefixes.end)
    steps += [Step(f"suffixes: {s.label}", s.span, s.detail) for s in suffixes.steps]
    prev = b""
    values = []
    for (prefix, prefix_span), suffix in zip(prefixes.values, suffixes.values, strict=False):
        value = prev[: min(_size(prefix), len(prev))] + suffix.value
        prev = value
        values.append(DecodedValue(value, suffix.span, [prefix_span, *suffix.extra]))
    return Decoded(values, steps, suffixes.end)


def byte_stream_split(data: bytes, base: int, width: int, count: int) -> list[tuple[bytes, list[Span]]]:
    """BYTE_STREAM_SPLIT: ``count`` values of ``width`` bytes, stored as ``width`` streams of
    ``count`` bytes. Value ``i``'s byte ``k`` is at ``k * count + i``."""
    if len(data) < width * count:
        raise UnexpectedEnd(base + len(data), width * count - len(data))
    return [
        (
            bytes(data[k * count + i] for k in range(width)),
            [Span(base + k * count + i, base + k * count + i + 1) for k in range(width)],
        )
        for i in range(count)
    ]
