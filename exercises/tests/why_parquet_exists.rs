//! Grades ch01's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test why_parquet_exists -- --ignored
//! ```

use exercises::why_parquet_exists::reads_for;
use parquet_lab::layout::{encode, ranges, Layout, Query, Table};

/// Every query over the sales table: each non-empty set of columns, with every row or one row.
fn every_query() -> Vec<Query> {
    let t = Table::sales();
    let mut out = Vec::new();
    for mask in 1u32..(1 << t.columns.len()) {
        let columns: Vec<usize> = (0..t.columns.len())
            .filter(|c| mask & (1 << c) != 0)
            .collect();
        out.push(Query {
            columns: columns.clone(),
            rows: (0..t.rows.len()).collect(),
        });
        for r in 0..t.rows.len() {
            out.push(Query {
                columns: columns.clone(),
                rows: vec![r],
            });
        }
    }
    out
}

fn value_spans(enc: &parquet_lab::layout::Encoded, q: &Query) -> Vec<(u64, u64)> {
    let mut spans: Vec<(u64, u64)> = q
        .rows
        .iter()
        .flat_map(|&r| q.columns.iter().map(move |&c| (r, c)))
        .map(|(r, c)| (enc.cells[r][c].start, enc.cells[r][c].end))
        .collect();
    // Hand them over in reverse, so a solution that forgets to sort is caught.
    spans.reverse();
    spans
}

#[test]
#[ignore = "problem 1.1: fails until you solve it"]
fn problem_1_1_reads_match_the_planner_for_every_query() {
    let t = Table::sales();
    for layout in [Layout::Rows, Layout::Columns] {
        let enc = encode(&t, layout);
        for q in every_query() {
            let expected: Vec<(u64, u64)> =
                ranges(&enc, &q).iter().map(|s| (s.start, s.end)).collect();
            let yours = reads_for(&value_spans(&enc, &q));
            assert_eq!(
                yours, expected,
                "{layout:?} layout, columns {:?}, rows {:?}: if you have more reads than expected, \
                 check that touching ranges are merged; if fewer, check that you do not merge across a gap",
                q.columns, q.rows
            );
        }
    }
}

#[test]
#[ignore = "problem 1.1: fails until you solve it"]
fn problem_1_1_gaps_are_never_merged() {
    assert_eq!(reads_for(&[(10, 20), (21, 30)]), vec![(10, 20), (21, 30)]);
    assert_eq!(reads_for(&[(21, 30), (10, 21)]), vec![(10, 30)]);
    assert_eq!(reads_for(&[]), vec![]);
}

/// Scaffolding, not a problem: the cases differ, so matching them is not luck.
#[test]
fn the_queries_include_both_layouts_winning() {
    let t = Table::sales();
    let (rows, cols) = (encode(&t, Layout::Rows), encode(&t, Layout::Columns));
    let qs = every_query();
    assert!(qs
        .iter()
        .any(|q| ranges(&rows, q).len() < ranges(&cols, q).len()));
    assert!(qs
        .iter()
        .any(|q| ranges(&rows, q).len() > ranges(&cols, q).len()));
}
