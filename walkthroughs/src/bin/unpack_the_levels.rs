//! Unpack a page's levels by hand: a length, a run header, then levels, lowest bits first.

use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::{pages, schema};

fn main() {
    let data =
        std::fs::read("fixtures/nested.parquet").expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let column = 4; // items[].discounts[]; try 2, which is tags[], or 1, which is email
    let leaf = &schema::leaves(&schema::build(&md.schema).expect("a schema"))[column];
    let chunk = md.row_groups[0].columns[column].byte_range();
    let (start, end) = (chunk.start as usize, chunk.end as usize);
    let pages = pages::walk_pages(&data[start..end], chunk.start).expect("pages");
    let page = &pages[0]; // its one page
    let body = &data[page.body_span.start as usize..page.body_span.end as usize];
    let slots = page.num_values.expect("a data page") as usize;

    let mut at = 0; // repetition levels come first, then definition levels, then values
    for (name, most) in [
        ("rep", leaf.max_repetition_level),
        ("def", leaf.max_definition_level),
    ] {
        if most == 0 {
            println!("{name}: none stored, since the maximum is 0");
            continue;
        }
        // A version-1 page's length prefix, then a ULEB128 header, one byte here.
        let size = u32::from_le_bytes(body[at..at + 4].try_into().unwrap()) as usize;
        let (header, width) = (body[at + 4], 32 - most.leading_zeros());
        let bits = body[at + 5..at + 4 + size]
            .iter()
            .rev()
            .fold(0u64, |acc, b| acc << 8 | u64::from(*b));
        let kind = format!("{name}: {size} bytes, header {header:02x},");
        if header & 1 == 1 {
            // Bit-packed: header >> 1 groups of eight levels, width bits each.
            let groups = (header >> 1) as usize;
            let level = |i: usize| bits >> (i as u32 * width) & ((1 << width) - 1);
            let levels: Vec<String> = (0..slots).map(|i| level(i).to_string()).collect();
            let padding = format!("(+{} padding)", 8 * groups - slots);
            println!(
                "{kind} bit-packed, {groups} group: {} {padding}",
                levels.join(" ")
            );
        } else {
            // RLE: header >> 1 copies of the one level that follows.
            println!("{kind} RLE, {} copies of {bits}", header >> 1);
        }
        at += 4 + size;
    }
}
