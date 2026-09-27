//! The same query to the `parquet` crate: row groups kept by a predicate you write on their
//! statistics, then rows of the two columns the query needs, filtered and counted.

use std::collections::BTreeMap;
use std::fs::File;

use parquet::file::metadata::RowGroupMetaData;
use parquet::file::reader::{FileReader, SerializedFileReader};
use parquet::file::serialized_reader::ReadOptionsBuilder;
use parquet::file::statistics::Statistics;
use parquet::record::RowAccessor;
use parquet::schema::types::Type;

const LIMIT: i64 = 300; // WHERE order_id < 300; try 450, then 1

/// Whether a row group's statistics for order_id leave room for an order below the limit.
fn may_pass(row_group: &RowGroupMetaData, _: usize) -> bool {
    match row_group.column(0).statistics() {
        Some(Statistics::Int64(s)) => s.min_opt().is_none_or(|&min| min < LIMIT),
        _ => true, // no statistics to rule it out
    }
}

fn main() {
    let path = "fixtures/writing-baseline.parquet";
    let file = File::open(path).expect("run this from the repository's root");
    let options = ReadOptionsBuilder::new()
        .with_predicate(Box::new(may_pass))
        .build();
    let reader = SerializedFileReader::new_with_options(file, options).expect("a file");
    let md = reader.metadata();
    let kept: Vec<_> = md.row_groups().iter().map(|rg| rg.ordinal()).collect();
    println!("row groups kept: {kept:?}");

    // A schema of order_id and country alone: the rows hold only those two columns.
    let fields = md.file_metadata().schema().get_fields();
    let projection = Type::group_type_builder("schema")
        .with_fields(vec![fields[0].clone(), fields[3].clone()])
        .build()
        .expect("a schema");
    let mut counts = BTreeMap::new();
    for row in reader.get_row_iter(Some(projection)).expect("rows") {
        let row = row.expect("a row");
        if row.get_long(0).expect("an order_id") < LIMIT {
            let country = row.get_string(1).expect("a country").clone();
            *counts.entry(country).or_insert(0) += 1;
        }
    }
    for (country, n) in &counts {
        println!("{country} {n}");
    }
}
