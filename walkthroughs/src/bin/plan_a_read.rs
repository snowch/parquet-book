//! Plan SELECT * WHERE order_id = 431 with the reader, one mechanism at a time.

use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::prune::{plan, Mechanisms, Op, Predicate};
use parquet_lab::schema::{build, leaves};

fn main() {
    let path = "fixtures/pruning-sorted.parquet"; // try pruning-shuffled.parquet
    let data = std::fs::read(path).expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let leaves = leaves(&build(&md.schema).expect("a schema"));
    let leaf = &leaves[0]; // order_id; try 1, customer_id, with "424242"
    let converted = md.schema[leaf.element].converted_type.as_deref();
    let p = Predicate::new(leaf, converted, Op::Eq, "431").expect("a condition");
    let use_ = Mechanisms {
        statistics: true,
        bloom: true,
        page_index: true, // turn each off
    };
    let every: Vec<usize> = leaves.iter().map(|x| x.column).collect(); // SELECT *

    let plan = plan(&data, &md, leaf, &p, &every, use_).expect("a plan");
    for g in &plan.row_groups {
        if g.skipped {
            println!("row group {}: skip", g.index);
        } else {
            println!("row group {}: read rows {:?}", g.index, g.rows);
        }
        for (mechanism, decision) in &g.steps {
            let verdict = if decision.skip { "skip" } else { "read" };
            println!("  {mechanism}: {verdict}, {}", decision.why);
        }
    }
    let (bytes, index) = (plan.bytes_read(), plan.index_bytes());
    println!("{bytes} bytes of column chunks, {index} to decide");
}
