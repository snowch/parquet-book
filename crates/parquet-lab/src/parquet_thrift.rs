//! The names Parquet gives to Thrift field ids: a hand-copied subset of `parquet.thrift`.
//!
//! [`crate::thrift`] decodes the footer as numbered fields. This table says that field 4 of a
//! `FileMetaData` is `row_groups`, that it holds `RowGroup` structs, and that the integer in
//! field 1 of a `ColumnMetaData` is a `Type` enum where 2 means `INT64`.
//!
//! Only what this reader uses, or shows, is listed. A field missing from the table still
//! decodes: it is displayed by number, and nothing is lost. That is the forward-compatibility
//! rule the compact protocol was designed for, and it is why a file written by a newer writer
//! than this table knows about still opens.

/// What a field holds, as far as naming it goes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Int,
    Bool,
    Str,
    Bytes,
    Enum(EnumName),
    Struct(&'static str),
    ListOf(&'static Kind),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EnumName {
    Type,
    ConvertedType,
    FieldRepetitionType,
    Encoding,
    CompressionCodec,
    PageType,
    BoundaryOrder,
}

#[derive(Clone, Copy, Debug)]
pub struct FieldDef {
    pub id: i16,
    pub name: &'static str,
    pub kind: Kind,
}

const fn f(id: i16, name: &'static str, kind: Kind) -> FieldDef {
    FieldDef { id, name, kind }
}

const STR_LIST: Kind = Kind::ListOf(&Kind::Str);
const INT_LIST: Kind = Kind::ListOf(&Kind::Int);
const ENCODING_LIST: Kind = Kind::ListOf(&Kind::Enum(EnumName::Encoding));

const FILE_META_DATA: &[FieldDef] = &[
    f(1, "version", Kind::Int),
    f(2, "schema", Kind::ListOf(&Kind::Struct("SchemaElement"))),
    f(3, "num_rows", Kind::Int),
    f(4, "row_groups", Kind::ListOf(&Kind::Struct("RowGroup"))),
    f(
        5,
        "key_value_metadata",
        Kind::ListOf(&Kind::Struct("KeyValue")),
    ),
    f(6, "created_by", Kind::Str),
    f(
        7,
        "column_orders",
        Kind::ListOf(&Kind::Struct("ColumnOrder")),
    ),
    f(
        8,
        "encryption_algorithm",
        Kind::Struct("EncryptionAlgorithm"),
    ),
    f(9, "footer_signing_key_metadata", Kind::Bytes),
];

const SCHEMA_ELEMENT: &[FieldDef] = &[
    f(1, "type", Kind::Enum(EnumName::Type)),
    f(2, "type_length", Kind::Int),
    f(
        3,
        "repetition_type",
        Kind::Enum(EnumName::FieldRepetitionType),
    ),
    f(4, "name", Kind::Str),
    f(5, "num_children", Kind::Int),
    f(6, "converted_type", Kind::Enum(EnumName::ConvertedType)),
    f(7, "scale", Kind::Int),
    f(8, "precision", Kind::Int),
    f(9, "field_id", Kind::Int),
    f(10, "logicalType", Kind::Struct("LogicalType")),
];

const ROW_GROUP: &[FieldDef] = &[
    f(1, "columns", Kind::ListOf(&Kind::Struct("ColumnChunk"))),
    f(2, "total_byte_size", Kind::Int),
    f(3, "num_rows", Kind::Int),
    f(
        4,
        "sorting_columns",
        Kind::ListOf(&Kind::Struct("SortingColumn")),
    ),
    f(5, "file_offset", Kind::Int),
    f(6, "total_compressed_size", Kind::Int),
    f(7, "ordinal", Kind::Int),
];

const COLUMN_CHUNK: &[FieldDef] = &[
    f(1, "file_path", Kind::Str),
    f(2, "file_offset", Kind::Int),
    f(3, "meta_data", Kind::Struct("ColumnMetaData")),
    f(4, "offset_index_offset", Kind::Int),
    f(5, "offset_index_length", Kind::Int),
    f(6, "column_index_offset", Kind::Int),
    f(7, "column_index_length", Kind::Int),
    f(8, "crypto_metadata", Kind::Struct("ColumnCryptoMetaData")),
    f(9, "encrypted_column_metadata", Kind::Bytes),
];

const COLUMN_META_DATA: &[FieldDef] = &[
    f(1, "type", Kind::Enum(EnumName::Type)),
    f(2, "encodings", ENCODING_LIST),
    f(3, "path_in_schema", STR_LIST),
    f(4, "codec", Kind::Enum(EnumName::CompressionCodec)),
    f(5, "num_values", Kind::Int),
    f(6, "total_uncompressed_size", Kind::Int),
    f(7, "total_compressed_size", Kind::Int),
    f(
        8,
        "key_value_metadata",
        Kind::ListOf(&Kind::Struct("KeyValue")),
    ),
    f(9, "data_page_offset", Kind::Int),
    f(10, "index_page_offset", Kind::Int),
    f(11, "dictionary_page_offset", Kind::Int),
    f(12, "statistics", Kind::Struct("Statistics")),
    f(
        13,
        "encoding_stats",
        Kind::ListOf(&Kind::Struct("PageEncodingStats")),
    ),
    f(14, "bloom_filter_offset", Kind::Int),
    f(15, "bloom_filter_length", Kind::Int),
    f(16, "size_statistics", Kind::Struct("SizeStatistics")),
    f(
        17,
        "geospatial_statistics",
        Kind::Struct("GeospatialStatistics"),
    ),
];

const STATISTICS: &[FieldDef] = &[
    f(1, "max", Kind::Bytes),
    f(2, "min", Kind::Bytes),
    f(3, "null_count", Kind::Int),
    f(4, "distinct_count", Kind::Int),
    f(5, "max_value", Kind::Bytes),
    f(6, "min_value", Kind::Bytes),
    f(7, "is_max_value_exact", Kind::Bool),
    f(8, "is_min_value_exact", Kind::Bool),
];

const PAGE_ENCODING_STATS: &[FieldDef] = &[
    f(1, "page_type", Kind::Enum(EnumName::PageType)),
    f(2, "encoding", Kind::Enum(EnumName::Encoding)),
    f(3, "count", Kind::Int),
];

const KEY_VALUE: &[FieldDef] = &[f(1, "key", Kind::Str), f(2, "value", Kind::Str)];

const SORTING_COLUMN: &[FieldDef] = &[
    f(1, "column_idx", Kind::Int),
    f(2, "descending", Kind::Bool),
    f(3, "nulls_first", Kind::Bool),
];

const COLUMN_ORDER: &[FieldDef] = &[f(1, "TYPE_ORDER", Kind::Struct("TypeDefinedOrder"))];

const SIZE_STATISTICS: &[FieldDef] = &[
    f(1, "unencoded_byte_array_data_bytes", Kind::Int),
    f(2, "repetition_level_histogram", INT_LIST),
    f(3, "definition_level_histogram", INT_LIST),
];

const LOGICAL_TYPE: &[FieldDef] = &[
    f(1, "STRING", Kind::Struct("StringType")),
    f(2, "MAP", Kind::Struct("MapType")),
    f(3, "LIST", Kind::Struct("ListType")),
    f(4, "ENUM", Kind::Struct("EnumType")),
    f(5, "DECIMAL", Kind::Struct("DecimalType")),
    f(6, "DATE", Kind::Struct("DateType")),
    f(7, "TIME", Kind::Struct("TimeType")),
    f(8, "TIMESTAMP", Kind::Struct("TimestampType")),
    f(10, "INTEGER", Kind::Struct("IntType")),
    f(11, "UNKNOWN", Kind::Struct("NullType")),
    f(12, "JSON", Kind::Struct("JsonType")),
    f(13, "BSON", Kind::Struct("BsonType")),
    f(14, "UUID", Kind::Struct("UUIDType")),
    f(15, "FLOAT16", Kind::Struct("Float16Type")),
    f(16, "VARIANT", Kind::Struct("VariantType")),
    f(17, "GEOMETRY", Kind::Struct("GeometryType")),
    f(18, "GEOGRAPHY", Kind::Struct("GeographyType")),
];

const DECIMAL_TYPE: &[FieldDef] = &[f(1, "scale", Kind::Int), f(2, "precision", Kind::Int)];

const TIME_UNIT: &[FieldDef] = &[
    f(1, "MILLIS", Kind::Struct("MilliSeconds")),
    f(2, "MICROS", Kind::Struct("MicroSeconds")),
    f(3, "NANOS", Kind::Struct("NanoSeconds")),
];

const TIME_TYPE: &[FieldDef] = &[
    f(1, "isAdjustedToUTC", Kind::Bool),
    f(2, "unit", Kind::Struct("TimeUnit")),
];

const INT_TYPE: &[FieldDef] = &[f(1, "bitWidth", Kind::Int), f(2, "isSigned", Kind::Bool)];

const PAGE_HEADER: &[FieldDef] = &[
    f(1, "type", Kind::Enum(EnumName::PageType)),
    f(2, "uncompressed_page_size", Kind::Int),
    f(3, "compressed_page_size", Kind::Int),
    f(4, "crc", Kind::Int),
    f(5, "data_page_header", Kind::Struct("DataPageHeader")),
    f(6, "index_page_header", Kind::Struct("IndexPageHeader")),
    f(
        7,
        "dictionary_page_header",
        Kind::Struct("DictionaryPageHeader"),
    ),
    f(8, "data_page_header_v2", Kind::Struct("DataPageHeaderV2")),
];

const DATA_PAGE_HEADER: &[FieldDef] = &[
    f(1, "num_values", Kind::Int),
    f(2, "encoding", Kind::Enum(EnumName::Encoding)),
    f(
        3,
        "definition_level_encoding",
        Kind::Enum(EnumName::Encoding),
    ),
    f(
        4,
        "repetition_level_encoding",
        Kind::Enum(EnumName::Encoding),
    ),
    f(5, "statistics", Kind::Struct("Statistics")),
];

const DICTIONARY_PAGE_HEADER: &[FieldDef] = &[
    f(1, "num_values", Kind::Int),
    f(2, "encoding", Kind::Enum(EnumName::Encoding)),
    f(3, "is_sorted", Kind::Bool),
];

const DATA_PAGE_HEADER_V2: &[FieldDef] = &[
    f(1, "num_values", Kind::Int),
    f(2, "num_nulls", Kind::Int),
    f(3, "num_rows", Kind::Int),
    f(4, "encoding", Kind::Enum(EnumName::Encoding)),
    f(5, "definition_levels_byte_length", Kind::Int),
    f(6, "repetition_levels_byte_length", Kind::Int),
    f(7, "is_compressed", Kind::Bool),
    f(8, "statistics", Kind::Struct("Statistics")),
];

/// The fields of a named struct, or an empty list for one this table does not describe.
pub fn fields_of(struct_name: &str) -> &'static [FieldDef] {
    match struct_name {
        "FileMetaData" => FILE_META_DATA,
        "SchemaElement" => SCHEMA_ELEMENT,
        "RowGroup" => ROW_GROUP,
        "ColumnChunk" => COLUMN_CHUNK,
        "ColumnMetaData" => COLUMN_META_DATA,
        "Statistics" => STATISTICS,
        "PageEncodingStats" => PAGE_ENCODING_STATS,
        "KeyValue" => KEY_VALUE,
        "SortingColumn" => SORTING_COLUMN,
        "ColumnOrder" => COLUMN_ORDER,
        "SizeStatistics" => SIZE_STATISTICS,
        "LogicalType" => LOGICAL_TYPE,
        "DecimalType" => DECIMAL_TYPE,
        "TimeType" | "TimestampType" => TIME_TYPE,
        "TimeUnit" => TIME_UNIT,
        "IntType" => INT_TYPE,
        "PageHeader" => PAGE_HEADER,
        "DataPageHeader" => DATA_PAGE_HEADER,
        "DictionaryPageHeader" => DICTIONARY_PAGE_HEADER,
        "DataPageHeaderV2" => DATA_PAGE_HEADER_V2,
        _ => &[],
    }
}

pub fn field_def(struct_name: &str, id: i16) -> Option<&'static FieldDef> {
    fields_of(struct_name).iter().find(|d| d.id == id)
}

/// The name of an enum value, or `None` for a value this table does not know.
pub fn enum_value_name(e: EnumName, v: i64) -> Option<&'static str> {
    let names: &[&str] = match e {
        EnumName::Type => &[
            "BOOLEAN",
            "INT32",
            "INT64",
            "INT96",
            "FLOAT",
            "DOUBLE",
            "BYTE_ARRAY",
            "FIXED_LEN_BYTE_ARRAY",
        ],
        EnumName::ConvertedType => &[
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
        EnumName::FieldRepetitionType => &["REQUIRED", "OPTIONAL", "REPEATED"],
        // Value 1 was GROUP_VAR_INT, which no writer ever produced and the format removed.
        EnumName::Encoding => &[
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
        EnumName::CompressionCodec => &[
            "UNCOMPRESSED",
            "SNAPPY",
            "GZIP",
            "LZO",
            "BROTLI",
            "LZ4",
            "ZSTD",
            "LZ4_RAW",
        ],
        EnumName::PageType => &["DATA_PAGE", "INDEX_PAGE", "DICTIONARY_PAGE", "DATA_PAGE_V2"],
        EnumName::BoundaryOrder => &["UNORDERED", "ASCENDING", "DESCENDING"],
    };
    usize::try_from(v).ok().and_then(|i| names.get(i).copied())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_struct_named_as_a_child_is_either_described_or_an_empty_marker() {
        // Structs Parquet uses as markers: they have no fields, so an empty table is correct.
        const MARKERS: &[&str] = &[
            "StringType",
            "MapType",
            "ListType",
            "EnumType",
            "DateType",
            "NullType",
            "JsonType",
            "BsonType",
            "UUIDType",
            "Float16Type",
            "VariantType",
            "TypeDefinedOrder",
            "MilliSeconds",
            "MicroSeconds",
            "NanoSeconds",
            // Not described yet: named here so the omission is a decision, not an accident.
            "EncryptionAlgorithm",
            "ColumnCryptoMetaData",
            "GeospatialStatistics",
            "GeometryType",
            "GeographyType",
            "IndexPageHeader",
        ];
        let all = [
            "FileMetaData",
            "SchemaElement",
            "RowGroup",
            "ColumnChunk",
            "ColumnMetaData",
            "Statistics",
            "PageEncodingStats",
            "KeyValue",
            "SortingColumn",
            "ColumnOrder",
            "SizeStatistics",
            "LogicalType",
            "DecimalType",
            "TimeType",
            "TimeUnit",
            "IntType",
            "PageHeader",
            "DataPageHeader",
            "DictionaryPageHeader",
            "DataPageHeaderV2",
        ];
        fn child(kind: Kind) -> Option<&'static str> {
            match kind {
                Kind::Struct(s) => Some(s),
                Kind::ListOf(inner) => child(*inner),
                _ => None,
            }
        }
        for name in all {
            assert!(!fields_of(name).is_empty(), "{name} has no fields");
            for def in fields_of(name) {
                if let Some(c) = child(def.kind) {
                    assert!(
                        !fields_of(c).is_empty() || MARKERS.contains(&c),
                        "{name}.{} names {c}, which is neither described nor a marker",
                        def.name
                    );
                }
            }
        }
    }

    #[test]
    fn field_ids_are_unique_within_a_struct() {
        for name in [
            "FileMetaData",
            "ColumnMetaData",
            "PageHeader",
            "LogicalType",
        ] {
            let mut ids: Vec<i16> = fields_of(name).iter().map(|d| d.id).collect();
            ids.sort();
            ids.dedup();
            assert_eq!(ids.len(), fields_of(name).len(), "{name}");
        }
    }

    #[test]
    fn enum_values_have_names() {
        assert_eq!(enum_value_name(EnumName::Type, 2), Some("INT64"));
        assert_eq!(
            enum_value_name(EnumName::Encoding, 8),
            Some("RLE_DICTIONARY")
        );
        assert_eq!(
            enum_value_name(EnumName::CompressionCodec, 7),
            Some("LZ4_RAW")
        );
        assert_eq!(enum_value_name(EnumName::Type, 99), None);
        assert_eq!(enum_value_name(EnumName::Type, -1), None);
    }
}
