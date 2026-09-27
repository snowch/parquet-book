//! The same bytes, read two ways: as the physical type stores them, then as the logical type says.

use parquet_lab::logical::{date_from_days, decimal, timestamp, TimeUnit};
use parquet_lab::metadata::decode_file_metadata;

fn main() {
    let data =
        std::fs::read("fixtures/types.parquet").expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let chunks = &md.row_groups[0].columns;
    let least = |path: &str| {
        let chunk = chunks
            .iter()
            .find(|c| c.dotted_path() == path)
            .expect("a column");
        let stats = chunk.statistics.as_ref().expect("statistics");
        stats.min_value.clone().expect("a minimum")
    };

    // Rust's standard library has no calendar, so the dates come from the book's reader.
    let raw = least("order_date"); // INT32, DATE: days since 1970-01-01
    let days = i32::from_le_bytes(raw[..].try_into().unwrap());
    let date = date_from_days(i64::from(days));
    println!("order_date {} -> {days} -> {date}", hex(&raw));
    let raw = least("paid_at"); // INT64, TIMESTAMP(MICROS, UTC): microseconds since 1970-01-01, UTC
    let micros = i64::from_le_bytes(raw[..].try_into().unwrap());
    let at = timestamp(micros, TimeUnit::Micros, true);
    println!("paid_at {} -> {micros} -> {at}", hex(&raw));
    let raw = least("amount"); // FIXED_LEN_BYTE_ARRAY(4), DECIMAL(9, 2): an integer of hundredths
    let cents = i32::from_be_bytes(raw[..].try_into().unwrap()); // most significant byte first
    let amount = decimal(i128::from(cents), 2);
    println!("amount {} -> {cents} -> {amount}", hex(&raw));
}

/// Bytes as two hex digits each, spaced, as Python's `bytes.hex(" ")` writes them.
fn hex(bytes: &[u8]) -> String {
    let digits: Vec<String> = bytes.iter().map(|b| format!("{b:02x}")).collect();
    digits.join(" ")
}
