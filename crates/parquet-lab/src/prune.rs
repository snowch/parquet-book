//! Skipping data: deciding, from metadata alone, what a query does not need to read (ch09).
//!
//! A reader is given a condition on one column, such as `order_id = 431` or `amount_cents > 9000`.
//! Before it reads a page it asks three things, each cheaper than the reading it may save:
//!
//! 1. **Row group statistics** ([`crate::stats`]), already in the footer: can any value in this
//!    column chunk's range satisfy the condition?
//! 2. **The Bloom filter** ([`crate::bloom`]), for equality only: was this exact value ever added?
//! 3. **The page index** ([`crate::page_index`]): the same question as the first, page by page,
//!    and then which rows those pages hold, and so which pages of the *other* columns to read.
//!
//! Every answer is either "skip", which must be certain, or "read", which only means "cannot rule
//! it out". A wrong "skip" loses rows; a wrong "read" costs bytes. Each decision records why.

use std::cmp::Ordering;

use crate::bytes::Span;
use crate::metadata::{ColumnChunk, FileMetaData};
use crate::schema::Leaf;
use crate::stats::{bounds, Comparator};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Op {
    Eq,
    NotEq,
    Lt,
    LtEq,
    Gt,
    GtEq,
    IsNull,
    IsNotNull,
}

impl Op {
    pub fn parse(s: &str) -> Result<Op, String> {
        Ok(match s {
            "=" => Op::Eq,
            "!=" => Op::NotEq,
            "<" => Op::Lt,
            "<=" => Op::LtEq,
            ">" => Op::Gt,
            ">=" => Op::GtEq,
            "is null" => Op::IsNull,
            "is not null" => Op::IsNotNull,
            other => return Err(format!("unknown comparison {other:?}")),
        })
    }

    pub fn symbol(&self) -> &'static str {
        match self {
            Op::Eq => "=",
            Op::NotEq => "!=",
            Op::Lt => "<",
            Op::LtEq => "<=",
            Op::Gt => ">",
            Op::GtEq => ">=",
            Op::IsNull => "is null",
            Op::IsNotNull => "is not null",
        }
    }

    /// Whether a value compares this way. Null matches nothing but `is null`.
    pub fn matches(&self, ordering: Option<Ordering>) -> bool {
        use Ordering::*;
        matches!(
            (self, ordering),
            (Op::Eq, Some(Equal))
                | (Op::NotEq, Some(Less | Greater))
                | (Op::Lt, Some(Less))
                | (Op::LtEq, Some(Less | Equal))
                | (Op::Gt, Some(Greater))
                | (Op::GtEq, Some(Greater | Equal))
        )
    }
}

/// A condition on one column: `column op value`.
#[derive(Clone, Debug, PartialEq)]
pub struct Predicate {
    pub column: usize,
    pub op: Op,
    /// The value as PLAIN bytes, as statistics store it. `None` for `is null` and `is not null`.
    pub value: Option<Vec<u8>>,
    pub comparator: Comparator,
}

impl Predicate {
    /// Parse a condition's value for `leaf`: integers, floats and strings.
    pub fn new(
        leaf: &Leaf,
        converted: Option<&str>,
        op: Op,
        text: &str,
    ) -> Result<Predicate, String> {
        let comparator = Comparator::for_leaf(leaf, converted);
        let value = match op {
            Op::IsNull | Op::IsNotNull => None,
            _ => Some(literal(comparator, text.trim())?),
        };
        Ok(Predicate {
            column: leaf.column,
            op,
            value,
            comparator,
        })
    }

    /// Whether one row's value satisfies the condition. `None` is null.
    pub fn row_matches(&self, value: Option<&[u8]>) -> bool {
        match (self.op, value, &self.value) {
            (Op::IsNull, v, _) => v.is_none(),
            (Op::IsNotNull, v, _) => v.is_some(),
            (op, Some(v), Some(x)) => op.matches(self.comparator.compare(v, x)),
            _ => false,
        }
    }
}

/// A literal as PLAIN bytes for a column compared with `c`.
fn literal(c: Comparator, text: &str) -> Result<Vec<u8>, String> {
    let bad = || format!("{text:?} is not a value of this column");
    Ok(match c {
        Comparator::I32 => text
            .parse::<i32>()
            .map_err(|_| bad())?
            .to_le_bytes()
            .to_vec(),
        Comparator::U32 => text
            .parse::<u32>()
            .map_err(|_| bad())?
            .to_le_bytes()
            .to_vec(),
        Comparator::I64 => text
            .parse::<i64>()
            .map_err(|_| bad())?
            .to_le_bytes()
            .to_vec(),
        Comparator::U64 => text
            .parse::<u64>()
            .map_err(|_| bad())?
            .to_le_bytes()
            .to_vec(),
        Comparator::F32 => text
            .parse::<f32>()
            .map_err(|_| bad())?
            .to_le_bytes()
            .to_vec(),
        Comparator::F64 => text
            .parse::<f64>()
            .map_err(|_| bad())?
            .to_le_bytes()
            .to_vec(),
        Comparator::Bytes => text.trim_matches('"').as_bytes().to_vec(),
        _ => {
            return Err(
                "this reader parses values only for integer, float and string columns".into(),
            )
        }
    })
}

/// A decision and the reason for it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    pub skip: bool,
    pub why: String,
}

fn skip(why: impl Into<String>) -> Decision {
    Decision {
        skip: true,
        why: why.into(),
    }
}

fn read(why: impl Into<String>) -> Decision {
    Decision {
        skip: false,
        why: why.into(),
    }
}

/// Decide from a minimum and maximum (when usable), a null count, and a value count.
pub fn against_bounds(
    p: &Predicate,
    bounds: Option<(&[u8], &[u8])>,
    null_count: Option<i64>,
    num_values: i64,
) -> Decision {
    let all_null = null_count == Some(num_values) && num_values > 0;
    match p.op {
        Op::IsNull if null_count == Some(0) => return skip("the null count is zero"),
        Op::IsNull => return read("the null count is not zero, or not recorded"),
        Op::IsNotNull if all_null => return skip("every value is null"),
        Op::IsNotNull => return read("some values are not null"),
        _ if all_null => return skip("every value is null, and null satisfies no comparison"),
        _ => {}
    }
    let (Some(x), Some((min, max))) = (&p.value, bounds) else {
        return read("no usable minimum and maximum");
    };
    let c = p.comparator;
    let (vs_min, vs_max) = match (c.compare(x, min), c.compare(x, max)) {
        (Some(a), Some(b)) => (a, b),
        _ => return read("the value cannot be placed in the column's order"),
    };
    use Ordering::*;
    let ruled_out = match p.op {
        Op::Eq => vs_min == Less || vs_max == Greater,
        Op::NotEq => vs_min == Equal && vs_max == Equal,
        Op::Lt => vs_min != Greater,   // min >= x
        Op::LtEq => vs_min == Less,    // min > x
        Op::Gt => vs_max != Less,      // max <= x
        Op::GtEq => vs_max == Greater, // max < x
        Op::IsNull | Op::IsNotNull => unreachable!(),
    };
    if ruled_out {
        skip(match p.op {
            Op::Eq if vs_min == Less => "the value is below the minimum",
            Op::Eq => "the value is above the maximum",
            Op::NotEq => "every value equals it",
            Op::Lt | Op::LtEq => "the minimum is too large",
            _ => "the maximum is too small",
        })
    } else {
        read("the range may hold a match")
    }
}

/// Which mechanisms a plan may use.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Mechanisms {
    pub statistics: bool,
    pub bloom: bool,
    pub page_index: bool,
}

impl Mechanisms {
    pub const ALL: Mechanisms = Mechanisms {
        statistics: true,
        bloom: true,
        page_index: true,
    };
    pub const NONE: Mechanisms = Mechanisms {
        statistics: false,
        bloom: false,
        page_index: false,
    };
}

/// One page of the condition's column, and whether its rows are kept.
#[derive(Clone, Debug, PartialEq)]
pub struct PagePlan {
    pub span: Span,
    pub rows: (i64, i64),
    pub decision: Decision,
}

/// The bytes of one projected column a plan reads in one row group.
#[derive(Clone, Debug, PartialEq)]
pub struct ColumnRead {
    pub column: usize,
    pub spans: Vec<Span>,
    /// How many of the chunk's data pages those spans include, and how many it has.
    pub pages_read: usize,
    pub pages_total: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RowGroupPlan {
    pub index: usize,
    pub num_rows: i64,
    /// Each mechanism consulted, in order, and what it decided.
    pub steps: Vec<(&'static str, Decision)>,
    pub skipped: bool,
    pub pages: Vec<PagePlan>,
    /// The rows still to read, as `[start, end)` ranges within the row group.
    pub rows: Vec<(i64, i64)>,
    pub reads: Vec<ColumnRead>,
    /// Bytes of Bloom filters and page indexes fetched to decide.
    pub index_bytes: u64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Plan {
    pub row_groups: Vec<RowGroupPlan>,
}

impl Plan {
    pub fn bytes_read(&self) -> u64 {
        self.row_groups
            .iter()
            .flat_map(|g| &g.reads)
            .flat_map(|r| &r.spans)
            .map(|s| s.len())
            .sum()
    }

    pub fn index_bytes(&self) -> u64 {
        self.row_groups.iter().map(|g| g.index_bytes).sum()
    }

    pub fn rows_read(&self) -> i64 {
        self.row_groups
            .iter()
            .flat_map(|g| &g.rows)
            .map(|(a, b)| b - a)
            .sum()
    }
}

fn overlaps(a: (i64, i64), b: (i64, i64)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

/// Merge touching or overlapping ranges.
fn merge(mut ranges: Vec<(i64, i64)>) -> Vec<(i64, i64)> {
    ranges.sort();
    let mut out: Vec<(i64, i64)> = Vec::new();
    for r in ranges {
        match out.last_mut() {
            Some(last) if r.0 <= last.1 => last.1 = last.1.max(r.1),
            _ => out.push(r),
        }
    }
    out
}

/// The bytes of `chunk` needed for `rows`: its dictionary page, if any, and the data pages
/// whose rows overlap them. Without an offset index, the whole chunk.
fn column_read(
    file: &[u8],
    chunk: &ColumnChunk,
    column: usize,
    rows: &[(i64, i64)],
    num_rows: i64,
    use_index: bool,
) -> (ColumnRead, u64) {
    let whole = chunk.byte_range();
    let oi = if use_index {
        crate::page_index::offset_index(file, chunk).ok().flatten()
    } else {
        None
    };
    let Some(oi) = oi else {
        let pages = crate::page_index::offset_index(file, chunk)
            .ok()
            .flatten()
            .map(|o| o.pages.len())
            .unwrap_or(0);
        return (
            ColumnRead {
                column,
                spans: vec![whole],
                pages_read: pages,
                pages_total: pages,
            },
            0,
        );
    };
    let mut spans = Vec::new();
    // The dictionary page sits before the first data page; any page read needs it.
    let first_data = oi
        .pages
        .first()
        .map(|p| p.offset as u64)
        .unwrap_or(whole.end);
    let ranges = oi.row_ranges(num_rows);
    let wanted: Vec<usize> = (0..oi.pages.len())
        .filter(|&i| rows.iter().any(|&r| overlaps(ranges[i], r)))
        .collect();
    if !wanted.is_empty() && first_data > whole.start {
        spans.push(Span::new(whole.start, first_data));
    }
    spans.extend(wanted.iter().map(|&i| oi.pages[i].span()));
    (
        ColumnRead {
            column,
            spans,
            pages_read: wanted.len(),
            pages_total: oi.pages.len(),
        },
        oi.span.len(),
    )
}

/// Plan a read of `projection` for rows satisfying `p`.
pub fn plan(
    file: &[u8],
    md: &FileMetaData,
    leaf: &Leaf,
    p: &Predicate,
    projection: &[usize],
    use_: Mechanisms,
) -> Result<Plan, String> {
    let type_order = md
        .column_orders
        .as_ref()
        .and_then(|o| o.get(leaf.column))
        .is_some_and(|o| o == "TYPE_ORDER");
    let mut groups = Vec::new();
    for (g, rg) in md.row_groups.iter().enumerate() {
        let chunk = &rg.columns[leaf.column];
        let mut steps = Vec::new();
        let mut index_bytes = 0;
        let mut skipped = false;
        if use_.statistics {
            let d = match &chunk.statistics {
                Some(s) => {
                    let b = bounds(s, p.comparator, type_order).ok();
                    against_bounds(
                        p,
                        b.as_ref().map(|b| (&b.min[..], &b.max[..])),
                        s.null_count,
                        chunk.num_values,
                    )
                }
                None => read("the column chunk has no statistics"),
            };
            skipped |= d.skip;
            steps.push(("statistics", d));
        }
        if use_.bloom && !skipped && p.op == Op::Eq {
            if let (Some(filter), Some(x)) = (crate::bloom::read(file, chunk)?, &p.value) {
                index_bytes += filter.bitset_span.end - filter.header_span.start;
                let probe = filter.probe(x);
                let d = if probe.may_contain {
                    read("every bit the value's hash chose is set")
                } else {
                    skip("a bit the value's hash chose is clear")
                };
                skipped |= d.skip;
                steps.push(("Bloom filter", d));
            }
        }
        let mut pages = Vec::new();
        let mut rows = if skipped {
            vec![]
        } else {
            vec![(0, rg.num_rows)]
        };
        // Page rows equal page values only when the column does not repeat; for a repeated
        // column the reader would need the level histograms, and this one does not use them.
        let use_pages = use_.page_index && !skipped && leaf.max_repetition_level == 0;
        if use_pages {
            let ci = crate::page_index::column_index(file, chunk)?;
            let oi = crate::page_index::offset_index(file, chunk)?;
            if let (Some(ci), Some(oi)) = (ci, oi) {
                index_bytes += ci.span.len();
                let ranges = oi.row_ranges(rg.num_rows);
                for (i, loc) in oi.pages.iter().enumerate() {
                    let page_rows = ranges[i].1 - ranges[i].0;
                    let nulls = ci.null_counts.as_ref().map(|n| n[i]);
                    let b = (!ci.null_pages[i] && type_order)
                        .then(|| (&ci.min_values[i][..], &ci.max_values[i][..]))
                        .filter(|(lo, hi)| {
                            p.comparator.compare(lo, lo).is_some()
                                && p.comparator.compare(hi, hi).is_some()
                        });
                    let nulls = if ci.null_pages[i] {
                        Some(page_rows)
                    } else {
                        nulls
                    };
                    let decision = against_bounds(p, b, nulls, page_rows);
                    pages.push(PagePlan {
                        span: loc.span(),
                        rows: ranges[i],
                        decision,
                    });
                }
                rows = merge(
                    pages
                        .iter()
                        .filter(|q| !q.decision.skip)
                        .map(|q| q.rows)
                        .collect(),
                );
                steps.push((
                    "page index",
                    if rows.is_empty() {
                        skip("every page's bounds rule it out")
                    } else {
                        read(format!(
                            "{} of {} pages may hold a match",
                            pages.iter().filter(|q| !q.decision.skip).count(),
                            pages.len()
                        ))
                    },
                ));
                skipped |= rows.is_empty();
            }
        }
        let mut reads = Vec::new();
        if !skipped {
            for &column in projection {
                let (r, oi_bytes) = column_read(
                    file,
                    &rg.columns[column],
                    column,
                    &rows,
                    rg.num_rows,
                    use_pages,
                );
                index_bytes += oi_bytes;
                reads.push(r);
            }
        }
        groups.push(RowGroupPlan {
            index: g,
            num_rows: rg.num_rows,
            steps,
            skipped,
            pages,
            rows: if skipped { vec![] } else { rows },
            reads,
            index_bytes,
        });
    }
    Ok(Plan { row_groups: groups })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ranges_merge_when_they_touch() {
        assert_eq!(
            merge(vec![(40, 80), (0, 40), (120, 160)]),
            vec![(0, 80), (120, 160)]
        );
    }
}
