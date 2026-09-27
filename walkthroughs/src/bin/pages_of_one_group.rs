//! Read the page index of order_id in one row group: each page's range and first row.

use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::page_index::{column_index, offset_index};

fn main() {
    let path = "fixtures/pruning-sorted.parquet"; // try pruning-shuffled.parquet
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    // order_id in row group 2. Per page, its ColumnIndex holds a minimum, a maximum and a
    // null count; its OffsetIndex an offset, a size and a first row.
    let chunk = &md.row_groups[2].columns[0];
    let ci = column_index(&data, chunk).unwrap().expect("a ColumnIndex");
    let oi = offset_index(&data, chunk).unwrap().expect("an OffsetIndex");
    let (pages, order) = (oi.pages.len(), &ci.boundary_order);
    println!("{pages} pages, boundary order {order}");
    let wanted = 431;

    for (i, page) in oi.pages.iter().enumerate() {
        let low = i64::from_le_bytes(ci.min_values[i][..].try_into().unwrap());
        let high = i64::from_le_bytes(ci.max_values[i][..].try_into().unwrap());
        let may_hold = (low..=high).contains(&wanted);
        let verdict = if may_hold { "read" } else { "skip" };
        let (start, end) = (page.offset, page.offset + page.compressed_page_size);
        let first = page.first_row_index;
        print!("page {i}: order_id {low} to {high}, {verdict}; ");
        println!("rows from {first}, bytes {start} to {end}");
    }
}
