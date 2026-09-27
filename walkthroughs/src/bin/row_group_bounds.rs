//! Read each row group's range of order_id from the footer: can it hold order 431?

use parquet_lab::metadata::decode_file_metadata;

fn main() {
    let path = "fixtures/pruning-sorted.parquet"; // try pruning-shuffled.parquet
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let wanted = 431; // order_id = 431; try 200 and 201

    for (g, row_group) in md.row_groups.iter().enumerate() {
        let chunk = &row_group.columns[0]; // order_id, an INT64
        let s = chunk.statistics.as_ref().expect("statistics");
        // Eight bytes each, least significant first.
        let low: [u8; 8] = s.min_value.as_deref().unwrap().try_into().unwrap();
        let high: [u8; 8] = s.max_value.as_deref().unwrap().try_into().unwrap();
        let (low, high) = (i64::from_le_bytes(low), i64::from_le_bytes(high));
        let may_hold = (low..=high).contains(&wanted);
        let verdict = if may_hold { "read" } else { "skip" };
        println!("row group {g}: order_id {low} to {high}, {verdict}");
    }
}
