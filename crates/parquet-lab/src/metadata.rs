//! `FileMetaData`: the footer, read into Rust types.
//!
//! [`crate::thrift`] turns the footer's bytes into numbered fields. This module picks out the
//! fields a reader needs and gives them types: the schema, the row groups, and for every column
//! chunk the offsets and sizes that say where its bytes are.
//!
//! It reads by field id, the way the Thrift definition does, so the numbers in this file are
//! the ids from `parquet.thrift`. A field the reader does not need is left in the decoded tree
//! and never looked at.

use std::fmt;

use crate::bytes::{ByteReader, Span};
use crate::logical::{self, LogicalType};
use crate::parquet_thrift::{enum_value_name, EnumName};
use crate::thrift::{read_struct, Node, Struct, ThriftError, Value};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MetadataError {
    Thrift(ThriftError),
    NotAStruct {
        span: Span,
    },
    Missing {
        structure: &'static str,
        field: &'static str,
        span: Span,
    },
    WrongType {
        structure: &'static str,
        field: &'static str,
        span: Span,
    },
    TrailingBytes {
        span: Span,
    },
}

impl fmt::Display for MetadataError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            MetadataError::Thrift(e) => write!(f, "{e}"),
            MetadataError::NotAStruct { span } => write!(f, "expected a struct at {span}"),
            MetadataError::Missing { structure, field, span } => {
                write!(f, "{structure} at {span} has no {field}, which is required")
            }
            MetadataError::WrongType { structure, field, span } => {
                write!(f, "{structure}.{field} at {span} has the wrong wire type")
            }
            MetadataError::TrailingBytes { span } => write!(
                f,
                "the footer's FileMetaData ends before the footer does; {} byte(s) left over at {span}",
                span.len()
            ),
        }
    }
}

impl std::error::Error for MetadataError {}

impl From<ThriftError> for MetadataError {
    fn from(e: ThriftError) -> Self {
        MetadataError::Thrift(e)
    }
}

/// A column's physical type: how its values are laid out in bytes (ch03).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PhysicalType(pub i64);

impl PhysicalType {
    pub fn name(&self) -> String {
        enum_name(EnumName::Type, self.0)
    }
}

/// One node of the flattened schema: a leaf column or a group (ch03).
///
/// The footer stores the schema tree as a list in depth-first order. A group says how many
/// children follow it; a leaf has none. [`crate::schema`] rebuilds the tree.
#[derive(Clone, Debug, PartialEq)]
pub struct SchemaElement {
    pub name: String,
    pub physical_type: Option<PhysicalType>,
    /// For `FIXED_LEN_BYTE_ARRAY`: how many bytes each value takes.
    pub type_length: Option<i64>,
    pub repetition: Option<String>,
    pub num_children: Option<i64>,
    /// The older annotation, kept by writers for readers that predate logical types.
    pub converted_type: Option<String>,
    pub logical_type: Option<LogicalType>,
    pub scale: Option<i64>,
    pub precision: Option<i64>,
    /// An identifier that survives renames; table formats use it (ch14).
    pub field_id: Option<i64>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Statistics {
    /// `min_value` and `max_value`: the smallest and largest value in the column's own sort
    /// order (ch08), PLAIN-encoded without a length prefix.
    pub min_value: Option<Vec<u8>>,
    pub max_value: Option<Vec<u8>>,
    /// Where the minimum's value bytes are, after their length prefix.
    pub min_span: Option<Span>,
    pub max_span: Option<Span>,
    /// `min` and `max`: the deprecated fields, computed with signed comparison whatever the
    /// type. A reader may use them only where signed comparison is the right order (ch08).
    pub min: Option<Vec<u8>>,
    pub max: Option<Vec<u8>>,
    pub min_deprecated_span: Option<Span>,
    pub max_deprecated_span: Option<Span>,
    pub null_count: Option<i64>,
    pub distinct_count: Option<i64>,
    /// False when a writer shortened a long value: the bound is then not a value in the column.
    pub is_min_value_exact: Option<bool>,
    pub is_max_value_exact: Option<bool>,
    pub span: Span,
}

/// What the footer says about one column chunk: which column, and where its bytes are.
#[derive(Clone, Debug, PartialEq)]
pub struct ColumnChunk {
    pub path: Vec<String>,
    pub physical_type: PhysicalType,
    pub encodings: Vec<String>,
    pub codec: String,
    pub num_values: i64,
    pub total_uncompressed_size: i64,
    pub total_compressed_size: i64,
    pub data_page_offset: i64,
    pub dictionary_page_offset: Option<i64>,
    pub statistics: Option<Statistics>,
    /// The page index (ch09): where this chunk's ColumnIndex and OffsetIndex are, if written.
    pub column_index: Option<Span>,
    pub offset_index: Option<Span>,
    /// Where this chunk's Bloom filter is (ch09), if written. The length is optional in the
    /// format; without it the filter's header says how long its bitset is.
    pub bloom_filter_offset: Option<i64>,
    pub bloom_filter_length: Option<i64>,
    /// Modular encryption (ch13): how this chunk's pages are encrypted, if they are.
    pub crypto: Option<ColumnCrypto>,
    /// Where this chunk's description sits in the footer.
    pub span: Span,
}

impl ColumnChunk {
    /// The chunk's bytes in the file: from its first page to the end of its last.
    ///
    /// The first page is the dictionary page when there is one, and a data page otherwise.
    /// `total_compressed_size` counts every page, headers included, so start plus size is the
    /// end of the chunk. This is the range a reader requests to read the column.
    pub fn byte_range(&self) -> Span {
        let start = match self.dictionary_page_offset {
            Some(d) if d > 0 => d.min(self.data_page_offset),
            _ => self.data_page_offset,
        } as u64;
        Span::new(start, start + self.total_compressed_size as u64)
    }

    pub fn dotted_path(&self) -> String {
        self.path.join(".")
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RowGroup {
    pub num_rows: i64,
    pub total_byte_size: i64,
    pub columns: Vec<ColumnChunk>,
    /// The columns the writer says each row group is sorted by, in order (ch08). A claim, not
    /// something the reader checks.
    pub sorting_columns: Vec<SortingColumn>,
    pub span: Span,
}

/// How a column chunk is encrypted (ch13).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ColumnCrypto {
    /// `None`: encrypted with the footer key. `Some`: with its own key, described by this key
    /// metadata, which names the key but never holds it.
    pub key_metadata: Option<Vec<u8>>,
    pub with_column_key: bool,
    /// The full ColumnMetaData, encrypted: only a reader with the column's key can read it.
    pub encrypted_metadata: Option<Span>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SortingColumn {
    pub column: i64,
    pub descending: bool,
    pub nulls_first: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct KeyValue {
    pub key: String,
    pub value: Option<String>,
}

/// The whole footer, typed.
#[derive(Clone, Debug, PartialEq)]
pub struct FileMetaData {
    pub version: i64,
    pub schema: Vec<SchemaElement>,
    pub num_rows: i64,
    pub row_groups: Vec<RowGroup>,
    pub key_value_metadata: Vec<KeyValue>,
    pub created_by: Option<String>,
    /// One entry per leaf column: the order `min_value` and `max_value` use. `TYPE_ORDER` is the
    /// one this reader knows. `None` when the footer has no `column_orders`, in which case the order of
    /// those fields is undefined (ch08).
    pub column_orders: Option<Vec<String>>,
    /// Set when the file uses modular encryption with a plaintext footer (ch13): the algorithm,
    /// such as `AES_GCM_V1`, and where the footer's signature is.
    pub encryption_algorithm: Option<String>,
    pub footer_signature: Option<Span>,
    /// The decoded Thrift tree the fields above were taken from. Kept, because the browser
    /// shows every field, including the ones this struct does not name.
    pub tree: Node,
}

impl FileMetaData {
    /// The leaf columns: the schema elements that hold data. Groups have children; leaves do not.
    pub fn leaves(&self) -> Vec<&SchemaElement> {
        self.schema
            .iter()
            .skip(1) // the root, which names the whole message
            .filter(|e| e.num_children.unwrap_or(0) == 0)
            .collect()
    }
}

/// Decode the footer: the `footer` bytes, which start at file offset `base`.
///
/// The footer must be exactly one `FileMetaData`. Bytes left over mean the trailer's length and
/// the structure disagree, and a reader that ignored that would be trusting a file it cannot
/// explain.
pub fn decode_file_metadata(footer: &[u8], base: u64) -> Result<FileMetaData, MetadataError> {
    let mut r = ByteReader::new(footer, base);
    let tree = read_struct(&mut r)?;
    let s = as_struct(&tree)?;
    // An encrypted file with a plaintext footer (ch13) signs it: the FileMetaData is followed by
    // a 12-byte nonce and a 16-byte AES-GCM tag, and the footer length counts them.
    let mut footer_signature = None;
    if !r.is_at_end() {
        let rest = Span::new(r.offset(), base + footer.len() as u64);
        if s.field(8).is_some() && rest.len() == FOOTER_SIGNATURE_LEN {
            footer_signature = Some(rest);
        } else {
            return Err(MetadataError::TrailingBytes { span: rest });
        }
    }
    const FMD: &str = "FileMetaData";
    Ok(FileMetaData {
        version: req_int(s, FMD, 1, "version", tree.span)?,
        schema: req_list(s, FMD, 2, "schema", tree.span)?
            .iter()
            .map(schema_element)
            .collect::<Result<_, _>>()?,
        num_rows: req_int(s, FMD, 3, "num_rows", tree.span)?,
        row_groups: req_list(s, FMD, 4, "row_groups", tree.span)?
            .iter()
            .map(row_group)
            .collect::<Result<_, _>>()?,
        key_value_metadata: match opt_list(s, 5) {
            Some(items) => items.iter().map(key_value).collect::<Result<_, _>>()?,
            None => Vec::new(),
        },
        created_by: opt_str(s, 6),
        encryption_algorithm: s.field(8).map(|f| union_member(&f.node)),
        footer_signature,
        column_orders: opt_list(s, 7).map(|items| {
            items
                .iter()
                .map(|n| match &n.value {
                    // A union: a struct with exactly one field set. Field 1 is TYPE_ORDER.
                    Value::Struct(u) if u.field(1).is_some() => "TYPE_ORDER".to_string(),
                    Value::Struct(u) => u
                        .fields
                        .first()
                        .map(|f| format!("UNKNOWN({})", f.id))
                        .unwrap_or_else(|| "UNKNOWN".into()),
                    _ => "UNKNOWN".into(),
                })
                .collect()
        }),
        tree,
    })
}

fn schema_element(node: &Node) -> Result<SchemaElement, MetadataError> {
    let s = as_struct(node)?;
    Ok(SchemaElement {
        name: req_str(s, "SchemaElement", 4, "name", node.span)?,
        physical_type: opt_int(s, 1).map(PhysicalType),
        type_length: opt_int(s, 2),
        repetition: opt_int(s, 3).map(|v| enum_name(EnumName::FieldRepetitionType, v)),
        num_children: opt_int(s, 5),
        converted_type: opt_int(s, 6).map(|v| enum_name(EnumName::ConvertedType, v)),
        scale: opt_int(s, 7),
        precision: opt_int(s, 8),
        field_id: opt_int(s, 9),
        logical_type: s.field(10).and_then(|f| logical::decode(&f.node)),
        span: node.span,
    })
}

fn row_group(node: &Node) -> Result<RowGroup, MetadataError> {
    let s = as_struct(node)?;
    const RG: &str = "RowGroup";
    Ok(RowGroup {
        columns: req_list(s, RG, 1, "columns", node.span)?
            .iter()
            .map(column_chunk)
            .collect::<Result<_, _>>()?,
        total_byte_size: req_int(s, RG, 2, "total_byte_size", node.span)?,
        num_rows: req_int(s, RG, 3, "num_rows", node.span)?,
        sorting_columns: opt_list(s, 4)
            .map(|items| {
                items
                    .iter()
                    .filter_map(|n| match &n.value {
                        Value::Struct(c) => Some(SortingColumn {
                            column: opt_int(c, 1)?,
                            descending: opt_bool(c, 2).unwrap_or(false),
                            nulls_first: opt_bool(c, 3).unwrap_or(false),
                        }),
                        _ => None,
                    })
                    .collect()
            })
            .unwrap_or_default(),
        span: node.span,
    })
}

fn column_chunk(node: &Node) -> Result<ColumnChunk, MetadataError> {
    let chunk = as_struct(node)?;
    // ColumnMetaData is optional in the Thrift definition only because an encrypted column
    // hides it. This reader does not decrypt, so for it the field is required.
    let meta_field = chunk.field(3).ok_or(MetadataError::Missing {
        structure: "ColumnChunk",
        field: "meta_data",
        span: node.span,
    })?;
    let m = as_struct(&meta_field.node)?;
    const CMD: &str = "ColumnMetaData";
    let span = meta_field.node.span;
    Ok(ColumnChunk {
        physical_type: PhysicalType(req_int(m, CMD, 1, "type", span)?),
        encodings: req_list(m, CMD, 2, "encodings", span)?
            .iter()
            .filter_map(|n| match n.value {
                Value::Int(v) => Some(enum_name(EnumName::Encoding, v)),
                _ => None,
            })
            .collect(),
        path: req_list(m, CMD, 3, "path_in_schema", span)?
            .iter()
            .filter_map(|n| match &n.value {
                Value::Binary(b) => Some(String::from_utf8_lossy(b).into_owned()),
                _ => None,
            })
            .collect(),
        codec: enum_name(
            EnumName::CompressionCodec,
            req_int(m, CMD, 4, "codec", span)?,
        ),
        num_values: req_int(m, CMD, 5, "num_values", span)?,
        total_uncompressed_size: req_int(m, CMD, 6, "total_uncompressed_size", span)?,
        total_compressed_size: req_int(m, CMD, 7, "total_compressed_size", span)?,
        data_page_offset: req_int(m, CMD, 9, "data_page_offset", span)?,
        dictionary_page_offset: opt_int(m, 11),
        statistics: match m.field(12) {
            Some(f) => Some(statistics(&f.node)?),
            None => None,
        },
        column_index: offset_and_length(chunk, 6, 7),
        offset_index: offset_and_length(chunk, 4, 5),
        bloom_filter_offset: opt_int(m, 14),
        bloom_filter_length: opt_int(m, 15),
        crypto: chunk.field(8).map(|f| {
            // A union: field 1 for the footer key, field 2 for a column key and its metadata.
            let with_key = match &f.node.value {
                Value::Struct(u) => u.field(2).map(|k| &k.node.value),
                _ => None,
            };
            let key_metadata = match with_key {
                Some(Value::Struct(k)) => opt_bytes(k, 2),
                _ => None,
            };
            ColumnCrypto {
                with_column_key: with_key.is_some(),
                key_metadata,
                encrypted_metadata: value_span(chunk, 9),
            }
        }),
        span: node.span,
    })
}

/// Page headers carry statistics too, in the same struct, so this is shared with
/// [`crate::pages`].
pub(crate) fn statistics(node: &Node) -> Result<Statistics, MetadataError> {
    let s = as_struct(node)?;
    Ok(Statistics {
        // min_value and max_value (fields 6 and 5) replaced min and max (2 and 1), whose order
        // was signed comparison whatever the type. The two pairs are kept apart: which one a
        // reader may use depends on the column's sort order (see crate::stats).
        min_value: opt_bytes(s, 6),
        max_value: opt_bytes(s, 5),
        min_span: value_span(s, 6),
        max_span: value_span(s, 5),
        min: opt_bytes(s, 2),
        max: opt_bytes(s, 1),
        min_deprecated_span: value_span(s, 2),
        max_deprecated_span: value_span(s, 1),
        null_count: opt_int(s, 3),
        distinct_count: opt_int(s, 4),
        is_max_value_exact: opt_bool(s, 7),
        is_min_value_exact: opt_bool(s, 8),
        span: node.span,
    })
}

/// The nonce and tag that sign a plaintext footer (ch13).
pub const FOOTER_SIGNATURE_LEN: u64 = 28;

/// The name of the member a Thrift union holds, from `parquet.thrift`'s names.
pub(crate) fn union_member(node: &Node) -> String {
    match &node.value {
        Value::Struct(u) => u
            .fields
            .first()
            .map(|f| match f.id {
                1 => "AES_GCM_V1".to_string(),
                2 => "AES_GCM_CTR_V1".to_string(),
                id => format!("UNKNOWN({id})"),
            })
            .unwrap_or_else(|| "UNKNOWN".into()),
        _ => "UNKNOWN".into(),
    }
}

/// A region given as an offset field and a length field, when both are present and sensible.
fn offset_and_length(s: &Struct, offset: i16, length: i16) -> Option<Span> {
    let (o, l) = (opt_int(s, offset)?, opt_int(s, length)?);
    (o >= 0 && l >= 0).then(|| Span::new(o as u64, (o + l) as u64))
}

/// The span of a binary field's bytes, without the varint length in front of them.
fn value_span(s: &Struct, id: i16) -> Option<Span> {
    let node = &s.field(id)?.node;
    match &node.value {
        Value::Binary(b) => Some(Span::new(node.span.end - b.len() as u64, node.span.end)),
        _ => None,
    }
}

fn key_value(node: &Node) -> Result<KeyValue, MetadataError> {
    let s = as_struct(node)?;
    Ok(KeyValue {
        key: req_str(s, "KeyValue", 1, "key", node.span)?,
        value: opt_str(s, 2),
    })
}

fn enum_name(e: EnumName, v: i64) -> String {
    enum_value_name(e, v)
        .map(str::to_string)
        .unwrap_or_else(|| format!("UNKNOWN({v})"))
}

pub(crate) fn as_struct(node: &Node) -> Result<&Struct, MetadataError> {
    match &node.value {
        Value::Struct(s) => Ok(s),
        _ => Err(MetadataError::NotAStruct { span: node.span }),
    }
}

pub(crate) fn opt_int(s: &Struct, id: i16) -> Option<i64> {
    match s.field(id)?.node.value {
        Value::Int(v) => Some(v),
        _ => None,
    }
}

pub(crate) fn opt_bool(s: &Struct, id: i16) -> Option<bool> {
    match s.field(id)?.node.value {
        Value::Bool(v) => Some(v),
        _ => None,
    }
}

fn opt_bytes(s: &Struct, id: i16) -> Option<Vec<u8>> {
    match &s.field(id)?.node.value {
        Value::Binary(b) => Some(b.clone()),
        _ => None,
    }
}

fn opt_str(s: &Struct, id: i16) -> Option<String> {
    opt_bytes(s, id).map(|b| String::from_utf8_lossy(&b).into_owned())
}

fn opt_list(s: &Struct, id: i16) -> Option<&Vec<Node>> {
    match &s.field(id)?.node.value {
        Value::List(items) => Some(items),
        _ => None,
    }
}

pub(crate) fn req_int(
    s: &Struct,
    structure: &'static str,
    id: i16,
    field: &'static str,
    span: Span,
) -> Result<i64, MetadataError> {
    match s.field(id) {
        None => Err(MetadataError::Missing {
            structure,
            field,
            span,
        }),
        Some(f) => match f.node.value {
            Value::Int(v) => Ok(v),
            _ => Err(MetadataError::WrongType {
                structure,
                field,
                span: f.span(),
            }),
        },
    }
}

fn req_str(
    s: &Struct,
    structure: &'static str,
    id: i16,
    field: &'static str,
    span: Span,
) -> Result<String, MetadataError> {
    match s.field(id) {
        None => Err(MetadataError::Missing {
            structure,
            field,
            span,
        }),
        Some(f) => match &f.node.value {
            Value::Binary(b) => Ok(String::from_utf8_lossy(b).into_owned()),
            _ => Err(MetadataError::WrongType {
                structure,
                field,
                span: f.span(),
            }),
        },
    }
}

fn req_list<'a>(
    s: &'a Struct,
    structure: &'static str,
    id: i16,
    field: &'static str,
    span: Span,
) -> Result<&'a Vec<Node>, MetadataError> {
    match s.field(id) {
        None => Err(MetadataError::Missing {
            structure,
            field,
            span,
        }),
        Some(f) => match &f.node.value {
            Value::List(items) => Ok(items),
            _ => Err(MetadataError::WrongType {
                structure,
                field,
                span: f.span(),
            }),
        },
    }
}
