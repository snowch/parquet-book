//! Which files a lookup of one order must open: the data files whose order_id range
//! holds it, and the delete files that name those.

use parquet_lab::changes::read_snapshots;

fn main() {
    let text = std::fs::read_to_string("fixtures/changes/_snapshots.json")
        .expect("run this from the repository's root");
    let snapshots = read_snapshots(&text).expect("snapshots");
    let snapshot = snapshots.iter().find(|s| s.id == "after-a-day").unwrap();
    let key = 300;

    let data: Vec<&str> = (snapshot.data_files.iter())
        .filter(|f| f.min_key <= key && key <= f.max_key)
        .map(|f| f.path.as_str())
        .collect();
    for path in &data {
        println!("order {key} can only be in {path}");
    }
    let deletes: Vec<&str> = (snapshot.delete_files.iter())
        .filter(|d| data.contains(&d.data_file.as_str()))
        .map(|d| d.path.as_str())
        .collect();
    println!(
        "and these delete files may remove it: {}",
        deletes.join(", ")
    );
}
