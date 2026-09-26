//! The read path: a query turned into requests, and requests into rows (ch10).
//!
//! Everything before this chapter decided *what* to read. This module decides *how*: in which
//! order, in how many requests, over how many connections. It runs a query, `SELECT columns
//! WHERE condition`, against a file in an object store, in three phases:
//!
//! 1. **The footer** ([`crate::reader`]), with whatever tail prefetch the strategy asks for.
//! 2. **The indexes the plan needs**: Bloom filters and page indexes ([`crate::prune`]), unless
//!    the prefetched tail already holds them.
//! 3. **The data**: the byte ranges the plan chose.
//!
//! In phases 2 and 3 the ranges are sorted, and two ranges whose gap is at most the strategy's
//! `coalesce_gap` become one request. That reads the gap too, which is waste, and saves a
//! request, which is time. With more than one connection, the requests of a phase overlap.
//!
//! The reader decodes only from bytes it fetched. It keeps a copy of the file that starts empty
//! and fills in each response, so a range it forgot to request reads as zeros and fails its
//! decode; the tests check every result against a full read.

use crate::bytes::Span;
use crate::json::Json;
use crate::metadata::FileMetaData;
use crate::object_store::{
    GetRange, MemoryStore, NetworkModel, ObjectStore, Request, TracingStore,
};
use crate::prune::{self, Mechanisms, Op, Predicate};
use crate::reader::{read_footer, FooterOptions};
use crate::schema::{build, leaves, Leaf};

/// How to issue requests.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Strategy {
    pub footer: FooterOptions,
    pub connections: usize,
    /// Two ranges this close or closer become one request: `Some(0)` merges ranges that touch.
    /// `None` never merges, so every range is its own request.
    pub coalesce_gap: Option<u64>,
    /// Read whole column chunks, even when the page index would allow single pages.
    pub whole_chunks: bool,
    pub mechanisms: Mechanisms,
}

/// A query: the columns to return, and at most one condition.
#[derive(Clone, Debug, PartialEq)]
pub struct Query {
    pub columns: Vec<usize>,
    pub condition: Option<(usize, Op, String)>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ScanResult {
    pub requests: Vec<Request>,
    pub elapsed_us: u64,
    pub bytes_fetched: u64,
    /// Bytes the reader planned to use: fetched bytes minus the gaps coalescing read.
    pub bytes_planned: u64,
    pub rows_decoded: u64,
    /// Row numbers in the file, counting from 0, of the rows that satisfy the condition.
    pub matches: Vec<u64>,
    /// The first matching rows, column by column, as JSON values.
    pub rows: Vec<Vec<Json>>,
    pub column_names: Vec<String>,
}

/// The file as the reader has it: the bytes it has fetched, and zeros elsewhere.
struct Fetched {
    bytes: Vec<u8>,
    have: Vec<Span>,
}

impl Fetched {
    fn add(&mut self, span: Span, data: &[u8]) {
        self.bytes[span.start as usize..span.end as usize].copy_from_slice(data);
        self.have.push(span);
    }

    /// The parts of `s` not yet fetched.
    fn missing(&self, s: Span) -> Vec<Span> {
        let mut parts = vec![s];
        for h in &self.have {
            parts = parts
                .into_iter()
                .flat_map(|p| {
                    let mut out = Vec::new();
                    if p.start < h.start.min(p.end) {
                        out.push(Span::new(p.start, h.start.min(p.end)));
                    }
                    if h.end.max(p.start) < p.end {
                        out.push(Span::new(h.end.max(p.start), p.end));
                    }
                    out
                })
                .collect();
        }
        parts
    }
}

/// Sort ranges and merge those whose gap is at most `gap` bytes. With no gap, only ranges that
/// overlap are merged, since fetching the same byte twice is never useful.
pub fn coalesce(mut spans: Vec<Span>, gap: Option<u64>) -> Vec<Span> {
    spans.sort();
    let mut out: Vec<Span> = Vec::new();
    for s in spans {
        let merges = |last: &Span| match gap {
            Some(g) => s.start <= last.end.saturating_add(g),
            None => s.start < last.end,
        };
        match out.last_mut() {
            Some(last) if merges(last) => {
                *last = Span::new(last.start, last.end.max(s.end));
            }
            _ => out.push(s),
        }
    }
    out
}

/// Fetch every range the reader does not already have, coalesced, as one phase.
fn fetch<S: ObjectStore>(
    store: &mut S,
    key: &str,
    have: &mut Fetched,
    wanted: Vec<Span>,
    gap: Option<u64>,
    why: &str,
) -> Result<u64, String> {
    // Only the bytes not already held: a merged request must not fetch the tail again.
    let missing: Vec<Span> = wanted.into_iter().flat_map(|s| have.missing(s)).collect();
    let planned: u64 = coalesce(missing.clone(), Some(0))
        .iter()
        .map(|s| s.len())
        .sum();
    let requests: Vec<Span> = coalesce(missing, gap)
        .into_iter()
        .flat_map(|r| have.missing(r))
        .collect();
    if requests.is_empty() {
        return Ok(0);
    }
    store.next_phase();
    for r in requests {
        let got = store
            .get(key, GetRange::Bounded(r), why)
            .map_err(|e| e.to_string())?;
        have.add(got.span, &got.bytes);
    }
    Ok(planned)
}

/// Run `query` against `object`, stored under `key`, with `strategy`, over `model`.
pub fn scan(
    object: &[u8],
    key: &str,
    query: &Query,
    strategy: Strategy,
    model: NetworkModel,
) -> Result<ScanResult, String> {
    let mut inner = MemoryStore::new();
    inner.put(key, object.to_vec());
    let mut store = TracingStore::with_connections(inner, model, strategy.connections);
    scan_in(&mut store, object, key, query, strategy)
}

/// [`scan`], in a store that other requests share: a table's reader opens one of its files
/// (ch15). `object` is the file's bytes, which the store holds under `key`; the result's
/// requests and totals are the whole store's.
pub fn scan_in(
    store: &mut TracingStore<MemoryStore>,
    object: &[u8],
    key: &str,
    query: &Query,
    strategy: Strategy,
) -> Result<ScanResult, String> {
    let mut have = Fetched {
        bytes: vec![0; object.len()],
        have: Vec::new(),
    };

    // Phase 1: the footer. Every byte the footer read returned is now the reader's.
    let before = store.requests.len();
    let footer = read_footer(store, key, strategy.footer).map_err(|e| e.to_string())?;
    for r in store.requests[before..].iter().filter(|r| r.key == key) {
        if let Some(span) = r.returned {
            let s = span.start as usize..span.end as usize;
            have.add(span, &object[s]);
        }
    }
    let md: FileMetaData = footer.metadata;
    let root = build(&md.schema).map_err(|e| e.to_string())?;
    let all = leaves(&root);
    let flat: Vec<&Leaf> = all.iter().filter(|l| l.max_repetition_level == 0).collect();
    let leaf_of = |c: usize| {
        flat.iter()
            .find(|l| l.column == c)
            .copied()
            .ok_or(format!("no column {c} that does not repeat"))
    };
    let columns: Vec<&Leaf> = query
        .columns
        .iter()
        .map(|&c| leaf_of(c))
        .collect::<Result<_, _>>()?;
    let predicate = match &query.condition {
        Some((c, op, text)) => {
            let leaf = leaf_of(*c)?;
            let converted = md.schema[leaf.element].converted_type.clone();
            Some((leaf, Predicate::new(leaf, converted.as_deref(), *op, text)?))
        }
        None => None,
    };
    // Every column the query touches: the condition's too, since it must be read to test rows.
    let mut touched: Vec<usize> = query.columns.clone();
    if let Some((leaf, _)) = &predicate {
        if !touched.contains(&leaf.column) {
            touched.push(leaf.column);
        }
    }

    // Phase 2: the indexes the plan will consult. Which ones depends on the footer alone.
    let mut planned = 0;
    if let Some((leaf, p)) = &predicate {
        let mut wanted = Vec::new();
        let type_order = md
            .column_orders
            .as_ref()
            .and_then(|o| o.get(leaf.column))
            .is_some_and(|o| o == "TYPE_ORDER");
        for rg in &md.row_groups {
            let chunk = &rg.columns[leaf.column];
            // A row group the footer's statistics already rule out needs no index.
            if strategy.mechanisms.statistics {
                if let Some(st) = &chunk.statistics {
                    let b = crate::stats::bounds(st, p.comparator, type_order).ok();
                    let bounds = b.as_ref().map(|b| (&b.min[..], &b.max[..]));
                    if prune::against_bounds(p, bounds, st.null_count, chunk.num_values).skip {
                        continue;
                    }
                }
            }
            if strategy.mechanisms.bloom && p.op == Op::Eq {
                if let (Some(o), Some(l)) = (chunk.bloom_filter_offset, chunk.bloom_filter_length) {
                    wanted.push(Span::new(o as u64, (o + l) as u64));
                }
            }
            if strategy.mechanisms.page_index && !strategy.whole_chunks {
                wanted.extend(chunk.column_index);
                wanted.extend(touched.iter().filter_map(|&c| rg.columns[c].offset_index));
            }
        }
        planned += fetch(
            store,
            key,
            &mut have,
            wanted,
            strategy.coalesce_gap,
            "read the indexes the plan needs",
        )?;
    }

    // Phase 3: the data. The plan runs on the fetched copy, so it sees only fetched indexes.
    let mut use_ = strategy.mechanisms;
    if strategy.whole_chunks {
        use_.page_index = false;
    }
    // A Bloom filter without a recorded length could not be fetched in one request; this reader
    // does not consult it.
    if let Some((leaf, _)) = &predicate {
        if md.row_groups.iter().any(|rg| {
            let c = &rg.columns[leaf.column];
            c.bloom_filter_offset.is_some() && c.bloom_filter_length.is_none()
        }) {
            use_.bloom = false;
        }
    }
    // For each row group read: its index, the rows kept, and the byte ranges to fetch.
    type GroupRead = (usize, Vec<(i64, i64)>, Vec<Span>);
    let groups: Vec<GroupRead> = match &predicate {
        Some((leaf, p)) => {
            let plan = prune::plan(&have.bytes, &md, leaf, p, &touched, use_)?;
            plan.row_groups
                .into_iter()
                .filter(|g| !g.skipped)
                .map(|g| {
                    let spans = g.reads.iter().flat_map(|r| r.spans.clone()).collect();
                    (g.index, g.rows, spans)
                })
                .collect()
        }
        None => md
            .row_groups
            .iter()
            .enumerate()
            .map(|(i, rg)| {
                let spans = touched
                    .iter()
                    .map(|&c| rg.columns[c].byte_range())
                    .collect();
                (i, vec![(0, rg.num_rows)], spans)
            })
            .collect(),
    };
    let wanted: Vec<Span> = groups.iter().flat_map(|g| g.2.clone()).collect();
    planned += fetch(
        store,
        key,
        &mut have,
        wanted,
        strategy.coalesce_gap,
        "read the pages the plan kept",
    )?;

    // Decode what was fetched, and keep the rows that satisfy the condition.
    let mut matches = Vec::new();
    let mut rows = Vec::new();
    let mut rows_decoded = 0u64;
    let mut first_row = 0u64;
    let mut group_starts = Vec::new();
    for rg in &md.row_groups {
        group_starts.push(first_row);
        first_row += rg.num_rows as u64;
    }
    for (g, ranges, spans) in &groups {
        let rg = &md.row_groups[*g];
        // Each touched column's values by row number within the row group.
        // Each column's values: row number, PLAIN bytes (None for null), and the value to show.
        type Values = Vec<(i64, Option<Vec<u8>>, Json)>;
        let mut by_column: Vec<(usize, Values)> = Vec::new();
        for &c in &touched {
            let leaf = leaf_of(c)?;
            let chunk = &rg.columns[c];
            let oi = crate::page_index::offset_index(&have.bytes, chunk)
                .ok()
                .flatten();
            let data = match &oi {
                Some(oi) if !strategy.whole_chunks && use_.page_index => {
                    let offsets: Vec<u64> = oi
                        .pages
                        .iter()
                        .filter(|p| spans.iter().any(|s| s.contains(p.span())))
                        .map(|p| p.offset as u64)
                        .collect();
                    let firsts: Vec<i64> = oi
                        .pages
                        .iter()
                        .filter(|p| offsets.contains(&(p.offset as u64)))
                        .map(|p| p.first_row_index)
                        .collect();
                    let d = crate::column::read_column_pages(&have.bytes, chunk, leaf, &offsets)
                        .map_err(|e| e.to_string())?;
                    (d, Some(firsts))
                }
                _ => (
                    crate::column::read_column(&have.bytes, chunk, leaf)
                        .map_err(|e| e.to_string())?,
                    None,
                ),
            };
            let (d, firsts) = data;
            let dict = usize::from(d.dictionary.is_some());
            let mut values = Vec::new();
            let mut row_in_page = 0;
            let mut last_page = usize::MAX;
            for t in &d.triples {
                if t.page != last_page {
                    last_page = t.page;
                    row_in_page = 0;
                }
                let base = firsts.as_ref().map(|f| f[t.page - dict]).unwrap_or(0);
                let row = if firsts.is_some() {
                    base + row_in_page
                } else {
                    values.len() as i64
                };
                row_in_page += 1;
                let raw = t
                    .value
                    .as_ref()
                    .map(|v| v.to_plain_bytes(leaf.physical_type));
                let shown = t
                    .value
                    .as_ref()
                    .map(|v| {
                        crate::logical::value_json(
                            leaf.physical_type,
                            leaf.logical_type.as_ref(),
                            v,
                        )
                    })
                    .unwrap_or(Json::Null);
                values.push((row, raw, shown));
            }
            by_column.push((c, values));
        }
        let find = |c: usize, row: i64| {
            by_column
                .iter()
                .find(|(k, _)| *k == c)
                .and_then(|(_, vs)| vs.iter().find(|(r, _, _)| *r == row))
        };
        for &(a, b) in ranges {
            for row in a..b {
                rows_decoded += 1;
                let keep = match &predicate {
                    Some((leaf, p)) => {
                        let v = find(leaf.column, row)
                            .ok_or(format!("row {row} of row group {g} was not decoded"))?;
                        p.row_matches(v.1.as_deref())
                    }
                    None => true,
                };
                if keep {
                    matches.push(group_starts[*g] + row as u64);
                    if rows.len() < 20 {
                        rows.push(
                            query
                                .columns
                                .iter()
                                .map(|&c| find(c, row).map(|v| v.2.clone()).unwrap_or(Json::Null))
                                .collect(),
                        );
                    }
                }
            }
        }
    }
    Ok(ScanResult {
        elapsed_us: store.elapsed_us(),
        bytes_fetched: store.bytes_returned(),
        bytes_planned: planned,
        requests: store.requests.clone(),
        rows_decoded,
        matches,
        rows,
        column_names: columns.iter().map(|l| l.dotted_path()).collect(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn close_ranges_merge_and_distant_ones_do_not() {
        // Gaps of 20 and 10 bytes: a 10-byte threshold merges only the second.
        let spans = vec![Span::new(100, 200), Span::new(0, 50), Span::new(70, 90)];
        let apart = vec![Span::new(0, 50), Span::new(70, 90), Span::new(100, 200)];
        assert_eq!(coalesce(spans.clone(), Some(0)), apart);
        let near = vec![Span::new(0, 50), Span::new(70, 200)];
        assert_eq!(coalesce(spans, Some(10)), near);
        let touching = vec![Span::new(0, 10), Span::new(10, 20)];
        assert_eq!(coalesce(touching.clone(), Some(0)), vec![Span::new(0, 20)]);
        assert_eq!(coalesce(touching.clone(), None), touching);
    }
}
