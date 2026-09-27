//! Read each file's footer: how many of its row groups could hold order 431?

use parquet_lab::metadata::decode_file_metadata;

fn main() {
    let files = "baseline one-group small-groups by-country shuffled plain no-index";
    let (column, wanted) = (0, 431); // order_id = 431; try 2, customer_id, and 500000

    for name in files.split_whitespace() {
        let path = format!("fixtures/writing-{name}.parquet");
        let data = std::fs::read(path).expect("run this from the repository's root");
        let n = data.len();
        let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
        let base = n - 8 - length;
        let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
        let mut hits = 0;
        for row_group in &md.row_groups {
            let chunk = &row_group.columns[column]; // an INT64: eight bytes, least first
            let s = chunk.statistics.as_ref().expect("statistics");
            let low: [u8; 8] = s.min_value.as_deref().unwrap().try_into().unwrap();
            let high: [u8; 8] = s.max_value.as_deref().unwrap().try_into().unwrap();
            let (low, high) = (i64::from_le_bytes(low), i64::from_le_bytes(high));
            hits += usize::from((low..=high).contains(&wanted));
        }
        let groups = md.row_groups.len();
        println!(
            "writing-{name}: footer {length} bytes, {hits} of {groups} row groups may hold it"
        );
    }
}
