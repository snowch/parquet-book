//! The book's reader opens the file as you did, and the store it reads from logs every request.

use parquet_lab::object_store::{MemoryStore, NetworkModel, TracingStore};
use parquet_lab::reader::{read_footer, FooterOptions, SizeSource};

fn main() {
    let mut files = MemoryStore::new();
    let data = std::fs::read("fixtures/tiny.parquet").expect("run this from the repository's root");
    files.put("tiny.parquet", data);
    let mut store = TracingStore::new(files, NetworkModel::default());

    // Try SizeSource::SuffixRange for Head, then raise prefetch until the footer comes in the first read.
    let options = FooterOptions {
        size: SizeSource::Head,
        prefetch: 8,
    };
    let opened = read_footer(&mut store, "tiny.parquet", options).expect("a Parquet file");

    for r in &store.requests {
        let range = r.range.as_deref().unwrap_or("·");
        let (method, bytes, ms) = (r.method.name(), r.bytes_returned, r.end_us / 1000);
        println!("{method} {range} -> {bytes} bytes by {ms} ms: {}", r.why);
    }
    println!(
        "footer length: {} rows: {}",
        opened.trailer.footer_length, opened.metadata.num_rows
    );
}
