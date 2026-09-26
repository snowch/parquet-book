//! ch12's problems. Edit this file; `exercises/tests/a_tiny_query_engine.rs` grades it.

/// Problem 12.1: a hash aggregate.
///
/// `keys[i]` is row `i`'s group and `values[i]` its value. Return each group with the sum of its
/// values, sorted by group, comparing groups as bytes. This is `SELECT key, sum(value) ... GROUP
/// BY key ORDER BY key`.
pub fn sum_by_key(keys: &[&str], values: &[i64]) -> Vec<(String, i64)> {
    let _ = (keys, values);
    todo!("problem 12.1")
}

/// Problem 12.2: the top `n`.
///
/// `rows` are `(order_id, amount)` pairs. Return the `n` with the largest amounts, largest first,
/// breaking ties by the smaller `order_id` first. This is `ORDER BY amount DESC, order_id LIMIT
/// n`. Sorting everything works; keeping only the best `n` as you go uses less memory.
pub fn top_n(rows: &[(i64, i64)], n: usize) -> Vec<(i64, i64)> {
    let _ = (rows, n);
    todo!("problem 12.2")
}
