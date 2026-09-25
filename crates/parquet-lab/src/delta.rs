//! The delta encodings, and BYTE_STREAM_SPLIT (ch05).
//!
//! **DELTA_BINARY_PACKED** stores integers as differences. Sorted or slowly changing values
//! (ids, timestamps, counters) have small differences, and small differences pack into few
//! bits:
//!
//! ```text
//! header:  block size · miniblocks per block · value count · first value (zigzag)
//! block:   min delta (zigzag) · one bit width per miniblock · the miniblocks, bit-packed
//! ```
//!
//! Each block subtracts its smallest delta from every delta, so all of them are zero or more,
//! and each miniblock packs its adjusted deltas in the fewest bits that hold its largest. A run of
//! values one apart has every adjusted delta zero, and bit width zero: the miniblock takes no
//! bytes at all.
//!
//! **DELTA_LENGTH_BYTE_ARRAY** stores every string's length first, delta-packed, then all the
//! bytes back to back. **DELTA_BYTE_ARRAY** stores, for each string, how many leading bytes it
//! shares with the previous one, then only the rest: sorted keys, paths and URLs shrink.
//!
//! **BYTE_STREAM_SPLIT** does not shrink anything. It writes every value's first byte, then
//! every value's second byte, and so on, which puts the slowly varying bytes of floats together
//! for a compressor to find (ch07).

use crate::bytes::{ByteReader, BytesError, Span};
use crate::decode::{Decoded, DecodedValue, Step};
use crate::plain::PlainValue;

/// What DELTA_BINARY_PACKED decodes to: integers with the bytes of their miniblock, the steps
/// that produced them, and the first byte after the encoding.
#[derive(Clone, Debug, PartialEq)]
pub struct Integers {
    pub values: Vec<(i64, Span)>,
    pub steps: Vec<Step>,
    pub end: u64,
}

/// Integers from DELTA_BINARY_PACKED, with the steps that produced them. `count` is how many
/// values the page says it holds; the header says too, and they must agree.
pub fn binary_packed(bytes: &[u8], base: u64) -> Result<Integers, BytesError> {
    let mut r = ByteReader::new(bytes, base);
    let mut steps = Vec::new();
    let start = r.offset();
    let block_size = r.read_uleb128()? as usize;
    let miniblocks = r.read_uleb128()?.max(1) as usize;
    let total = r.read_uleb128()? as usize;
    let first = r.read_zigzag()?;
    steps.push(Step::new(
        "header",
        Span::new(start, r.offset()),
        format!(
            "blocks of {block_size} values in {miniblocks} miniblocks; {total} values; the first is {first}"
        ),
    ));
    let per_miniblock = block_size / miniblocks;
    let mut out = Vec::with_capacity(total);
    if total == 0 {
        return Ok(Integers {
            values: out,
            steps,
            end: r.offset(),
        });
    }
    out.push((first, Span::new(start, r.offset())));
    let mut prev = first;
    let mut block = 0;
    while out.len() < total {
        let block_start = r.offset();
        let min_delta = r.read_zigzag()?;
        let (widths, _) = r.read_bytes(miniblocks)?;
        let widths = widths.to_vec();
        steps.push(Step::new(
            &format!("block {block}"),
            Span::new(block_start, r.offset()),
            format!("smallest delta {min_delta}; bit widths {widths:?}"),
        ));
        for (m, &w) in widths.iter().enumerate() {
            if out.len() >= total {
                break; // Unneeded miniblocks have a width byte and no body.
            }
            let len = per_miniblock * w as usize / 8;
            let (raw, span) = r.read_bytes(len)?;
            let mut deltas = Vec::new();
            for i in 0..per_miniblock {
                if out.len() >= total {
                    break;
                }
                let mut packed: u64 = 0;
                for bit in 0..w as usize {
                    let at = i * w as usize + bit;
                    if raw[at / 8] >> (at % 8) & 1 == 1 {
                        packed |= 1 << bit;
                    }
                }
                let delta = min_delta.wrapping_add(packed as i64);
                prev = prev.wrapping_add(delta);
                deltas.push(delta);
                out.push((prev, span));
            }
            steps.push(Step::new(
                &format!("block {block}, miniblock {m}"),
                span,
                format!("{w} bits per delta; deltas {deltas:?}"),
            ));
        }
        block += 1;
    }
    Ok(Integers {
        values: out,
        steps,
        end: r.offset(),
    })
}

/// DELTA_LENGTH_BYTE_ARRAY: delta-packed lengths, then the bytes of every value in one run.
pub fn length_byte_array(bytes: &[u8], base: u64) -> Result<Decoded, BytesError> {
    let Integers {
        values: lengths,
        mut steps,
        end,
    } = binary_packed(bytes, base)?;
    for s in &mut steps {
        s.label = format!("lengths: {}", s.label);
    }
    let mut r = ByteReader::new(&bytes[(end - base) as usize..], end);
    let mut values = Vec::with_capacity(lengths.len());
    let data_start = r.offset();
    for (len, len_span) in &lengths {
        let (b, span) = r.read_bytes(*len as usize)?;
        values.push(DecodedValue {
            value: PlainValue::Bytes(b.to_vec()),
            span,
            extra: vec![*len_span],
        });
    }
    steps.push(Step::new(
        "bytes",
        Span::new(data_start, r.offset()),
        format!("{} values' bytes, back to back", values.len()),
    ));
    Ok(Decoded {
        values,
        steps,
        end: r.offset(),
    })
}

/// DELTA_BYTE_ARRAY: shared-prefix lengths, then the suffixes as DELTA_LENGTH_BYTE_ARRAY.
pub fn byte_array(bytes: &[u8], base: u64) -> Result<Decoded, BytesError> {
    let Integers {
        values: prefixes,
        mut steps,
        end,
    } = binary_packed(bytes, base)?;
    for s in &mut steps {
        s.label = format!("prefix lengths: {}", s.label);
    }
    let suffixes = length_byte_array(&bytes[(end - base) as usize..], end)?;
    for mut s in suffixes.steps {
        s.label = format!("suffixes: {}", s.label);
        steps.push(s);
    }
    let mut prev: Vec<u8> = Vec::new();
    let mut values = Vec::with_capacity(prefixes.len());
    for ((prefix, prefix_span), suffix) in prefixes.iter().zip(suffixes.values) {
        let PlainValue::Bytes(tail) = &suffix.value else {
            continue;
        };
        let keep = (*prefix as usize).min(prev.len());
        let mut v = prev[..keep].to_vec();
        v.extend_from_slice(tail);
        prev = v.clone();
        let mut extra = vec![*prefix_span];
        extra.extend(suffix.extra);
        values.push(DecodedValue {
            value: PlainValue::Bytes(v),
            span: suffix.span,
            extra,
        });
    }
    Ok(Decoded {
        values,
        steps,
        end: suffixes.end,
    })
}

/// One BYTE_STREAM_SPLIT value: its bytes, and where each of them was, one per stream.
pub type SplitValue = (Vec<u8>, Vec<Span>);

/// BYTE_STREAM_SPLIT: `count` values of `width` bytes, stored as `width` streams of `count`
/// bytes. Value `i`'s byte `k` is at `k * count + i`.
pub fn byte_stream_split(
    bytes: &[u8],
    base: u64,
    width: usize,
    count: usize,
) -> Result<Vec<SplitValue>, BytesError> {
    if bytes.len() < width * count {
        return Err(BytesError::UnexpectedEnd {
            offset: base + bytes.len() as u64,
            wanted: (width * count - bytes.len()) as u64,
        });
    }
    Ok((0..count)
        .map(|i| {
            let value: Vec<u8> = (0..width).map(|k| bytes[k * count + i]).collect();
            let spans = (0..width)
                .map(|k| {
                    let at = base + (k * count + i) as u64;
                    Span::new(at, at + 1)
                })
                .collect();
            (value, spans)
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_constant_step_packs_into_nothing() {
        // Block of 128 in 4 miniblocks, 5 values, first 7 (zigzag 14). One block: min delta 1
        // (zigzag 2), widths 0,0,0,0, and no miniblock bytes at all.
        let bytes = [0x80, 0x01, 0x04, 0x05, 0x0e, 0x02, 0, 0, 0, 0];
        let d = binary_packed(&bytes, 0).unwrap();
        let end = d.end;
        let v: Vec<i64> = d.values.iter().map(|(v, _)| *v).collect();
        assert_eq!(v, [7, 8, 9, 10, 11]);
        assert_eq!(end, 10);
    }

    #[test]
    fn deltas_above_the_minimum_are_bit_packed() {
        // Values 1, 3, 4, 8: deltas 2, 1, 4; min 1; adjusted 1, 0, 3 at 2 bits. A miniblock of 32
        // values at 2 bits is 8 bytes, the first holding 1 | 0<<2 | 3<<4 = 0x31.
        let mut bytes = vec![0x80, 0x01, 0x04, 0x04, 0x02, 0x02, 2, 0, 0, 0, 0x31];
        bytes.extend_from_slice(&[0; 7]);
        let d = binary_packed(&bytes, 0).unwrap();
        let steps = d.steps;
        let v: Vec<i64> = d.values.iter().map(|(v, _)| *v).collect();
        assert_eq!(v, [1, 3, 4, 8]);
        assert!(steps.iter().any(|s| s.detail.contains("deltas [2, 1, 4]")));
    }

    #[test]
    fn byte_stream_split_interleaves_by_byte_position() {
        let v = byte_stream_split(&[1, 2, 10, 20], 0, 2, 2).unwrap();
        assert_eq!(v[0].0, [1, 10]);
        assert_eq!(v[1].0, [2, 20]);
        assert_eq!(v[1].1, [Span::new(1, 2), Span::new(3, 4)]);
    }
}
