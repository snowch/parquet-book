//! Walk a column chunk page by page: each header says how long its body is.

use parquet_lab::bytes::ByteReader;
use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::pages;

fn main() {
    let path = "fixtures/pages.parquet"; // try pages-v2.parquet
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let chunk = &md.row_groups[0].columns[1]; // country; try 2, which is amount_cents

    // The first page's header, and the end of every page, headers included.
    let start = match chunk.dictionary_page_offset {
        Some(offset) => offset as usize,
        None => chunk.data_page_offset as usize,
    };
    let end = start + chunk.total_compressed_size as usize;
    println!("{}: bytes {start} to {end}", chunk.dotted_path());
    let mut r = ByteReader::new(&data[start..end], start as u64);
    while !r.is_at_end() {
        // A Thrift header, then as many bytes of body as it says.
        let page = pages::read_page(&mut r).expect("a page");
        let (kind, at) = (&page.page_type, page.header_span.start);
        let header = page.header_span.end - at;
        let (body, values) = (page.compressed_page_size, page.num_values.unwrap_or(0));
        print!("{kind} at {at}: {header}-byte header, {body}-byte body, {values} values");
        if let Some(v2) = page.v2 {
            // A version 2 header also counts the page's rows and nulls.
            print!(", {} rows, {} nulls", v2.num_rows, v2.num_nulls);
        }
        println!();
    }
}
