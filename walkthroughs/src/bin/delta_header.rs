//! DELTA_BINARY_PACKED by hand: a header of varints, then a block of bit-packed deltas.

use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::pages;

/// Seven bits a byte, lowest first, until a byte without its top bit.
fn uleb128(body: &[u8], at: &mut usize) -> u64 {
    let (mut n, mut shift) = (0, 0);
    loop {
        let b = body[*at];
        *at += 1;
        n |= u64::from(b & 0x7F) << shift;
        shift += 7;
        if b & 0x80 == 0 {
            return n;
        }
    }
}

/// 0, 1, 2, 3, 4 stand for 0, -1, 1, -2, 2: small either side of zero.
fn zigzag(body: &[u8], at: &mut usize) -> i64 {
    let n = uleb128(body, at);
    (n >> 1) as i64 ^ -((n & 1) as i64)
}

fn main() {
    let data =
        std::fs::read("fixtures/encodings.parquet").expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let column = 1; // ordered_at; try 0, which is order_id
    let chunk = md.row_groups[0].columns[column].byte_range();
    let (start, end) = (chunk.start as usize, chunk.end as usize);
    let page = &pages::walk_pages(&data[start..end], chunk.start).expect("pages")[0];
    // The column is required, so the body holds values and no levels.
    let body = &data[page.body_span.start as usize..page.body_span.end as usize];

    let mut at = 0;
    let block = uleb128(body, &mut at);
    let miniblocks = uleb128(body, &mut at) as usize;
    let count = uleb128(body, &mut at);
    let first = zigzag(body, &mut at);
    println!("{} bytes; header {:02x?}", body.len(), &body[..at]);
    println!("blocks of {block}, {miniblocks} miniblocks, {count} values, first {first}");
    let smallest = zigzag(body, &mut at);
    let widths = &body[at..at + miniblocks];
    println!("min delta {smallest}; widths {widths:?}");
    at += miniblocks; // the first miniblock: each delta less the smallest, in widths[0] bits
    let width = u32::from(widths[0]);
    let bits = body[at..at + width as usize]
        .iter()
        .rev()
        .fold(0u64, |acc, b| acc << 8 | u64::from(*b));
    let deltas: Vec<i64> = (0..8)
        .map(|i| smallest + (bits >> (i * width) & ((1 << width) - 1)) as i64)
        .collect();
    println!("first deltas: {deltas:?}");
}
