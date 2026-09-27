//! The book's reader finds one order in a snapshot, and the store logs each request.

use parquet_lab::changes::lookup;
use parquet_lab::object_store::{MemoryStore, NetworkModel};
use std::path::Path;

/// Every file under `dir`, under its path from `root`.
fn put_files(store: &mut MemoryStore, root: &Path, dir: &Path) {
    for entry in std::fs::read_dir(dir).expect("run this from the repository's root") {
        let path = entry.expect("an entry").path();
        if path.is_dir() {
            put_files(store, root, &path);
        } else {
            let key = path.strip_prefix(root).unwrap().to_string_lossy();
            store.put(&key, std::fs::read(&path).expect("a file"));
        }
    }
}

fn main() {
    let mut store = MemoryStore::new(); // every file of the table, under its key
    let root = Path::new("fixtures/changes");
    put_files(&mut store, root, root);

    // Try order 250; then the snapshot "written"; then prefetch 65536.
    let (snapshot, key, prefetch) = ("after-a-day", 300, 0);
    let model = NetworkModel::default();
    let result = lookup(store, "", snapshot, key, prefetch, 4, model).expect("a lookup");

    let mut trips = 0;
    for (i, r) in result.requests.iter().enumerate() {
        if i == 0 || r.phase != result.requests[i - 1].phase {
            trips += 1;
            println!("round trip {trips}:");
        }
        let (ms, method, object) = (r.end_us / 1000, r.method.name(), &r.key);
        let range = r.range.as_deref().unwrap_or("·");
        println!("  {ms:>3} ms: {method} {object} {range} {}", r.why);
    }
    match (&result.found, &result.deleted_by) {
        (None, _) => println!("no file holds order {key}"),
        (Some((path, pos)), Some(by)) => {
            println!("order {key} is row {pos} of {path}, but {by} deletes it")
        }
        (Some((path, pos)), None) => println!("order {key} is row {pos} of {path}"),
    }
    for (column, value) in &result.row {
        println!("  {column}: {}", value.to_json());
    }
    let n = result.requests.len();
    let (fetched, ms) = (result.bytes_fetched, result.elapsed_us / 1000);
    println!("{n} requests, {fetched} bytes, {ms} ms");
}
