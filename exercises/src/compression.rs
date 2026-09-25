//! ch07's problems. Edit this file; `exercises/tests/compression.rs` grades it.

/// Problem 7.1: decompress Snappy.
///
/// `input` is a raw Snappy block, as a SNAPPY page body holds it: a ULEB128 varint giving the
/// output's length, then elements until the input ends. Each element starts with a tag byte
/// whose low two bits say what it is:
///
/// ```text
/// 00  literal: (tag >> 2) + 1 bytes follow. If tag >> 2 is 60, 61, 62 or 63, the length - 1
///     is instead in the next 1, 2, 3 or 4 bytes, little-endian.
/// 01  copy: length 4 + ((tag >> 2) & 7); offset ((tag >> 5) << 8) | the next byte
/// 10  copy: length (tag >> 2) + 1; offset in the next two bytes, little-endian
/// 11  copy: length (tag >> 2) + 1; offset in the next four bytes, little-endian
/// ```
///
/// A copy repeats `length` bytes starting `offset` bytes back from the end of the output so far.
/// The length can be larger than the offset, so copy one byte at a time.
pub fn snappy_decompress(input: &[u8]) -> Result<Vec<u8>, String> {
    let _ = input;
    todo!("problem 7.1")
}

/// Problem 7.2: decompress an LZ4 block (the LZ4_RAW codec).
///
/// `input` is a run of sequences. Each starts with a token byte. Its high four bits are the
/// literal count and its low four bits are the match length minus 4; a value of 15 in either
/// continues in the bytes that follow, each added to it, until one is less than 255. After the
/// token and any literal-count bytes come the literals, then a two-byte little-endian offset,
/// then any match-length bytes. The last sequence ends after its literals, with no offset.
///
/// `size` is the output's length, which the page header gives.
pub fn lz4_raw_decompress(input: &[u8], size: usize) -> Result<Vec<u8>, String> {
    let _ = (input, size);
    todo!("problem 7.2")
}
