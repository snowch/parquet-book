//! Binary primitives: the handful of ways Parquet turns bytes into numbers.
//!
//! Everything else in this crate is built from these. A Parquet file uses three integer
//! encodings, and this module has one function for each:
//!
//! - fixed-width little-endian integers, for the footer length and PLAIN values;
//! - ULEB128 variable-length integers ("varints"), for Thrift lengths and sizes;
//! - zigzag, which maps signed integers onto unsigned ones so small negatives stay small.
//!
//! Every read reports *where* it read from, as a [`Span`] of absolute file offsets. The browser
//! uses those spans to answer the question the book keeps asking: which bytes caused this value?

use std::fmt;

/// A half-open range of absolute file offsets: `start` is included, `end` is not.
///
/// Half-open because lengths then fall out as `end - start`, and two adjacent spans share an
/// endpoint instead of overlapping by one.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Span {
    pub start: u64,
    pub end: u64,
}

impl Span {
    pub fn new(start: u64, end: u64) -> Span {
        assert!(
            start <= end,
            "a span cannot end before it starts: {start}..{end}"
        );
        Span { start, end }
    }

    pub fn len(&self) -> u64 {
        self.end - self.start
    }

    pub fn is_empty(&self) -> bool {
        self.start == self.end
    }

    pub fn contains(&self, other: Span) -> bool {
        self.start <= other.start && other.end <= self.end
    }

    /// The HTTP `Range` header for these bytes. HTTP ranges are inclusive at both ends, so the
    /// last byte is `end - 1`. Getting this wrong by one is the classic range-request bug.
    pub fn http_range(&self) -> String {
        format!("bytes={}-{}", self.start, self.end - 1)
    }
}

impl fmt::Display for Span {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}, {})", self.start, self.end)
    }
}

/// What went wrong while reading bytes, and where.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BytesError {
    /// Asked for `wanted` bytes at `offset`, but the buffer ends first.
    UnexpectedEnd { offset: u64, wanted: u64 },
    /// A varint ran past the width of the integer it encodes.
    VarintTooLong { offset: u64 },
}

impl fmt::Display for BytesError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            BytesError::UnexpectedEnd { offset, wanted } => {
                write!(
                    f,
                    "needed {wanted} more byte(s) at offset {offset}, but the data ends"
                )
            }
            BytesError::VarintTooLong { offset } => {
                write!(
                    f,
                    "varint starting at offset {offset} is longer than 10 bytes"
                )
            }
        }
    }
}

impl std::error::Error for BytesError {}

/// Read `bytes` as an unsigned little-endian integer: the first byte is the least significant.
///
/// `[0x7c, 0x01, 0x00, 0x00]` is `0x7c + 0x01 × 256 = 380`.
pub fn read_le_u32(bytes: [u8; 4]) -> u32 {
    u32::from(bytes[0])
        | u32::from(bytes[1]) << 8
        | u32::from(bytes[2]) << 16
        | u32::from(bytes[3]) << 24
}

/// Each byte of a little-endian integer with the weight it is multiplied by.
///
/// The sum of `byte × weight` over the terms is the value. The browser prints this so the
/// arithmetic behind a decoded length is on the screen, not just its answer.
pub fn le_terms(bytes: &[u8]) -> Vec<(u8, u64)> {
    bytes
        .iter()
        .enumerate()
        .map(|(i, &b)| (b, 1u64 << (8 * i)))
        .collect()
}

/// Map an unsigned zigzag value back to the signed integer it encodes.
///
/// Zigzag interleaves the signed integers: 0, -1, 1, -2, 2 … become 0, 1, 2, 3, 4 …. A small
/// negative number therefore stays a small varint instead of becoming a huge two's-complement
/// one.
pub fn zigzag_decode(n: u64) -> i64 {
    ((n >> 1) as i64) ^ -((n & 1) as i64)
}

/// The CRC-32 checksum of `bytes`: the IEEE polynomial, as zlib and Ethernet compute it.
///
/// Parquet page headers may carry one over the page body, so a reader can tell a damaged page
/// from a page whose values happen to look odd. Computed a bit at a time: slower than a table,
/// and short enough to read.
pub fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for &b in bytes {
        crc ^= u32::from(b);
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xedb8_8320 & mask);
        }
    }
    !crc
}

/// A cursor over a slice of bytes that knows the absolute file offset of its first byte.
///
/// The footer arrives as a separate buffer from the rest of the file, but every span this
/// reader reports is an offset into the *file*. `base` is what makes those agree.
#[derive(Clone, Debug)]
pub struct ByteReader<'a> {
    data: &'a [u8],
    base: u64,
    pos: usize,
}

impl<'a> ByteReader<'a> {
    /// A reader over `data`, whose first byte is at file offset `base`.
    pub fn new(data: &'a [u8], base: u64) -> ByteReader<'a> {
        ByteReader { data, base, pos: 0 }
    }

    /// The absolute file offset of the next byte to be read.
    pub fn offset(&self) -> u64 {
        self.base + self.pos as u64
    }

    pub fn remaining(&self) -> usize {
        self.data.len() - self.pos
    }

    pub fn is_at_end(&self) -> bool {
        self.pos == self.data.len()
    }

    pub fn read_u8(&mut self) -> Result<u8, BytesError> {
        let b = *self.data.get(self.pos).ok_or(BytesError::UnexpectedEnd {
            offset: self.offset(),
            wanted: 1,
        })?;
        self.pos += 1;
        Ok(b)
    }

    /// Take the next `n` bytes, and the span they came from.
    pub fn read_bytes(&mut self, n: usize) -> Result<(&'a [u8], Span), BytesError> {
        if self.remaining() < n {
            return Err(BytesError::UnexpectedEnd {
                offset: self.offset(),
                wanted: n as u64,
            });
        }
        let start = self.offset();
        let slice = &self.data[self.pos..self.pos + n];
        self.pos += n;
        Ok((slice, Span::new(start, start + n as u64)))
    }

    pub fn read_le_u32(&mut self) -> Result<u32, BytesError> {
        let (b, _) = self.read_bytes(4)?;
        Ok(read_le_u32([b[0], b[1], b[2], b[3]]))
    }

    pub fn read_le_u64(&mut self) -> Result<u64, BytesError> {
        let (b, _) = self.read_bytes(8)?;
        Ok(u64::from_le_bytes([
            b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
        ]))
    }

    /// Read an unsigned LEB128 varint: seven bits of value per byte, least significant group
    /// first, and the high bit set on every byte except the last.
    ///
    /// `0x96 0x01` is `0x16 + (0x01 << 7) = 150`.
    pub fn read_uleb128(&mut self) -> Result<u64, BytesError> {
        let start = self.offset();
        let mut value: u64 = 0;
        for i in 0..10 {
            let byte = self.read_u8()?;
            value |= u64::from(byte & 0x7f) << (7 * i);
            if byte & 0x80 == 0 {
                return Ok(value);
            }
        }
        Err(BytesError::VarintTooLong { offset: start })
    }

    /// A zigzag varint: how Thrift's compact protocol writes every signed integer.
    pub fn read_zigzag(&mut self) -> Result<i64, BytesError> {
        Ok(zigzag_decode(self.read_uleb128()?))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn little_endian_puts_the_least_significant_byte_first() {
        assert_eq!(read_le_u32([0x7c, 0x01, 0x00, 0x00]), 380);
        assert_eq!(read_le_u32([0x00, 0x00, 0x00, 0x01]), 1 << 24);
    }

    #[test]
    fn le_terms_sum_to_the_value() {
        let bytes = [0x7c, 0x01, 0x00, 0x00];
        let sum: u64 = le_terms(&bytes)
            .iter()
            .map(|&(b, w)| u64::from(b) * w)
            .sum();
        assert_eq!(sum, u64::from(read_le_u32(bytes)));
    }

    #[test]
    fn zigzag_interleaves_the_signed_integers() {
        let decoded: Vec<i64> = (0..6).map(zigzag_decode).collect();
        assert_eq!(decoded, [0, -1, 1, -2, 2, -3]);
        assert_eq!(zigzag_decode(u64::MAX), i64::MIN);
    }

    #[test]
    fn uleb128_reads_seven_bits_per_byte() {
        let mut r = ByteReader::new(&[0x96, 0x01, 0x05], 100);
        assert_eq!(r.read_uleb128().unwrap(), 150);
        assert_eq!(r.offset(), 102);
        assert_eq!(r.read_uleb128().unwrap(), 5);
        assert!(r.is_at_end());
    }

    #[test]
    fn a_varint_that_never_ends_is_an_error_not_a_panic() {
        let mut r = ByteReader::new(&[0xff; 11], 0);
        assert_eq!(
            r.read_uleb128(),
            Err(BytesError::VarintTooLong { offset: 0 })
        );
        let mut r = ByteReader::new(&[0x80, 0x80], 7);
        assert_eq!(
            r.read_uleb128(),
            Err(BytesError::UnexpectedEnd {
                offset: 9,
                wanted: 1
            })
        );
    }

    #[test]
    fn crc32_matches_the_standard_check_value() {
        // The check value every CRC-32 implementation is tested against.
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
        assert_eq!(crc32(b""), 0);
    }

    #[test]
    fn spans_are_absolute_file_offsets() {
        let mut r = ByteReader::new(b"abcdef", 1000);
        r.read_u8().unwrap();
        let (bytes, span) = r.read_bytes(3).unwrap();
        assert_eq!(bytes, b"bcd");
        assert_eq!(span, Span::new(1001, 1004));
        assert_eq!(span.http_range(), "bytes=1001-1003");
    }
}
