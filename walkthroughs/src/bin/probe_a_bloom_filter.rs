//! Probe each row group's Bloom filter on customer_id for one customer number.

use parquet_lab::bloom::{read, xxh64};
use parquet_lab::metadata::decode_file_metadata;

fn main() {
    let path = "fixtures/pruning-shuffled.parquet"; // try pruning-sorted.parquet
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let value = 424242i64.to_le_bytes(); // an INT64's PLAIN bytes; try another customer
    println!("xxHash64 of {value:02x?}: {:016x}", xxh64(&value, 0));

    for (g, row_group) in md.row_groups.iter().enumerate() {
        let chunk = &row_group.columns[1]; // customer_id
        let f = read(&data, chunk).unwrap().expect("a Bloom filter");
        // The hash's high half picks a block, its low half a bit in each of its words.
        let p = f.probe(&value);
        let (block, blocks, bits) = (p.block, f.num_blocks(), p.bits);
        println!("row group {g}: block {block} of {blocks}, bits {bits:?}");
        println!("  may contain it: {}", p.may_contain);
    }
}
