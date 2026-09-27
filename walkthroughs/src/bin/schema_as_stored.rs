//! The schema as the footer stores it: a flat list, one element per field, groups included.

use parquet_lab::metadata::decode_file_metadata;

fn main() {
    let data =
        std::fs::read("fixtures/types.parquet").expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length; // where the footer starts, as in ch02
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");

    for e in &md.schema {
        let repetition = e.repetition.as_deref().unwrap_or("");
        match (e.num_children.unwrap_or(0), e.physical_type) {
            (0, Some(physical)) => {
                let logical = e.logical_type.as_ref().map(|l| l.to_string());
                let logical = logical.unwrap_or_default();
                println!("{} {repetition} {} {logical}", e.name, physical.name());
            }
            (children, _) => println!("{} {children} children {repetition}", e.name),
        }
    }
}
