//! The same questions to the `parquet` crate: row groups kept by a predicate you write on
//! their statistics, a page index, and Bloom filters, each read only when you ask for it.

use std::fs::File;

use parquet::file::metadata::RowGroupMetaData;
use parquet::file::page_index::column_index::ColumnIndexMetaData;
use parquet::file::properties::ReaderProperties;
use parquet::file::reader::{FileReader, SerializedFileReader};
use parquet::file::serialized_reader::ReadOptionsBuilder;
use parquet::file::statistics::Statistics;

/// Whether a row group's statistics for order_id leave room for 431.
fn may_hold_431(row_group: &RowGroupMetaData, _: usize) -> bool {
    match row_group.column(0).statistics() {
        Some(Statistics::Int64(s)) => match (s.min_opt(), s.max_opt()) {
            (Some(&min), Some(&max)) => (min..=max).contains(&431),
            _ => true,
        },
        _ => true, // no statistics to rule it out
    }
}

fn open(path: &str) -> File {
    File::open(path).expect("run this from the repository's root")
}

fn main() {
    let options = ReadOptionsBuilder::new()
        .with_predicate(Box::new(may_hold_431))
        .with_page_index()
        .build();
    let file = open("fixtures/pruning-sorted.parquet");
    let reader = SerializedFileReader::new_with_options(file, options).expect("a file");
    let md = reader.metadata();
    for row_group in md.row_groups() {
        println!("order_id = 431: kept row group {:?}", row_group.ordinal());
    }
    // The page index of the first row group kept: order_id's ColumnIndex.
    let page_index = md.page_index_for_row_group(0);
    let index = page_index.column_index(0).expect("a ColumnIndex");
    let order = index.get_boundary_order().expect("an order");
    if let ColumnIndexMetaData::INT64(pages) = index {
        let (min, max) = (pages.min_values(), pages.max_values());
        println!("  pages in {order:?} order: {min:?} to {max:?}");
    }

    let props = ReaderProperties::builder()
        .set_read_bloom_filter(true)
        .build();
    let options = ReadOptionsBuilder::new()
        .with_reader_properties(props)
        .build();
    let file = open("fixtures/pruning-shuffled.parquet");
    let reader = SerializedFileReader::new_with_options(file, options).expect("a file");
    for i in 0..reader.num_row_groups() {
        let row_group = reader.get_row_group(i).expect("a row group");
        let filter = row_group.get_column_bloom_filter(1); // customer_id's
        let may = filter.map(|f| f.check(&424242i64));
        println!("customer_id = 424242: row group {i}, may contain it: {may:?}");
    }
}
