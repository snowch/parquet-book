"""Split block Bloom filters (ch09): where a column chunk's filter is, and its parts.

Probing a filter arrives with ch09. The structure view needs only to find the filter's header
and bitset.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import ByteReader, Span
from .metadata import ColumnChunk, as_struct, req_int
from .thrift import Node, Struct, read_struct


class BloomError(ValueError):
    pass


@dataclass
class BloomFilter:
    """A decoded filter: where its header and bitset are, and the bitset itself."""

    header: Node
    header_span: Span
    bitset_span: Span
    bitset: bytes

    def num_blocks(self) -> int:
        return len(self.bitset) // 32


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
