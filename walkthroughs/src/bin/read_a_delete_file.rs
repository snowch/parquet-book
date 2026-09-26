//! A position delete file is a Parquet file of (file_path, pos): read one with the book's reader.

use parquet_lab::engine::{run, Value};

fn main() {
    let deletes = std::fs::read("fixtures/changes/deletes/delete-00.parquet")
        .expect("run this from the repository's root");
    for row in run(&deletes, "SELECT file_path, pos FROM deletes")
        .unwrap()
        .rows
    {
        let [Value::Str(path), Value::Int(pos)] = &row[..] else {
            panic!("a delete file holds a path and a position");
        };
        let data = std::fs::read(format!("fixtures/changes/{path}")).unwrap();
        let orders = run(&data, "SELECT order_id FROM orders").unwrap().rows;
        let order = orders[*pos as usize][0].to_json().to_json();
        println!("row {pos} of {path} is deleted: order {order}");
    }
}
