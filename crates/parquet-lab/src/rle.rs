//! The RLE / bit-packing hybrid: how Parquet stores small integers (ch04, ch05).
//!
//! Repetition levels, definition levels and dictionary indices are all small integers with a
//! known maximum, so they need only a few bits each. Parquet stores them as a sequence of runs,
//! and each run starts with a ULEB128 header whose lowest bit says what kind of run it is:
//!
//! ```text
//! header & 1 == 0   RLE run:         (header >> 1) copies of one value,
//!                                    stored in ceil(bit_width / 8) bytes, little-endian
//! header & 1 == 1   bit-packed run:  (header >> 1) groups of eight values,
//!                                    each value bit_width bits, least significant bit first
//! ```
//!
//! A writer uses an RLE run where a value repeats and a bit-packed run where values vary. A
//! column with no nulls has definition levels that are all the maximum, and the whole page's
//! levels become one RLE run of a few bytes.
//!
//! This decoder records every run with the bytes of its header and its body, so the browser can
//! show which bytes produced which levels.

use crate::bytes::{ByteReader, BytesError, Span};

/// How many bits it takes to store every integer from 0 to `max`.
///
/// `bit_width(0)` is 0: a column whose maximum level is 0 stores no levels at all.
pub fn bit_width(max: u32) -> u32 {
    32 - max.leading_zeros()
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RunKind {
    Rle,
    BitPacked,
}

impl RunKind {
    pub fn name(&self) -> &'static str {
        match self {
            RunKind::Rle => "RLE",
            RunKind::BitPacked => "bit-packed",
        }
    }
}

/// One run, as decoded.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Run {
    pub kind: RunKind,
    /// The ULEB128 header.
    pub header: Span,
    /// The bytes after the header that hold this run's values.
    pub body: Span,
    /// The values this run contributed. A bit-packed run holds a multiple of eight values, and
    /// the last one in a stream may hold padding past the count; the padding is not included.
    pub values: Vec<u32>,
}

/// Decode `count` values of `bit_width` bits from `bytes`, which start at file offset `base`.
pub fn decode(
    bytes: &[u8],
    base: u64,
    bit_width: u32,
    count: usize,
) -> Result<Vec<Run>, BytesError> {
    let mut r = ByteReader::new(bytes, base);
    let mut runs = Vec::new();
    let mut produced = 0;
    let value_bytes = bit_width.div_ceil(8) as usize;
    while produced < count {
        let header_start = r.offset();
        let header = r.read_uleb128()?;
        let header_span = Span::new(header_start, r.offset());
        let wanted = count - produced;
        let run = if header & 1 == 0 {
            // RLE: one value, repeated.
            let repeat = (header >> 1) as usize;
            let (raw, body) = r.read_bytes(value_bytes)?;
            let mut value = 0u32;
            for (i, b) in raw.iter().enumerate() {
                value |= u32::from(*b) << (8 * i);
            }
            Run {
                kind: RunKind::Rle,
                header: header_span,
                body,
                values: vec![value; repeat.min(wanted)],
            }
        } else {
            // Bit-packed: groups of eight values, packed least significant bit first.
            let groups = (header >> 1) as usize;
            let (raw, body) = r.read_bytes(groups * bit_width as usize)?;
            let total = groups * 8;
            let mut values = Vec::with_capacity(total.min(wanted));
            for i in 0..total.min(wanted) {
                values.push(unpack(raw, i, bit_width));
            }
            Run {
                kind: RunKind::BitPacked,
                header: header_span,
                body,
                values,
            }
        };
        if run.values.is_empty() && run.body.is_empty() {
            // A run that produces nothing and consumes nothing would loop forever.
            return Err(BytesError::UnexpectedEnd {
                offset: header_start,
                wanted: 1,
            });
        }
        produced += run.values.len();
        runs.push(run);
    }
    Ok(runs)
}

/// The `i`th value of `bit_width` bits in a little-endian bit stream.
fn unpack(raw: &[u8], i: usize, bit_width: u32) -> u32 {
    let mut value = 0u32;
    for bit in 0..bit_width as usize {
        let at = i * bit_width as usize + bit;
        if raw[at / 8] >> (at % 8) & 1 == 1 {
            value |= 1 << bit;
        }
    }
    value
}

/// All the values of a sequence of runs, in order.
pub fn values(runs: &[Run]) -> Vec<u32> {
    runs.iter().flat_map(|r| r.values.iter().copied()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bit_width_is_the_bits_needed_for_the_maximum() {
        let widths: Vec<u32> = [0, 1, 2, 3, 4, 7, 8, 255, 256]
            .iter()
            .map(|&m| bit_width(m))
            .collect();
        assert_eq!(widths, [0, 1, 2, 2, 3, 3, 4, 8, 9]);
    }

    #[test]
    fn an_rle_run_repeats_one_value() {
        // header 0x08: RLE (low bit 0), count 4; value 0x01 in one byte.
        let runs = decode(&[0x08, 0x01], 100, 1, 4).unwrap();
        assert_eq!(runs.len(), 1);
        assert_eq!(runs[0].kind, RunKind::Rle);
        assert_eq!(runs[0].values, [1, 1, 1, 1]);
        assert_eq!(runs[0].header, Span::new(100, 101));
        assert_eq!(runs[0].body, Span::new(101, 102));
    }

    #[test]
    fn a_bit_packed_run_packs_least_significant_bit_first() {
        // header 0x03: bit-packed, one group of eight. Width 3: values 0..8 are the example in
        // the Parquet specification, packed into 0x88 0xc6 0xfa.
        let runs = decode(&[0x03, 0x88, 0xc6, 0xfa], 0, 3, 8).unwrap();
        assert_eq!(runs[0].kind, RunKind::BitPacked);
        assert_eq!(runs[0].values, [0, 1, 2, 3, 4, 5, 6, 7]);
    }

    #[test]
    fn padding_past_the_count_is_dropped() {
        let runs = decode(&[0x03, 0x88, 0xc6, 0xfa], 0, 3, 5).unwrap();
        assert_eq!(values(&runs), [0, 1, 2, 3, 4]);
    }

    #[test]
    fn runs_follow_one_another() {
        // RLE: three 2s at width 2, then bit-packed: 1, 0, 3, 2, 0, 0, 0, 0.
        let runs = decode(&[0x06, 0x02, 0x03, 0b1100_0001, 0b0000_0010], 0, 2, 7).unwrap();
        assert_eq!(values(&runs), [2, 2, 2, 1, 0, 0, 3]);
    }

    #[test]
    fn a_stream_that_ends_early_is_an_error() {
        assert!(decode(&[0x03, 0x88], 0, 3, 8).is_err());
        assert!(decode(&[], 0, 1, 1).is_err());
    }
}
