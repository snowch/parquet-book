//! The book's reader decodes a column, and records each step: a label, bytes, what it read.

use parquet_lab::encoding::hex;
use parquet_lab::logical::value_json;
use parquet_lab::metadata::decode_file_metadata;
use parquet_lab::plain::PlainValue;
use parquet_lab::{column, schema};

fn main() {
    let data = std::fs::read("fixtures/encodings.parquet") // or dictionary.parquet
        .expect("run this from the repository's root");
    let n = data.len();
    let length = u32::from_le_bytes(data[n - 8..n - 4].try_into().unwrap()) as usize;
    let base = n - 8 - length;
    let md = decode_file_metadata(&data[base..n - 8], base as u64).expect("a footer");
    let name = "url"; // try "order_id", "sku" or "weight_kg"; or "country" in dictionary.parquet
    let leaves = schema::leaves(&schema::build(&md.schema).expect("a schema"));
    let leaf = leaves.iter().find(|l| l.path == [name]).expect("a column");
    let chunk = &md.row_groups[0].columns[leaf.column];
    let read = column::read_column(&data, chunk, leaf).expect("a column");
    let show = |v: &PlainValue| value_json(leaf.physical_type, leaf.logical_type.as_ref(), v);

    if let Some(dictionary) = &read.dictionary {
        let entries = dictionary.entries.iter().map(|(v, _)| show(v).to_json());
        println!("dictionary page: {}", entries.collect::<Vec<_>>().join(" "));
    }
    for page in &read.pages {
        println!("{} page", page.encoding);
        for step in &page.steps {
            let raw = &data[step.span.start as usize..step.span.end as usize];
            let shown = hex(&raw[..raw.len().min(8)]);
            let more = (raw.len() > 8).then(|| format!(" … ({} bytes)", raw.len()));
            let more = more.unwrap_or_default();
            println!("  {}: {shown}{more}\n    {}", step.label, step.detail);
        }
    }
    let values = read.triples.iter().take(4).filter_map(|t| t.value.as_ref());
    let values: Vec<String> = values.map(|v| show(v).to_json()).collect();
    println!("values: {} …", values.join(" "));
}
