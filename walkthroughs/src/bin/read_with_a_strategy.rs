//! The book's reader runs SELECT * WHERE order_id = 431, and the store logs each request.

use parquet_lab::object_store::NetworkModel;
use parquet_lab::prune::{Mechanisms, Op};
use parquet_lab::reader::{FooterOptions, SizeSource};
use parquet_lab::scan::{scan, Query, Strategy};

fn main() {
    let data = std::fs::read("fixtures/pruning-sorted.parquet")
        .expect("run this from the repository's root");
    let query = Query {
        columns: vec![0, 1, 2, 3], // every column, where order_id = 431
        condition: Some((0, Op::Eq, "431".to_string())),
    };

    // Try SizeSource::SuffixRange and prefetch 8192; then Some(4096); then 4 connections.
    let strategy = Strategy {
        footer: FooterOptions {
            size: SizeSource::Head,
            prefetch: 8,
        },
        connections: 1,
        coalesce_gap: None,
        whole_chunks: false,
        mechanisms: Mechanisms::ALL,
    };
    let model = NetworkModel::default();
    let result = scan(&data, "orders.parquet", &query, strategy, model).expect("rows");

    for r in &result.requests {
        let when = format!("{:>3}-{:>3} ms", r.start_us / 1000, r.end_us / 1000);
        let (method, range) = (r.method.name(), r.range.as_deref().unwrap_or(""));
        println!("{when} on {}: {method} {range} {}", r.connection + 1, r.why);
    }
    let (fetched, ms) = (result.bytes_fetched, result.elapsed_us / 1000);
    println!(
        "{} requests, {fetched} bytes, {ms} ms",
        result.requests.len()
    );
    println!("rows matching: {:?}", result.matches);
}
