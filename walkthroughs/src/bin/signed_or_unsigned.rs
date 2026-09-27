//! Take a column's bounds from the footer, and read their bytes two ways.

use parquet_lab::metadata::decode_file_metadata;

fn main() {
    let path = "fixtures/statistics.parquet";
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let column = 1; // customer_id; try 2, which is delta
    let e = md.leaves()[column];
    let kind = e.physical_type.expect("a leaf").name();
    let logical = e.logical_type.as_ref().expect("a logical type");
    println!("{} {kind} {logical}", e.name);

    for (g, row_group) in md.row_groups.iter().enumerate() {
        let chunk = &row_group.columns[column];
        let s = chunk.statistics.as_ref().expect("statistics");
        // Four bytes each, least significant first.
        let low: [u8; 4] = s.min_value.as_deref().unwrap().try_into().unwrap();
        let high: [u8; 4] = s.max_value.as_deref().unwrap().try_into().unwrap();
        let unsigned = [u32::from_le_bytes(low), u32::from_le_bytes(high)];
        let signed = [i32::from_le_bytes(low), i32::from_le_bytes(high)];
        print!("row group {g}: max {high:02x?}; ");
        println!("unsigned {unsigned:?}, signed {signed:?}");
    }
}
