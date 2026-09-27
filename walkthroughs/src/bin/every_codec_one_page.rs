//! Decompress one page under three codecs, and compare it with the uncompressed file's.

use parquet_lab::compress;
use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::pages::{self, Page};

fn first_page(name: &str, column: usize) -> (String, Page, Vec<u8>) {
    let path = format!("fixtures/codec-{name}.parquet");
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let chunk = &md.row_groups[0].columns[column];
    let span = chunk.byte_range();
    let (from, to) = (span.start as usize, span.end as usize);
    let page = pages::walk_pages(&data[from..to], span.start)
        .expect("pages")
        .remove(0);
    let body = data[page.body_span.start as usize..page.body_span.end as usize].to_vec();
    (chunk.codec.clone(), page, body)
}

fn main() {
    let column = 1; // country; try 5, which is distance_km
    let (_, _, plain) = first_page("none", column);
    // Try adding "zstd".
    for name in ["snappy", "lz4", "gzip"] {
        let (codec, page, body) = first_page(name, column);
        let size = page.uncompressed_page_size as usize;
        let out = compress::decompress(&codec, &body, page.body_span.start, size).expect("a page");
        let (tokens, same) = (out.tokens.len(), out.bytes == plain);
        let compressed = body.len();
        println!("{codec}: {compressed} bytes become {size} in {tokens} tokens, the same: {same}");
    }
}
