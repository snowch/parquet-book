//! PLAIN encoding: values written back to back (ch04, ch05).
//!
//! The simplest encoding, and the one every other encoding falls back to:
//!
//! - fixed-width numbers (`INT32`, `INT64`, `FLOAT`, `DOUBLE`) are little-endian, in full;
//! - `FIXED_LEN_BYTE_ARRAY` values are their bytes, each the length the schema declares;
//! - `BYTE_ARRAY` values are a four-byte little-endian length, then the bytes;
//! - `BOOLEAN` values are bit-packed, one bit each, least significant bit first.
//!
//! Only non-null values are stored. A null has a definition level and nothing here.

use crate::bytes::{ByteReader, BytesError, Span};
use crate::json::Json;
use crate::metadata::PhysicalType;

/// A decoded value, before any logical type is applied.
#[derive(Clone, Debug, PartialEq)]
pub enum PlainValue {
    Bool(bool),
    Int(i64),
    Float(f64),
    Bytes(Vec<u8>),
}

impl PlainValue {
    /// The value's PLAIN bytes for a column of physical type `physical`, without the length
    /// prefix a byte array has in a page. Statistics store values this way (ch08).
    pub fn to_plain_bytes(&self, physical: PhysicalType) -> Vec<u8> {
        match (self, physical.0) {
            (PlainValue::Bool(b), _) => vec![u8::from(*b)],
            (PlainValue::Int(v), 1) => (*v as i32).to_le_bytes().to_vec(),
            (PlainValue::Int(v), _) => v.to_le_bytes().to_vec(),
            (PlainValue::Float(v), 4) => (*v as f32).to_le_bytes().to_vec(),
            (PlainValue::Float(v), _) => v.to_le_bytes().to_vec(),
            (PlainValue::Bytes(b), _) => b.clone(),
        }
    }

    /// As JSON: text for bytes that are UTF-8, and a hex string for bytes that are not.
    pub fn to_json(&self) -> Json {
        match self {
            PlainValue::Bool(b) => Json::Bool(*b),
            PlainValue::Int(v) => Json::Int(*v),
            PlainValue::Float(v) => Json::Float(*v),
            PlainValue::Bytes(b) => match std::str::from_utf8(b) {
                Ok(s) => Json::Str(s.to_string()),
                Err(_) => Json::Str(crate::encoding::hex(b)),
            },
        }
    }
}

/// Decode `count` PLAIN values of a physical type from `bytes`, which start at `base`. Each value
/// comes back with the span it occupied.
pub fn decode(
    physical: PhysicalType,
    type_length: Option<i64>,
    bytes: &[u8],
    base: u64,
    count: usize,
) -> Result<Vec<(PlainValue, Span)>, BytesError> {
    let mut r = ByteReader::new(bytes, base);
    let mut out = Vec::with_capacity(count);
    if physical.0 == 0 {
        // BOOLEAN: one bit per value. A value's span is the byte its bit sits in.
        let (raw, span) = r.read_bytes(count.div_ceil(8))?;
        for i in 0..count {
            let byte = span.start + (i / 8) as u64;
            out.push((
                PlainValue::Bool(raw[i / 8] >> (i % 8) & 1 == 1),
                Span::new(byte, byte + 1),
            ));
        }
        return Ok(out);
    }
    for _ in 0..count {
        let start = r.offset();
        let value = match physical.0 {
            1 => PlainValue::Int(i64::from(r.read_le_u32()? as i32)),
            2 => PlainValue::Int(r.read_le_u64()? as i64),
            3 => PlainValue::Bytes(r.read_bytes(12)?.0.to_vec()),
            4 => PlainValue::Float(f64::from(f32::from_bits(r.read_le_u32()?))),
            5 => PlainValue::Float(f64::from_bits(r.read_le_u64()?)),
            6 => {
                let len = r.read_le_u32()? as usize;
                PlainValue::Bytes(r.read_bytes(len)?.0.to_vec())
            }
            7 => {
                let len = type_length.unwrap_or(0).max(0) as usize;
                PlainValue::Bytes(r.read_bytes(len)?.0.to_vec())
            }
            _ => {
                return Err(BytesError::UnexpectedEnd {
                    offset: start,
                    wanted: 0,
                })
            }
        };
        out.push((value, Span::new(start, r.offset())));
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn byte_arrays_are_a_length_then_bytes() {
        let bytes = [2, 0, 0, 0, b'U', b'K', 0, 0, 0, 0];
        let v = decode(PhysicalType(6), None, &bytes, 10, 2).unwrap();
        assert_eq!(v[0], (PlainValue::Bytes(b"UK".to_vec()), Span::new(10, 16)));
        assert_eq!(v[1], (PlainValue::Bytes(vec![]), Span::new(16, 20)));
    }

    #[test]
    fn booleans_are_one_bit_each() {
        let v = decode(PhysicalType(0), None, &[0b0000_0101], 0, 3).unwrap();
        let bools: Vec<_> = v.iter().map(|(b, _)| b.clone()).collect();
        assert_eq!(
            bools,
            [
                PlainValue::Bool(true),
                PlainValue::Bool(false),
                PlainValue::Bool(true)
            ]
        );
    }

    #[test]
    fn integers_are_little_endian_and_signed() {
        let mut bytes = (-3i32).to_le_bytes().to_vec();
        bytes.extend_from_slice(&7i64.to_le_bytes());
        assert_eq!(
            decode(PhysicalType(1), None, &bytes[..4], 0, 1).unwrap()[0].0,
            PlainValue::Int(-3)
        );
        assert_eq!(
            decode(PhysicalType(2), None, &bytes[4..], 4, 1).unwrap()[0].1,
            Span::new(4, 12)
        );
    }
}
