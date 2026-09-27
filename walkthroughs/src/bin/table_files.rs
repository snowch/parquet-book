//! What a snapshot says the table is: its data files and delete files, from its metadata.

use parquet_lab::changes::read_snapshots;

fn main() {
    let text = std::fs::read_to_string("fixtures/changes/_snapshots.json")
        .expect("run this from the repository's root");
    let snapshots = read_snapshots(&text).expect("snapshots");
    let snapshot = snapshots.iter().find(|s| s.id == "after-a-day").unwrap();

    for f in &snapshot.data_files {
        let (path, rows, size) = (&f.path, f.record_count, f.file_size);
        println!(
            "{path}: {rows} rows in {size} bytes, {} bytes a row",
            size as i64 / rows
        );
    }
    let (data, deletes) = (snapshot.data_files.len(), snapshot.delete_files.len());
    println!("{data} data files and {deletes} delete files");
}
