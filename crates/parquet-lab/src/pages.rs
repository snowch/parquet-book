//! Pages: walking a column chunk one page header at a time (ch06).
//!
//! A column chunk is a run of pages laid end to end. Each page is a Thrift `PageHeader` followed
//! by `compressed_page_size` bytes of body. The header says how long the body is, and so where
//! the next header starts, which is how a reader walks a chunk without any index.
//!
//! This module reads the headers, measures the bodies, and checks each body against the CRC its
//! header carries, when it carries one. [`crate::column`] decodes what the bodies hold.

use crate::bytes::{crc32, ByteReader, Span};
use crate::metadata::{
    as_struct, opt_bool, opt_int, req_int, statistics, MetadataError, Statistics,
};
use crate::parquet_thrift::{enum_value_name, EnumName};
use crate::thrift::{read_struct, Node};

#[derive(Clone, Debug, PartialEq)]
pub struct Page {
    pub page_type: String,
    /// The Thrift header.
    pub header_span: Span,
    /// The body that follows it: `compressed_page_size` bytes.
    pub body_span: Span,
    pub uncompressed_page_size: i64,
    pub compressed_page_size: i64,
    pub num_values: Option<i64>,
    pub encoding: Option<String>,
    pub statistics: Option<Statistics>,
    /// The checksum the header carries, and whether the body still matches it.
    pub crc: Option<i64>,
    pub crc_ok: Option<bool>,
    /// Data page version 2's extra fields.
    pub v2: Option<PageV2>,
    pub header: Node,
}

/// What a data page version 2 header adds (ch06).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PageV2 {
    pub num_nulls: i64,
    pub num_rows: i64,
    /// The level streams' lengths: in version 2 they are in the header, not the body.
    pub definition_levels_byte_length: i64,
    pub repetition_levels_byte_length: i64,
    /// Whether the values section is compressed. The levels never are.
    pub is_compressed: bool,
}

impl Page {
    pub fn span(&self) -> Span {
        Span::new(self.header_span.start, self.body_span.end)
    }
}

/// Walk the pages of a column chunk whose bytes are `chunk`, starting at file offset `base`.
///
/// Stops at the end of the chunk. A page whose body would run past the end is an error: the
/// chunk's size in the footer and the sizes in its page headers must agree.
pub fn walk_pages(chunk: &[u8], base: u64) -> Result<Vec<Page>, MetadataError> {
    let mut r = ByteReader::new(chunk, base);
    let mut pages = Vec::new();
    while !r.is_at_end() {
        let header = read_struct(&mut r)?;
        let h = as_struct(&header)?;
        const PH: &str = "PageHeader";
        let page_type = req_int(h, PH, 1, "type", header.span)?;
        let uncompressed = req_int(h, PH, 2, "uncompressed_page_size", header.span)?;
        let compressed = req_int(h, PH, 3, "compressed_page_size", header.span)?;
        // The sub-header that matches the page type: 5 for a v1 data page, 7 for a dictionary
        // page, 8 for a v2 data page. All three put num_values in field 1; the encoding is in
        // field 2 for v1 and dictionary pages and field 4 for v2.
        let (sub, encoding_field) = match page_type {
            0 => (h.field(5), 2),
            2 => (h.field(7), 2),
            3 => (h.field(8), 4),
            _ => (None, 0),
        };
        let sub = match sub {
            Some(f) => Some(as_struct(&f.node)?),
            None => None,
        };
        let stats_field = match page_type {
            0 => 5,
            3 => 8,
            _ => 0,
        };
        let stats = match sub.and_then(|s| s.field(stats_field)) {
            Some(f) => Some(statistics(&f.node)?),
            None => None,
        };
        let (body, body_span) = r
            .read_bytes(usize::try_from(compressed).unwrap_or(usize::MAX))
            .map_err(|e| MetadataError::Thrift(e.into()))?;
        let crc = opt_int(h, 4);
        // The header stores the CRC as a signed 32-bit integer.
        let crc_ok = crc.map(|c| c as i32 as u32 == crc32(body));
        let v2 = match (page_type, sub) {
            (3, Some(s)) => Some(PageV2 {
                num_nulls: opt_int(s, 2).unwrap_or(0),
                num_rows: opt_int(s, 3).unwrap_or(0),
                definition_levels_byte_length: opt_int(s, 5).unwrap_or(0),
                repetition_levels_byte_length: opt_int(s, 6).unwrap_or(0),
                is_compressed: opt_bool(s, 7).unwrap_or(true),
            }),
            _ => None,
        };
        pages.push(Page {
            page_type: enum_value_name(EnumName::PageType, page_type)
                .map(str::to_string)
                .unwrap_or_else(|| format!("UNKNOWN({page_type})")),
            header_span: header.span,
            body_span,
            uncompressed_page_size: uncompressed,
            compressed_page_size: compressed,
            num_values: sub.and_then(|s| opt_int(s, 1)),
            encoding: sub
                .and_then(|s| opt_int(s, encoding_field))
                .and_then(|v| enum_value_name(EnumName::Encoding, v))
                .map(str::to_string),
            statistics: stats,
            crc,
            crc_ok,
            v2,
            header,
        });
    }
    Ok(pages)
}
