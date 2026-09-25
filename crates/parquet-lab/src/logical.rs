//! Logical types: what the bytes of a physical type mean (ch03).
//!
//! Parquet stores every value as one of eight physical types, which say only how many bytes a
//! value takes and in what order. A logical type, recorded beside the physical type in the
//! schema, says how to read those bytes as something a person means: a date, a decimal, a
//! string, an unsigned integer.
//!
//! The same four bytes can be three different values:
//!
//! ```text
//! e8 4f 00 00   INT32                       20456
//!               INT32 + DATE                2026-01-03
//!               INT32 + INTEGER(16, false)  20456
//! ```
//!
//! This module decodes the logical type from the footer, and applies it to a value's bytes.

use std::fmt;

use crate::metadata::PhysicalType;
use crate::thrift::{Node, Value};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TimeUnit {
    Millis,
    Micros,
    Nanos,
}

impl TimeUnit {
    /// How many of this unit make one second.
    pub fn per_second(&self) -> i64 {
        match self {
            TimeUnit::Millis => 1_000,
            TimeUnit::Micros => 1_000_000,
            TimeUnit::Nanos => 1_000_000_000,
        }
    }
}

/// The `LogicalType` union from `parquet.thrift`, with its parameters.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LogicalType {
    String,
    Map,
    List,
    Enum,
    Decimal {
        scale: i64,
        precision: i64,
    },
    Date,
    Time {
        utc: bool,
        unit: Option<TimeUnit>,
    },
    Timestamp {
        utc: bool,
        unit: Option<TimeUnit>,
    },
    Integer {
        bit_width: i64,
        signed: bool,
    },
    Unknown,
    Json,
    Bson,
    Uuid,
    Float16,
    Variant,
    Geometry,
    Geography,
    /// A union member this reader does not know, by field id.
    Other(i16),
}

impl fmt::Display for LogicalType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let unit = |u: &Option<TimeUnit>| match u {
            Some(TimeUnit::Millis) => "MILLIS",
            Some(TimeUnit::Micros) => "MICROS",
            Some(TimeUnit::Nanos) => "NANOS",
            None => "?",
        };
        match self {
            LogicalType::String => write!(f, "STRING"),
            LogicalType::Map => write!(f, "MAP"),
            LogicalType::List => write!(f, "LIST"),
            LogicalType::Enum => write!(f, "ENUM"),
            LogicalType::Decimal { scale, precision } => write!(f, "DECIMAL({precision}, {scale})"),
            LogicalType::Date => write!(f, "DATE"),
            LogicalType::Time { utc, unit: u } => {
                write!(
                    f,
                    "TIME({}, {})",
                    unit(u),
                    if *utc { "UTC" } else { "local" }
                )
            }
            LogicalType::Timestamp { utc, unit: u } => {
                write!(
                    f,
                    "TIMESTAMP({}, {})",
                    unit(u),
                    if *utc { "UTC" } else { "local" }
                )
            }
            LogicalType::Integer { bit_width, signed } => write!(
                f,
                "INTEGER({bit_width}, {})",
                if *signed { "signed" } else { "unsigned" }
            ),
            LogicalType::Unknown => write!(f, "UNKNOWN"),
            LogicalType::Json => write!(f, "JSON"),
            LogicalType::Bson => write!(f, "BSON"),
            LogicalType::Uuid => write!(f, "UUID"),
            LogicalType::Float16 => write!(f, "FLOAT16"),
            LogicalType::Variant => write!(f, "VARIANT"),
            LogicalType::Geometry => write!(f, "GEOMETRY"),
            LogicalType::Geography => write!(f, "GEOGRAPHY"),
            LogicalType::Other(id) => write!(f, "logical type {id}"),
        }
    }
}

fn int_field(s: &crate::thrift::Struct, id: i16) -> Option<i64> {
    match s.field(id)?.node.value {
        Value::Int(v) => Some(v),
        _ => None,
    }
}

fn bool_field(s: &crate::thrift::Struct, id: i16) -> Option<bool> {
    match s.field(id)?.node.value {
        Value::Bool(v) => Some(v),
        _ => None,
    }
}

/// Decode a `LogicalType` union: exactly one field is set, and its id says which type it is.
pub fn decode(node: &Node) -> Option<LogicalType> {
    let Value::Struct(union) = &node.value else {
        return None;
    };
    let member = union.fields.first()?;
    let inner = match &member.node.value {
        Value::Struct(s) => Some(s),
        _ => None,
    };
    let time_unit = |s: &crate::thrift::Struct| -> Option<TimeUnit> {
        let Value::Struct(u) = &s.field(2)?.node.value else {
            return None;
        };
        match u.fields.first()?.id {
            1 => Some(TimeUnit::Millis),
            2 => Some(TimeUnit::Micros),
            3 => Some(TimeUnit::Nanos),
            _ => None,
        }
    };
    Some(match member.id {
        1 => LogicalType::String,
        2 => LogicalType::Map,
        3 => LogicalType::List,
        4 => LogicalType::Enum,
        5 => LogicalType::Decimal {
            scale: inner.and_then(|s| int_field(s, 1)).unwrap_or(0),
            precision: inner.and_then(|s| int_field(s, 2)).unwrap_or(0),
        },
        6 => LogicalType::Date,
        7 => LogicalType::Time {
            utc: inner.and_then(|s| bool_field(s, 1)).unwrap_or(false),
            unit: inner.and_then(time_unit),
        },
        8 => LogicalType::Timestamp {
            utc: inner.and_then(|s| bool_field(s, 1)).unwrap_or(false),
            unit: inner.and_then(time_unit),
        },
        10 => LogicalType::Integer {
            bit_width: inner.and_then(|s| int_field(s, 1)).unwrap_or(0),
            signed: inner.and_then(|s| bool_field(s, 2)).unwrap_or(true),
        },
        11 => LogicalType::Unknown,
        12 => LogicalType::Json,
        13 => LogicalType::Bson,
        14 => LogicalType::Uuid,
        15 => LogicalType::Float16,
        16 => LogicalType::Variant,
        17 => LogicalType::Geometry,
        18 => LogicalType::Geography,
        other => LogicalType::Other(other),
    })
}

/// The date `days` after 1970-01-01, as `YYYY-MM-DD`.
///
/// Howard Hinnant's `civil_from_days`: shift the epoch to 0000-03-01 so leap days fall at the
/// end of a year, split into 400-year eras, and read off year, month and day.
pub fn date_from_days(days: i64) -> String {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02}")
}

/// A count of `unit` since midnight, as `HH:MM:SS` with a fraction when there is one.
fn time_of_day(ticks: i64, unit: TimeUnit) -> String {
    let per = unit.per_second();
    let secs = ticks.div_euclid(per);
    let frac = ticks.rem_euclid(per);
    let (h, m, s) = (secs / 3600, (secs / 60) % 60, secs % 60);
    let digits = match unit {
        TimeUnit::Millis => 3,
        TimeUnit::Micros => 6,
        TimeUnit::Nanos => 9,
    };
    if frac == 0 {
        format!("{h:02}:{m:02}:{s:02}")
    } else {
        format!("{h:02}:{m:02}:{s:02}.{frac:0digits$}")
    }
}

/// A timestamp: `ticks` of `unit` since 1970-01-01T00:00:00.
///
/// `utc` is `isAdjustedToUTC`. True means an instant, shown with a `Z`. False means a wall-clock
/// reading with no zone: the same digits, but no claim about which instant they name.
pub fn timestamp(ticks: i64, unit: TimeUnit, utc: bool) -> String {
    let per_day = unit.per_second() * 86_400;
    let days = ticks.div_euclid(per_day);
    let rest = ticks.rem_euclid(per_day);
    format!(
        "{}T{}{}",
        date_from_days(days),
        time_of_day(rest, unit),
        if utc { "Z" } else { "" }
    )
}

/// An unscaled integer and a scale, as a decimal string: `(12345, 2)` is `123.45`.
pub fn decimal(unscaled: i128, scale: i64) -> String {
    if scale <= 0 {
        return (unscaled * 10i128.pow((-scale) as u32)).to_string();
    }
    let digits = unscaled.unsigned_abs().to_string();
    let scale = scale as usize;
    let padded = format!("{digits:0>width$}", width = scale + 1);
    let (int, frac) = padded.split_at(padded.len() - scale);
    format!("{}{int}.{frac}", if unscaled < 0 { "-" } else { "" })
}

/// A big-endian two's-complement integer, of any length up to 16 bytes.
///
/// Decimals stored as `FIXED_LEN_BYTE_ARRAY` or `BYTE_ARRAY` use this, and they are the one place
/// Parquet puts the most significant byte first. Everything else is little-endian.
pub fn be_twos_complement(bytes: &[u8]) -> Option<i128> {
    if bytes.is_empty() || bytes.len() > 16 {
        return None;
    }
    let negative = bytes[0] & 0x80 != 0;
    let mut v: i128 = if negative { -1 } else { 0 };
    for &b in bytes {
        v = (v << 8) | i128::from(b);
    }
    Some(v)
}

/// A half-precision float's bits as an `f32`.
fn f16_to_f32(bits: u16) -> f32 {
    let sign = if bits & 0x8000 != 0 { -1.0 } else { 1.0 };
    let exp = i32::from((bits >> 10) & 0x1f);
    let frac = f32::from(bits & 0x3ff);
    match exp {
        0 => sign * frac * 2f32.powi(-24),
        31 if frac == 0.0 => sign * f32::INFINITY,
        31 => f32::NAN,
        e => sign * (1.0 + frac / 1024.0) * 2f32.powi(e - 15),
    }
}

/// One PLAIN-encoded value, read through its logical type. `None` when the bytes do not fit, or
/// when the logical type adds nothing to the physical reading.
///
/// A PLAIN statistics value has no length prefix, so a `BYTE_ARRAY` value here is the bare bytes.
pub fn interpret(physical: PhysicalType, logical: &LogicalType, bytes: &[u8]) -> Option<String> {
    let le_i32 = || bytes.try_into().ok().map(i32::from_le_bytes);
    let le_i64 = || bytes.try_into().ok().map(i64::from_le_bytes);
    match (physical.0, logical) {
        (1, LogicalType::Date) => le_i32().map(|d| date_from_days(i64::from(d))),
        (1, LogicalType::Integer { signed: false, .. }) => le_i32().map(|v| (v as u32).to_string()),
        (2, LogicalType::Integer { signed: false, .. }) => le_i64().map(|v| (v as u64).to_string()),
        (1, LogicalType::Integer { signed: true, .. }) => le_i32().map(|v| v.to_string()),
        (2, LogicalType::Integer { signed: true, .. }) => le_i64().map(|v| v.to_string()),
        (2, LogicalType::Timestamp { utc, unit: Some(u) }) => {
            le_i64().map(|t| timestamp(t, *u, *utc))
        }
        (1 | 2, LogicalType::Time { unit: Some(u), .. }) => {
            let t = if physical.0 == 1 {
                le_i32().map(i64::from)
            } else {
                le_i64()
            }?;
            Some(time_of_day(t, *u))
        }
        (1, LogicalType::Decimal { scale, .. }) => le_i32().map(|v| decimal(i128::from(v), *scale)),
        (2, LogicalType::Decimal { scale, .. }) => le_i64().map(|v| decimal(i128::from(v), *scale)),
        (6 | 7, LogicalType::Decimal { scale, .. }) => {
            be_twos_complement(bytes).map(|v| decimal(v, *scale))
        }
        (6 | 7, LogicalType::String | LogicalType::Enum | LogicalType::Json) => {
            std::str::from_utf8(bytes).ok().map(|s| format!("{s:?}"))
        }
        (7, LogicalType::Float16) if bytes.len() == 2 => {
            Some(f16_to_f32(u16::from_le_bytes([bytes[0], bytes[1]])).to_string())
        }
        (7, LogicalType::Uuid) if bytes.len() == 16 => {
            let h: Vec<String> = bytes.iter().map(|b| format!("{b:02x}")).collect();
            Some(format!(
                "{}-{}-{}-{}-{}",
                h[..4].concat(),
                h[4..6].concat(),
                h[6..8].concat(),
                h[8..10].concat(),
                h[10..].concat()
            ))
        }
        _ => None,
    }
}

/// A decoded value as JSON, read through its logical type when it has one.
///
/// Numbers without a logical type stay numbers. A value a logical type changes (a date, a
/// timestamp, a decimal, an unsigned integer) becomes the string `interpret` produces.
pub fn value_json(
    physical: PhysicalType,
    logical: Option<&LogicalType>,
    value: &crate::plain::PlainValue,
) -> crate::json::Json {
    use crate::json::Json;
    use crate::plain::PlainValue;
    let raw = match (physical.0, value) {
        (1, PlainValue::Int(v)) => (*v as i32).to_le_bytes().to_vec(),
        (2, PlainValue::Int(v)) => v.to_le_bytes().to_vec(),
        (_, PlainValue::Bytes(b)) => b.clone(),
        _ => return value.to_json(),
    };
    match logical {
        Some(LogicalType::String | LogicalType::Enum | LogicalType::Json) => value.to_json(),
        Some(LogicalType::Integer { signed: true, .. }) => value.to_json(),
        Some(LogicalType::Integer { signed: false, .. }) => {
            match interpret(physical, logical.unwrap(), &raw) {
                Some(s) => s.parse::<u64>().map(Json::UInt).unwrap_or(Json::Str(s)),
                None => value.to_json(),
            }
        }
        Some(l) => interpret(physical, l, &raw)
            .map(Json::Str)
            .unwrap_or_else(|| value.to_json()),
        None => value.to_json(),
    }
}

/// An `INT96` value: eight bytes of nanoseconds within the day, then a four-byte Julian day.
///
/// Deprecated, and still written by some engines. It has no logical type: the convention lives
/// outside the specification, which is why it caused so many time-zone bugs.
pub fn int96_timestamp(bytes: &[u8]) -> Option<String> {
    let b: [u8; 12] = bytes.try_into().ok()?;
    let nanos = i64::from_le_bytes(b[..8].try_into().ok()?);
    let julian = i64::from(i32::from_le_bytes(b[8..].try_into().ok()?));
    // Julian day 2440588 is 1970-01-01.
    let days = julian - 2_440_588;
    Some(timestamp(
        days * 86_400 * 1_000_000_000 + nanos,
        TimeUnit::Nanos,
        false,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn day_numbers_are_dates() {
        assert_eq!(date_from_days(0), "1970-01-01");
        assert_eq!(date_from_days(20456), "2026-01-03");
        assert_eq!(date_from_days(-1), "1969-12-31");
        assert_eq!(date_from_days(11016), "2000-02-29");
    }

    #[test]
    fn timestamps_keep_their_unit_and_their_zone() {
        assert_eq!(timestamp(0, TimeUnit::Micros, true), "1970-01-01T00:00:00Z");
        assert_eq!(
            timestamp(1_767_432_600_000_000, TimeUnit::Micros, true),
            "2026-01-03T09:30:00Z"
        );
        assert_eq!(
            timestamp(1_500, TimeUnit::Millis, false),
            "1970-01-01T00:00:01.500"
        );
        assert_eq!(
            timestamp(-1, TimeUnit::Nanos, true),
            "1969-12-31T23:59:59.999999999Z"
        );
    }

    #[test]
    fn decimals_put_the_point_where_the_scale_says() {
        assert_eq!(decimal(12345, 2), "123.45");
        assert_eq!(decimal(-5, 2), "-0.05");
        assert_eq!(decimal(500, 2), "5.00");
        assert_eq!(decimal(7, 0), "7");
        assert_eq!(decimal(7, -2), "700");
    }

    #[test]
    fn decimal_bytes_are_big_endian_twos_complement() {
        assert_eq!(be_twos_complement(&[0x00, 0x00, 0x07, 0xcf]), Some(1999));
        assert_eq!(be_twos_complement(&[0xff, 0xff]), Some(-1));
        assert_eq!(be_twos_complement(&[0x80]), Some(-128));
        assert_eq!(be_twos_complement(&[]), None);
    }

    #[test]
    fn the_same_bytes_mean_what_the_logical_type_says() {
        let bytes = 20456i32.to_le_bytes();
        let int32 = PhysicalType(1);
        assert_eq!(
            interpret(int32, &LogicalType::Date, &bytes).as_deref(),
            Some("2026-01-03")
        );
        let neg = (-1i32).to_le_bytes();
        let unsigned = LogicalType::Integer {
            bit_width: 32,
            signed: false,
        };
        assert_eq!(
            interpret(int32, &unsigned, &neg).as_deref(),
            Some("4294967295")
        );
        let dec = LogicalType::Decimal {
            scale: 2,
            precision: 9,
        };
        assert_eq!(
            interpret(PhysicalType(7), &dec, &[0, 0, 0x01, 0xf4]).as_deref(),
            Some("5.00")
        );
    }

    #[test]
    fn half_floats_decode() {
        assert_eq!(f16_to_f32(0x3c00), 1.0);
        assert_eq!(f16_to_f32(0xc000), -2.0);
        assert_eq!(f16_to_f32(0x3555), 0.333_251_95);
    }

    #[test]
    fn int96_is_nanoseconds_and_a_julian_day() {
        let mut b = Vec::new();
        b.extend_from_slice(&(3_600_000_000_000i64).to_le_bytes());
        b.extend_from_slice(&2_440_589i32.to_le_bytes());
        assert_eq!(int96_timestamp(&b).as_deref(), Some("1970-01-02T01:00:00"));
    }
}
