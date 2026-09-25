//! ch03's problems. Edit this file; `exercises/tests/the_type_system.rs` grades it.

use parquet_lab::schema::Repetition;

/// Problem 3.1: rebuild the tree, and name its leaves.
///
/// `elements` is a schema as the footer stores it: each element's name and number of children,
/// in depth-first order, starting with the root. Return the path of every leaf, in order, as
/// the names from the root's child down to the leaf joined with dots (`shipping.city`). The
/// root's own name is not part of any path. A leaf is an element with no children.
///
/// The test runs your function on the fixtures and on hundreds of generated schemas.
pub fn leaf_paths(elements: &[(&str, usize)]) -> Vec<String> {
    let _ = elements;
    todo!("problem 3.1")
}

/// Problem 3.2: the maximum levels of a leaf.
///
/// `path` is the repetition of every field from the root's child down to the leaf. Return
/// `(max_definition_level, max_repetition_level)`.
pub fn max_levels(path: &[Repetition]) -> (u32, u32) {
    let _ = path;
    todo!("problem 3.2")
}

/// Problem 3.3: a decimal stored as bytes.
///
/// A `DECIMAL` stored in a `FIXED_LEN_BYTE_ARRAY` is an unscaled integer in big-endian
/// two's-complement form: most significant byte first, and negative when the first byte's top
/// bit is set. The value is that integer divided by ten to the power `scale`.
///
/// Return the value as a string with exactly `scale` digits after the point (`"5.00"`,
/// `"-0.05"`). `bytes` is between one and sixteen bytes long; `scale` is at least one.
pub fn decimal_from_bytes(bytes: &[u8], scale: u32) -> String {
    let _ = (bytes, scale);
    todo!("problem 3.3")
}
