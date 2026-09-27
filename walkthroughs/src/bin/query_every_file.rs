//! The book's reader runs one query on every file: what does it read after the footer?

use parquet_lab::object_store::NetworkModel;
use parquet_lab::prune::{Mechanisms, Op};
use parquet_lab::reader::{FooterOptions, SizeSource};
use parquet_lab::scan::{scan, Query, Strategy};

fn main() {
    let files = "baseline one-group small-groups by-country shuffled plain no-index";
    let query = Query {
        columns: vec![0, 1, 2, 3, 4, 5], // every column, where order_id = 431
        // Try 3, country, and "FR"; then 4, status, and "refunded".
        condition: Some((0, Op::Eq, "431".to_string())),
    };
    // The footer found exactly, every skipping mechanism, and only ranges that touch merged.
    let strategy = Strategy {
        footer: FooterOptions {
            size: SizeSource::Head,
            prefetch: 8,
        },
        connections: 1,
        coalesce_gap: Some(0),
        whole_chunks: false,
        mechanisms: Mechanisms::ALL,
    };
    let later = ["read the indexes", "read the pages"]; // the requests after the footer

    for name in files.split_whitespace() {
        let path = format!("fixtures/writing-{name}.parquet");
        let data = std::fs::read(path).expect("run this from the repository's root");
        let model = NetworkModel::default();
        let result = scan(&data, name, &query, strategy, model).expect("rows");
        let after: Vec<_> = (result.requests.iter())
            .filter(|r| later.iter().any(|w| r.why.starts_with(w)))
            .collect();
        let fetched: u64 = after.iter().map(|r| r.bytes_returned).sum();
        let (n, rows) = (after.len(), result.matches.len());
        println!("writing-{name}: {fetched} bytes in {n} requests, {rows} rows matching");
    }
}
