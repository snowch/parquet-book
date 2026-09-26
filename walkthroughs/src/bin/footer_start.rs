//! Where the footer starts: it ends where the last eight bytes begin, and is as long as they say.

fn main() {
    let data = std::fs::read("fixtures/tiny.parquet").expect("run this from the repository's root");
    let length_bytes: [u8; 4] = data[data.len() - 8..data.len() - 4].try_into().unwrap();
    let footer_length = u32::from_le_bytes(length_bytes) as usize;

    let footer_start = data.len() - 8 - footer_length;
    let footer = &data[footer_start..data.len() - 8];
    println!(
        "the footer starts at byte {footer_start} and is {} bytes long",
        footer.len()
    );
    println!("its first eight bytes: {}", hex(&footer[..8]));
}

/// Bytes as two hex digits each, spaced, as Python's `bytes.hex(" ")` writes them.
fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}
