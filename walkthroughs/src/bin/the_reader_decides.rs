//! Ask the reader which bounds it may use, column chunk by column chunk, and why not.

use parquet_lab::encoding::plain_scalar;
use parquet_lab::logical::interpret;
use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::schema::{build, leaves, Leaf};
use parquet_lab::stats::{bounds, Comparator};

/// Through the logical type if it has one, else the physical type.
fn show(leaf: &Leaf, v: &[u8]) -> String {
    let t = leaf.physical_type;
    let read = leaf.logical_type.as_ref().and_then(|l| interpret(t, l, v));
    read.or_else(|| plain_scalar(t, v)).unwrap_or_default()
}

fn main() {
    let path = "fixtures/statistics.parquet";
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    // Try true: keep only the deprecated min and max, as old writers did.
    let old_writer = false;

    for leaf in leaves(&build(&md.schema).expect("a schema")) {
        let converted = md.schema[leaf.element].converted_type.as_deref();
        let comparator = Comparator::for_leaf(&leaf, converted);
        let type_order = md.column_orders.as_ref().unwrap()[leaf.column] == "TYPE_ORDER";
        println!("{}, compared as {}:", leaf.dotted_path(), comparator.name());
        for (g, row_group) in md.row_groups.iter().enumerate() {
            let Some(mut s) = row_group.columns[leaf.column].statistics.clone() else {
                println!("  row group {g}: no statistics");
                continue;
            };
            if old_writer {
                (s.min_value, s.max_value) = (None, None);
            }
            match bounds(&s, comparator, type_order) {
                Ok(b) => {
                    let (min, max) = (show(&leaf, &b.min), show(&leaf, &b.max));
                    println!("  row group {g}: {min} to {max}, from {:?}", b.source);
                }
                Err(refused) => {
                    let nulls = s.null_count.unwrap_or(0);
                    println!("  row group {g}: refused, {refused}; null count {nulls}");
                }
            }
        }
    }
}
