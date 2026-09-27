//! The same damage as before, handed to the book's reader: it checks the length before trusting it.

use parquet_lab::object_store::{MemoryStore, NetworkModel, TracingStore};
use parquet_lab::reader::{read_footer, FooterOptions};

fn main() {
    let mut data =
        std::fs::read("fixtures/tiny.parquet").expect("run this from the repository's root");
    let n = data.len();
    data[n - 7] = 0xFF; // the second byte of the footer length
    let mut files = MemoryStore::new();
    files.put("tiny.parquet", data);
    let mut store = TracingStore::new(files, NetworkModel::default());

    if let Err(refused) = read_footer(&mut store, "tiny.parquet", FooterOptions::default()) {
        println!("the reader refuses: {refused}");
    }
    let why: Vec<&str> = store.requests.iter().map(|r| r.why.as_str()).collect();
    println!(
        "after {} requests: {}",
        store.requests.len(),
        why.join(", ")
    );
}
