//! The `parquet` crate keeps each field's id in its basic information.

use parquet::file::reader::{FileReader, SerializedFileReader};

fn main() {
    let file = std::fs::File::open("fixtures/changes/data/part-0.parquet")
        .expect("run this from the repository's root");
    let reader = SerializedFileReader::new(file).expect("a Parquet file");
    let fields = reader.metadata().file_metadata().schema().get_fields();
    for field in fields {
        let info = field.get_basic_info();
        println!("field id {}: {}", info.id(), info.name());
    }

    // The crate reads columns by position, so the id the table knows is turned into one.
    let wanted = 1;
    let ids: Vec<i32> = fields.iter().map(|f| f.get_basic_info().id()).collect();
    let at = ids.iter().position(|&id| id == wanted);
    let at = at.expect("no column with that id in this file");
    let mut rows = reader.get_row_iter(None).expect("rows");
    let first = rows.next().expect("a row").expect("a row");
    let (name, value) = first.get_column_iter().nth(at).unwrap();
    println!("id {wanted} <- {name}: {value}");
}
