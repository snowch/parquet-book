//! One encrypted module, read from its length prefix: the first of email's column chunk.

use parquet_lab::report::open_bytes;

/// Bytes as two hex digits each, spaced, as Python's `bytes.hex(" ")` writes them.
fn hex(bytes: &[u8]) -> String {
    let each: Vec<String> = bytes.iter().map(|b| format!("{b:02x}")).collect();
    each.join(" ")
}

fn main() {
    let path = "fixtures/plaintext-footer.parquet";
    let data = std::fs::read(path).expect("run this from the repository's root");
    let md = open_bytes(&data).expect("a footer"); // decoded as in ch02
    let chunk = &md.row_groups[0].columns[2]; // email; try 3, amount_cents
    let (start, size) = (chunk.data_page_offset, chunk.total_compressed_size);
    let stats = &chunk.statistics;
    println!(
        "email: bytes {start} to {}, statistics {stats:?}",
        start + size
    );
    let at = start as usize; // try the byte where the next module starts
                             // The length: the bytes that follow it.
    let n = u32::from_le_bytes(data[at..at + 4].try_into().unwrap()) as usize;
    println!("a module at byte {at}: length {n}");
    println!("  nonce: {}", hex(&data[at + 4..at + 16]));
    println!("  ciphertext: {} bytes", n - 12 - 16);
    println!("  tag: {}", hex(&data[at + 4 + n - 16..at + 4 + n]));
    println!("the next module starts at byte {}", at + 4 + n);
}
