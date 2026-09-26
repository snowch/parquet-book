//! Grades ch14's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test lakehouse_and_beyond -- --ignored
//! ```

use std::path::PathBuf;

use exercises::lakehouse_and_beyond::{files_to_read, partition_values};
use parquet_lab::json::Json;
use parquet_lab::object_store::{MemoryStore, NetworkModel};
use parquet_lab::table::{self, Discovery, LOG};

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures")
}

/// The table's objects, by key, from the listing pyarrow's generator wrote.
fn objects() -> Vec<(String, Vec<u8>)> {
    let text = std::fs::read_to_string(fixtures().join("table.json")).unwrap();
    let listing = Json::parse(&text).unwrap();
    listing
        .get("objects")
        .and_then(Json::as_array)
        .unwrap()
        .iter()
        .map(|o| {
            let key = o.get("key").and_then(Json::as_str).unwrap().to_string();
            let bytes = std::fs::read(fixtures().join(&key)).unwrap();
            (key, bytes)
        })
        .collect()
}

#[test]
#[ignore = "problem 14.1: fails until you solve it"]
fn problem_14_1_reads_the_paths_the_reader_reads() {
    let mut paths: Vec<String> = objects()
        .into_iter()
        .map(|(k, _)| k["table/".len()..].to_string())
        .collect();
    paths.extend(
        [
            "part-0.parquet",
            "year=2026/month=01/day=31/part-0.parquet",
            "country=UK/not-a-partition/part-0.parquet",
            "country=UK/status=a=b/part-0.parquet",
            "country=/part-0.parquet",
            "country=UK/x=y.parquet",
            "city=S%C3%A3o%20Paulo/part-0.parquet",
            "path=a%2Fb%3Dc/part-0.parquet",
            "odd%3Dname=1/part-0.parquet",
            "pct=100%25/part-0.parquet",
            "broken=%zz%4/part-0.parquet",
            "country=__HIVE_DEFAULT_PARTITION__/part-0.parquet",
        ]
        .map(str::to_string),
    );
    for p in paths {
        assert_eq!(partition_values(&p), table::partition_values(&p), "{p}");
    }
}

#[test]
#[ignore = "problem 14.2: fails until you solve it"]
fn problem_14_2_keeps_exactly_the_files_the_reader_keeps() {
    let objects = objects();
    let log = objects
        .iter()
        .find(|(k, _)| k.ends_with(LOG))
        .map(|(_, b)| String::from_utf8(b.clone()).unwrap())
        .unwrap();
    let mut checked = 0;
    for (lo, hi) in [
        (1, 801),
        (431, 436),
        (0, 1),
        (1, 2),
        (272, 274),
        (271, 272),
        (533, 536),
        (790, 801),
        (799, 900),
        (800, 801),
        (-5, 0),
        (500, 400),
    ] {
        let sql = format!("SELECT count(*) FROM orders WHERE order_id >= {lo} AND order_id < {hi}");
        let mut store = MemoryStore::new();
        for (k, v) in &objects {
            store.put(k, v.clone());
        }
        let a = table::query(
            store,
            "table/",
            &sql,
            Discovery::Log,
            4,
            NetworkModel::default(),
        )
        .unwrap();
        let expected: Vec<String> = a
            .files
            .iter()
            .filter(|f| f.read)
            .map(|f| f.key.clone())
            .collect();
        let mine = files_to_read(&log, lo, hi);
        assert_eq!(mine, expected, "{sql}");
        // Never lose a row: every file with a matching row is kept.
        for f in &a.files {
            let bytes = &objects
                .iter()
                .find(|(k, _)| k == &format!("table/{}", f.key))
                .unwrap()
                .1;
            let n = parquet_lab::engine::run(bytes, &sql).unwrap().rows[0][0].to_json();
            if n != Json::Int(0) {
                assert!(mine.contains(&f.key), "{sql}: {} holds {n:?} rows", f.key);
            }
        }
        checked += 1;
    }
    assert_eq!(checked, 12);
}

#[test]
#[ignore = "problem 14.2: fails until you solve it"]
fn problem_14_2_follows_removes_and_keeps_files_without_statistics() {
    let add = |path: &str, stats: Option<(i64, i64)>| {
        let stats = stats.map_or(String::new(), |(lo, hi)| {
            let s = format!(
                r#"{{"numRecords": 10, "minValues": {{"order_id": {lo}}}, "maxValues": {{"order_id": {hi}}}}}"#
            );
            format!(r#", "stats": {}"#, Json::Str(s).to_json())
        });
        format!(r#"{{"add": {{"path": "{path}", "partitionValues": {{}}, "size": 1{stats}}}}}"#)
    };
    let log = [
        r#"{"protocol": {"minReaderVersion": 1, "minWriterVersion": 2}}"#.to_string(),
        add("a.parquet", Some((1, 100))),
        add("b.parquet", Some((101, 200))),
        add("c.parquet", None),
        add("d.parquet", Some((150, 250))),
        r#"{"remove": {"path": "b.parquet", "dataChange": true}}"#.to_string(),
        add("e.parquet", Some((101, 120))),
    ]
    .join("\n");
    assert_eq!(files_to_read(&log, 50, 60), ["a.parquet", "c.parquet"]);
    assert_eq!(
        files_to_read(&log, 100, 160),
        ["a.parquet", "c.parquet", "d.parquet", "e.parquet"]
    );
    assert_eq!(files_to_read(&log, 121, 150), ["c.parquet"]);
    assert_eq!(files_to_read(&log, 250, 251), ["c.parquet", "d.parquet"]);
}
