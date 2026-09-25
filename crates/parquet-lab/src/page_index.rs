//! The page index: statistics and locations for every page, gathered in one place (ch09).
//!
//! A column chunk's statistics describe all of its pages together. Page headers carry their own
//! statistics ([`crate::pages`]), but a reader has to walk the chunk to see them, which costs the
//! reads it was trying to avoid. The page index moves both into two structures written after the
//! row groups, which a reader fetches in one range per column chunk:
//!
//! - a **ColumnIndex**: per page, whether it is all null, its minimum and maximum, and its null
//!   count, plus whether the pages' bounds are in ascending or descending order;
//! - an **OffsetIndex**: per page, its offset, its size, and the index of its first row.
//!
//! With the OffsetIndex, a reader can fetch one page without reading the ones before it. With
//! the ColumnIndex it can decide which pages to fetch.

use crate::bytes::{ByteReader, Span};
use crate::metadata::{as_struct, ColumnChunk};
use crate::thrift::{read_struct, Node, Struct, Value};

#[derive(Clone, Debug, PartialEq)]
pub struct ColumnIndex {
    pub null_pages: Vec<bool>,
    pub min_values: Vec<Vec<u8>>,
    pub max_values: Vec<Vec<u8>>,
    pub boundary_order: String,
    pub null_counts: Option<Vec<i64>>,
    pub span: Span,
    pub tree: Node,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PageLocation {
    pub offset: i64,
    pub compressed_page_size: i64,
    pub first_row_index: i64,
}

impl PageLocation {
    pub fn span(&self) -> Span {
        Span::new(
            self.offset as u64,
            (self.offset + self.compressed_page_size) as u64,
        )
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct OffsetIndex {
    /// Data pages only: a dictionary page, if any, comes before the first of them.
    pub pages: Vec<PageLocation>,
    pub span: Span,
    pub tree: Node,
}

impl OffsetIndex {
    /// The rows each page holds, as `[first, end)`, given the row group's row count.
    pub fn row_ranges(&self, num_rows: i64) -> Vec<(i64, i64)> {
        (0..self.pages.len())
            .map(|i| {
                let end = self
                    .pages
                    .get(i + 1)
                    .map(|p| p.first_row_index)
                    .unwrap_or(num_rows);
                (self.pages[i].first_row_index, end)
            })
            .collect()
    }
}

fn read_at(file: &[u8], span: Span, what: &str) -> Result<Node, String> {
    let bytes = file
        .get(span.start as usize..span.end as usize)
        .ok_or(format!("the {what} at {span} is past the end of the file"))?;
    let mut r = ByteReader::new(bytes, span.start);
    let node = read_struct(&mut r).map_err(|e| format!("{what} at {span}: {e}"))?;
    if !r.is_at_end() {
        return Err(format!(
            "the {what} at {span} is shorter than the footer says"
        ));
    }
    Ok(node)
}

fn list(s: &Struct, id: i16) -> &[Node] {
    match s.field(id).map(|f| &f.node.value) {
        Some(Value::List(items)) => items,
        _ => &[],
    }
}

fn ints(items: &[Node]) -> Vec<i64> {
    items
        .iter()
        .filter_map(|n| match n.value {
            Value::Int(v) => Some(v),
            _ => None,
        })
        .collect()
}

fn binaries(items: &[Node]) -> Vec<Vec<u8>> {
    items
        .iter()
        .map(|n| match &n.value {
            Value::Binary(b) => b.clone(),
            _ => Vec::new(),
        })
        .collect()
}

/// Read a column chunk's ColumnIndex, if it has one.
pub fn column_index(file: &[u8], chunk: &ColumnChunk) -> Result<Option<ColumnIndex>, String> {
    let Some(span) = chunk.column_index else {
        return Ok(None);
    };
    let tree = read_at(file, span, "ColumnIndex")?;
    let s = as_struct(&tree).map_err(|e| e.to_string())?;
    let null_pages = list(s, 1)
        .iter()
        .map(|n| matches!(n.value, Value::Bool(true)))
        .collect();
    let boundary_order = match s.field(4).map(|f| &f.node.value) {
        Some(Value::Int(v)) => crate::parquet_thrift::enum_value_name(
            crate::parquet_thrift::EnumName::BoundaryOrder,
            *v,
        )
        .unwrap_or("UNKNOWN")
        .to_string(),
        _ => "UNKNOWN".to_string(),
    };
    Ok(Some(ColumnIndex {
        null_pages,
        min_values: binaries(list(s, 2)),
        max_values: binaries(list(s, 3)),
        boundary_order,
        null_counts: s.field(5).map(|_| ints(list(s, 5))),
        span,
        tree,
    }))
}

/// Read a column chunk's OffsetIndex, if it has one.
pub fn offset_index(file: &[u8], chunk: &ColumnChunk) -> Result<Option<OffsetIndex>, String> {
    let Some(span) = chunk.offset_index else {
        return Ok(None);
    };
    let tree = read_at(file, span, "OffsetIndex")?;
    let s = as_struct(&tree).map_err(|e| e.to_string())?;
    let pages = list(s, 1)
        .iter()
        .map(|n| {
            let p = as_struct(n).map_err(|e| e.to_string())?;
            let int = |id| match p.field(id).map(|f| &f.node.value) {
                Some(Value::Int(v)) => Ok(*v),
                _ => Err(format!("PageLocation at {} has no field {id}", n.span)),
            };
            Ok(PageLocation {
                offset: int(1)?,
                compressed_page_size: int(2)?,
                first_row_index: int(3)?,
            })
        })
        .collect::<Result<_, String>>()?;
    Ok(Some(OffsetIndex { pages, span, tree }))
}
