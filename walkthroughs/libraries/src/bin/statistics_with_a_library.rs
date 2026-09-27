//! The same facts from the `parquet` crate: each column's sort order, and its statistics, which
//! it reads as the physical type says.

use parquet::file::metadata::ParquetMetaDataReader;
use parquet::file::statistics::Statistics;

fn main() {
    let path = "fixtures/statistics.parquet";
    let file = std::fs::File::open(path).expect("run this from the repository's root");
    let md = ParquetMetaDataReader::new()
        .parse_and_finish(&file)
        .expect("a Parquet file");
    let row_group = md.row_group(0); // try 1
    println!("sorted by {:?}", row_group.sorting_columns());
    for (i, chunk) in row_group.columns().iter().enumerate() {
        let order = md.file_metadata().column_order(i);
        print!("{}: {order}", chunk.column_path().string());
        match chunk.statistics() {
            Some(s) => {
                let (exact, deprecated) = (s.min_is_exact(), s.is_min_max_deprecated());
                println!(", exact {exact}, from the deprecated fields {deprecated}");
            }
            None => println!(", no statistics"),
        }
    }
    // The column order says unsigned; the crate hands you an i32 all the same.
    if let Some(Statistics::Int32(s)) = row_group.column(1).statistics() {
        println!("customer_id: {:?} to {:?}", s.min_opt(), s.max_opt());
    }
}
