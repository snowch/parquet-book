//! Grades ch12's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test a_tiny_query_engine -- --ignored
//! ```
//!
//! Each problem is graded against pyarrow's answer to the same question about the ch11 baseline
//! file, from `fixtures/queries.json`, and against many generated cases.

use std::path::PathBuf;

use exercises::a_tiny_query_engine::{sum_by_key, top_n};
use parquet_lab::json::Json;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

/// pyarrow's answer to the query that starts with `sql`.
fn answer(sql: &str) -> Vec<Vec<Json>> {
    let text = std::fs::read_to_string(root().join("fixtures/queries.json")).unwrap();
    let all = Json::parse(&text).unwrap();
    let q = all
        .as_array()
        .unwrap()
        .iter()
        .find(|q| {
            q.get("sql")
                .and_then(Json::as_str)
                .unwrap()
                .starts_with(sql)
        })
        .unwrap();
    q.get("rows")
        .and_then(Json::as_array)
        .unwrap()
        .iter()
        .map(|r| r.as_array().unwrap().clone())
        .collect()
}

/// The baseline file's columns, decoded by the book's reader.
fn column(name: &str) -> Vec<Json> {
    let bytes = std::fs::read(root().join("fixtures/writing-baseline.parquet")).unwrap();
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let tree = parquet_lab::schema::build(&md.schema).unwrap();
    let leaf = parquet_lab::schema::leaves(&tree)
        .into_iter()
        .find(|l| l.dotted_path() == name)
        .unwrap();
    md.row_groups
        .iter()
        .flat_map(|rg| {
            parquet_lab::column::read_column(&bytes, &rg.columns[leaf.column], &leaf)
                .unwrap()
                .triples
        })
        .map(|t| t.value.unwrap().to_json())
        .collect()
}

struct Lcg(u64);

impl Lcg {
    fn next(&mut self, below: u64) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        (self.0 >> 33) % below
    }
}

#[test]
#[ignore = "problem 12.1: fails until you solve it"]
fn problem_12_1_matches_pyarrows_group_by() {
    let statuses: Vec<String> = column("status")
        .iter()
        .map(|j| j.as_str().unwrap().to_string())
        .collect();
    let amounts: Vec<i64> = column("amount_cents")
        .iter()
        .map(|j| j.as_i64().unwrap())
        .collect();
    let keys: Vec<&str> = statuses.iter().map(String::as_str).collect();
    let expected: Vec<(String, i64)> = answer("SELECT status, sum(amount_cents)")
        .iter()
        .map(|r| (r[0].as_str().unwrap().to_string(), r[1].as_i64().unwrap()))
        .collect();
    assert_eq!(sum_by_key(&keys, &amounts), expected);
    let mut rng = Lcg(3);
    let names = ["a", "b", "ab", "Z", "é", ""];
    for case in 0..500 {
        let n = rng.next(40) as usize;
        let keys: Vec<&str> = (0..n).map(|_| names[rng.next(6) as usize]).collect();
        let values: Vec<i64> = (0..n).map(|_| rng.next(1000) as i64 - 500).collect();
        let mut expected = std::collections::BTreeMap::<Vec<u8>, i64>::new();
        for (k, v) in keys.iter().zip(&values) {
            *expected.entry(k.as_bytes().to_vec()).or_default() += v;
        }
        let expected: Vec<(String, i64)> = expected
            .into_iter()
            .map(|(k, v)| (String::from_utf8(k).unwrap(), v))
            .collect();
        assert_eq!(sum_by_key(&keys, &values), expected, "case {case}");
    }
}

#[test]
#[ignore = "problem 12.2: fails until you solve it"]
fn problem_12_2_matches_pyarrows_sort() {
    let ids: Vec<i64> = column("order_id")
        .iter()
        .map(|j| j.as_i64().unwrap())
        .collect();
    let amounts: Vec<i64> = column("amount_cents")
        .iter()
        .map(|j| j.as_i64().unwrap())
        .collect();
    let rows: Vec<(i64, i64)> = ids
        .into_iter()
        .zip(amounts)
        .filter(|&(_, a)| a > 9800)
        .collect();
    let expected: Vec<(i64, i64)> =
        answer("SELECT order_id, amount_cents FROM orders WHERE amount_cents > 9800")
            .iter()
            .map(|r| (r[0].as_i64().unwrap(), r[1].as_i64().unwrap()))
            .collect();
    assert_eq!(top_n(&rows, 5), expected);
    let mut rng = Lcg(5);
    for case in 0..500 {
        let rows: Vec<(i64, i64)> = (0..rng.next(60))
            .map(|i| (i as i64, rng.next(20) as i64))
            .collect();
        let n = rng.next(10) as usize;
        let mut sorted = rows.clone();
        sorted.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        sorted.truncate(n);
        assert_eq!(top_n(&rows, n), sorted, "case {case}");
    }
}
