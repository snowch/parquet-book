//! Check a page's checksum, then flip one bit of its body and check again.

use parquet_lab::bytes::crc32;
use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::pages;

fn main() {
    let path = "fixtures/pages-v2.parquet";
    let mut data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let chunk = md.row_groups[0].columns[1].byte_range(); // country
    let (from, to) = (chunk.start as usize, chunk.end as usize);
    let walked = pages::walk_pages(&data[from..to], chunk.start).expect("pages");
    let page = walked.last().expect("a page"); // its last page
    let (start, end) = (page.body_span.start as usize, page.body_span.end as usize);
    // The header stores it as a signed 32-bit integer.
    let stored = page.crc.expect("a checksum") as i32 as u32;
    let (kind, at) = (&page.page_type, page.header_span.start);
    println!("{kind} at {at}: its header says {stored:08x}");

    let check = |label: &str, body: &[u8]| {
        let crc = crc32(body); // the book's reader's CRC-32
        println!("{label}: {crc:08x}, matches the header: {}", crc == stored);
    };
    check("the body as written", &data[start..end]);
    data[end - 2] ^= 1; // one bit of the values; try another byte, or another bit
    check("one bit flipped", &data[start..end]);
    let walked = pages::walk_pages(&data[from..to], chunk.start).expect("pages");
    let found: Vec<_> = walked.iter().map(|p| p.crc_ok).collect();
    println!("the reader's walk: {found:?}");
}
