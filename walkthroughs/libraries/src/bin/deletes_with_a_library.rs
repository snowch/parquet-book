//! The same deletes applied with the `parquet` crate, which reads Parquet files but not tables:
//! you apply them.

use parquet::file::reader::{FileReader, SerializedFileReader};
use parquet::record::{Row, RowAccessor};

fn rows(path: &std::path::Path) -> Vec<Row> {
    let file = std::fs::File::open(path).expect("run this from the repository's root");
    let reader = SerializedFileReader::new(file).expect("a Parquet file");
    let rows = reader.get_row_iter(None).expect("rows");
    rows.map(|r| r.expect("a row")).collect()
}

fn main() {
    let path = "data/part-1.parquet";
    let data = rows(format!("fixtures/changes/{path}").as_ref());
    let mut gone = Vec::new();
    let mut deletes: Vec<_> = std::fs::read_dir("fixtures/changes/deletes")
        .unwrap()
        .map(|e| e.unwrap().path())
        .collect();
    deletes.sort();
    for d in deletes {
        for named in rows(&d) {
            if named.get_string(0).unwrap() == path {
                gone.push(named.get_long(1).unwrap());
            }
        }
    }

    let live: Vec<&Row> = (0..data.len())
        .filter(|i| !gone.contains(&(*i as i64)))
        .map(|i| &data[i])
        .collect();
    println!(
        "{path} holds {} rows; {} are deleted; {} are live",
        data.len(),
        gone.len(),
        live.len()
    );
    let sum: i64 = live.iter().map(|r| r.get_long(5).unwrap()).sum();
    println!("their amounts sum to {sum}");
}
