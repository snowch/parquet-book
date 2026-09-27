//! Rebuild the tree from the flat list: each group's count of children is all it takes.

use parquet_lab::metadata::{decode_file_metadata, SchemaElement};
use parquet_lab::schema;

fn main() {
    let mut data =
        std::fs::read("fixtures/types.parquet").expect("run this from the repository's root");
    data[674] = 0x14; // the root's count of children, 10, as a zigzag varint; try 0x12, which is 9
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");

    walk(&mut md.schema.iter(), 0, 0, 0);
    match schema::build(&md.schema) {
        Ok(root) => {
            let columns = schema::leaves(&root).len();
            println!("the reader's build finds {columns} columns");
        }
        Err(refused) => println!("the reader refuses: {refused}"),
    }
}

/// Take one element and print it, then as many subtrees as it says it has children.
fn walk<'a>(
    elements: &mut impl Iterator<Item = &'a SchemaElement>,
    depth: usize,
    mut definition: u32,
    mut repetition: u32,
) {
    let e = elements.next().expect("an element for every child");
    if depth > 0 {
        // Every optional or repeated field on the way down adds a level.
        definition += u32::from(e.repetition.as_deref() != Some("REQUIRED"));
        repetition += u32::from(e.repetition.as_deref() == Some("REPEATED"));
    }
    let children = e.num_children.unwrap_or(0);
    let levels = format!("  max levels: definition {definition}, repetition {repetition}");
    let levels = if children > 0 { "" } else { &levels };
    println!("{}{}{levels}", "  ".repeat(depth), e.name);
    for _ in 0..children {
        walk(elements, depth + 1, definition, repetition);
    }
}
