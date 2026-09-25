//! ch04's problems. Edit this file; `exercises/tests/nested_data.rs` grades it.

/// Problem 4.1: the RLE / bit-packing hybrid.
///
/// Decode `count` values of `bit_width` bits each from `bytes`. The stream is a sequence of runs,
/// each starting with a ULEB128 header:
///
/// - if the header's lowest bit is 0, it is an RLE run: `header >> 1` copies of one value, which
///   follows in `ceil(bit_width / 8)` bytes, little-endian;
/// - if it is 1, it is a bit-packed run: `header >> 1` groups of eight values, each packed into
///   `bit_width` bits, least significant bit first.
///
/// Stop when you have `count` values: the last bit-packed group may be padded past it.
pub fn decode_hybrid(bytes: &[u8], bit_width: u32, count: usize) -> Vec<u32> {
    let _ = (bytes, bit_width, count);
    todo!("problem 4.1")
}

/// Problem 4.2: rebuild a list column from its levels.
///
/// The column is a standard list of optional strings:
///
/// ```text
/// optional group tags (LIST) {
///   repeated group list {
///     optional binary element (STRING);
///   }
/// }
/// ```
///
/// Its maximum definition level is 3 and its maximum repetition level 1. `rep` and `def` hold
/// one level each per value slot; `values` holds only the values that are present, in order.
/// Return one entry per record: `None` for a null list, `Some(vec![])` for an empty one, and
/// `Some` of the elements otherwise, with `None` for a null element.
pub fn list_from_levels(
    rep: &[u32],
    def: &[u32],
    values: &[String],
) -> Vec<Option<Vec<Option<String>>>> {
    let _ = (rep, def, values);
    todo!("problem 4.2")
}
