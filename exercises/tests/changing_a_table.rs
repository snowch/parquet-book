//! Grades ch15's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test changing_a_table -- --ignored
//! ```

use std::path::PathBuf;

use exercises::changing_a_table::{files_to_open, plan_compaction};
use parquet_lab::changes::{self, read_snapshots, DataFile, DeleteFile, Snapshot};

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

/// Every snapshot of ch15's table, as pyarrow's generator recorded them.
fn snapshots() -> Vec<Snapshot> {
    let text = std::fs::read_to_string(fixtures().join("changes/_snapshots.json")).unwrap();
    read_snapshots(&text).unwrap()
}

/// Snapshots the fixture does not have: ranges that overlap, files that are all small, deletes
/// on every file, and an empty table.
fn made_up() -> Vec<Snapshot> {
    let file = |path: &str, rows: i64, lo: i64, hi: i64| DataFile {
        path: path.into(),
        record_count: rows,
        file_size: 40 * rows as u64 + 900,
        min_key: lo,
        max_key: hi,
    };
    let delete = |path: &str, rows: i64, of: &str| DeleteFile {
        path: path.into(),
        record_count: rows,
        file_size: 1000,
        data_file: of.into(),
    };
    let snapshot = |data_files, delete_files| Snapshot {
        id: "made-up".into(),
        summary: String::new(),
        data_files,
        delete_files,
    };
    vec![
        snapshot(
            vec![
                file("late.parquet", 50, 500, 600),
                file("wide.parquet", 300, 1, 1000),
                file("early.parquet", 20, 1, 40),
                file("tiny.parquet", 5, 41, 45),
            ],
            vec![
                delete("d1.parquet", 3, "wide.parquet"),
                delete("d2.parquet", 1, "late.parquet"),
                delete("d3.parquet", 2, "wide.parquet"),
            ],
        ),
        snapshot(
            (0..12)
                .map(|i| {
                    file(
                        &format!("s{i:02}.parquet"),
                        10 + i,
                        100 * i,
                        100 * i + 9 + i,
                    )
                })
                .collect(),
            Vec::new(),
        ),
        snapshot(
            vec![
                file("a.parquet", 100, 1, 100),
                file("b.parquet", 100, 101, 200),
            ],
            vec![
                delete("x.parquet", 100, "a.parquet"),
                delete("y.parquet", 1, "b.parquet"),
            ],
        ),
        snapshot(Vec::new(), Vec::new()),
    ]
}

#[test]
#[ignore = "problem 15.1: fails until you solve it"]
fn problem_15_1_opens_the_files_the_reader_opens() {
    for s in snapshots().iter().chain(&made_up()) {
        for key in (-1..=1001).chain([2000, i64::MIN, i64::MAX]) {
            let (data, deletes) = changes::files_to_open(s, key);
            let expected = (
                data.iter().map(|f| f.path.clone()).collect::<Vec<_>>(),
                deletes.iter().map(|d| d.path.clone()).collect::<Vec<_>>(),
            );
            assert_eq!(files_to_open(s, key), expected, "{} {key}", s.id);
        }
    }
}

#[test]
#[ignore = "problem 15.2: fails until you solve it"]
fn problem_15_2_plans_what_the_reader_plans() {
    for s in snapshots().iter().chain(&made_up()) {
        for target in [0, 1, 10, 50, 100, 196, 200, 250, 400, 1000] {
            for small in [0, 1, 10, 20, 100, 200, 1000] {
                let expected: Vec<Vec<String>> = changes::plan_compaction(s, target, small)
                    .into_iter()
                    .map(|g| g.data_files)
                    .collect();
                assert_eq!(
                    plan_compaction(s, target, small),
                    expected,
                    "{} target {target} small {small}",
                    s.id
                );
            }
        }
    }
}

#[test]
#[ignore = "problem 15.2: fails until you solve it"]
fn problem_15_2_rewrites_what_the_compacted_snapshot_replaced() {
    let all = snapshots();
    let find = |id: &str| all.iter().find(|s| s.id == id).unwrap();
    let mut planned: Vec<String> = plan_compaction(find("after-a-day"), 200, 100).concat();
    let kept: Vec<&str> = find("compacted")
        .data_files
        .iter()
        .map(|f| f.path.as_str())
        .collect();
    let mut dropped: Vec<String> = find("after-a-day")
        .data_files
        .iter()
        .filter(|f| !kept.contains(&f.path.as_str()))
        .map(|f| f.path.clone())
        .collect();
    planned.sort();
    dropped.sort();
    assert_eq!(planned, dropped);
}

// Scaffolding: the problems are answerable from what the snapshots record.

#[test]
fn every_snapshot_reads_and_the_readers_plan_matches_the_compacted_one() {
    let all = snapshots();
    assert!(all.len() > 4);
    let find = |id: &str| all.iter().find(|s| s.id == id).unwrap();
    let plan = changes::plan_compaction(find("after-a-day"), 200, 100);
    changes::compaction_cost(
        find("after-a-day"),
        find("compacted"),
        &plan,
        parquet_lab::object_store::NetworkModel::default(),
    )
    .unwrap();
    for s in made_up() {
        for key in [0, 42, 550] {
            let _ = changes::files_to_open(&s, key);
        }
    }
}
