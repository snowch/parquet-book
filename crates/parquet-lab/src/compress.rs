//! Compression: turning a page's compressed bytes back into its encoded bytes (ch07).
//!
//! A writer encodes a page's values first ([`crate::decode`] reads encodings), then hands the
//! encoded bytes to a general-purpose compressor. The column chunk's metadata names the codec,
//! and every page header gives both sizes, so a reader knows how large the output will be before
//! it starts.
//!
//! Three codecs are decoded here, each small enough to read in full:
//!
//! - **SNAPPY**, raw Snappy: literals and back-references, byte-aligned.
//! - **LZ4_RAW**, an LZ4 block: the same idea with a different layout.
//! - **GZIP**, a gzip member around a DEFLATE stream: back-references too, but written with
//!   Huffman codes, so the tokens are bit-aligned.
//!
//! ZSTD and BROTLI are not decoded. Each needs a decoder several times the size of all three
//! above together, and neither would teach more than DEFLATE does. A file that uses them still
//! opens, its sizes are still read from the footer, and a page that needs decompressing is
//! reported as one this reader cannot decompress.
//!
//! Every decoder records what it did as [`Token`]s: which compressed bytes it read, which output
//! bytes it wrote, and, for a back-reference, where in the output it copied them from. The
//! laboratory steps through them.

use crate::bytes::{crc32, Span};

/// What one step of a decompressor did.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TokenKind {
    /// Bytes that describe the stream rather than hold data: a length, a header, a checksum.
    Header,
    /// Output bytes copied from the input as they are.
    Literal,
    /// Output bytes copied from earlier in the output: `distance` bytes back.
    Copy { distance: u64 },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Token {
    pub kind: TokenKind,
    pub label: String,
    /// The compressed bytes it read. For GZIP, whose codes are bit-aligned, the bytes that hold
    /// those bits.
    pub input: Span,
    /// The output bytes it wrote, as offsets into the decompressed page.
    pub output: Span,
    pub detail: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decompressed {
    pub bytes: Vec<u8>,
    pub tokens: Vec<Token>,
}

/// Whether [`decompress`] can decode a codec.
pub fn supported(codec: &str) -> bool {
    matches!(codec, "UNCOMPRESSED" | "SNAPPY" | "LZ4_RAW" | "GZIP")
}

/// Decompress `input`, which starts at file offset `base`, into exactly `size` bytes.
pub fn decompress(
    codec: &str,
    input: &[u8],
    base: u64,
    size: usize,
) -> Result<Decompressed, String> {
    let out = match codec {
        "UNCOMPRESSED" => Decompressed {
            bytes: input.to_vec(),
            tokens: vec![Token {
                kind: TokenKind::Literal,
                label: "stored".into(),
                input: Span::new(base, base + input.len() as u64),
                output: Span::new(0, input.len() as u64),
                detail: "not compressed".into(),
            }],
        },
        "SNAPPY" => snappy(input, base)?,
        "LZ4_RAW" => lz4_raw(input, base, size)?,
        "GZIP" => gzip(input, base)?,
        other => {
            return Err(format!(
                "this reader does not decompress {other}; it reads {other} files' sizes from the \
                 footer, but not their pages"
            ))
        }
    };
    if out.bytes.len() != size {
        return Err(format!(
            "{codec}: the page header says {size} bytes, and decompressing gave {}",
            out.bytes.len()
        ));
    }
    Ok(out)
}

/// Copy `len` bytes from `distance` bytes back in `out`. The source may overlap the bytes being
/// written: a distance of one repeats the last byte `len` times. So the copy is byte by byte.
fn copy_back(out: &mut Vec<u8>, distance: usize, len: usize) -> Result<(), String> {
    if distance == 0 || distance > out.len() {
        return Err(format!(
            "a copy reaches {distance} bytes back, and only {} bytes have been written",
            out.len()
        ));
    }
    let from = out.len() - distance;
    for i in 0..len {
        out.push(out[from + i]);
    }
    Ok(())
}

/// "1 byte", "2 bytes".
fn n_bytes(n: usize) -> String {
    if n == 1 {
        "1 byte".into()
    } else {
        format!("{n} bytes")
    }
}

fn span(base: u64, start: usize, end: usize) -> Span {
    Span::new(base + start as u64, base + end as u64)
}

fn get(input: &[u8], at: usize) -> Result<u8, String> {
    input
        .get(at)
        .copied()
        .ok_or_else(|| format!("the compressed bytes end at offset {at}, mid-token"))
}

/// Little-endian, `n` bytes.
fn le(input: &[u8], at: usize, n: usize) -> Result<usize, String> {
    let mut v = 0usize;
    for i in 0..n {
        v |= (get(input, at + i)? as usize) << (8 * i);
    }
    Ok(v)
}

/// Raw Snappy: a varint giving the output length, then elements. Each element starts with a tag
/// byte whose low two bits say what it is:
///
/// ```text
/// 00  literal             length - 1 in the tag's top six bits; 60..63 mean "in the next 1..4 bytes"
/// 01  copy, 1-byte offset length 4..11 in three bits, offset in three bits and the next byte
/// 10  copy, 2-byte offset length 1..64 in the top six bits, offset in the next two bytes
/// 11  copy, 4-byte offset length 1..64 in the top six bits, offset in the next four bytes
/// ```
pub fn snappy(input: &[u8], base: u64) -> Result<Decompressed, String> {
    let mut tokens = Vec::new();
    let (mut size, mut shift, mut i) = (0usize, 0, 0);
    loop {
        let b = get(input, i)?;
        i += 1;
        size |= ((b & 0x7f) as usize) << shift;
        shift += 7;
        if b & 0x80 == 0 {
            break;
        }
    }
    tokens.push(Token {
        kind: TokenKind::Header,
        label: "length".into(),
        input: span(base, 0, i),
        output: Span::new(0, 0),
        detail: format!("varint: the output is {size} bytes"),
    });
    let mut out = Vec::with_capacity(size);
    while i < input.len() {
        let start = i;
        let tag = input[i];
        i += 1;
        let at = out.len() as u64;
        match tag & 0b11 {
            0b00 => {
                let mut len = (tag >> 2) as usize;
                if len >= 60 {
                    let extra = len - 59;
                    len = le(input, i, extra)?;
                    i += extra;
                }
                len += 1;
                let bytes = input
                    .get(i..i + len)
                    .ok_or("a literal runs past the end of the compressed bytes")?;
                out.extend_from_slice(bytes);
                i += len;
                tokens.push(Token {
                    kind: TokenKind::Literal,
                    label: "literal".into(),
                    input: span(base, start, i),
                    output: Span::new(at, out.len() as u64),
                    detail: format!("tag {tag:02x}: a literal, the next {}", n_bytes(len)),
                });
            }
            kind => {
                let (len, distance) = match kind {
                    0b01 => {
                        let len = 4 + ((tag >> 2) & 0b111) as usize;
                        let distance = (((tag >> 5) as usize) << 8) | get(input, i)? as usize;
                        i += 1;
                        (len, distance)
                    }
                    0b10 => {
                        let d = le(input, i, 2)?;
                        i += 2;
                        (1 + (tag >> 2) as usize, d)
                    }
                    _ => {
                        let d = le(input, i, 4)?;
                        i += 4;
                        (1 + (tag >> 2) as usize, d)
                    }
                };
                copy_back(&mut out, distance, len)?;
                tokens.push(Token {
                    kind: TokenKind::Copy {
                        distance: distance as u64,
                    },
                    label: "copy".into(),
                    input: span(base, start, i),
                    output: Span::new(at, out.len() as u64),
                    detail: format!("tag {tag:02x}: copy {} from {distance} back", n_bytes(len)),
                });
            }
        }
    }
    if out.len() != size {
        return Err(format!(
            "Snappy promised {size} bytes and its elements wrote {}",
            out.len()
        ));
    }
    Ok(Decompressed { bytes: out, tokens })
}

/// An LZ4 block: a run of sequences, each some literals and then one match.
///
/// ```text
/// token      literal length in the high four bits, match length - 4 in the low four;
///            15 in either means "add the bytes that follow, until one is not 255"
/// literals
/// offset     two bytes, little-endian: how far back the match starts
/// ```
///
/// The last sequence has literals and no match: the block ends after them.
pub fn lz4_raw(input: &[u8], base: u64, size: usize) -> Result<Decompressed, String> {
    let mut tokens = Vec::new();
    let mut out = Vec::with_capacity(size);
    let mut i = 0;
    // A length of 15 continues in the bytes that follow, each added until one is not 255.
    let more = |i: &mut usize, mut n: usize| -> Result<usize, String> {
        if n == 15 {
            loop {
                let b = get(input, *i)?;
                *i += 1;
                n += b as usize;
                if b != 255 {
                    break;
                }
            }
        }
        Ok(n)
    };
    while i < input.len() {
        let start = i;
        let token = input[i];
        i += 1;
        let literals = more(&mut i, (token >> 4) as usize)?;
        let at = out.len() as u64;
        let bytes = input
            .get(i..i + literals)
            .ok_or("literals run past the end of the compressed bytes")?;
        out.extend_from_slice(bytes);
        i += literals;
        tokens.push(Token {
            kind: TokenKind::Literal,
            label: "literals".into(),
            input: span(base, start, i),
            output: Span::new(at, out.len() as u64),
            detail: format!(
                "token {token:02x}: a literal, the next {}",
                n_bytes(literals)
            ),
        });
        if i == input.len() {
            break; // the last sequence: no match
        }
        let match_start = i;
        let distance = le(input, i, 2)?;
        i += 2;
        let len = more(&mut i, (token & 0x0f) as usize)? + 4;
        let at = out.len() as u64;
        copy_back(&mut out, distance, len)?;
        tokens.push(Token {
            kind: TokenKind::Copy {
                distance: distance as u64,
            },
            label: "match".into(),
            input: span(base, match_start, i),
            output: Span::new(at, out.len() as u64),
            detail: format!("copy {} from {distance} back", n_bytes(len)),
        });
    }
    Ok(Decompressed { bytes: out, tokens })
}

/// A gzip member: a header, a DEFLATE stream, and a trailer holding the output's CRC-32 and
/// length. The reader checks both.
pub fn gzip(input: &[u8], base: u64) -> Result<Decompressed, String> {
    if input.len() < 18 || input[0] != 0x1f || input[1] != 0x8b || input[2] != 8 {
        return Err("not a gzip member: it should start 1f 8b 08".into());
    }
    let flags = input[3];
    let mut i = 10;
    if flags & 0x04 != 0 {
        i += 2 + le(input, i, 2)?; // FEXTRA
    }
    for flag in [0x08, 0x10] {
        // FNAME, FCOMMENT: zero-terminated strings
        if flags & flag != 0 {
            while get(input, i)? != 0 {
                i += 1;
            }
            i += 1;
        }
    }
    if flags & 0x02 != 0 {
        i += 2; // FHCRC
    }
    let mut tokens = vec![Token {
        kind: TokenKind::Header,
        label: "gzip header".into(),
        input: span(base, 0, i),
        output: Span::new(0, 0),
        detail: "1f 8b: gzip; 08: DEFLATE".into(),
    }];
    let (out, end) = inflate(&input[i..], base + i as u64, &mut tokens)?;
    let i = i + end;
    let crc = le(input, i, 4)? as u32;
    let length = le(input, i + 4, 4)?;
    let actual = crc32(&out);
    tokens.push(Token {
        kind: TokenKind::Header,
        label: "gzip trailer".into(),
        input: span(base, i, i + 8),
        output: Span::new(out.len() as u64, out.len() as u64),
        detail: format!(
            "CRC-32 {crc:08x} ({}), length {length}",
            if crc == actual {
                "matches"
            } else {
                "does not match"
            }
        ),
    });
    if crc != actual || length != out.len() & 0xffff_ffff {
        return Err(format!(
            "the gzip trailer does not match the output: CRC-32 {crc:08x} against {actual:08x}"
        ));
    }
    Ok(Decompressed { bytes: out, tokens })
}

/// DEFLATE reads bits least significant first, and Huffman codes most significant first.
struct Bits<'a> {
    data: &'a [u8],
    /// Position in bits from the start of `data`.
    pos: usize,
}

impl Bits<'_> {
    fn bit(&mut self) -> Result<u32, String> {
        let byte = get(self.data, self.pos / 8)?;
        let b = (byte >> (self.pos % 8)) & 1;
        self.pos += 1;
        Ok(b as u32)
    }

    fn bits(&mut self, n: u32) -> Result<u32, String> {
        let mut v = 0;
        for i in 0..n {
            v |= self.bit()? << i;
        }
        Ok(v)
    }

    /// The bytes holding bits `from..self.pos`, as file offsets.
    fn span(&self, base: u64, from: usize) -> Span {
        Span::new(base + (from / 8) as u64, base + self.pos.div_ceil(8) as u64)
    }
}

/// A canonical Huffman code, described the way DEFLATE describes it: by each symbol's code
/// length alone. `count[n]` is how many codes are `n` bits long, and `symbols` lists the symbols
/// in code order.
struct Huffman {
    count: [u16; 16],
    symbols: Vec<u16>,
}

impl Huffman {
    fn new(lengths: &[u8]) -> Huffman {
        let mut count = [0u16; 16];
        for &l in lengths {
            count[l as usize] += 1;
        }
        count[0] = 0;
        let mut symbols = Vec::new();
        for len in 1..16 {
            for (s, &l) in lengths.iter().enumerate() {
                if l as usize == len {
                    symbols.push(s as u16);
                }
            }
        }
        Huffman { count, symbols }
    }

    /// Read one code a bit at a time. The codes of each length are consecutive integers, so
    /// after `n` bits the code is either among the `count[n]` codes of that length or longer.
    fn decode(&self, bits: &mut Bits) -> Result<u16, String> {
        let (mut code, mut first, mut index) = (0i32, 0i32, 0i32);
        for len in 1..16 {
            code |= bits.bit()? as i32;
            let count = self.count[len] as i32;
            if code - first < count {
                return Ok(self.symbols[(index + code - first) as usize]);
            }
            index += count;
            first = (first + count) << 1;
            code <<= 1;
        }
        Err("a Huffman code longer than fifteen bits".into())
    }
}

/// Lengths 3..258 and distances 1..32768 are each a base plus some extra bits.
const LENGTH_BASE: [u16; 29] = [
    3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131,
    163, 195, 227, 258,
];
const LENGTH_EXTRA: [u8; 29] = [
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0,
];
const DIST_BASE: [u16; 30] = [
    1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537,
    2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577,
];
const DIST_EXTRA: [u8; 30] = [
    0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13,
    13,
];
/// The order a dynamic block lists the code-length code's own lengths in.
const CODE_LENGTH_ORDER: [usize; 19] = [
    16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15,
];

/// Inflate a DEFLATE stream. Returns the output and how many bytes of `data` it used.
pub fn inflate(
    data: &[u8],
    base: u64,
    tokens: &mut Vec<Token>,
) -> Result<(Vec<u8>, usize), String> {
    let mut bits = Bits { data, pos: 0 };
    let mut out = Vec::new();
    loop {
        let from = bits.pos;
        let last = bits.bit()? == 1;
        let kind = bits.bits(2)?;
        let final_note = if last { ", the last" } else { "" };
        let (lit, dist, what) = match kind {
            0 => {
                // Stored: skip to a byte boundary, then a length, its complement, and the bytes.
                bits.pos = bits.pos.div_ceil(8) * 8;
                let at = bits.pos / 8;
                let len = le(data, at, 2)?;
                let nlen = le(data, at + 2, 2)?;
                if len != !nlen & 0xffff {
                    return Err("a stored block's length and its complement disagree".into());
                }
                let bytes = data
                    .get(at + 4..at + 4 + len)
                    .ok_or("a stored block runs past the end")?;
                let start = out.len() as u64;
                out.extend_from_slice(bytes);
                bits.pos = (at + 4 + len) * 8;
                tokens.push(Token {
                    kind: TokenKind::Literal,
                    label: "stored block".into(),
                    input: bits.span(base, from),
                    output: Span::new(start, out.len() as u64),
                    detail: format!("{}, not compressed{final_note}", n_bytes(len)),
                });
                if last {
                    break;
                }
                continue;
            }
            1 => {
                // Fixed codes: lengths the specification lists, the same in every stream.
                let mut l = [8u8; 288];
                l[144..256].fill(9);
                l[256..280].fill(7);
                (
                    Huffman::new(&l),
                    Huffman::new(&[5u8; 30]),
                    "fixed Huffman codes",
                )
            }
            2 => {
                let (lit, dist) = dynamic_codes(&mut bits)?;
                (lit, dist, "its own Huffman codes")
            }
            _ => return Err("block type 3 is reserved".into()),
        };
        tokens.push(Token {
            kind: TokenKind::Header,
            label: "block".into(),
            input: bits.span(base, from),
            output: Span::new(out.len() as u64, out.len() as u64),
            detail: format!("a compressed block with {what}{final_note}"),
        });
        loop {
            let from = bits.pos;
            let symbol = lit.decode(&mut bits)? as usize;
            let at = out.len() as u64;
            if symbol < 256 {
                out.push(symbol as u8);
                // Consecutive literals are one token, so the list stays readable.
                match tokens.last_mut() {
                    Some(t) if t.kind == TokenKind::Literal && t.output.end == at => {
                        t.input = Span::new(t.input.start, bits.span(base, from).end);
                        t.output = Span::new(t.output.start, at + 1);
                        t.detail = format!(
                            "{}, each its own Huffman code",
                            n_bytes(t.output.len() as usize)
                        );
                    }
                    _ => tokens.push(Token {
                        kind: TokenKind::Literal,
                        label: "literals".into(),
                        input: bits.span(base, from),
                        output: Span::new(at, at + 1),
                        detail: "1 byte, its own Huffman code".into(),
                    }),
                }
                continue;
            }
            if symbol == 256 {
                break; // end of block
            }
            let s = symbol - 257;
            if s >= 29 {
                return Err(format!("length symbol {symbol} does not exist"));
            }
            let len = LENGTH_BASE[s] as usize + bits.bits(LENGTH_EXTRA[s] as u32)? as usize;
            let d = dist.decode(&mut bits)? as usize;
            if d >= 30 {
                return Err(format!("distance symbol {d} does not exist"));
            }
            let distance = DIST_BASE[d] as usize + bits.bits(DIST_EXTRA[d] as u32)? as usize;
            copy_back(&mut out, distance, len)?;
            tokens.push(Token {
                kind: TokenKind::Copy {
                    distance: distance as u64,
                },
                label: "copy".into(),
                input: bits.span(base, from),
                output: Span::new(at, out.len() as u64),
                detail: format!("copy {} from {distance} back", n_bytes(len)),
            });
        }
        if last {
            break;
        }
    }
    Ok((out, bits.pos.div_ceil(8)))
}

/// A dynamic block's codes, which it describes before its data: how many codes of each kind,
/// then the code lengths of a small code, then every literal and distance code's length written
/// in that small code, with run lengths for repeats and zeros.
fn dynamic_codes(bits: &mut Bits) -> Result<(Huffman, Huffman), String> {
    let hlit = bits.bits(5)? as usize + 257;
    let hdist = bits.bits(5)? as usize + 1;
    let hclen = bits.bits(4)? as usize + 4;
    let mut cl = [0u8; 19];
    for &i in &CODE_LENGTH_ORDER[..hclen] {
        cl[i] = bits.bits(3)? as u8;
    }
    let cl = Huffman::new(&cl);
    let mut lengths = Vec::with_capacity(hlit + hdist);
    while lengths.len() < hlit + hdist {
        let (value, repeat) = match cl.decode(bits)? {
            n @ 0..=15 => (n as u8, 1),
            16 => {
                let previous = *lengths.last().ok_or("a repeat with nothing before it")?;
                (previous, 3 + bits.bits(2)?)
            }
            17 => (0, 3 + bits.bits(3)?),
            _ => (0, 11 + bits.bits(7)?),
        };
        lengths.extend(std::iter::repeat(value).take(repeat as usize));
    }
    if lengths.len() != hlit + hdist {
        return Err("the code lengths overrun their count".into());
    }
    Ok((
        Huffman::new(&lengths[..hlit]),
        Huffman::new(&lengths[hlit..]),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snappy_literal_then_overlapping_copy() {
        // Output "abababab": length 8, a two-byte literal, then a copy of six bytes from two
        // back, which overlaps the bytes it writes.
        let input = [8, 0b0000_0100, b'a', b'b', 0b0000_1001, 2];
        let d = snappy(&input, 100).unwrap();
        assert_eq!(d.bytes, b"abababab");
        assert_eq!(d.tokens[2].kind, TokenKind::Copy { distance: 2 });
        assert_eq!(d.tokens[2].input, Span::new(104, 106));
    }

    #[test]
    fn lz4_sequence_and_last_literals() {
        // "abcabcabcX": three literals then a match of six from three back, then one literal.
        let input = [0x32, b'a', b'b', b'c', 3, 0, 0x10, b'X'];
        let d = lz4_raw(&input, 0, 10).unwrap();
        assert_eq!(d.bytes, b"abcabcabcX");
    }

    #[test]
    fn inflate_stored_and_fixed_blocks() {
        // A stored final block holding "hi".
        let stored = [0x01, 0x02, 0x00, 0xfd, 0xff, b'h', b'i'];
        assert_eq!(inflate(&stored, 0, &mut vec![]).unwrap().0, b"hi");
        // zlib's fixed-code encoding of "aaaaaaaaaa": a literal and a copy of nine from one back.
        let fixed = [0x4b, 0x4c, 0x84, 0x01, 0x00];
        assert_eq!(inflate(&fixed, 0, &mut vec![]).unwrap().0, b"aaaaaaaaaa");
    }

    #[test]
    fn unsupported_codecs_say_so() {
        let e = decompress("ZSTD", &[], 0, 0).unwrap_err();
        assert!(e.contains("does not decompress ZSTD"), "{e}");
    }
}
