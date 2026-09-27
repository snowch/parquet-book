//! The book's reader plans a compaction: which files it would rewrite together.

use parquet_lab::changes::{plan_compaction, read_snapshots};

fn main() {
    let text = std::fs::read_to_string("fixtures/changes/_snapshots.json")
        .expect("run this from the repository's root");
    let snapshots = read_snapshots(&text).expect("snapshots");
    let snapshot = snapshots.iter().find(|s| s.id == "after-a-day").unwrap();

    // Try a target of 100 rows; then small files under 10 rows; then "merge-on-read-8".
    let (target_rows, small_rows) = (200, 100);
    let plan = plan_compaction(snapshot, target_rows, small_rows);

    for (n, group) in plan.iter().enumerate() {
        let (rows_in, rows_out, bytes) = (group.rows_in, group.rows_out, group.bytes_in);
        println!(
            "group {}: {rows_in} rows in, {rows_out} out, {bytes} bytes to read",
            n + 1
        );
        for path in group.data_files.iter().chain(&group.delete_files) {
            println!("  {path}");
        }
    }
    let read: u64 = plan.iter().map(|g| g.bytes_in).sum();
    println!("{} files to write, from {read} bytes read", plan.len());
}
