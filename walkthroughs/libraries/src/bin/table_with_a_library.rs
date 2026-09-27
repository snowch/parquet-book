//! The same table to the `parquet` crate, which reads files, not tables: walk the directories,
//! take the partition from each path and the range of order_id from each file's footer.

use std::fs::{self, File};
use std::path::PathBuf;

use parquet::file::metadata::ParquetMetaDataReader;
use parquet::file::statistics::Statistics;

/// The paths in a directory, in order.
fn paths(dir: &str) -> Vec<PathBuf> {
    let entries = fs::read_dir(dir).expect("run this from the repository's root");
    let mut paths: Vec<PathBuf> = entries.map(|e| e.expect("an entry").path()).collect();
    paths.sort();
    paths
}

fn main() {
    for dir in paths("fixtures/table") {
        let name = dir.file_name().unwrap().to_string_lossy().into_owned();
        let Some((_, country)) = name.split_once('=') else {
            continue; // _delta_log, which the crate knows nothing about
        };
        for path in paths(&dir.to_string_lossy()) {
            let file = File::open(&path).expect("a file");
            let md = ParquetMetaDataReader::new()
                .parse_and_finish(&file)
                .expect("a Parquet file");
            let rows = md.file_metadata().num_rows();
            // One row group a file; order_id is its first column.
            let Some(Statistics::Int64(s)) = md.row_group(0).column(0).statistics() else {
                continue;
            };
            let (low, high) = (s.min_opt().unwrap(), s.max_opt().unwrap());
            // Could it hold country = 'UK' AND order_id < 200? Try 300.
            let kept = country == "UK" && *low < 200;
            let key = path.strip_prefix("fixtures/table").unwrap().display();
            println!("{key}: {rows} rows, order_id {low} to {high}, kept {kept}");
        }
    }
}
