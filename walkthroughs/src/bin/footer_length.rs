//! The four bytes before the closing magic, read as a little-endian number.

fn main() {
    let data = std::fs::read("fixtures/tiny.parquet").expect("run this from the repository's root");

    let length_bytes: [u8; 4] = data[data.len() - 8..data.len() - 4].try_into().unwrap();
    println!("the four before them: {}", hex(&length_bytes));
    println!("read little-endian: {}", u32::from_le_bytes(length_bytes));
}

/// Bytes as two hex digits each, spaced, as Python's `bytes.hex(" ")` writes them.
fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}
