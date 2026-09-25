//! Encodings: how values become bytes (ch05).
//!
//! This holds the one-value readers: a single PLAIN-encoded value, which is how the footer stores
//! a column's minimum and maximum, and bytes as hex. Whole pages are decoded by
//! [`crate::plain`], [`crate::decode`] and [`crate::delta`].

use crate::bytes::read_le_u32;
use crate::metadata::PhysicalType;

/// One value in PLAIN form, rendered for display. `None` when the bytes do not fit the type.
///
/// PLAIN writes fixed-width numbers little-endian and in full. A statistics value for a
/// `BYTE_ARRAY` column is the bare bytes, without the four-byte length prefix a PLAIN page
/// would give it, because the Thrift field already carries a length.
pub fn plain_scalar(physical: PhysicalType, bytes: &[u8]) -> Option<String> {
    match (physical.0, bytes.len()) {
        (0, 1) => Some((bytes[0] != 0).to_string()),
        (1, 4) => Some((read_le_u32([bytes[0], bytes[1], bytes[2], bytes[3]]) as i32).to_string()),
        (2, 8) => Some(i64::from_le_bytes(bytes.try_into().ok()?).to_string()),
        (4, 4) => Some(f32::from_le_bytes(bytes.try_into().ok()?).to_string()),
        (5, 8) => Some(f64::from_le_bytes(bytes.try_into().ok()?).to_string()),
        (6, _) | (7, _) => Some(match std::str::from_utf8(bytes) {
            Ok(s) if s.chars().all(|c| !c.is_control()) => format!("{s:?}"),
            _ => hex(bytes),
        }),
        _ => None,
    }
}

pub fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_numbers_are_little_endian() {
        assert_eq!(
            plain_scalar(PhysicalType(2), &4i64.to_le_bytes()),
            Some("4".into())
        );
        assert_eq!(
            plain_scalar(PhysicalType(1), &(-2i32).to_le_bytes()),
            Some("-2".into())
        );
        assert_eq!(
            plain_scalar(PhysicalType(5), &1.5f64.to_le_bytes()),
            Some("1.5".into())
        );
    }

    #[test]
    fn byte_arrays_show_as_text_when_they_are_text() {
        assert_eq!(plain_scalar(PhysicalType(6), b"UK"), Some("\"UK\"".into()));
        assert_eq!(plain_scalar(PhysicalType(6), &[0, 1]), Some("00 01".into()));
    }

    #[test]
    fn a_value_of_the_wrong_width_is_not_guessed_at() {
        assert_eq!(plain_scalar(PhysicalType(2), &[1, 2, 3]), None);
    }
}
