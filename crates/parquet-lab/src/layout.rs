//! Row layout and column layout: the same table, stored two ways (ch01).
//!
//! Not Parquet yet. This is the question Parquet answers, asked with the smallest possible
//! encoding: integers are eight bytes, little-endian; a date is a four-byte day number; a string
//! is a four-byte length and then its bytes. The two layouts use identical encodings and differ
//! only in order:
//!
//! ```text
//! row layout:     id₁ cust₁ country₁ amount₁ date₁ | id₂ cust₂ country₂ …
//! column layout:  id₁ id₂ id₃ … | cust₁ cust₂ … | country₁ country₂ … | …
//! ```
//!
//! Every value's position is recorded, so a query can be turned into the exact byte ranges it
//! needs, and the ranges into requests.

use crate::bytes::Span;

/// A column of the sales table, and how its values are stored.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ColumnType {
    /// Eight bytes, little-endian.
    Int64,
    /// Four bytes, little-endian: days since 1970-01-01.
    Date,
    /// A four-byte little-endian length, then UTF-8 bytes.
    Text,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Cell {
    Int(i64),
    Date(i32),
    Text(String),
}

impl Cell {
    fn encode(&self, out: &mut Vec<u8>) {
        match self {
            Cell::Int(v) => out.extend_from_slice(&v.to_le_bytes()),
            Cell::Date(d) => out.extend_from_slice(&d.to_le_bytes()),
            Cell::Text(s) => {
                out.extend_from_slice(&(s.len() as u32).to_le_bytes());
                out.extend_from_slice(s.as_bytes());
            }
        }
    }

    /// For display: a date as `YYYY-MM-DD`, everything else as itself.
    pub fn show(&self) -> String {
        match self {
            Cell::Int(v) => v.to_string(),
            Cell::Text(s) => s.clone(),
            Cell::Date(d) => civil_from_days(i64::from(*d)),
        }
    }
}

/// The date for a count of days since 1970-01-01, by Howard Hinnant's `civil_from_days`.
fn civil_from_days(z: i64) -> String {
    let z = z + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02}")
}

#[derive(Clone, Debug)]
pub struct Table {
    pub columns: Vec<(&'static str, ColumnType)>,
    pub rows: Vec<Vec<Cell>>,
}

impl Table {
    /// Eight orders. Small enough to see every byte, large enough that the layouts differ.
    pub fn sales() -> Table {
        // Day numbers for 2026-01-03 onwards: 20456 is 2026-01-03.
        let rows = [
            (1, 501, "UK", 1999, 20456),
            (2, 502, "SE", 500, 20456),
            (3, 501, "UK", 4210, 20457),
            (4, 503, "PL", 1250, 20457),
            (5, 504, "US", 875, 20458),
            (6, 502, "SE", 3000, 20458),
            (7, 505, "UK", 640, 20459),
            (8, 501, "UK", 2275, 20459),
        ];
        Table {
            columns: vec![
                ("order_id", ColumnType::Int64),
                ("customer_id", ColumnType::Int64),
                ("country", ColumnType::Text),
                ("amount_cents", ColumnType::Int64),
                ("order_date", ColumnType::Date),
            ],
            rows: rows
                .iter()
                .map(|&(id, cust, country, amount, date)| {
                    vec![
                        Cell::Int(id),
                        Cell::Int(cust),
                        Cell::Text(country.to_string()),
                        Cell::Int(amount),
                        Cell::Date(date),
                    ]
                })
                .collect(),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Layout {
    Rows,
    Columns,
}

/// A table encoded in one layout, with the position of every value.
#[derive(Clone, Debug)]
pub struct Encoded {
    pub layout: Layout,
    pub bytes: Vec<u8>,
    /// `cells[row][column]` is the span that value occupies.
    pub cells: Vec<Vec<Span>>,
}

pub fn encode(table: &Table, layout: Layout) -> Encoded {
    let (nrows, ncols) = (table.rows.len(), table.columns.len());
    let mut bytes = Vec::new();
    let mut cells = vec![vec![Span::new(0, 0); ncols]; nrows];
    let mut put = |r: usize, c: usize, bytes: &mut Vec<u8>| {
        let start = bytes.len() as u64;
        table.rows[r][c].encode(bytes);
        cells[r][c] = Span::new(start, bytes.len() as u64);
    };
    match layout {
        Layout::Rows => {
            for r in 0..nrows {
                for c in 0..ncols {
                    put(r, c, &mut bytes);
                }
            }
        }
        Layout::Columns => {
            for c in 0..ncols {
                for r in 0..nrows {
                    put(r, c, &mut bytes);
                }
            }
        }
    }
    Encoded {
        layout,
        bytes,
        cells,
    }
}

/// What a query needs: some columns of some rows.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Query {
    pub columns: Vec<usize>,
    pub rows: Vec<usize>,
}

/// The byte ranges a query needs, with touching ranges merged: each is one read.
///
/// Merging only ranges that touch is the most generous thing a reader can do without reading
/// bytes it does not need. Chapter 10 lets it read small gaps too, and counts the cost.
pub fn ranges(enc: &Encoded, q: &Query) -> Vec<Span> {
    let mut spans: Vec<Span> = q
        .rows
        .iter()
        .flat_map(|&r| q.columns.iter().map(move |&c| enc.cells[r][c]))
        .collect();
    spans.sort();
    let mut merged: Vec<Span> = Vec::new();
    for s in spans {
        match merged.last_mut() {
            Some(last) if last.end == s.start => last.end = s.end,
            _ => merged.push(s),
        }
    }
    merged
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn both_layouts_hold_the_same_bytes_in_a_different_order() {
        let t = Table::sales();
        let (r, c) = (encode(&t, Layout::Rows), encode(&t, Layout::Columns));
        assert_eq!(r.bytes.len(), c.bytes.len());
        let mut a = r.bytes.clone();
        let mut b = c.bytes.clone();
        a.sort();
        b.sort();
        assert_eq!(a, b);
    }

    #[test]
    fn a_column_is_one_range_in_the_column_layout_and_one_per_row_in_the_row_layout() {
        let t = Table::sales();
        let all_rows: Vec<usize> = (0..t.rows.len()).collect();
        let q = Query {
            columns: vec![2],
            rows: all_rows,
        };
        assert_eq!(ranges(&encode(&t, Layout::Columns), &q).len(), 1);
        assert_eq!(ranges(&encode(&t, Layout::Rows), &q).len(), t.rows.len());
    }

    #[test]
    fn a_whole_row_is_one_range_in_the_row_layout() {
        let t = Table::sales();
        let q = Query {
            columns: (0..t.columns.len()).collect(),
            rows: vec![3],
        };
        assert_eq!(ranges(&encode(&t, Layout::Rows), &q).len(), 1);
        assert_eq!(
            ranges(&encode(&t, Layout::Columns), &q).len(),
            t.columns.len()
        );
    }

    #[test]
    fn day_numbers_are_dates() {
        assert_eq!(civil_from_days(0), "1970-01-01");
        assert_eq!(civil_from_days(20456), "2026-01-03");
        assert_eq!(civil_from_days(-1), "1969-12-31");
    }
}
