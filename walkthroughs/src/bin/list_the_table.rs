//! The table's files, found by walking its directories: each one's partition and size.

use std::fs;

/// The names in a directory, in order.
fn names(dir: &str) -> Vec<String> {
    let entries = fs::read_dir(dir).expect("run this from the repository's root");
    let mut names: Vec<String> = entries
        .map(|e| {
            e.expect("an entry")
                .file_name()
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    names.sort();
    names
}

fn main() {
    let table = "fixtures/table";
    for directory in names(table) {
        // A name, an equals sign and a value. The log's directory, _delta_log, has none.
        let Some((name, value)) = directory.split_once('=') else {
            continue;
        };
        for file in names(&format!("{table}/{directory}")) {
            let key = format!("{directory}/{file}"); // country=UK/part-0.parquet
            let size = fs::metadata(format!("{table}/{key}"))
                .expect("a file")
                .len();
            println!("{key}: {name} is {value}, {size} bytes");
        }
    }
}
