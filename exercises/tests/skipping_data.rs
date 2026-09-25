//! Grades ch09's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test skipping_data -- --ignored
//! ```
//!
//! Problem 9.1 is graded against the data: for every page of the pruning fixtures and many
//! conditions, a page you skip must hold no matching row, and you must skip every page the
//! bounds alone rule out.

use std::path::PathBuf;

use exercises::skipping_data::{can_skip, may_contain, Cmp};

fn fixture(name: &str) -> Vec<u8> {
    std::fs::read(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../fixtures")
            .join(name),
    )
    .unwrap()
}

/// Every page of every INT64 column of the pruning fixtures: its values (None for null), and
/// the bounds and null count its ColumnIndex records.
type Page = (Vec<Option<i64>>, Option<(i64, i64)>, i64);

fn pages() -> Vec<Page> {
    let mut out = Vec::new();
    for name in ["pruning-sorted.parquet", "pruning-shuffled.parquet"] {
        let bytes = fixture(name);
        let md = parquet_lab::report::open_bytes(&bytes).unwrap();
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        for leaf in parquet_lab::schema::leaves(&root) {
            if leaf.physical_type.0 != 2 {
                continue;
            }
            for rg in &md.row_groups {
                let chunk = &rg.columns[leaf.column];
                let ci = parquet_lab::page_index::column_index(&bytes, chunk)
                    .unwrap()
                    .unwrap();
                let data = parquet_lab::column::read_column(&bytes, chunk, &leaf).unwrap();
                for (i, _) in data.pages.iter().enumerate() {
                    let values = data
                        .triples
                        .iter()
                        .filter(|t| t.page == i)
                        .map(|t| {
                            t.value.as_ref().map(|v| {
                                i64::from_le_bytes(
                                    v.to_plain_bytes(leaf.physical_type).try_into().unwrap(),
                                )
                            })
                        })
                        .collect();
                    let int = |b: &[u8]| i64::from_le_bytes(b.try_into().unwrap());
                    let bounds = (!ci.null_pages[i])
                        .then(|| (int(&ci.min_values[i]), int(&ci.max_values[i])));
                    out.push((values, bounds, ci.null_counts.as_ref().unwrap()[i]));
                }
            }
        }
    }
    out
}

fn matches(cmp: Cmp, value: i64, v: Option<i64>) -> bool {
    match (cmp, v) {
        (Cmp::IsNull, v) => v.is_none(),
        (_, None) => false,
        (Cmp::Eq, Some(v)) => v == value,
        (Cmp::Lt, Some(v)) => v < value,
        (Cmp::Gt, Some(v)) => v > value,
    }
}

#[test]
#[ignore = "problem 9.1: fails until you solve it"]
fn problem_9_1_never_skips_a_match_and_skips_what_the_bounds_rule_out() {
    let (mut checked, mut skipped) = (0, 0);
    for (values, bounds, nulls) in pages() {
        let n = values.len() as i64;
        let probes = [
            i64::MIN,
            0,
            1,
            100,
            431,
            500,
            5_000,
            9_800,
            424_242,
            999_999,
            i64::MAX,
        ];
        let own: Vec<i64> = values.iter().flatten().copied().step_by(9).collect();
        for value in probes.iter().chain(&own) {
            for cmp in [Cmp::Eq, Cmp::Lt, Cmp::Gt, Cmp::IsNull] {
                let skip = can_skip(cmp, *value, bounds, nulls, n);
                let any = values.iter().any(|&v| matches(cmp, *value, v));
                assert!(!(skip && any), "{cmp:?} {value}: you skipped a page holding a match ({bounds:?}, {nulls} nulls)");
                // What the metadata alone proves: then the answer must be skip.
                let provable = match (cmp, bounds) {
                    (Cmp::IsNull, _) => nulls == 0,
                    (_, None) => nulls == n,
                    (Cmp::Eq, Some((lo, hi))) => *value < lo || *value > hi,
                    (Cmp::Lt, Some((lo, _))) => lo >= *value,
                    (Cmp::Gt, Some((_, hi))) => hi <= *value,
                };
                assert_eq!(
                    skip, provable,
                    "{cmp:?} {value} against {bounds:?} with {nulls} of {n} null"
                );
                skipped += usize::from(skip);
                checked += 1;
            }
        }
    }
    assert!(checked > 1000 && skipped > 100);
}

#[test]
#[ignore = "problem 9.2: fails until you solve it"]
fn problem_9_2_agrees_with_the_fixtures_filters() {
    let bytes = fixture("pruning-shuffled.parquet");
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let mut probes = 0;
    for rg in &md.row_groups {
        let filter = parquet_lab::bloom::read(&bytes, &rg.columns[1])
            .unwrap()
            .unwrap();
        for candidate in (100_000i64..1_000_000).step_by(311) {
            let hash = parquet_lab::bloom::xxh64(&candidate.to_le_bytes(), 0);
            assert_eq!(
                may_contain(&filter.bitset, hash),
                filter.probe_hash(hash).may_contain,
                "customer {candidate}"
            );
            probes += 1;
        }
    }
    assert!(probes > 10_000);
}
