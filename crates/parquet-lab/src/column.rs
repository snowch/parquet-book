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
//! The values may be encoded in any way [`crate::decode`] knows (ch05). A dictionary page, when
//! there is one, comes first, and the data pages then hold indices into it.
//!
//! A data page version 2 (ch06) keeps the same three parts, but the level streams' lengths move
//! into the page header, so the levels have no length prefix, and they are never compressed.
//!
//! A compressed page (ch07) is decompressed before any of this. Under version 1 the whole body
//! is one compressed block; under version 2 only the values are, and only when the header says
//! so. Spans into a decompressed copy would point at bytes that are not in the file, so every
//! span found inside one is reported as the compressed bytes that hold it: the reader can say
//! which compressed block a value came from, not which of its bytes.

use std::fmt;

use crate::bytes::{ByteReader, Span};
use crate::compress;
use crate::decode::{self, Dictionary, Step};
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
    /// Other bytes the value needed: its dictionary index run, its length, its prefix length.
    pub extra_spans: Vec<Span>,
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
    pub encoding: String,
    /// How the values were decoded, step by step.
    pub steps: Vec<Step>,
}

/// A column chunk's dictionary page, decoded.
#[derive(Clone, Debug, PartialEq)]
pub struct DictionaryPage {
    pub page: Page,
    pub entries: Dictionary,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ColumnData {
    pub dictionary: Option<DictionaryPage>,
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

/// Read one level stream of RLE / bit-packed runs.
///
/// In a version 1 page the stream starts with its own four-byte length (`known_len` is `None`).
/// In a version 2 page the header already gave the length, and the stream has no prefix.
fn level_stream(
    r: &mut ByteReader,
    max_level: u32,
    count: usize,
    known_len: Option<usize>,
) -> Result<(Span, Vec<Run>), ColumnError> {
    let start = r.offset();
    let len = match known_len {
        Some(n) => n,
        None => r.read_le_u32().map_err(|e| ColumnError(e.to_string()))? as usize,
    };
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
    refuse_encrypted(chunk)?;
    let range = chunk.byte_range();
    let Some(bytes) = file.get(range.start as usize..range.end as usize) else {
        return err(format!(
            "the column chunk claims bytes {range}, past the end of the file"
        ));
    };
    let pages = walk_pages(bytes, range.start).map_err(|e| ColumnError(e.to_string()))?;
    decode_pages(file, chunk, leaf, pages)
}

/// Read only some pages of a column chunk: its dictionary page, if it has one, and the data
/// pages starting at `offsets`, each read where the page index says it is (ch10). The bytes
/// between them are never looked at, so a reader need not have fetched them.
pub fn read_column_pages(
    file: &[u8],
    chunk: &ColumnChunk,
    leaf: &Leaf,
    offsets: &[u64],
) -> Result<ColumnData, ColumnError> {
    refuse_encrypted(chunk)?;
    let range = chunk.byte_range();
    let one = |at: u64| -> Result<Page, ColumnError> {
        let bytes = file
            .get(at as usize..range.end as usize)
            .ok_or_else(|| ColumnError(format!("no page at offset {at} in chunk {range}")))?;
        crate::pages::read_page(&mut ByteReader::new(bytes, at))
            .map_err(|e| ColumnError(format!("page at offset {at}: {e}")))
    };
    let mut pages = Vec::new();
    if chunk.dictionary_page_offset.is_some_and(|d| d > 0) {
        pages.push(one(range.start)?);
    }
    for &at in offsets {
        pages.push(one(at)?);
    }
    decode_pages(file, chunk, leaf, pages)
}

/// An encrypted column chunk's pages are encrypted modules (ch13). Without its key they cannot
/// be read, and the reader says so rather than decoding ciphertext.
fn refuse_encrypted(chunk: &ColumnChunk) -> Result<(), ColumnError> {
    match &chunk.crypto {
        Some(c) => err(format!(
            "column {} is encrypted with {}, and this reader has no keys",
            chunk.dotted_path(),
            if c.with_column_key {
                "its own key"
            } else {
                "the footer key"
            }
        )),
        None => Ok(()),
    }
}

/// Decode pages already located: a dictionary page first, if there is one, then data pages.
fn decode_pages(
    file: &[u8],
    chunk: &ColumnChunk,
    leaf: &Leaf,
    pages: Vec<Page>,
) -> Result<ColumnData, ColumnError> {
    let mut out = ColumnData {
        dictionary: None,
        pages: Vec::new(),
        triples: Vec::new(),
    };
    let codec = chunk.codec.as_str();
    for (index, page) in pages.into_iter().enumerate() {
        let Some(body) = file.get(page.body_span.start as usize..page.body_span.end as usize)
        else {
            return err(format!(
                "page body {} is past the end of the file",
                page.body_span
            ));
        };
        match page.page_type.as_str() {
            "DATA_PAGE" | "DATA_PAGE_V2" => {}
            "DICTIONARY_PAGE" => {
                // The dictionary: every distinct value, PLAIN-encoded, once.
                let count = page.num_values.unwrap_or(0).max(0) as usize;
                let plain_body = decompress(codec, body, &page, page.uncompressed_page_size)?;
                let mut entries = plain::decode(
                    leaf.physical_type,
                    leaf.type_length,
                    &plain_body,
                    page.body_span.start,
                    count,
                )
                .map_err(|e| ColumnError(format!("dictionary: {e}")))?;
                if codec != "UNCOMPRESSED" {
                    for (_, s) in &mut entries {
                        *s = page.body_span;
                    }
                }
                out.dictionary = Some(DictionaryPage { page, entries });
                continue;
            }
            other => return err(format!("unexpected page type {other}")),
        }
        let count = page.num_values.unwrap_or(0).max(0) as usize;
        // Version 1 compresses the whole body as one block. Decompress it, and read the levels
        // and values from the copy.
        let whole = page.v2.is_none() && codec != "UNCOMPRESSED";
        let v1_plain;
        let (levels_bytes, levels_base) = if whole {
            v1_plain = decompress(codec, body, &page, page.uncompressed_page_size)?;
            (&v1_plain[..], page.body_span.start)
        } else {
            (body, page.body_span.start)
        };
        let mut r = ByteReader::new(levels_bytes, levels_base);
        // Version 2 moves the level lengths into the header and never compresses the levels.
        let (rep_len, def_len) = match page.v2 {
            Some(v2) => (
                Some(v2.repetition_levels_byte_length.max(0) as usize),
                Some(v2.definition_levels_byte_length.max(0) as usize),
            ),
            None => (None, None),
        };
        let rep_levels = if leaf.max_repetition_level > 0 {
            Some(level_stream(
                &mut r,
                leaf.max_repetition_level,
                count,
                rep_len,
            )?)
        } else {
            None
        };
        let def_levels = if leaf.max_definition_level > 0 {
            Some(level_stream(
                &mut r,
                leaf.max_definition_level,
                count,
                def_len,
            )?)
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
        let rest = &levels_bytes[(values_start - levels_base) as usize..];
        // Version 2 compresses only the values, and only when the header says so.
        let values_compressed =
            codec != "UNCOMPRESSED" && page.v2.is_some_and(|v2| v2.is_compressed);
        let v2_plain;
        let rest = if values_compressed {
            let levels = (values_start - page.body_span.start) as i64;
            v2_plain = decompress(codec, rest, &page, page.uncompressed_page_size - levels)?;
            &v2_plain[..]
        } else {
            rest
        };
        let encoding = page.encoding.clone().unwrap_or_default();
        let mut decoded = decode::values(
            &encoding,
            leaf.physical_type,
            leaf.type_length,
            rest,
            values_start,
            present,
            out.dictionary.as_ref().map(|d| &d.entries),
        )
        .map_err(|e| ColumnError(format!("values: {e}")))?;
        let mut values = Span::new(values_start, decoded.end.max(values_start));
        let mut rep_levels = rep_levels;
        let mut def_levels = def_levels;
        // Spans found in a decompressed copy become the compressed bytes that hold them.
        if whole || values_compressed {
            let from = if whole {
                page.body_span.start
            } else {
                values_start
            };
            let compressed = Span::new(from, page.body_span.end);
            blur(&mut decoded, compressed);
            values = compressed;
            if whole {
                for (s, runs) in rep_levels.iter_mut().chain(def_levels.iter_mut()) {
                    *s = compressed;
                    for run in runs {
                        run.header = compressed;
                        run.body = compressed;
                    }
                }
            }
        }
        let mut next = decoded.values.into_iter();
        for i in 0..count {
            let (value, value_span, extra_spans) = if defs[i] == leaf.max_definition_level {
                match next.next() {
                    Some(v) => (Some(v.value), Some(v.span), v.extra),
                    None => return err("fewer values than definition levels say are present"),
                }
            } else {
                (None, None, vec![])
            };
            out.triples.push(Triple {
                rep: reps[i],
                def: defs[i],
                value,
                value_span,
                extra_spans,
                page: index,
            });
        }
        out.pages.push(DataPage {
            page,
            rep_levels,
            def_levels,
            values,
            encoding,
            steps: decoded.steps,
        });
    }
    Ok(out)
}

/// Decompress a page body, or a version 2 page's values section, into `size` bytes.
fn decompress(codec: &str, bytes: &[u8], page: &Page, size: i64) -> Result<Vec<u8>, ColumnError> {
    let size = usize::try_from(size).map_err(|_| ColumnError(format!("page size {size}")))?;
    compress::decompress(codec, bytes, page.body_span.start, size)
        .map(|d| d.bytes)
        .map_err(|e| ColumnError(format!("page at offset {}: {e}", page.header_span.start)))
}

/// Report every span of a decode as `to`: the compressed bytes the decoded bytes came from.
fn blur(decoded: &mut decode::Decoded, to: Span) {
    for v in &mut decoded.values {
        v.span = to;
        v.extra.clear();
    }
    for step in &mut decoded.steps {
        step.span = to;
    }
    decoded.end = to.end;
}

/// The index of the first row each page holds, given each page's repetition levels.
///
/// A row starts wherever the repetition level is 0. Under data page version 1 a row can begin in
/// one page and continue in the next, so a page's first slot may not start a row; the page's
/// first row is then the one that starts next. Counting the zeros before each page is enough.
pub fn first_rows(rep_levels_per_page: &[Vec<u32>]) -> Vec<u64> {
    let mut out = Vec::with_capacity(rep_levels_per_page.len());
    let mut started = 0u64;
    for page in rep_levels_per_page {
        out.push(started);
        started += page.iter().filter(|&&r| r == 0).count() as u64;
    }
    out
}
