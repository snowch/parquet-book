//! Damage the footer length, and see where the arithmetic now puts the footer.

fn main() {
    let mut data =
        std::fs::read("fixtures/tiny.parquet").expect("run this from the repository's root");
    let n = data.len();
    data[n - 7] = 0xFF; // the second of the four length bytes

    let length_bytes: [u8; 4] = data[n - 8..n - 4].try_into().unwrap();
    let footer_length = u32::from_le_bytes(length_bytes);
    println!("the footer length now reads {footer_length}");
    // Signed arithmetic: the answer can be negative, and that is the point.
    println!(
        "so the footer would start at byte {}",
        n as i64 - 8 - i64::from(footer_length)
    );
}
