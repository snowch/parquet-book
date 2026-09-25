//! ch08's problems. Edit this file; `exercises/tests/metadata_and_statistics.rs` grades it.

use std::cmp::Ordering;

use parquet_lab::metadata::Statistics;

/// The kinds of column the problems use, each with its own sort order.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    /// `INT32`, signed. Little-endian, four bytes.
    Int32,
    /// `INT32` annotated as an unsigned integer. Little-endian, four bytes.
    UInt32,
    /// `INT64`, signed. Little-endian, eight bytes.
    Int64,
    /// `DOUBLE`. Little-endian, eight bytes. NaN has no place in the order.
    Double,
    /// `BYTE_ARRAY` holding a string: the bytes, without a length prefix.
    String,
    /// A `DECIMAL` in a `FIXED_LEN_BYTE_ARRAY`: big-endian two's complement.
    Decimal,
}

/// Problem 8.1: compare two values in their column's sort order.
///
/// `a` and `b` are PLAIN bytes as the footer stores them. Return `None` if either is NaN, and
/// the ordering otherwise. Do not call `parquet_lab::stats`.
pub fn compare(kind: Kind, a: &[u8], b: &[u8]) -> Option<Ordering> {
    let _ = (kind, a, b);
    todo!("problem 8.1")
}

/// Problem 8.2: the bounds a reader may use.
///
/// Return the minimum and maximum a reader may compare values against, or `None` if it may use
/// none. Apply the rules from the chapter:
///
/// - `min_value` and `max_value`, when both are present, and only if `type_order` is true (the
///   footer's `column_orders` gives this column `TYPE_ORDER`);
/// - otherwise the deprecated `min` and `max`, and only for `Int32`, `Int64` and `Double`;
/// - never a bound that is NaN.
///
/// You may use your `compare` from problem 8.1 to spot NaN.
pub fn usable_bounds(
    stats: &Statistics,
    kind: Kind,
    type_order: bool,
) -> Option<(Vec<u8>, Vec<u8>)> {
    let _ = (stats, kind, type_order);
    todo!("problem 8.2")
}
