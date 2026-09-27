//! The `parquet` crate without keys: a plaintext footer opens, an encrypted one does not.

use std::fs::File;

use parquet::file::reader::{FileReader, SerializedFileReader};
use parquet::file::statistics::Statistics;
use parquet::schema::types::Type;

/// A column's bounds, if the footer holds them where this reader can read them.
fn bounds(statistics: Option<&Statistics>) -> String {
    match statistics {
        Some(Statistics::Int64(s)) => {
            format!("{} to {}", s.min_opt().unwrap(), s.max_opt().unwrap())
        }
        Some(Statistics::ByteArray(s)) => {
            let (min, max) = (s.min_opt().unwrap(), s.max_opt().unwrap());
            format!(
                "{:?} to {:?}",
                min.as_utf8().unwrap(),
                max.as_utf8().unwrap()
            )
        }
        _ => "none".to_string(),
    }
}

fn main() {
    let path = "fixtures/plaintext-footer.parquet";
    let file = File::open(path).expect("run this from the repository's root");
    let reader = SerializedFileReader::new(file).expect("a plaintext footer");
    let metadata = reader.metadata();
    let rows = metadata.file_metadata().num_rows();
    println!("plaintext-footer.parquet: {rows} rows");
    for chunk in metadata.row_group(0).columns() {
        let name = chunk.column_path().string();
        println!("  {name}: statistics {}", bounds(chunk.statistics()));
    }
    // Without its encryption feature the crate does not know email's pages are encrypted.
    let fields = metadata.file_metadata().schema().get_fields();
    let column = &fields[2]; // email; try 3, amount_cents
    let projection = Type::group_type_builder("schema").with_fields(vec![column.clone()]);
    let mut rows = reader
        .get_row_iter(Some(projection.build().unwrap()))
        .expect("rows");
    match rows.next().expect("a row") {
        Ok(row) => println!("  {}'s first row: {row}", column.name()),
        Err(e) => println!("  {}'s first row: {e}", column.name()),
    }

    let file = File::open("fixtures/encrypted-footer.parquet").unwrap();
    match SerializedFileReader::new(file) {
        Ok(_) => println!("encrypted-footer.parquet: opened"),
        Err(e) => println!("encrypted-footer.parquet: {e}"),
    }
}
