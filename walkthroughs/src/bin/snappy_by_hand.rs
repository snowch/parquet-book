//! Undo Snappy by hand: a length, then tags that say "literal" or "copy".

use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::pages;

fn le(bytes: &[u8]) -> usize {
    bytes.iter().rev().fold(0, |acc, &b| acc << 8 | b as usize)
}

fn main() {
    let path = "fixtures/codec-snappy.parquet";
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let chunk = md.row_groups[0].columns[1].byte_range(); // country; try 5, distance_km
    let (from, to) = (chunk.start as usize, chunk.end as usize);
    let page = &pages::walk_pages(&data[from..to], chunk.start).expect("pages")[0];
    let body = &data[page.body_span.start as usize..page.body_span.end as usize];

    // A varint: seven bits a byte, lowest first; a top bit means more.
    let (mut size, mut shift, mut i) = (0, 0, 0);
    while body[i] & 0x80 != 0 {
        (size, shift, i) = (size | (body[i] as usize & 0x7f) << shift, shift + 7, i + 1);
    }
    (size, i) = (size | (body[i] as usize) << shift, i + 1);
    println!("{} bytes; the varint says {size} will come out", body.len());
    let (mut out, mut tokens) = (Vec::new(), Vec::new());
    while i < body.len() {
        let (tag, kind) = (body[i] as usize, body[i] & 3); // the low two bits say what it is
        if kind == 0 {
            // A literal: its length - 1 in the top six bits, or in 1..4 more bytes.
            let (mut n, mut at) = ((tag >> 2) + 1, i + 1);
            if n > 60 {
                (n, at) = (le(&body[at..at + n - 60]) + 1, at + n - 60);
            }
            out.extend_from_slice(&body[at..at + n]);
            i = at + n;
            tokens.push(format!("literal {n} bytes"));
            continue;
        }
        let (n, back) = if kind == 1 {
            // A copy of 4..11 bytes, up to 2047 back.
            i += 2;
            (4 + (tag >> 2 & 7), (tag >> 5) << 8 | body[i - 1] as usize)
        } else {
            // A copy of 1..64 bytes, its distance in 2 or 4 more bytes.
            let width = if kind == 2 { 2 } else { 4 };
            i += 1 + width;
            ((tag >> 2) + 1, le(&body[i - width..i]))
        };
        for _ in 0..n {
            // Byte by byte: a copy may overlap the bytes it writes.
            out.push(out[out.len() - back]);
        }
        tokens.push(format!("copy {n} from {back} back"));
    }
    for token in tokens.iter().take(6) {
        println!("{token}"); // try tokens.iter().rev()
    }
    let (count, header) = (tokens.len(), page.uncompressed_page_size);
    println!(
        "{count} tokens wrote {} bytes; the page header says {header}",
        out.len()
    );
}
