//! The `parquet` crate reads Parquet files, not tables: the deletes are yours to apply.

use parquet::file::reader::{FileReader, SerializedFileReader};
use parquet::record::{Row, RowAccessor};

fn rows(path: impl AsRef<std::path::Path>) -> Vec<Row> {
    let file = std::fs::File::open(path).expect("run this from the repository's root");
    let reader = SerializedFileReader::new(file).expect("a Parquet file");
    let rows = reader.get_row_iter(None).expect("rows");
    rows.map(|r| r.expect("a row")).collect()
}

fn main() {
    let path = "data/part-1.parquet";
    let data = rows(format!("fixtures/changes/{path}"));
    let mut gone = Vec::new();
    for d in std::fs::read_dir("fixtures/changes/deletes").unwrap() {
        for named in rows(d.unwrap().path()) {
            if named.get_string(0).unwrap() == path {
                gone.push(named.get_long(1).unwrap() as usize);
            }
        }
    }

    let live: Vec<&Row> = (data.iter().enumerate())
        .filter_map(|(i, r)| (!gone.contains(&i)).then_some(r))
        .collect();
    let (n, deleted) = (data.len(), gone.len());
    println!(
        "{path} holds {n} rows; {deleted} are deleted; {} are live",
        live.len()
    );
    let sum: i64 = live.iter().map(|r| r.get_long(5).unwrap()).sum();
    println!("their amounts sum to {sum}");
}
