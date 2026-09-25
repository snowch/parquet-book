//! Grades ch11's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test writing_parquet_well -- --ignored
//! ```
//!
//! Problem 11.1 is graded against the reader's own plans for the ch11 fixtures: for values in a
//! column, the number of row groups the reader keeps when asked for each. Problem 11.2 is graded
//! against the ranges the row groups' decoded values actually span.

use std::path::PathBuf;

use exercises::writing_parquet_well::{mean_row_groups_per_lookup, row_groups_for};
use parquet_lab::prune::{plan, Mechanisms, Op, Predicate};

const FILES: [&str; 7] = [
    "writing-baseline.parquet",
    "writing-one-group.parquet",
    "writing-small-groups.parquet",
    "writing-by-country.parquet",
    "writing-shuffled.parquet",
    "writing-plain.parquet",
    "writing-no-index.parquet",
];

/// For each file and integer column: its values in file order, each row group's bounds, the row
/// group size, and for each distinct value the row groups the reader keeps.
type Case = (String, Vec<i64>, Vec<(i64, i64)>, usize, Vec<(i64, usize)>);

fn cases() -> Vec<Case> {
    let mut out = Vec::new();
    for name in FILES {
        let bytes = std::fs::read(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../fixtures")
                .join(name),
        )
        .unwrap();
        let md = parquet_lab::report::open_bytes(&bytes).unwrap();
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        for leaf in parquet_lab::schema::leaves(&root) {
            if leaf.dotted_path() != "order_id" && leaf.dotted_path() != "customer_id" {
                continue;
            }
            let mut values = Vec::new();
            let mut bounds = Vec::new();
            for rg in &md.row_groups {
                let d = parquet_lab::column::read_column(&bytes, &rg.columns[leaf.column], &leaf)
                    .unwrap();
                let vs: Vec<i64> = d
                    .triples
                    .iter()
                    .map(|t| {
                        i64::from_le_bytes(
                            t.value
                                .as_ref()
                                .unwrap()
                                .to_plain_bytes(leaf.physical_type)
                                .try_into()
                                .unwrap(),
                        )
                    })
                    .collect();
                bounds.push((*vs.iter().min().unwrap(), *vs.iter().max().unwrap()));
                values.extend(vs);
            }
            let mut distinct = values.clone();
            distinct.sort();
            distinct.dedup();
            let only_stats = Mechanisms {
                statistics: true,
                bloom: false,
                page_index: false,
            };
            let kept = distinct
                .iter()
                .step_by(3)
                .map(|&v| {
                    let p = Predicate::new(&leaf, None, Op::Eq, &v.to_string()).unwrap();
                    let pl = plan(&bytes, &md, &leaf, &p, &[leaf.column], only_stats).unwrap();
                    (v, pl.row_groups.iter().filter(|g| !g.skipped).count())
                })
                .collect();
            let size = md.row_groups[0].num_rows as usize;
            out.push((
                format!("{name} {}", leaf.dotted_path()),
                values,
                bounds,
                size,
                kept,
            ));
        }
    }
    out
}

#[test]
#[ignore = "problem 11.1: fails until you solve it"]
fn problem_11_1_counts_what_the_reader_reads() {
    for (name, _, bounds, _, kept) in cases() {
        for (v, n) in kept {
            assert_eq!(row_groups_for(&bounds, v), n, "{name}: order {v}");
        }
    }
}

#[test]
#[ignore = "problem 11.2: fails until you solve it"]
fn problem_11_2_predicts_the_mean_from_the_values() {
    for (name, values, bounds, size, _) in cases() {
        let mut distinct = values.clone();
        distinct.sort();
        distinct.dedup();
        let expected = distinct
            .iter()
            .map(|&v| {
                bounds
                    .iter()
                    .filter(|&&(lo, hi)| lo <= v && v <= hi)
                    .count()
            })
            .sum::<usize>() as f64
            / distinct.len() as f64;
        let got = mean_row_groups_per_lookup(&values, size);
        assert!(
            (got - expected).abs() < 1e-9,
            "{name}: {got} against {expected}"
        );
    }
}
