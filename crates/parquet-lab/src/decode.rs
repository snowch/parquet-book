//! Decoding a page's values, whatever their encoding, with a record of how (ch05).
//!
//! Every encoding turns bytes into values differently, but a reader wants the same thing from
//! each: the values, which bytes produced each one, and, for the book, the steps in between. This
//! module is that common shape, and the dispatch from an encoding's name to its decoder.

use crate::bytes::{BytesError, Span};
use crate::delta;
use crate::metadata::PhysicalType;
use crate::plain::{self, PlainValue};
use crate::rle;

/// One step of a decode: a labelled range of bytes and what the decoder read from it.
#[derive(Clone, Debug, PartialEq)]
pub struct Step {
    pub label: String,
    pub span: Span,
    pub detail: String,
}

impl Step {
    pub fn new(label: &str, span: Span, detail: String) -> Step {
        Step {
            label: label.to_string(),
            span,
            detail,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct DecodedValue {
    pub value: PlainValue,
    /// The bytes that hold the value itself: its PLAIN bytes, its dictionary entry, its suffix.
    pub span: Span,
    /// Other bytes it needed: an index run, a length, a prefix length, scattered stream bytes.
    pub extra: Vec<Span>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Decoded {
    pub values: Vec<DecodedValue>,
    pub steps: Vec<Step>,
    /// The first byte after the encoded values.
    pub end: u64,
}

/// A decoded dictionary page: its values, each with the bytes it came from.
pub type Dictionary = Vec<(PlainValue, Span)>;

fn wrong(offset: u64, what: &str) -> Result<Decoded, String> {
    Err(format!("offset {offset}: {what}"))
}

/// Decode `count` values of a column's physical type, encoded with `encoding`.
pub fn values(
    encoding: &str,
    physical: PhysicalType,
    type_length: Option<i64>,
    bytes: &[u8],
    base: u64,
    count: usize,
    dictionary: Option<&Dictionary>,
) -> Result<Decoded, String> {
    let e = |err: BytesError| err.to_string();
    match encoding {
        "PLAIN" => {
            let values = plain::decode(physical, type_length, bytes, base, count).map_err(e)?;
            let end = values.last().map(|(_, s)| s.end).unwrap_or(base);
            let steps = values
                .iter()
                .enumerate()
                .map(|(i, (v, s))| Step::new(&format!("value {i}"), *s, v.to_json().to_json()))
                .collect();
            Ok(Decoded {
                values: values
                    .into_iter()
                    .map(|(value, span)| DecodedValue {
                        value,
                        span,
                        extra: vec![],
                    })
                    .collect(),
                steps,
                end,
            })
        }
        "RLE_DICTIONARY" | "PLAIN_DICTIONARY" => {
            let Some(dict) = dictionary else {
                return wrong(
                    base,
                    "dictionary indices, but no dictionary page came first",
                );
            };
            // One byte of bit width, then the indices as an RLE / bit-packing hybrid with no length.
            let Some(&width) = bytes.first() else {
                return wrong(base, "an empty page where the index bit width should be");
            };
            let runs = rle::decode(&bytes[1..], base + 1, u32::from(width), count).map_err(e)?;
            let mut steps = vec![Step::new(
                "bit width",
                Span::new(base, base + 1),
                format!(
                    "{width} bits per index: enough for {} dictionary entries",
                    dict.len()
                ),
            )];
            let mut values = Vec::with_capacity(count);
            for (n, run) in runs.iter().enumerate() {
                steps.push(Step::new(
                    &format!("run {n}"),
                    Span::new(run.header.start, run.body.end),
                    format!("{}: indices {:?}", run.kind.name(), run.values),
                ));
                for &i in &run.values {
                    let Some((v, s)) = dict.get(i as usize) else {
                        return wrong(
                            run.body.start,
                            &format!("index {i} is past the dictionary's {} entries", dict.len()),
                        );
                    };
                    values.push(DecodedValue {
                        value: v.clone(),
                        span: *s,
                        extra: vec![run.body],
                    });
                }
            }
            let end = runs.last().map(|r| r.body.end).unwrap_or(base + 1);
            Ok(Decoded { values, steps, end })
        }
        "DELTA_BINARY_PACKED" => {
            let delta::Integers {
                values: ints,
                steps,
                end,
            } = delta::binary_packed(bytes, base).map_err(e)?;
            if ints.len() != count {
                return wrong(
                    base,
                    &format!("the header counts {} values, the page {count}", ints.len()),
                );
            }
            let values = ints
                .into_iter()
                .map(|(v, span)| DecodedValue {
                    // An INT32 column's deltas wrap at 32 bits.
                    value: PlainValue::Int(if physical.0 == 1 {
                        i64::from(v as i32)
                    } else {
                        v
                    }),
                    span,
                    extra: vec![],
                })
                .collect();
            Ok(Decoded { values, steps, end })
        }
        "DELTA_LENGTH_BYTE_ARRAY" => delta::length_byte_array(bytes, base).map_err(e),
        "DELTA_BYTE_ARRAY" => delta::byte_array(bytes, base).map_err(e),
        "BYTE_STREAM_SPLIT" => {
            let width = match physical.0 {
                1 | 4 => 4,
                2 | 5 => 8,
                7 => type_length.unwrap_or(0).max(0) as usize,
                _ => return wrong(base, "BYTE_STREAM_SPLIT on a type it does not apply to"),
            };
            let split = delta::byte_stream_split(bytes, base, width, count).map_err(e)?;
            let steps = (0..width)
                .map(|k| {
                    let at = base + (k * count) as u64;
                    Step::new(
                        &format!("stream {k}"),
                        Span::new(at, at + count as u64),
                        format!("byte {k} of every value"),
                    )
                })
                .collect();
            let values = split
                .into_iter()
                .map(|(raw, spans)| DecodedValue {
                    value: match (physical.0, raw.len()) {
                        (4, 4) => PlainValue::Float(f64::from(f32::from_le_bytes(
                            raw[..4].try_into().unwrap(),
                        ))),
                        (5, 8) => {
                            PlainValue::Float(f64::from_le_bytes(raw[..8].try_into().unwrap()))
                        }
                        (1, 4) => PlainValue::Int(i64::from(i32::from_le_bytes(
                            raw[..4].try_into().unwrap(),
                        ))),
                        (2, 8) => PlainValue::Int(i64::from_le_bytes(raw[..8].try_into().unwrap())),
                        _ => PlainValue::Bytes(raw),
                    },
                    span: spans[0],
                    extra: spans[1..].to_vec(),
                })
                .collect();
            Ok(Decoded {
                values,
                steps,
                end: base + (width * count) as u64,
            })
        }
        other => wrong(
            base,
            &format!("the {other} encoding is not implemented by this reader"),
        ),
    }
}
