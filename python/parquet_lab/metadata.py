"""``FileMetaData``: the footer, read into Python types.

:mod:`parquet_lab.thrift` turns the footer's bytes into numbered fields. This module picks out
the fields a reader needs and gives them types: the schema, the row groups, and for every column
chunk the offsets and sizes that say where its bytes are.

It reads by field id, the way the Thrift definition does, so the numbers in this file are the ids
from ``parquet.thrift``. A field the reader does not need is left in the decoded tree and never
looked at.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import logical
from .bytes import ByteReader, Span
from .logical import LogicalType
from .parquet_thrift import enum_value_name
from .thrift import Node, Struct, read_struct


class MetadataError(ValueError):
    pass


class NotAStruct(MetadataError):
    def __init__(self, span: Span) -> None:
        super().__init__(f"expected a struct at {span}")


class Missing(MetadataError):
    def __init__(self, structure: str, name: str, span: Span) -> None:
        super().__init__(f"{structure} at {span} has no {name}, which is required")


class WrongType(MetadataError):
    def __init__(self, structure: str, name: str, span: Span) -> None:
        super().__init__(f"{structure}.{name} at {span} has the wrong wire type")


class TrailingBytes(MetadataError):
    def __init__(self, span: Span) -> None:
        super().__init__(
            "the footer's FileMetaData ends before the footer does; "
            f"{span.length} byte(s) left over at {span}"
        )


class PhysicalType(int):
    """A column's physical type: how its values are laid out in bytes (ch03)."""

    @property
    def name(self) -> str:
        return enum_name("Type", self)


@dataclass
class SchemaElement:
    """One node of the flattened schema: a leaf column or a group (ch03).

    The footer stores the schema tree as a list in depth-first order. A group says how many
    children follow it; a leaf has none.
    """

    name: str
    physical_type: PhysicalType | None
    type_length: int | None
    """For ``FIXED_LEN_BYTE_ARRAY``: how many bytes each value takes."""
    repetition: str | None
    num_children: int | None
    converted_type: str | None
    """The older annotation, kept by writers for readers that predate logical types."""
    logical_type: LogicalType | None
    scale: int | None
    precision: int | None
    field_id: int | None
    """An identifier that survives renames; table formats use it (ch14)."""
    span: Span


@dataclass
class Statistics:
    min_value: bytes | None
    """``min_value`` and ``max_value``: the smallest and largest value in the column's own sort
    order (ch08), PLAIN-encoded without a length prefix."""
    max_value: bytes | None
    min_span: Span | None
    """Where the minimum's value bytes are, after their length prefix."""
    max_span: Span | None
    min: bytes | None
    """``min`` and ``max``: the deprecated fields, computed with signed comparison whatever the
    type. A reader may use them only where signed comparison is the right order (ch08)."""
    max: bytes | None
    min_deprecated_span: Span | None
    max_deprecated_span: Span | None
    null_count: int | None
    distinct_count: int | None
    is_min_value_exact: bool | None
    """False when a writer shortened a long value: the bound is then not a value in the column."""
    is_max_value_exact: bool | None
    span: Span


@dataclass
class ColumnCrypto:
    """How a column chunk is encrypted (ch13)."""

    key_metadata: bytes | None
    """``None``: encrypted with the footer key. Otherwise its own key, described by this key
    metadata, which names the key but never holds it."""
    with_column_key: bool
    encrypted_metadata: Span | None
    """The full ColumnMetaData, encrypted: only a reader with the column's key can read it."""


@dataclass
class ColumnChunk:
    """What the footer says about one column chunk: which column, and where its bytes are."""

    path: list[str]
    physical_type: PhysicalType
    encodings: list[str]
    codec: str
    num_values: int
    total_uncompressed_size: int
    total_compressed_size: int
    data_page_offset: int
    dictionary_page_offset: int | None
    statistics: Statistics | None
    column_index: Span | None
    """The page index (ch09): where this chunk's ColumnIndex and OffsetIndex are, if written."""
    offset_index: Span | None
    bloom_filter_offset: int | None
    """Where this chunk's Bloom filter is (ch09), if written."""
    bloom_filter_length: int | None
    crypto: ColumnCrypto | None
    """Modular encryption (ch13): how this chunk's pages are encrypted, if they are."""
    span: Span
    """Where this chunk's description sits in the footer."""

    def byte_range(self) -> Span:
        """The chunk's bytes in the file: from its first page to the end of its last.

        The first page is the dictionary page when there is one, and a data page otherwise.
        ``total_compressed_size`` counts every page, headers included, so start plus size is the
        end of the chunk. This is the range a reader requests to read the column.
        """
        d = self.dictionary_page_offset
        start = min(d, self.data_page_offset) if d is not None and d > 0 else self.data_page_offset
        return Span(start, start + self.total_compressed_size)

    def dotted_path(self) -> str:
        return ".".join(self.path)


@dataclass
class SortingColumn:
    column: int
    descending: bool
    nulls_first: bool


@dataclass
class RowGroup:
    num_rows: int
    total_byte_size: int
    columns: list[ColumnChunk]
    sorting_columns: list[SortingColumn]
    """The columns the writer says each row group is sorted by, in order (ch08). A claim, not
    something the reader checks."""
    span: Span


@dataclass
class KeyValue:
    key: str
    value: str | None


@dataclass
class FileMetaData:
    """The whole footer, typed."""

    version: int
    schema: list[SchemaElement]
    num_rows: int
    row_groups: list[RowGroup]
    key_value_metadata: list[KeyValue]
    created_by: str | None
    column_orders: list[str] | None
    """One entry per leaf column: the order ``min_value`` and ``max_value`` use. ``None`` when
    the footer has no ``column_orders``, in which case their order is undefined (ch08)."""
    encryption_algorithm: str | None
    """Set when the file uses modular encryption with a plaintext footer (ch13)."""
    footer_signature: Span | None
    tree: Node = field(repr=False)
    """The decoded Thrift tree the fields above were taken from. Kept, because the browser shows
    every field, including the ones this class does not name."""

    def leaves(self) -> list[SchemaElement]:
        """The leaf columns: the schema elements that hold data. Groups have children; leaves do
        not."""
        return [e for e in self.schema[1:] if (e.num_children or 0) == 0]


FOOTER_SIGNATURE_LEN = 28
"""The nonce and tag that sign a plaintext footer (ch13)."""


def decode_file_metadata(footer: bytes, base: int) -> FileMetaData:
    """Decode the footer: the ``footer`` bytes, which start at file offset ``base``.

    The footer must be exactly one ``FileMetaData``. Bytes left over mean the trailer's length
    and the structure disagree, and a reader that ignored that would be trusting a file it cannot
    explain.
    """
    r = ByteReader(footer, base)
    tree = read_struct(r)
    s = as_struct(tree)
    # An encrypted file with a plaintext footer (ch13) signs it: the FileMetaData is followed by
    # a 12-byte nonce and a 16-byte AES-GCM tag, and the footer length counts them.
    footer_signature = None
    if not r.is_at_end():
        rest = Span(r.offset(), base + len(footer))
        if s.field(8) is None or rest.length != FOOTER_SIGNATURE_LEN:
            raise TrailingBytes(rest)
        footer_signature = rest
    fmd = "FileMetaData"
    version = req_int(s, fmd, 1, "version", tree.span)
    schema = [schema_element(n) for n in req_list(s, fmd, 2, "schema", tree.span)]
    num_rows = req_int(s, fmd, 3, "num_rows", tree.span)
    row_groups = [row_group(n) for n in req_list(s, fmd, 4, "row_groups", tree.span)]
    kv = opt_list(s, 5)
    orders = opt_list(s, 7)
    return FileMetaData(
        version=version,
        schema=schema,
        num_rows=num_rows,
        row_groups=row_groups,
        key_value_metadata=[key_value(n) for n in kv] if kv is not None else [],
        created_by=opt_str(s, 6),
        column_orders=[_column_order(n) for n in orders] if orders is not None else None,
        encryption_algorithm=union_member(s.field(8).node) if s.field(8) else None,
        footer_signature=footer_signature,
        tree=tree,
    )


def _column_order(n: Node) -> str:
    # A union: a struct with exactly one field set. Field 1 is TYPE_ORDER.
    if not isinstance(n.value, Struct):
        return "UNKNOWN"
    if n.value.field(1) is not None:
        return "TYPE_ORDER"
    return f"UNKNOWN({n.value.fields[0].id})" if n.value.fields else "UNKNOWN"


def schema_element(node: Node) -> SchemaElement:
    s = as_struct(node)
    physical = opt_int(s, 1)
    repetition, converted = opt_int(s, 3), opt_int(s, 6)
    logical_field = s.field(10)
    return SchemaElement(
        name=req_str(s, "SchemaElement", 4, "name", node.span),
        physical_type=PhysicalType(physical) if physical is not None else None,
        type_length=opt_int(s, 2),
        repetition=enum_name("FieldRepetitionType", repetition) if repetition is not None else None,
        num_children=opt_int(s, 5),
        converted_type=enum_name("ConvertedType", converted) if converted is not None else None,
        scale=opt_int(s, 7),
        precision=opt_int(s, 8),
        field_id=opt_int(s, 9),
        logical_type=logical.decode(logical_field.node) if logical_field else None,
        span=node.span,
    )


def row_group(node: Node) -> RowGroup:
    s = as_struct(node)
    rg = "RowGroup"
    columns = [column_chunk(n) for n in req_list(s, rg, 1, "columns", node.span)]
    total_byte_size = req_int(s, rg, 2, "total_byte_size", node.span)
    num_rows = req_int(s, rg, 3, "num_rows", node.span)
    sorting = []
    for n in opt_list(s, 4) or []:
        if isinstance(n.value, Struct) and opt_int(n.value, 1) is not None:
            sorting.append(
                SortingColumn(
                    column=opt_int(n.value, 1),
                    descending=bool(opt_bool(n.value, 2)),
                    nulls_first=bool(opt_bool(n.value, 3)),
                )
            )
    return RowGroup(num_rows, total_byte_size, columns, sorting, node.span)


def column_chunk(node: Node) -> ColumnChunk:
    chunk = as_struct(node)
    # ColumnMetaData is optional in the Thrift definition only because an encrypted column hides
    # it. This reader does not decrypt, so for it the field is required.
    meta_field = chunk.field(3)
    if meta_field is None:
        raise Missing("ColumnChunk", "meta_data", node.span)
    m = as_struct(meta_field.node)
    cmd, span = "ColumnMetaData", meta_field.node.span
    physical_type = PhysicalType(req_int(m, cmd, 1, "type", span))
    encodings = [
        enum_name("Encoding", n.value) for n in req_list(m, cmd, 2, "encodings", span) if type(n.value) is int
    ]
    path = [
        n.value.decode("utf-8", "replace")
        for n in req_list(m, cmd, 3, "path_in_schema", span)
        if isinstance(n.value, bytes)
    ]
    codec = enum_name("CompressionCodec", req_int(m, cmd, 4, "codec", span))
    num_values = req_int(m, cmd, 5, "num_values", span)
    uncompressed = req_int(m, cmd, 6, "total_uncompressed_size", span)
    compressed = req_int(m, cmd, 7, "total_compressed_size", span)
    data_page_offset = req_int(m, cmd, 9, "data_page_offset", span)
    stats = m.field(12)
    return ColumnChunk(
        path=path,
        physical_type=physical_type,
        encodings=encodings,
        codec=codec,
        num_values=num_values,
        total_uncompressed_size=uncompressed,
        total_compressed_size=compressed,
        data_page_offset=data_page_offset,
        dictionary_page_offset=opt_int(m, 11),
        statistics=statistics(stats.node) if stats else None,
        column_index=_offset_and_length(chunk, 6, 7),
        offset_index=_offset_and_length(chunk, 4, 5),
        bloom_filter_offset=opt_int(m, 14),
        bloom_filter_length=opt_int(m, 15),
        crypto=_crypto(chunk),
        span=node.span,
    )


def _crypto(chunk: Struct) -> ColumnCrypto | None:
    f = chunk.field(8)
    if f is None:
        return None
    # A union: field 1 for the footer key, field 2 for a column key and its metadata.
    with_key = f.node.value.field(2) if isinstance(f.node.value, Struct) else None
    key = with_key.node.value if with_key else None
    return ColumnCrypto(
        key_metadata=opt_bytes(key, 2) if isinstance(key, Struct) else None,
        with_column_key=with_key is not None,
        encrypted_metadata=_value_span(chunk, 9),
    )


def statistics(node: Node) -> Statistics:
    """Page headers carry statistics too, in the same struct, so this is shared with
    :mod:`parquet_lab.pages`."""
    s = as_struct(node)
    # min_value and max_value (fields 6 and 5) replaced min and max (2 and 1), whose order was
    # signed comparison whatever the type. The two pairs are kept apart: which one a reader may
    # use depends on the column's sort order.
    return Statistics(
        min_value=opt_bytes(s, 6),
        max_value=opt_bytes(s, 5),
        min_span=_value_span(s, 6),
        max_span=_value_span(s, 5),
        min=opt_bytes(s, 2),
        max=opt_bytes(s, 1),
        min_deprecated_span=_value_span(s, 2),
        max_deprecated_span=_value_span(s, 1),
        null_count=opt_int(s, 3),
        distinct_count=opt_int(s, 4),
        is_max_value_exact=opt_bool(s, 7),
        is_min_value_exact=opt_bool(s, 8),
        span=node.span,
    )


def union_member(node: Node) -> str:
    """The name of the member an ``EncryptionAlgorithm`` union holds."""
    if not isinstance(node.value, Struct) or not node.value.fields:
        return "UNKNOWN"
    id = node.value.fields[0].id
    return {1: "AES_GCM_V1", 2: "AES_GCM_CTR_V1"}.get(id, f"UNKNOWN({id})")


def _offset_and_length(s: Struct, offset: int, length: int) -> Span | None:
    """A region given as an offset field and a length field, when both are present and
    sensible."""
    o, n = opt_int(s, offset), opt_int(s, length)
    if o is None or n is None or o < 0 or n < 0:
        return None
    return Span(o, o + n)


def _value_span(s: Struct, id: int) -> Span | None:
    """The span of a binary field's bytes, without the varint length in front of them."""
    f = s.field(id)
    if f is None or not isinstance(f.node.value, bytes):
        return None
    return Span(f.node.span.end - len(f.node.value), f.node.span.end)


def key_value(node: Node) -> KeyValue:
    s = as_struct(node)
    return KeyValue(req_str(s, "KeyValue", 1, "key", node.span), opt_str(s, 2))


def enum_name(enum: str, v: int) -> str:
    return enum_value_name(enum, v) or f"UNKNOWN({v})"


def as_struct(node: Node) -> Struct:
    if not isinstance(node.value, Struct):
        raise NotAStruct(node.span)
    return node.value


def opt_int(s: Struct, id: int) -> int | None:
    f = s.field(id)
    return f.node.value if f and type(f.node.value) is int else None


def opt_bool(s: Struct, id: int) -> bool | None:
    f = s.field(id)
    return f.node.value if f and type(f.node.value) is bool else None


def opt_bytes(s: Struct, id: int) -> bytes | None:
    f = s.field(id)
    return f.node.value if f and isinstance(f.node.value, bytes) else None


def opt_str(s: Struct, id: int) -> str | None:
    b = opt_bytes(s, id)
    return b.decode("utf-8", "replace") if b is not None else None


def opt_list(s: Struct, id: int) -> list[Node] | None:
    f = s.field(id)
    return f.node.value if f and type(f.node.value) is list else None


def _required(s: Struct, structure: str, id: int, name: str, span: Span, ok) -> object:
    f = s.field(id)
    if f is None:
        raise Missing(structure, name, span)
    if not ok(f.node.value):
        raise WrongType(structure, name, f.span())
    return f.node.value


def req_int(s: Struct, structure: str, id: int, name: str, span: Span) -> int:
    return _required(s, structure, id, name, span, lambda v: type(v) is int)


def req_str(s: Struct, structure: str, id: int, name: str, span: Span) -> str:
    v = _required(s, structure, id, name, span, lambda v: isinstance(v, bytes))
    return v.decode("utf-8", "replace")


def req_list(s: Struct, structure: str, id: int, name: str, span: Span) -> list[Node]:
    return _required(s, structure, id, name, span, lambda v: type(v) is list)
