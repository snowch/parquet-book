"""Bloom filters: a compact "definitely not here" for one column chunk (ch09).

Statistics rule out a value outside a chunk's range. They cannot rule out a value inside it: a
chunk of customer numbers from 100000 to 999999 may or may not hold 424242. A Bloom filter can.
It is a bitset. To add a value, a writer hashes it and sets a few bits the hash picks. To test a
value, a reader hashes it and checks those bits: if any is clear, the value was never added. If
all are set, it may have been, or other values may have set them: a false positive.

Parquet uses one kind: the **split block Bloom filter**. The bitset is a run of 32-byte blocks,
each eight 32-bit words. A value's hash picks one block, then one bit in each of its eight words.
The hash is xxHash64 of the value's PLAIN bytes, with seed 0. ::

    [BloomFilterHeader, Thrift]   numBytes, algorithm, hash, compression
    [bitset]                      numBytes bytes: numBytes / 32 blocks
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span
from .metadata import ColumnChunk, as_struct, req_int
from .thrift import Node, Struct, read_struct


class BloomError(ValueError):
    pass


MASK = 2**64 - 1
P1 = 0x9E37_79B1_85EB_CA87
P2 = 0xC2B2_AE3D_27D4_EB4F
P3 = 0x1656_67B1_9E37_79F9
P4 = 0x85EB_CA77_C2B2_AE63
P5 = 0x27D4_EB2F_1656_67C5


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (64 - r))) & MASK


def _round(acc: int, lane: int) -> int:
    return _rotl((acc + lane * P2) & MASK, 31) * P1 & MASK


def _merge(acc: int, v: int) -> int:
    return ((acc ^ _round(0, v)) * P1 + P4) & MASK


def xxh64(data: bytes, seed: int = 0) -> int:
    """xxHash64, as its specification describes it: four accumulators over 32-byte stripes,
    then the tail eight, four and one bytes at a time, then a final mixing of the bits. Python
    integers do not wrap, so every step is masked to 64 bits."""

    def u64_at(i: int) -> int:
        return int.from_bytes(data[i : i + 8], "little")

    i = 0
    if len(data) >= 32:
        v = [(seed + P1 + P2) & MASK, (seed + P2) & MASK, seed, (seed - P1) & MASK]
        while i + 32 <= len(data):
            v = [_round(acc, u64_at(i + 8 * k)) for k, acc in enumerate(v)]
            i += 32
        h = (_rotl(v[0], 1) + _rotl(v[1], 7) + _rotl(v[2], 12) + _rotl(v[3], 18)) & MASK
        for acc in v:
            h = _merge(h, acc)
    else:
        h = (seed + P5) & MASK
    h = (h + len(data)) & MASK
    while i + 8 <= len(data):
        h ^= _round(0, u64_at(i))
        h = (_rotl(h, 27) * P1 + P4) & MASK
        i += 8
    if i + 4 <= len(data):
        h ^= int.from_bytes(data[i : i + 4], "little") * P1 & MASK
        h = (_rotl(h, 23) * P2 + P3) & MASK
        i += 4
    for b in data[i:]:
        h ^= b * P5 & MASK
        h = _rotl(h, 11) * P1 & MASK
    h ^= h >> 33
    h = h * P2 & MASK
    h ^= h >> 29
    h = h * P3 & MASK
    return h ^ (h >> 32)


SALT = [0x47B6137B, 0x44974D91, 0x8824AD5B, 0xA2B7289D, 0x705495C7, 0x2DF1424B, 0x9EFC4947, 0x5C6BFB31]
"""The eight odd constants the format fixes, one per word of a block."""


@dataclass
class Probe:
    """What a probe for one value did: its hash, the block that hash chose, the bit it tested in
    each of the block's words, and whether every one was set."""

    hash: int
    block: int
    bits: list[tuple[int, bool]]
    may_contain: bool


@dataclass
class BloomFilter:
    """A decoded filter: where its header and bitset are, and the bitset itself."""

    header: Node
    header_span: Span
    bitset_span: Span
    bitset: bytes

    def num_blocks(self) -> int:
        return len(self.bitset) // 32

    def block_span(self, block: int) -> Span:
        """The bytes of the block a probe tests."""
        start = self.bitset_span.start + 32 * block
        return Span(start, start + 32)

    def probe(self, value: bytes) -> Probe:
        """Test a value, given as its PLAIN bytes (without a length prefix for byte arrays)."""
        return self.probe_hash(xxh64(value, 0))

    def probe_hash(self, hash: int) -> Probe:
        # The high 32 bits choose the block, scaled to the number of blocks without a division.
        block = ((hash >> 32) * self.num_blocks()) >> 32
        # The low 32 bits, multiplied by each salt, choose one bit in each word: the top five bits
        # of the product are a bit position from 0 to 31.
        key = hash & 0xFFFF_FFFF
        bits = []
        for w, salt in enumerate(SALT):
            position = ((key * salt) & 0xFFFF_FFFF) >> 27
            at = 32 * block + 4 * w
            word = int.from_bytes(self.bitset[at : at + 4], "little")
            bits.append((position, bool(word >> position & 1)))
        return Probe(hash, block, bits, all(b for _, b in bits))


def read(file: bytes, chunk: ColumnChunk) -> BloomFilter | None:
    """Read a column chunk's Bloom filter, if it has one."""
    offset = chunk.bloom_filter_offset
    if offset is None:
        return None

    def bad(what: str) -> BloomError:
        return BloomError(f"Bloom filter at offset {offset}: {what}")

    start = max(offset, 0)
    if start > len(file):
        raise bad("the Bloom filter starts past the end of the file")
    r = ByteReader(file[start:], offset)
    try:
        header = read_struct(r)
        h = as_struct(header)
        num_bytes = req_int(h, "BloomFilterHeader", 1, "numBytes", header.span)
    except ValueError as e:
        raise bad(str(e)) from e
    # Only one algorithm, hash and compression are defined; each is a union whose field 1 is it.
    for id, what in ((2, "algorithm BLOCK"), (3, "hash XXHASH"), (4, "compression UNCOMPRESSED")):
        f = h.field(id)
        if not (f and isinstance(f.node.value, Struct) and f.node.value.field(1)):
            raise bad(f"a Bloom filter that is not {what}")
    if num_bytes <= 0 or num_bytes % 32 != 0:
        raise bad("a Bloom filter bitset must be a whole number of 32-byte blocks")
    try:
        bitset, bitset_span = r.read_bytes(num_bytes)
    except ValueError as e:
        raise bad(str(e)) from e
    return BloomFilter(header, header.span, bitset_span, bitset)
