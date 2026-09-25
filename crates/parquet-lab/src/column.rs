//! Reading a column chunk into levels and values (ch04).
//!
//! A column chunk's pages hold, for every value slot, a repetition level, a definition level,
//! and, when the slot is not null, a value. This module reads them out as triples:
//!
//! ```text
//! (r, d, value)    r: where in the nesting a new element starts
//!                  d: how deep along the path the value is defined
//!                  value: present only when d is the column's maximum
//! ```
//!
//! A data page (version 1) body is laid out in three parts, and the levels are only there when
//! the column can have them:
//!
//! ```text
//! [u32 length][repetition levels]   if max repetition level > 0
//! [u32 length][definition levels]   if max definition level > 0
//! [values, PLAIN]                   one per slot whose d is the maximum
//! ```
//!
//! What this reader does not do yet, and says so rather than guessing: decompress pages (ch07),
//! decode dictionary pages and indices (ch05), and read data page version 2 (ch06).

use std::fmt;

use crate::bytes::{ByteReader, Span};
use crate::metadata::ColumnChunk;
use crate::pages::{walk_pages, Page};
use crate::plain::{self, PlainValue};
use crate::rle::{self, bit_width, Run};
use crate::schema::Leaf;

/// One value slot of a column.
#[derive(Clone, Debug, PartialEq)]
pub struct Triple {
    pub rep: u32,
    pub def: u32,
    pub value: Option<PlainValue>,
    pub value_span: Option<Span>,
    /// Which page it came from.
    pub page: usize,
}

/// A data page's body, split into its parts.
#[derive(Clone, Debug, PartialEq)]
pub struct DataPage {
    pub page: Page,
    /// The four-byte length and the repetition-level runs after it.
    pub rep_levels: Option<(Span, Vec<Run>)>,
    pub def_levels: Option<(Span, Vec<Run>)>,
    pub values: Span,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ColumnData {
    pub pages: Vec<DataPage>,
    pub triples: Vec<Triple>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ColumnError(pub String);

impl fmt::Display for ColumnError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for ColumnError {}

fn err<T>(message: impl Into<String>) -> Result<T, ColumnError> {
    Err(ColumnError(message.into()))
}

/// Read one level stream: a four-byte length, then that many bytes of RLE/bit-packed runs.
fn level_stream(
    r: &mut ByteReader,
    max_level: u32,
    count: usize,
) -> Result<(Span, Vec<Run>), ColumnError> {
    let start = r.offset();
    let len = r.read_le_u32().map_err(|e| ColumnError(e.to_string()))? as usize;
    let (bytes, body) = r.read_bytes(len).map_err(|e| ColumnError(e.to_string()))?;
    let runs = rle::decode(bytes, body.start, bit_width(max_level), count)
        .map_err(|e| ColumnError(format!("levels: {e}")))?;
    Ok((Span::new(start, body.end), runs))
}

/// Read every data page of a column chunk into triples.
pub fn read_column(
    file: &[u8],
    chunk: &ColumnChunk,
    leaf: &Leaf,
) -> Result<ColumnData, ColumnError> {
    if chunk.codec != "UNCOMPRESSED" {
        return err(format!(
            "this column is compressed with {}; the reader decompresses pages from ch07 on",
            chunk.codec
        ));
    }
    let range = chunk.byte_range();
    let Some(bytes) = file.get(range.start as usize..range.end as usize) else {
        return err(format!(
            "the column chunk claims bytes {range}, past the end of the file"
        ));
    };
    let pages = walk_pages(bytes, range.start).map_err(|e| ColumnError(e.to_string()))?;
    let mut out = ColumnData {
        pages: Vec::new(),
        triples: Vec::new(),
    };
    for (index, page) in pages.into_iter().enumerate() {
        match page.page_type.as_str() {
            "DATA_PAGE" => {}
            "DICTIONARY_PAGE" => {
                return err("this column is dictionary-encoded; ch05 decodes dictionaries")
            }
            "DATA_PAGE_V2" => return err("this column uses data page version 2; ch06 reads it"),
            other => return err(format!("unexpected page type {other}")),
        }
        if page.encoding.as_deref() != Some("PLAIN") {
            return err(format!(
                "values encoded with {}; ch05 decodes encodings other than PLAIN",
                page.encoding.as_deref().unwrap_or("an unknown encoding")
            ));
        }
        let count = page.num_values.unwrap_or(0).max(0) as usize;
        let body_start = page.body_span.start as usize - range.start as usize;
        let body = &bytes[body_start..body_start + page.body_span.len() as usize];
        let mut r = ByteReader::new(body, page.body_span.start);
        let rep_levels = if leaf.max_repetition_level > 0 {
            Some(level_stream(&mut r, leaf.max_repetition_level, count)?)
        } else {
            None
        };
        let def_levels = if leaf.max_definition_level > 0 {
            Some(level_stream(&mut r, leaf.max_definition_level, count)?)
        } else {
            None
        };
        let reps = rep_levels
            .as_ref()
            .map(|(_, runs)| rle::values(runs))
            .unwrap_or(vec![0; count]);
        let defs = def_levels
            .as_ref()
            .map(|(_, runs)| rle::values(runs))
            .unwrap_or(vec![leaf.max_definition_level; count]);
        let present = defs
            .iter()
            .filter(|&&d| d == leaf.max_definition_level)
            .count();
        let values_start = r.offset();
        let rest = &body[(values_start - page.body_span.start) as usize..];
        let values = plain::decode(
            leaf.physical_type,
            leaf.type_length,
            rest,
            values_start,
            present,
        )
        .map_err(|e| ColumnError(format!("values: {e}")))?;
        let mut next = values.into_iter();
        for i in 0..count {
            let (value, value_span) = if defs[i] == leaf.max_definition_level {
                match next.next() {
                    Some((v, s)) => (Some(v), Some(s)),
                    None => return err("fewer values than definition levels say are present"),
                }
            } else {
                (None, None)
            };
            out.triples.push(Triple {
                rep: reps[i],
                def: defs[i],
                value,
                value_span,
                page: index,
            });
        }
        out.pages.push(DataPage {
            page,
            rep_levels,
            def_levels,
            values: Span::new(values_start, page_end(&out.triples, values_start)),
        });
    }
    Ok(out)
}

fn page_end(triples: &[Triple], start: u64) -> u64 {
    triples
        .iter()
        .rev()
        .find_map(|t| t.value_span.map(|s| s.end))
        .unwrap_or(start)
        .max(start)
}
