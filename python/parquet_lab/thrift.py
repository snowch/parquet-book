"""Apache Thrift's compact protocol, decoded without knowing the schema.

Parquet serialises its footer and every page header with Thrift's compact protocol. The
protocol is self-delimiting: every field carries its own id and wire type, so a decoder can walk
a message it has no schema for. This one does exactly that, and records the span of every field
header and every value on the way.

Names come later, from :mod:`parquet_lab.parquet_thrift`, which knows that field 3 of a
``FileMetaData`` is ``num_rows``. Keeping the two apart is deliberate. The wire format is small
and regular; the Parquet schema is large and grows with every format release. A field this
decoder has never heard of still decodes, keeps its bytes, and shows up in the browser as
"field 17, a struct", which is how a reader stays forward-compatible.

The encoding, in the order this module reads it:

- A **field header** is one byte. The high four bits are the difference between this field's id
  and the previous one; the low four bits are the wire type. A difference of 0 means the id
  follows as a zigzag varint.
- **Booleans** live in the header: wire type 1 is true, 2 is false. No value bytes follow.
- **Integers** of every width are zigzag varints. **Doubles** are eight bytes, little-endian.
- **Binary** (strings too) is a varint length and then the bytes.
- A **list** header is one byte: the size in the high four bits (15 means a varint size
  follows) and the element type in the low four.
- A **struct** is fields until a header byte of 0, the stop field.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum

from .bytes import ByteReader, Span


class WireType(Enum):
    """The compact protocol's wire types, by the nibble that names them."""

    BOOL_TRUE = 1
    BOOL_FALSE = 2
    BYTE = 3
    I16 = 4
    I32 = 5
    I64 = 6
    DOUBLE = 7
    BINARY = 8
    LIST = 9
    SET = 10
    MAP = 11
    STRUCT = 12
    UUID = 13

    @staticmethod
    def from_nibble(n: int) -> WireType | None:
        try:
            return WireType(n)
        except ValueError:
            return None

    @property
    def type_name(self) -> str:
        return _NAMES[self]


_NAMES = {
    WireType.BOOL_TRUE: "bool",
    WireType.BOOL_FALSE: "bool",
    WireType.BYTE: "i8",
    WireType.I16: "i16",
    WireType.I32: "i32",
    WireType.I64: "i64",
    WireType.DOUBLE: "double",
    WireType.BINARY: "binary",
    WireType.LIST: "list",
    WireType.SET: "set",
    WireType.MAP: "map",
    WireType.STRUCT: "struct",
    WireType.UUID: "uuid",
}


@dataclass
class Node:
    """A decoded value, with the bytes it came from.

    ``value`` is a ``bool``, an ``int``, a ``float``, ``bytes``, a ``list`` of nodes, a
    :class:`Map`, or a :class:`Struct`.
    """

    span: Span
    value: object


class Map(list):
    """A Thrift map: a list of ``(key, value)`` node pairs, in the order they were written."""


@dataclass
class Field:
    """One field of a struct: its id, its wire type, the span of its header, and its value."""

    id: int
    wire: WireType
    header: Span
    """The header byte, plus the id varint when the delta did not fit in four bits."""
    node: Node

    def span(self) -> Span:
        """Everything this field occupies: header and value together."""
        return Span(self.header.start, max(self.node.span.end, self.header.end))


@dataclass
class Struct:
    fields: list[Field] = field(default_factory=list)

    def field(self, id: int) -> Field | None:
        return next((f for f in self.fields if f.id == id), None)


class ThriftError(ValueError):
    pass


class UnknownWireType(ThriftError):
    def __init__(self, nibble: int, offset: int) -> None:
        super().__init__(f"unknown Thrift wire type {nibble} at offset {offset}")


class TooDeep(ThriftError):
    def __init__(self, offset: int) -> None:
        super().__init__(f"structures nested too deeply at offset {offset}")


MAX_DEPTH = 64
"""How deep structs and lists may nest. Parquet's deepest is about six; a corrupt or hostile
footer should hit this long before it exhausts the stack."""


def _i16(v: int) -> int:
    """Wrap an integer to 16 bits, as the field id it will be stored as."""
    return (v + 0x8000) % 0x10000 - 0x8000


def read_struct(r: ByteReader) -> Node:
    """Decode one struct, starting at the reader's position, up to and including its stop
    byte."""
    return _read_struct(r, 0)


def _read_struct(r: ByteReader, depth: int) -> Node:
    if depth > MAX_DEPTH:
        raise TooDeep(r.offset())
    start = r.offset()
    fields = []
    last_id = 0
    while True:
        header_start = r.offset()
        byte = r.read_u8()
        if byte == 0:
            break  # the stop field
        delta = byte >> 4
        nibble = byte & 0x0F
        wire = WireType.from_nibble(nibble)
        if wire is None:
            raise UnknownWireType(nibble, header_start)
        if delta == 0:
            id = _i16(r.read_zigzag())
        else:
            id = _i16(last_id + delta)
        last_id = id
        header = Span(header_start, r.offset())
        # A field's boolean is its header's type nibble. It has no bytes of its own, so its span
        # is the header.
        if wire is WireType.BOOL_TRUE:
            node = Node(header, True)
        elif wire is WireType.BOOL_FALSE:
            node = Node(header, False)
        else:
            node = _read_value(r, wire, depth + 1)
        fields.append(Field(id, wire, header, node))
    return Node(Span(start, r.offset()), Struct(fields))


def _read_value(r: ByteReader, wire: WireType, depth: int) -> Node:
    start = r.offset()
    if wire in (WireType.BOOL_TRUE, WireType.BOOL_FALSE):
        # Inside a list a boolean has no header to hide in, so it takes a byte: 1 is true.
        value: object = r.read_u8() == 1
    elif wire is WireType.BYTE:
        value = struct.unpack("b", bytes([r.read_u8()]))[0]
    elif wire in (WireType.I16, WireType.I32, WireType.I64):
        value = r.read_zigzag()
    elif wire is WireType.DOUBLE:
        value = struct.unpack("<d", r.read_bytes(8)[0])[0]
    elif wire is WireType.BINARY:
        value = r.read_bytes(r.read_uleb128())[0]
    elif wire is WireType.UUID:
        value = r.read_bytes(16)[0]
    elif wire in (WireType.LIST, WireType.SET):
        header = r.read_u8()
        size = r.read_uleb128() if header >> 4 == 15 else header >> 4
        nibble = header & 0x0F
        elem = WireType.from_nibble(nibble)
        if elem is None:
            raise UnknownWireType(nibble, start)
        value = [_read_element(r, elem, depth) for _ in range(size)]
    elif wire is WireType.MAP:
        size = r.read_uleb128()
        value = Map()
        if size > 0:
            types = r.read_u8()
            k, v = WireType.from_nibble(types >> 4), WireType.from_nibble(types & 0x0F)
            if k is None:
                raise UnknownWireType(types >> 4, start)
            if v is None:
                raise UnknownWireType(types & 0x0F, start)
            for _ in range(size):
                value.append((_read_element(r, k, depth), _read_element(r, v, depth)))
    else:  # a struct
        return _read_struct(r, depth)
    return Node(Span(start, r.offset()), value)


def _read_element(r: ByteReader, wire: WireType, depth: int) -> Node:
    if depth > MAX_DEPTH:
        raise TooDeep(r.offset())
    return _read_value(r, wire, depth + 1)
