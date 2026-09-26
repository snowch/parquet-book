//! ch14's problems. Edit this file; `exercises/tests/lakehouse_and_beyond.rs` grades it.

/// Problem 14.1: read the partition values in a Hive-style path.
///
/// `path` is a file's key under a table, such as `year=2026/month=01/part-0.parquet`. Every
/// directory of the form `name=value` is a partition value; the file's own name is not, even
/// if it holds an `=`. Names and values are percent-encoded where a path could not hold them:
/// `%2F` is `/`, `%3D` is `=`, and `S%C3%A3o` is `São`, as UTF-8. Return the pairs in path order.
pub fn partition_values(path: &str) -> Vec<(String, String)> {
    let _ = path;
    todo!("problem 14.1")
}

/// Problem 14.2: which files could hold `lo <= order_id < hi`?
///
/// `log` is a Delta-style log: one JSON action per line. An `add` action names a file and
/// carries its statistics as a JSON string, with `minValues` and `maxValues` by column. A
/// `remove` action takes a file out of the table. Return the paths of the files the table holds
/// that the statistics cannot rule out, in the order the log adds them. A file with no
/// statistics for `order_id` cannot be ruled out.
///
/// You may use the book's reader: `parquet_lab::table::read_log(log)` returns the files, and
/// `parquet_lab::json::Json` parses JSON.
pub fn files_to_read(log: &str, lo: i64, hi: i64) -> Vec<String> {
    let _ = (log, lo, hi);
    todo!("problem 14.2")
}
