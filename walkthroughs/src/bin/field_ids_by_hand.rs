//! Iceberg names a column by its field id, a number each data file's footer records.

use parquet_lab::engine::run;
use parquet_lab::metadata::decode_file_metadata;
use std::collections::BTreeMap;

fn main() {
    let data = std::fs::read("fixtures/changes/data/part-0.parquet")
        .expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length; // where the footer starts, as in ch02
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let by_id: BTreeMap<i64, &str> = (md.schema.iter())
        .filter_map(|e| Some((e.field_id?, e.name.as_str())))
        .collect();
    for (id, name) in &by_id {
        println!("field id {id}: {name}");
    }

    // The table's schema now, by id: order_id has been renamed, and channel added since.
    let table = [
        (1, "order_number"),
        (4, "country"),
        (6, "amount_cents"),
        (7, "channel"),
    ];
    let names: Vec<&str> = (table.iter()) // this file's names for them
        .filter_map(|(id, _)| by_id.get(id).copied())
        .collect();
    let answer = run(&data, &format!("SELECT {} FROM orders", names.join(", "))).unwrap();
    let first: BTreeMap<&str, String> = (answer.columns.iter().map(|c| c.as_str()))
        .zip(answer.rows[0].iter().map(|v| v.to_json().to_json()))
        .collect();
    for (id, name) in table {
        // No column: the file predates the column.
        let column = by_id.get(&id).copied().unwrap_or("no column");
        let value = first.get(column).map_or("null", |v| v.as_str());
        println!("{name} (id {id}) <- {column}: {value}");
    }
    let missing: Vec<&str> = (table.iter().map(|(_, name)| *name))
        .filter(|name| !first.contains_key(name))
        .collect();
    println!("by name, the file has no {}", missing.join(", "));
}
