//! Bloom filters: a compact "definitely not here" for one column chunk (ch09).
//!
//! Statistics rule out a value outside a chunk's range. They cannot rule out a value inside it:
//! a chunk of customer numbers from 100000 to 999999 may or may not hold 424242. A Bloom filter
//! can. It is a bitset. To add a value, a writer hashes it and sets a few bits the hash picks. To
//! test a value, a reader hashes it and checks those bits: if any is clear, the value was never
//! added. If all are set, it may have been, or other values may have set them: a false positive.
//!
//! Parquet uses one kind: the **split block Bloom filter**. The bitset is a run of 32-byte
//! blocks, each eight 32-bit words. A value's hash picks one block, then one bit in each of its
//! eight words. The hash is xxHash64 of the value's PLAIN bytes, with seed 0.
//!
//! ```text
//! [BloomFilterHeader, Thrift]   numBytes, algorithm, hash, compression
//! [bitset]                      numBytes bytes: numBytes / 32 blocks
//! ```

use crate::bytes::{ByteReader, Span};
use crate::metadata::{as_struct, req_int, ColumnChunk};
use crate::thrift::{read_struct, Node};

const P1: u64 = 0x9E37_79B1_85EB_CA87;
const P2: u64 = 0xC2B2_AE3D_27D4_EB4F;
const P3: u64 = 0x1656_67B1_9E37_79F9;
const P4: u64 = 0x85EB_CA77_C2B2_AE63;
const P5: u64 = 0x27D4_EB2F_1656_67C5;

fn round(acc: u64, input: u64) -> u64 {
    acc.wrapping_add(input.wrapping_mul(P2))
        .rotate_left(31)
        .wrapping_mul(P1)
}

fn merge(acc: u64, v: u64) -> u64 {
    (acc ^ round(0, v)).wrapping_mul(P1).wrapping_add(P4)
}

/// xxHash64, as its specification describes it: four accumulators over 32-byte stripes, then
/// the tail eight, four and one bytes at a time, then a final mixing of the bits.
pub fn xxh64(data: &[u8], seed: u64) -> u64 {
    let u64_at = |i: usize| u64::from_le_bytes(data[i..i + 8].try_into().unwrap());
    let u32_at = |i: usize| u32::from_le_bytes(data[i..i + 4].try_into().unwrap()) as u64;
    let mut i = 0;
    let mut h = if data.len() >= 32 {
        let mut v = [
            seed.wrapping_add(P1).wrapping_add(P2),
            seed.wrapping_add(P2),
            seed,
            seed.wrapping_sub(P1),
        ];
        while i + 32 <= data.len() {
            for (k, acc) in v.iter_mut().enumerate() {
                *acc = round(*acc, u64_at(i + 8 * k));
            }
            i += 32;
        }
        let mut h = v[0]
            .rotate_left(1)
            .wrapping_add(v[1].rotate_left(7))
            .wrapping_add(v[2].rotate_left(12))
            .wrapping_add(v[3].rotate_left(18));
        for acc in v {
            h = merge(h, acc);
        }
        h
    } else {
        seed.wrapping_add(P5)
    };
    h = h.wrapping_add(data.len() as u64);
    while i + 8 <= data.len() {
        h ^= round(0, u64_at(i));
        h = h.rotate_left(27).wrapping_mul(P1).wrapping_add(P4);
        i += 8;
    }
    if i + 4 <= data.len() {
        h ^= u32_at(i).wrapping_mul(P1);
        h = h.rotate_left(23).wrapping_mul(P2).wrapping_add(P3);
        i += 4;
    }
    for &b in &data[i..] {
        h ^= (b as u64).wrapping_mul(P5);
        h = h.rotate_left(11).wrapping_mul(P1);
    }
    h ^= h >> 33;
    h = h.wrapping_mul(P2);
    h ^= h >> 29;
    h = h.wrapping_mul(P3);
    h ^ (h >> 32)
}

/// The eight odd constants the format fixes, one per word of a block.
pub const SALT: [u32; 8] = [
    0x47b6_137b,
    0x4497_4d91,
    0x8824_ad5b,
    0xa2b7_289d,
    0x7054_95c7,
    0x2df1_424b,
    0x9efc_4947,
    0x5c6b_fb31,
];

/// A decoded filter: where its header and bitset are, and the bitset itself.
#[derive(Clone, Debug, PartialEq)]
pub struct BloomFilter {
    pub header: Node,
    pub header_span: Span,
    pub bitset_span: Span,
    pub bitset: Vec<u8>,
}

/// What a probe for one value did: its hash, the block that hash chose, the bit it tested in each
/// of the block's words, and whether every one was set.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Probe {
    pub hash: u64,
    pub block: usize,
    /// For each of the eight words: the bit tested, and whether it was set.
    pub bits: [(u32, bool); 8],
    pub may_contain: bool,
}

impl BloomFilter {
    pub fn num_blocks(&self) -> usize {
        self.bitset.len() / 32
    }

    /// The bytes of the block a probe tests.
    pub fn block_span(&self, block: usize) -> Span {
        let start = self.bitset_span.start + 32 * block as u64;
        Span::new(start, start + 32)
    }

    /// Test a value, given as its PLAIN bytes (without a length prefix for byte arrays).
    pub fn probe(&self, value: &[u8]) -> Probe {
        self.probe_hash(xxh64(value, 0))
    }

    pub fn probe_hash(&self, hash: u64) -> Probe {
        // The high 32 bits choose the block, scaled to the number of blocks without a division.
        let block = (((hash >> 32) * self.num_blocks() as u64) >> 32) as usize;
        // The low 32 bits, multiplied by each salt, choose one bit in each word: the top five
        // bits of the product are a bit position from 0 to 31.
        let key = hash as u32;
        let mut bits = [(0u32, false); 8];
        for (w, bit) in bits.iter_mut().enumerate() {
            let position = key.wrapping_mul(SALT[w]) >> 27;
            let at = 32 * block + 4 * w;
            let word = u32::from_le_bytes(self.bitset[at..at + 4].try_into().unwrap());
            *bit = (position, word & (1 << position) != 0);
        }
        Probe {
            hash,
            block,
            bits,
            may_contain: bits.iter().all(|&(_, set)| set),
        }
    }
}

/// Read a column chunk's Bloom filter, if it has one.
pub fn read(file: &[u8], chunk: &ColumnChunk) -> Result<Option<BloomFilter>, String> {
    let Some(offset) = chunk.bloom_filter_offset else {
        return Ok(None);
    };
    let bad = |what: &str| format!("Bloom filter at offset {offset}: {what}");
    let rest = file
        .get(offset.max(0) as usize..)
        .ok_or_else(|| bad("the Bloom filter starts past the end of the file"))?;
    let mut r = ByteReader::new(rest, offset as u64);
    let header = read_struct(&mut r).map_err(|e| bad(&e.to_string()))?;
    let h = as_struct(&header).map_err(|e| bad(&e.to_string()))?;
    let num_bytes = req_int(h, "BloomFilterHeader", 1, "numBytes", header.span)
        .map_err(|e| bad(&e.to_string()))?;
    // Only one algorithm, hash and compression are defined; each is a union whose field 1 is it.
    for (id, what) in [
        (2, "algorithm BLOCK"),
        (3, "hash XXHASH"),
        (4, "compression UNCOMPRESSED"),
    ] {
        let known = h
            .field(id)
            .and_then(|f| as_struct(&f.node).ok())
            .is_some_and(|u| u.field(1).is_some());
        if !known {
            return Err(bad(&format!("a Bloom filter that is not {what}")));
        }
    }
    if num_bytes <= 0 || num_bytes % 32 != 0 {
        return Err(bad(
            "a Bloom filter bitset must be a whole number of 32-byte blocks",
        ));
    }
    let (bitset, bitset_span) = r
        .read_bytes(num_bytes as usize)
        .map_err(|e| bad(&e.to_string()))?;
    Ok(Some(BloomFilter {
        header_span: header.span,
        header,
        bitset_span,
        bitset: bitset.to_vec(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn xxh64_matches_its_reference_values() {
        assert_eq!(xxh64(b"", 0), 0xEF46_DB37_51D8_E999);
        assert_eq!(xxh64(b"a", 0), 0xD24E_C4F1_A98C_6E5B);
        assert_eq!(xxh64(b"abc", 0), 0x44BC_2CF5_AD77_0999);
    }
}
