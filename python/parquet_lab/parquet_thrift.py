"""The names Parquet gives to Thrift field ids: a hand-copied subset of ``parquet.thrift``.

:mod:`parquet_lab.thrift` decodes the footer as numbered fields. This table says that field 4
of a ``FileMetaData`` is ``row_groups``, that it holds ``RowGroup`` structs, and that the integer
in field 1 of a ``ColumnMetaData`` is a ``Type`` enum where 2 means ``INT64``.

Only what this reader uses, or shows, is listed. A field missing from the table still decodes:
it is displayed by number, and nothing is lost. That is the forward-compatibility rule the
compact protocol was designed for, and it is why a file written by a newer writer than this
table knows about still opens.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    """What a field holds, as far as naming it goes: ``int``, ``bool``, ``str``, ``bytes``,
    ``enum`` (``of`` names the enum), ``struct`` (``of`` names the struct) or ``list`` (``of`` is
    the element's kind)."""

    tag: str
    of: object = None


INT, BOOL, STR, BYTES = Kind("int"), Kind("bool"), Kind("str"), Kind("bytes")


def enum(name: str) -> Kind:
    return Kind("enum", name)


def struct(name: str) -> Kind:
    return Kind("struct", name)


def list_of(kind: Kind) -> Kind:
    return Kind("list", kind)


@dataclass(frozen=True)
class FieldDef:
    id: int
    name: str
    kind: Kind


def _fields(*defs: tuple[int, str, Kind]) -> list[FieldDef]:
    return [FieldDef(*d) for d in defs]


STR_LIST, INT_LIST = list_of(STR), list_of(INT)

FIELDS: dict[str, list[FieldDef]] = {
    "FileMetaData": _fields(
        (1, "version", INT),
        (2, "schema", list_of(struct("SchemaElement"))),
        (3, "num_rows", INT),
        (4, "row_groups", list_of(struct("RowGroup"))),
        (5, "key_value_metadata", list_of(struct("KeyValue"))),
        (6, "created_by", STR),
        (7, "column_orders", list_of(struct("ColumnOrder"))),
        (8, "encryption_algorithm", struct("EncryptionAlgorithm")),
        (9, "footer_signing_key_metadata", BYTES),
    ),
    "SchemaElement": _fields(
        (1, "type", enum("Type")),
        (2, "type_length", INT),
        (3, "repetition_type", enum("FieldRepetitionType")),
        (4, "name", STR),
        (5, "num_children", INT),
        (6, "converted_type", enum("ConvertedType")),
        (7, "scale", INT),
        (8, "precision", INT),
        (9, "field_id", INT),
        (10, "logicalType", struct("LogicalType")),
    ),
    "RowGroup": _fields(
        (1, "columns", list_of(struct("ColumnChunk"))),
        (2, "total_byte_size", INT),
        (3, "num_rows", INT),
        (4, "sorting_columns", list_of(struct("SortingColumn"))),
        (5, "file_offset", INT),
        (6, "total_compressed_size", INT),
        (7, "ordinal", INT),
    ),
    "ColumnChunk": _fields(
        (1, "file_path", STR),
        (2, "file_offset", INT),
        (3, "meta_data", struct("ColumnMetaData")),
        (4, "offset_index_offset", INT),
        (5, "offset_index_length", INT),
        (6, "column_index_offset", INT),
        (7, "column_index_length", INT),
        (8, "crypto_metadata", struct("ColumnCryptoMetaData")),
        (9, "encrypted_column_metadata", BYTES),
    ),
    "ColumnMetaData": _fields(
        (1, "type", enum("Type")),
        (2, "encodings", list_of(enum("Encoding"))),
        (3, "path_in_schema", STR_LIST),
        (4, "codec", enum("CompressionCodec")),
        (5, "num_values", INT),
        (6, "total_uncompressed_size", INT),
        (7, "total_compressed_size", INT),
        (8, "key_value_metadata", list_of(struct("KeyValue"))),
        (9, "data_page_offset", INT),
        (10, "index_page_offset", INT),
        (11, "dictionary_page_offset", INT),
        (12, "statistics", struct("Statistics")),
        (13, "encoding_stats", list_of(struct("PageEncodingStats"))),
        (14, "bloom_filter_offset", INT),
        (15, "bloom_filter_length", INT),
        (16, "size_statistics", struct("SizeStatistics")),
        (17, "geospatial_statistics", struct("GeospatialStatistics")),
    ),
    "Statistics": _fields(
        (1, "max", BYTES),
        (2, "min", BYTES),
        (3, "null_count", INT),
        (4, "distinct_count", INT),
        (5, "max_value", BYTES),
        (6, "min_value", BYTES),
        (7, "is_max_value_exact", BOOL),
        (8, "is_min_value_exact", BOOL),
    ),
    "PageEncodingStats": _fields(
        (1, "page_type", enum("PageType")),
        (2, "encoding", enum("Encoding")),
        (3, "count", INT),
    ),
    "KeyValue": _fields((1, "key", STR), (2, "value", STR)),
    "SortingColumn": _fields(
        (1, "column_idx", INT),
        (2, "descending", BOOL),
        (3, "nulls_first", BOOL),
    ),
    "ColumnOrder": _fields((1, "TYPE_ORDER", struct("TypeDefinedOrder"))),
    "SizeStatistics": _fields(
        (1, "unencoded_byte_array_data_bytes", INT),
        (2, "repetition_level_histogram", INT_LIST),
        (3, "definition_level_histogram", INT_LIST),
    ),
    "LogicalType": _fields(
        (1, "STRING", struct("StringType")),
        (2, "MAP", struct("MapType")),
        (3, "LIST", struct("ListType")),
        (4, "ENUM", struct("EnumType")),
        (5, "DECIMAL", struct("DecimalType")),
        (6, "DATE", struct("DateType")),
        (7, "TIME", struct("TimeType")),
        (8, "TIMESTAMP", struct("TimestampType")),
        (10, "INTEGER", struct("IntType")),
        (11, "UNKNOWN", struct("NullType")),
        (12, "JSON", struct("JsonType")),
        (13, "BSON", struct("BsonType")),
        (14, "UUID", struct("UUIDType")),
        (15, "FLOAT16", struct("Float16Type")),
        (16, "VARIANT", struct("VariantType")),
        (17, "GEOMETRY", struct("GeometryType")),
        (18, "GEOGRAPHY", struct("GeographyType")),
    ),
    "DecimalType": _fields((1, "scale", INT), (2, "precision", INT)),
    "TimeUnit": _fields(
        (1, "MILLIS", struct("MilliSeconds")),
        (2, "MICROS", struct("MicroSeconds")),
        (3, "NANOS", struct("NanoSeconds")),
    ),
    "TimeType": _fields((1, "isAdjustedToUTC", BOOL), (2, "unit", struct("TimeUnit"))),
    "IntType": _fields((1, "bitWidth", INT), (2, "isSigned", BOOL)),
    "PageHeader": _fields(
        (1, "type", enum("PageType")),
        (2, "uncompressed_page_size", INT),
        (3, "compressed_page_size", INT),
        (4, "crc", INT),
        (5, "data_page_header", struct("DataPageHeader")),
        (6, "index_page_header", struct("IndexPageHeader")),
        (7, "dictionary_page_header", struct("DictionaryPageHeader")),
        (8, "data_page_header_v2", struct("DataPageHeaderV2")),
    ),
    "DataPageHeader": _fields(
        (1, "num_values", INT),
        (2, "encoding", enum("Encoding")),
        (3, "definition_level_encoding", enum("Encoding")),
        (4, "repetition_level_encoding", enum("Encoding")),
        (5, "statistics", struct("Statistics")),
    ),
    "DictionaryPageHeader": _fields(
        (1, "num_values", INT),
        (2, "encoding", enum("Encoding")),
        (3, "is_sorted", BOOL),
    ),
    "DataPageHeaderV2": _fields(
        (1, "num_values", INT),
        (2, "num_nulls", INT),
        (3, "num_rows", INT),
        (4, "encoding", enum("Encoding")),
        (5, "definition_levels_byte_length", INT),
        (6, "repetition_levels_byte_length", INT),
        (7, "is_compressed", BOOL),
        (8, "statistics", struct("Statistics")),
    ),
    # The page index (ch09): one ColumnIndex and one OffsetIndex per column chunk, written
    # between the last row group and the footer.
    "ColumnIndex": _fields(
        (1, "null_pages", list_of(BOOL)),
        (2, "min_values", list_of(BYTES)),
        (3, "max_values", list_of(BYTES)),
        (4, "boundary_order", enum("BoundaryOrder")),
        (5, "null_counts", INT_LIST),
        (6, "repetition_level_histograms", INT_LIST),
        (7, "definition_level_histograms", INT_LIST),
    ),
    "OffsetIndex": _fields(
        (1, "page_locations", list_of(struct("PageLocation"))),
        (2, "unencoded_byte_array_data_bytes", INT_LIST),
    ),
    "PageLocation": _fields(
        (1, "offset", INT),
        (2, "compressed_page_size", INT),
        (3, "first_row_index", INT),
    ),
    # A Bloom filter's header (ch09). The three unions each have one member so far.
    "BloomFilterHeader": _fields(
        (1, "numBytes", INT),
        (2, "algorithm", struct("BloomFilterAlgorithm")),
        (3, "hash", struct("BloomFilterHash")),
        (4, "compression", struct("BloomFilterCompression")),
    ),
    "BloomFilterAlgorithm": _fields((1, "BLOCK", struct("SplitBlockAlgorithm"))),
    "BloomFilterHash": _fields((1, "XXHASH", struct("XxHash"))),
    "BloomFilterCompression": _fields((1, "UNCOMPRESSED", struct("Uncompressed"))),
    # Modular encryption (ch13).
    "FileCryptoMetaData": _fields(
        (1, "encryption_algorithm", struct("EncryptionAlgorithm")),
        (2, "key_metadata", BYTES),
    ),
    "EncryptionAlgorithm": _fields(
        (1, "AES_GCM_V1", struct("AesGcmV1")),
        (2, "AES_GCM_CTR_V1", struct("AesGcmCtrV1")),
    ),
    "AesGcmV1": _fields(
        (1, "aad_prefix", BYTES),
        (2, "aad_file_unique", BYTES),
        (3, "supply_aad_prefix", BOOL),
    ),
    "ColumnCryptoMetaData": _fields(
        (1, "ENCRYPTION_WITH_FOOTER_KEY", struct("EncryptionWithFooterKey")),
        (2, "ENCRYPTION_WITH_COLUMN_KEY", struct("EncryptionWithColumnKey")),
    ),
    "EncryptionWithColumnKey": _fields((1, "path_in_schema", STR_LIST), (2, "key_metadata", BYTES)),
}
FIELDS["TimestampType"] = FIELDS["TimeType"]
FIELDS["AesGcmCtrV1"] = FIELDS["AesGcmV1"]


def field_def(struct_name: str, id: int) -> FieldDef | None:
    return next((d for d in FIELDS.get(struct_name, []) if d.id == id), None)


ENUMS: dict[str, list[str]] = {
    "Type": [
        "BOOLEAN",
        "INT32",
        "INT64",
        "INT96",
        "FLOAT",
        "DOUBLE",
        "BYTE_ARRAY",
        "FIXED_LEN_BYTE_ARRAY",
    ],
    "ConvertedType": [
        "UTF8",
        "MAP",
        "MAP_KEY_VALUE",
        "LIST",
        "ENUM",
        "DECIMAL",
        "DATE",
        "TIME_MILLIS",
        "TIME_MICROS",
        "TIMESTAMP_MILLIS",
        "TIMESTAMP_MICROS",
        "UINT_8",
        "UINT_16",
        "UINT_32",
        "UINT_64",
        "INT_8",
        "INT_16",
        "INT_32",
        "INT_64",
        "JSON",
        "BSON",
        "INTERVAL",
    ],
    "FieldRepetitionType": ["REQUIRED", "OPTIONAL", "REPEATED"],
    # Value 1 was GROUP_VAR_INT, which no writer ever produced and the format removed.
    "Encoding": [
        "PLAIN",
        "GROUP_VAR_INT",
        "PLAIN_DICTIONARY",
        "RLE",
        "BIT_PACKED",
        "DELTA_BINARY_PACKED",
        "DELTA_LENGTH_BYTE_ARRAY",
        "DELTA_BYTE_ARRAY",
        "RLE_DICTIONARY",
        "BYTE_STREAM_SPLIT",
    ],
    "CompressionCodec": [
        "UNCOMPRESSED",
        "SNAPPY",
        "GZIP",
        "LZO",
        "BROTLI",
        "LZ4",
        "ZSTD",
        "LZ4_RAW",
    ],
    "PageType": ["DATA_PAGE", "INDEX_PAGE", "DICTIONARY_PAGE", "DATA_PAGE_V2"],
    "BoundaryOrder": ["UNORDERED", "ASCENDING", "DESCENDING"],
}


def enum_value_name(enum_name: str, v: int) -> str | None:
    """The name of an enum value, or ``None`` for a value this table does not know."""
    names = ENUMS[enum_name]
    return names[v] if 0 <= v < len(names) else None
