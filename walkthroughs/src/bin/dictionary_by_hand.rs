//! A dictionary page and the indices into it, by hand.

use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::pages;

fn main() {
    let data =
        std::fs::read("fixtures/dictionary.parquet").expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let chunk = md.row_groups[0].columns[1].byte_range(); // country
    let (start, end) = (chunk.start as usize, chunk.end as usize);
    let found = pages::walk_pages(&data[start..end], chunk.start).expect("pages");
    let (dictionary, page) = (&found[0], &found[1]);
    let bytes_of = |p: &pages::Page| &data[p.body_span.start as usize..p.body_span.end as usize];

    let body = bytes_of(dictionary);
    let (mut entries, mut at) = (Vec::new(), 0);
    while at < body.len() {
        // PLAIN strings: a four-byte length, then the bytes.
        let n = u32::from_le_bytes(body[at..at + 4].try_into().unwrap()) as usize;
        entries.push(String::from_utf8_lossy(&body[at + 4..at + 4 + n]));
        at += 4 + n;
    }
    let encoding = dictionary.encoding.as_deref().unwrap_or("?");
    println!("{} {encoding} {entries:?}", dictionary.page_type);

    let body = bytes_of(page);
    // The indices' bit width, then a run's ULEB128 header.
    let (width, header) = (u32::from(body[0]), body[1]);
    let encoding = page.encoding.as_deref().unwrap_or("?");
    let (kind, size) = (&page.page_type, body.len());
    println!("{kind} {encoding}: {size} bytes, width {width}, header {header:02x}");
    // Bit-packed: header >> 1 groups of eight indices, lowest bits first.
    let bits = body[2..]
        .iter()
        .rev()
        .fold(0u64, |acc, b| acc << 8 | u64::from(*b));
    let slots = page.num_values.expect("a data page"); // try 8 * (header >> 1) as i64
    let indices: Vec<u64> = (0..slots as u32)
        .map(|i| bits >> (i * width) & ((1 << width) - 1))
        .collect();
    println!("indices: {indices:?}");
    let values: Vec<_> = indices.iter().map(|&i| &entries[i as usize]).collect();
    println!("values: {values:?}");
}
