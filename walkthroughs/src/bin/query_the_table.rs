//! The book's reader queries the table: what it decided about each file, and every request.

use parquet_lab::object_store::{MemoryStore, NetworkModel};
use parquet_lab::table::{query, Discovery};

/// Every file under `dir`, with its path.
fn files(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
    for entry in std::fs::read_dir(dir).expect("run this from the repository's root") {
        let path = entry.expect("an entry").path();
        if path.is_dir() {
            files(&path, out)
        } else {
            out.push(path)
        }
    }
}

fn main() {
    let mut paths = Vec::new();
    files("fixtures/table".as_ref(), &mut paths);
    let mut store = MemoryStore::new(); // every file of the table, under its key
    for path in paths {
        let key = path.to_string_lossy().replacen("fixtures/", "", 1); // table/...
        store.put(&key, std::fs::read(&path).expect("a file"));
    }

    let sql = "SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200";
    // Try Discovery::ListAndPrune, then Discovery::List; then 1 or 8 connections.
    let model = NetworkModel::default();
    let result = query(store, "table/", sql, Discovery::Log, 4, model).expect("an answer");

    for f in &result.files {
        println!("{}: {}", f.key, f.why);
    }
    for r in &result.requests {
        let when = format!("{:>3}-{:>3} ms", r.start_us / 1000, r.end_us / 1000);
        let (on, method, key) = (r.connection + 1, r.method.name(), &r.key);
        println!("{when} on {on}: {method} {key}, {} bytes", r.bytes_returned);
    }
    println!("{}", result.answer.columns.join(" "));
    for row in &result.answer.rows {
        let cells: Vec<String> = row.iter().map(|v| v.to_json().to_json()).collect();
        println!("{}", cells.join(" "));
    }
}
