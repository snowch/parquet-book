//! The book's reader: every slot of a column as its two levels and a value, then the records.

use parquet_lab::json::Json;
use parquet_lab::logical::value_json;
use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::{column, nested, schema};

fn main() {
    let data =
        std::fs::read("fixtures/nested.parquet").expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let root = schema::build(&md.schema).expect("a schema");
    let name = "tags"; // try "email", "order_id", or "items", which has two columns

    for leaf in schema::leaves(&root).iter().filter(|l| l.path[0] == name) {
        let fields = nested::path_fields(&root, leaf); // each field on the path, with its levels
        let chunk = &md.row_groups[0].columns[leaf.column];
        let read = column::read_column(&data, chunk, leaf).expect("a column");
        let triples = read.triples;
        let label = &fields.last().expect("a path").label;
        let (d, r) = (leaf.max_definition_level, leaf.max_repetition_level);
        println!("{label}  max levels: definition {d}, repetition {r}\nr d value");
        let logical = leaf.logical_type.as_ref();
        for t in &triples {
            let v = t.value.as_ref();
            let v = v.map_or(Json::Null, |v| value_json(leaf.physical_type, logical, v));
            println!("{} {} {}", t.rep, t.def, v.to_json());
        }
        for record in nested::assemble(&fields, leaf, &triples) {
            println!("{}", record.to_json());
        }
    }
}
