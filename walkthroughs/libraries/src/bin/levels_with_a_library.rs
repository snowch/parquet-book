//! The same column from the `parquet` crate, whose column reader hands you the levels as stored.

use parquet::column::reader::get_typed_column_reader;
use parquet::data_type::ByteArrayType;
use parquet::file::reader::{FileReader, SerializedFileReader};

fn main() {
    let file = std::fs::File::open("fixtures/nested.parquet")
        .expect("run this from the repository's root");
    let reader = SerializedFileReader::new(file).expect("a Parquet file");
    let row_group = reader.get_row_group(0).expect("a row group");
    let column = row_group.get_column_reader(2).expect("a column"); // tags[]
    let mut tags = get_typed_column_reader::<ByteArrayType>(column);
    let (mut defs, mut reps, mut values) = (Vec::new(), Vec::new(), Vec::new());
    let (records, _, _) = tags
        .read_records(usize::MAX, Some(&mut defs), Some(&mut reps), &mut values)
        .expect("the column's pages");
    println!("{records} records");
    println!("rep: {reps:?}");
    println!("def: {defs:?}");
    let values: Vec<&str> = values.iter().map(|v| v.as_utf8().unwrap()).collect();
    println!("values: {values:?}");
}
