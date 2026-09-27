//! Answer SELECT country, count(*) WHERE order_id < 300 GROUP BY country, by hand.

use std::collections::BTreeMap;

use parquet_lab::column::read_column;
use parquet_lab::plain::PlainValue::{Bytes, Int};
use parquet_lab::report::open_bytes;
use parquet_lab::schema::{build, leaves, Leaf};

fn main() {
    let path = "fixtures/writing-baseline.parquet";
    let data = std::fs::read(path).expect("run this from the repository's root");
    let md = open_bytes(&data).expect("a footer"); // found and decoded as in ch02
    let columns = leaves(&build(&md.schema).expect("a schema"));
    let (order_id, country) = (&columns[0], &columns[3]);
    let limit = 300; // WHERE order_id < 300; try 450, then 1
    let mut counts = BTreeMap::new();

    for (g, row_group) in md.row_groups.iter().enumerate() {
        let chunk = &row_group.columns[order_id.column]; // an INT64, least byte first
        let s = chunk.statistics.as_ref().expect("statistics");
        let low: [u8; 8] = s.min_value.as_deref().unwrap().try_into().unwrap();
        let low = i64::from_le_bytes(low);
        if low >= limit {
            // No row here can pass: read none of its pages.
            println!("row group {g} skipped: min order_id {low}");
            continue;
        }
        let read = |leaf: &Leaf| {
            let chunk = &row_group.columns[leaf.column];
            read_column(&data, chunk, leaf).expect("a column").triples
        };
        let (ids, names) = (read(order_id), read(country));
        let mut kept = 0;
        for (id, name) in ids.iter().zip(&names) {
            if let (Some(Int(id)), Some(Bytes(name))) = (&id.value, &name.value) {
                if *id < limit {
                    // The filter passes the row; the aggregate counts it for its country.
                    kept += 1;
                    let name = String::from_utf8_lossy(name).into_owned();
                    *counts.entry(name).or_insert(0) += 1;
                }
            }
        }
        println!("row group {g} read: {} rows, {kept} pass", ids.len());
    }
    for (name, n) in &counts {
        println!("{name} {n}");
    }
}
