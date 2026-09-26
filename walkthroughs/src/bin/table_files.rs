//! What a snapshot says the table is: its data files and delete files, from the table's metadata.

use parquet_lab::json::Json;

fn main() {
    let text = std::fs::read_to_string("fixtures/changes/_snapshots.json")
        .expect("run this from the repository's root");
    let all = Json::parse(&text).expect("JSON");
    let snapshot = all
        .get("snapshots")
        .and_then(Json::as_array)
        .and_then(|s| {
            s.iter()
                .find(|s| s.get("id").and_then(Json::as_str) == Some("after-a-day"))
        })
        .expect("a snapshot called after-a-day");
    let list = |k: &str| snapshot.get(k).and_then(Json::as_array).unwrap();

    for f in list("data_files") {
        let path = f.get("path").and_then(Json::as_str).unwrap();
        let rows = f.get("record_count").and_then(Json::as_i64).unwrap();
        let size = f.get("file_size").and_then(Json::as_i64).unwrap();
        let per_row = size / rows;
        println!("{path}: {rows} rows in {size} bytes, {per_row} bytes a row");
    }
    println!(
        "{} data files and {} delete files",
        list("data_files").len(),
        list("delete_files").len()
    );
}
