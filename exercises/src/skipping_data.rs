//! ch09's problems. Edit this file; `exercises/tests/skipping_data.rs` grades it.

/// The comparisons problem 9.1 handles.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Cmp {
    Eq,
    Lt,
    Gt,
    IsNull,
}

/// Problem 9.1: may a reader skip a page or a column chunk?
///
/// The condition is `column cmp value` on an `INT64` column. From metadata, the reader knows the
/// smallest and largest non-null values (`bounds`, `None` when every value is null or none are
/// recorded), how many values are null (`null_count`), and how many values there are in all
/// (`num_values`). Return `true` only if no row can satisfy the condition. Null satisfies no
/// comparison except `IsNull`.
pub fn can_skip(
    cmp: Cmp,
    value: i64,
    bounds: Option<(i64, i64)>,
    null_count: i64,
    num_values: i64,
) -> bool {
    let _ = (cmp, value, bounds, null_count, num_values);
    todo!("problem 9.1")
}

/// Problem 9.2: probe a split block Bloom filter.
///
/// `bitset` is the filter's bitset: blocks of 32 bytes, each eight little-endian `u32` words.
/// `hash` is the xxHash64 of the value. The block is `((hash >> 32) * number_of_blocks) >> 32`.
/// For each word `i`, the bit to test is the top five bits of `(hash as u32) * SALT[i]`, with
/// wrapping multiplication. Return `false` if any tested bit is clear.
pub fn may_contain(bitset: &[u8], hash: u64) -> bool {
    const SALT: [u32; 8] = [
        0x47b6137b, 0x44974d91, 0x8824ad5b, 0xa2b7289d, 0x705495c7, 0x2df1424b, 0x9efc4947,
        0x5c6bfb31,
    ];
    let _ = (bitset, hash, SALT);
    todo!("problem 9.2")
}
