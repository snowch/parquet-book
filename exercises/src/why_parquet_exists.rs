//! ch01's problems. Edit this file; `exercises/tests/why_parquet_exists.rs` grades it.

/// Problem 1.1: turn the values a query needs into the reads it must make.
///
/// `spans` is the byte range of every value the query needs, as `(start, end)` pairs with `end`
/// excluded, in no particular order. Return the ranges a reader would request: sorted by start,
/// with any two ranges that touch (one ends where the next starts) merged into one. Do not merge
/// ranges with a gap between them, however small: reading bytes the query does not need is a
/// decision ch10 makes, not this function.
///
/// The test runs your function over every combination of columns and rows of the chapter's
/// sales table, in both layouts, and compares the number of reads with the book's own planner.
pub fn reads_for(spans: &[(u64, u64)]) -> Vec<(u64, u64)> {
    let _ = spans;
    todo!("problem 1.1")
}
