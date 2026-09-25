//! Statistics: what the footer says about a column chunk's values, and when a reader may
//! believe it (ch08).
//!
//! A column chunk's `Statistics` hold a minimum and a maximum as bytes. They mean something only
//! with an order, and the right order depends on the column's type, not on its bytes:
//!
//! | Column | Order |
//! |---|---|
//! | `INT32`, `INT64`, and the dates, times and timestamps on them | signed |
//! | `INT32`, `INT64` marked as unsigned integers | unsigned |
//! | `FLOAT`, `DOUBLE`, `FLOAT16` | signed, by value, with NaN left out |
//! | `DECIMAL` on bytes | signed, as a big-endian two's complement number |
//! | any other byte array: strings, UUIDs, binary | unsigned, byte by byte |
//! | `INT96`, `INTERVAL` | undefined |
//!
//! [`Comparator`] is that table as code. [`bounds`] applies the rules for which fields a reader
//! may use: the newer `min_value` and `max_value` when the footer says their order, and the
//! deprecated `min` and `max` only where signed comparison was the right order anyway.

use std::cmp::Ordering;

use crate::logical::{f16_to_f32, LogicalType};
use crate::metadata::Statistics;
use crate::schema::Leaf;

/// The three sort orders the format distinguishes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SortOrder {
    Signed,
    Unsigned,
    Undefined,
}

impl SortOrder {
    pub fn name(&self) -> &'static str {
        match self {
            SortOrder::Signed => "signed",
            SortOrder::Unsigned => "unsigned",
            SortOrder::Undefined => "undefined",
        }
    }
}

/// How to compare two PLAIN-encoded values of one column (without a length prefix).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Comparator {
    Bool,
    I32,
    U32,
    I64,
    U64,
    F32,
    F64,
    F16,
    /// A decimal stored in bytes: big-endian two's complement.
    BigEndianSigned,
    /// Strings and other byte arrays: byte by byte, each byte unsigned, shorter first on a tie.
    Bytes,
    /// Byte by byte with each byte signed, as Java's `byte` compares. Never right; it is how
    /// early writers computed the deprecated `min` and `max` of strings.
    SignedBytes,
    /// A float's bits compared as a signed integer. Never right either.
    FloatBits,
    None,
}

impl Comparator {
    /// The comparator for a leaf column, from its physical type and its annotation.
    pub fn for_leaf(leaf: &Leaf, converted: Option<&str>) -> Comparator {
        let logical = leaf.logical_type.as_ref();
        let unsigned = matches!(logical, Some(LogicalType::Integer { signed: false, .. }))
            || matches!(
                converted,
                Some("UINT_8" | "UINT_16" | "UINT_32" | "UINT_64")
            );
        let decimal =
            matches!(logical, Some(LogicalType::Decimal { .. })) || converted == Some("DECIMAL");
        match leaf.physical_type.0 {
            0 => Comparator::Bool,
            1 if unsigned => Comparator::U32,
            1 => Comparator::I32,
            2 if unsigned => Comparator::U64,
            2 => Comparator::I64,
            4 => Comparator::F32,
            5 => Comparator::F64,
            7 if matches!(logical, Some(LogicalType::Float16)) => Comparator::F16,
            7 if converted == Some("INTERVAL") => Comparator::None,
            6 | 7 if decimal => Comparator::BigEndianSigned,
            6 | 7 => Comparator::Bytes,
            _ => Comparator::None, // INT96
        }
    }

    pub fn order(&self) -> SortOrder {
        match self {
            Comparator::U32 | Comparator::U64 | Comparator::Bytes => SortOrder::Unsigned,
            Comparator::None => SortOrder::Undefined,
            _ => SortOrder::Signed,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Comparator::Bool => "booleans, false first",
            Comparator::I32 | Comparator::I64 => "signed integers",
            Comparator::U32 | Comparator::U64 => "unsigned integers",
            Comparator::F32 | Comparator::F64 | Comparator::F16 => {
                "floating-point values, leaving out NaN"
            }
            Comparator::BigEndianSigned => "signed big-endian integers",
            Comparator::Bytes => "unsigned bytes",
            Comparator::SignedBytes => "signed bytes",
            Comparator::FloatBits => "the bits as signed integers",
            Comparator::None => "nothing, because the order is undefined",
        }
    }

    /// The mistake a reader is most likely to make with this column, and what it does wrong.
    pub fn mistake(&self) -> Option<(Comparator, &'static str)> {
        Some(match self {
            Comparator::U32 => (
                Comparator::I32,
                "reads values of 2^31 and above as negative",
            ),
            Comparator::U64 => (
                Comparator::I64,
                "reads values of 2^63 and above as negative",
            ),
            Comparator::I32 => (
                Comparator::U32,
                "reads negative values as large positive ones",
            ),
            Comparator::I64 => (
                Comparator::U64,
                "reads negative values as large positive ones",
            ),
            Comparator::Bytes => (
                Comparator::SignedBytes,
                "puts bytes 0x80 and above, every non-ASCII character, before the letter A",
            ),
            Comparator::BigEndianSigned => (
                Comparator::Bytes,
                "ignores the sign, so negative amounts sort last",
            ),
            Comparator::F32 | Comparator::F64 => (
                Comparator::FloatBits,
                "reverses negative numbers and sorts NaN above everything",
            ),
            _ => return None,
        })
    }

    /// Compare two values. `None` when either is not a valid value of the type, or either is
    /// NaN, which has no place in the order.
    pub fn compare(&self, a: &[u8], b: &[u8]) -> Option<Ordering> {
        fn fixed<const N: usize>(v: &[u8]) -> Option<[u8; N]> {
            v.try_into().ok()
        }
        match self {
            Comparator::Bool => Some(a.first()?.cmp(b.first()?)),
            Comparator::I32 => {
                Some(i32::from_le_bytes(fixed(a)?).cmp(&i32::from_le_bytes(fixed(b)?)))
            }
            Comparator::U32 => {
                Some(u32::from_le_bytes(fixed(a)?).cmp(&u32::from_le_bytes(fixed(b)?)))
            }
            Comparator::I64 => {
                Some(i64::from_le_bytes(fixed(a)?).cmp(&i64::from_le_bytes(fixed(b)?)))
            }
            Comparator::U64 => {
                Some(u64::from_le_bytes(fixed(a)?).cmp(&u64::from_le_bytes(fixed(b)?)))
            }
            Comparator::F32 => {
                f32::from_le_bytes(fixed(a)?).partial_cmp(&f32::from_le_bytes(fixed(b)?))
            }
            Comparator::F64 => {
                f64::from_le_bytes(fixed(a)?).partial_cmp(&f64::from_le_bytes(fixed(b)?))
            }
            Comparator::F16 => {
                let f = |v: &[u8]| Some(f16_to_f32(u16::from_le_bytes(fixed(v)?)));
                f(a)?.partial_cmp(&f(b)?)
            }
            Comparator::BigEndianSigned => {
                let v = |v: &[u8]| crate::logical::be_twos_complement(v);
                Some(v(a)?.cmp(&v(b)?))
            }
            Comparator::Bytes => Some(a.cmp(b)),
            Comparator::SignedBytes => {
                let s = |v: &[u8]| v.iter().map(|&x| x as i8).collect::<Vec<_>>();
                Some(s(a).cmp(&s(b)))
            }
            Comparator::FloatBits => match a.len() {
                4 => Some(i32::from_le_bytes(fixed(a)?).cmp(&i32::from_le_bytes(fixed(b)?))),
                8 => Some(i64::from_le_bytes(fixed(a)?).cmp(&i64::from_le_bytes(fixed(b)?))),
                _ => None,
            },
            Comparator::None => None,
        }
    }

    /// The smallest and largest of `values` in this order, skipping values it cannot place
    /// (NaN). This is how a writer computes the statistics, so a reader can check them.
    pub fn min_max<'a>(
        &self,
        values: impl IntoIterator<Item = &'a [u8]>,
    ) -> Option<(&'a [u8], &'a [u8])> {
        let mut out: Option<(&[u8], &[u8])> = None;
        for v in values {
            if self.compare(v, v).is_none() {
                continue;
            }
            out = Some(match out {
                None => (v, v),
                Some((lo, hi)) => (
                    if self.compare(v, lo) == Some(Ordering::Less) {
                        v
                    } else {
                        lo
                    },
                    if self.compare(v, hi) == Some(Ordering::Greater) {
                        v
                    } else {
                        hi
                    },
                ),
            });
        }
        out
    }
}

/// Which pair of fields the bounds came from.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Source {
    MinMaxValue,
    Deprecated,
}

/// A minimum and a maximum a reader may compare values against.
#[derive(Clone, Debug, PartialEq)]
pub struct Bounds {
    pub min: Vec<u8>,
    pub max: Vec<u8>,
    pub source: Source,
    /// False when the writer shortened the value: the bound holds, but no row has it.
    pub min_exact: bool,
    pub max_exact: bool,
}

/// The bounds a reader may use, or why it may not use any.
///
/// `type_order` is whether the footer's `column_orders` gives this column `TYPE_ORDER`.
pub fn bounds(
    stats: &Statistics,
    comparator: Comparator,
    type_order: bool,
) -> Result<Bounds, String> {
    let is_nan = |v: &[u8]| comparator.compare(v, v).is_none();
    if comparator.order() == SortOrder::Undefined {
        return Err(
            "this type has no defined sort order, so its minimum and maximum mean nothing".into(),
        );
    }
    if let (Some(min), Some(max)) = (&stats.min_value, &stats.max_value) {
        if !type_order {
            return Err("the footer has no column_orders, so the order of min_value and max_value is undefined".into());
        }
        if is_nan(min) || is_nan(max) {
            return Err(
                "a bound is NaN, which writers were never meant to store; ignore both".into(),
            );
        }
        return Ok(Bounds {
            min: min.clone(),
            max: max.clone(),
            source: Source::MinMaxValue,
            min_exact: stats.is_min_value_exact.unwrap_or(true),
            max_exact: stats.is_max_value_exact.unwrap_or(true),
        });
    }
    if let (Some(min), Some(max)) = (&stats.min, &stats.max) {
        // The deprecated fields were computed with signed comparison. That is right only for
        // types whose order is signed and that are not compared as bytes.
        let byte_array = matches!(comparator, Comparator::Bytes | Comparator::BigEndianSigned);
        if comparator.order() != SortOrder::Signed || byte_array {
            return Err(format!(
                "only the deprecated min and max are present, and they were computed with signed \
                 comparison; this column's order is {}",
                comparator.name()
            ));
        }
        if is_nan(min) || is_nan(max) {
            return Err(
                "a bound is NaN, which writers were never meant to store; ignore both".into(),
            );
        }
        return Ok(Bounds {
            min: min.clone(),
            max: max.clone(),
            source: Source::Deprecated,
            min_exact: true,
            max_exact: true,
        });
    }
    Err("the footer records no minimum and maximum for this column chunk".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unsigned_and_signed_disagree_above_two_to_the_31() {
        let big = 3_000_000_000u32.to_le_bytes();
        let small = 7u32.to_le_bytes();
        assert_eq!(
            Comparator::U32.compare(&big, &small),
            Some(Ordering::Greater)
        );
        assert_eq!(Comparator::I32.compare(&big, &small), Some(Ordering::Less));
    }

    #[test]
    fn strings_sort_by_unsigned_bytes() {
        let lodz = "Łódź".as_bytes();
        assert_eq!(
            Comparator::Bytes.compare(b"Leeds", lodz),
            Some(Ordering::Less)
        );
        assert_eq!(
            Comparator::SignedBytes.compare(b"Leeds", lodz),
            Some(Ordering::Greater)
        );
        assert_eq!(
            Comparator::Bytes.compare(b"Oslo", b"Os"),
            Some(Ordering::Greater)
        );
    }

    #[test]
    fn decimals_compare_by_value_and_nan_has_no_place() {
        let minus = (-500i32).to_be_bytes();
        let plus = 1999i32.to_be_bytes();
        assert_eq!(
            Comparator::BigEndianSigned.compare(&minus, &plus),
            Some(Ordering::Less)
        );
        assert_eq!(
            Comparator::Bytes.compare(&minus, &plus),
            Some(Ordering::Greater)
        );
        let nan = f64::NAN.to_le_bytes();
        assert_eq!(Comparator::F64.compare(&nan, &1.0f64.to_le_bytes()), None);
        let vals = [nan, 2.0f64.to_le_bytes(), (-1.0f64).to_le_bytes()];
        let (lo, hi) = Comparator::F64
            .min_max(vals.iter().map(|v| &v[..]))
            .unwrap();
        assert_eq!(
            (
                f64::from_le_bytes(lo.try_into().unwrap()),
                f64::from_le_bytes(hi.try_into().unwrap())
            ),
            (-1.0, 2.0)
        );
    }
}
