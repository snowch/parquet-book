//! ch15's problems. Edit this file; `exercises/tests/changing_a_table.rs` grades it.

use parquet_lab::changes::Snapshot;

/// Problem 15.1: which files must a lookup of one `order_id` open?
///
/// Return the paths of every data file in `snapshot` whose `order_id` range, from `min_key` to
/// `max_key` inclusive, holds `key`, in the snapshot's order; and the paths of every delete file
/// that names one of those data files, in the snapshot's order. A data file whose range cannot
/// hold the key need not be opened, and neither do the delete files that name only such files.
pub fn files_to_open(snapshot: &Snapshot, key: i64) -> (Vec<String>, Vec<String>) {
    let _ = (snapshot, key);
    todo!("problem 15.1")
}

/// Problem 15.2: plan a compaction.
///
/// A data file is rewritten if a delete file names it, or if it holds fewer than `small_rows`
/// live rows: its `record_count`, less the `record_count` of every delete file that names it.
/// Take those files in order of their `min_key`, and pack them into groups: a file joins the
/// current group if the group's live rows, with the file's, stay within `target_rows`, and
/// starts a new group otherwise. Drop any group of one file that no delete file names: it
/// would be rewritten unchanged. Return each group's data file paths, groups in order.
///
/// `snapshot.live_rows(f)` and `snapshot.deletes_for(path)` are yours to use.
pub fn plan_compaction(snapshot: &Snapshot, target_rows: i64, small_rows: i64) -> Vec<Vec<String>> {
    let _ = (snapshot, target_rows, small_rows);
    todo!("problem 15.2")
}
