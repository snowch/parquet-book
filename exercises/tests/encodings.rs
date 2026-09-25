//! Grades ch05's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test encodings -- --ignored
//! ```

use std::path::PathBuf;

use exercises::encodings::{apply_prefixes, decode_delta_binary_packed, dictionary_values};
use parquet_lab::column::read_column;
use parquet_lab::plain::PlainValue;
use parquet_lab::schema::{build, leaves};

fn fixture(name: &str) -> Vec<u8> {
    std::fs::read(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../fixtures")
            .join(name),
    )
    .unwrap()
}

/// A column as the book's reader read it: its path, its values section's bytes, its values, and
/// its dictionary when it has one.
type Column = (String, Vec<u8>, Vec<PlainValue>, Option<Vec<PlainValue>>);

fn columns(name: &str) -> Vec<Column> {
    let bytes = fixture(name);
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let root = build(&md.schema).unwrap();
    leaves(&root)
        .iter()
        .map(|leaf| {
            let data = read_column(&bytes, &md.row_groups[0].columns[leaf.column], leaf).unwrap();
            let page = &data.pages[0];
            let section = bytes[page.values.start as usize..page.values.end as usize].to_vec();
            let values = data
                .triples
                .iter()
                .filter_map(|t| t.value.clone())
                .collect();
            let dict = data
                .dictionary
                .map(|d| d.entries.into_iter().map(|(v, _)| v).collect());
            (leaf.dotted_path(), section, values, dict)
        })
        .collect()
}

fn text(v: &PlainValue) -> String {
    match v {
        PlainValue::Bytes(b) => String::from_utf8_lossy(b).into_owned(),
        other => other.to_json().to_json(),
    }
}

struct Rng(u64);
impl Rng {
    fn next(&mut self, n: u64) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0 % n
    }
}

/// A DELTA_BINARY_PACKED writer, so the decoder meets block sizes and widths the fixtures lack.
fn encode_delta(values: &[i64], block: usize, miniblocks: usize) -> Vec<u8> {
    fn uleb(mut v: u64, out: &mut Vec<u8>) {
        loop {
            let b = (v & 0x7f) as u8;
            v >>= 7;
            if v == 0 {
                out.push(b);
                return;
            }
            out.push(b | 0x80);
        }
    }
    let zz = |v: i64| ((v << 1) ^ (v >> 63)) as u64;
    let mut out = Vec::new();
    uleb(block as u64, &mut out);
    uleb(miniblocks as u64, &mut out);
    uleb(values.len() as u64, &mut out);
    uleb(zz(values.first().copied().unwrap_or(0)), &mut out);
    let deltas: Vec<i64> = values.windows(2).map(|w| w[1].wrapping_sub(w[0])).collect();
    let per = block / miniblocks;
    for chunk in deltas.chunks(block) {
        let min = *chunk.iter().min().unwrap();
        uleb(zz(min), &mut out);
        let adjusted: Vec<u64> = chunk.iter().map(|d| d.wrapping_sub(min) as u64).collect();
        let mbs: Vec<&[u64]> = adjusted.chunks(per).collect();
        let widths: Vec<u8> = (0..miniblocks)
            .map(|m| {
                mbs.get(m)
                    .map(|mb| 64 - mb.iter().max().unwrap().leading_zeros())
                    .unwrap_or(0) as u8
            })
            .collect();
        out.extend_from_slice(&widths);
        for (m, mb) in mbs.iter().enumerate() {
            let w = widths[m] as usize;
            let mut bits = vec![0u8; per * w / 8];
            for (i, v) in mb.iter().enumerate() {
                for b in 0..w {
                    if v >> b & 1 == 1 {
                        bits[(i * w + b) / 8] |= 1 << ((i * w + b) % 8);
                    }
                }
            }
            out.extend_from_slice(&bits);
        }
    }
    out
}

#[test]
#[ignore = "problem 5.1: fails until you solve it"]
fn problem_5_1_decodes_the_fixture_columns() {
    for (path, section, values, _) in columns("encodings.parquet") {
        if path != "order_id" && path != "ordered_at" {
            continue;
        }
        let expected: Vec<i64> = values
            .iter()
            .map(|v| match v {
                PlainValue::Int(i) => *i,
                _ => unreachable!(),
            })
            .collect();
        assert_eq!(decode_delta_binary_packed(&section), expected, "{path}");
    }
}

#[test]
#[ignore = "problem 5.1: fails until you solve it"]
fn problem_5_1_decodes_generated_blocks() {
    let mut rng = Rng(0x5eed_1234_abcd_0001);
    for _ in 0..300 {
        let n = 1 + rng.next(700) as usize;
        let mut v = Vec::with_capacity(n);
        let mut x = rng.next(1 << 40) as i64 - (1 << 39);
        for _ in 0..n {
            v.push(x);
            x = x.wrapping_add(match rng.next(4) {
                0 => 1,
                1 => rng.next(1000) as i64 - 500,
                2 => -(rng.next(1 << 30) as i64),
                _ => rng.next(8) as i64,
            });
        }
        let (block, mbs) = [(128, 4), (256, 8), (128, 1), (256, 4)][rng.next(4) as usize];
        let bytes = encode_delta(&v, block, mbs);
        assert_eq!(
            decode_delta_binary_packed(&bytes),
            v,
            "{n} values, blocks of {block} in {mbs} miniblocks: check that deltas add to the \
             block's min delta, and that unneeded miniblocks take no bytes"
        );
    }
}

#[test]
#[ignore = "problem 5.2: fails until you solve it"]
fn problem_5_2_rebuilds_urls_and_generated_strings() {
    let mut rng = Rng(0x0dd_ba11_c0ff_ee00);
    let urls: Vec<Vec<u8>> = columns("encodings.parquet")
        .into_iter()
        .find(|c| c.0 == "url")
        .unwrap()
        .2
        .iter()
        .map(|v| text(v).into_bytes())
        .collect();
    let mut cases = vec![urls];
    for _ in 0..300 {
        let mut words: Vec<Vec<u8>> = (0..1 + rng.next(30))
            .map(|_| {
                (0..rng.next(12))
                    .map(|_| b'a' + rng.next(3) as u8)
                    .collect()
            })
            .collect();
        words.sort();
        cases.push(words);
    }
    for values in cases {
        let mut prefixes = Vec::new();
        let mut suffixes = Vec::new();
        let mut prev: &[u8] = &[];
        for v in &values {
            let p = prev.iter().zip(v).take_while(|(a, b)| a == b).count();
            prefixes.push(p);
            suffixes.push(&v[p..]);
            prev = v;
        }
        assert_eq!(apply_prefixes(&prefixes, &suffixes), values);
    }
}

#[test]
#[ignore = "problem 5.3: fails until you solve it"]
fn problem_5_3_reads_the_fixture_dictionary_pages() {
    for (path, section, values, dict) in columns("dictionary.parquet") {
        let dict: Vec<String> = dict.unwrap().iter().map(text).collect();
        let expected: Vec<String> = values.iter().map(text).collect();
        assert_eq!(
            dictionary_values(&section, expected.len(), &dict),
            expected,
            "{path}"
        );
    }
}

/// Scaffolding, not a problem: the generated blocks reach widths and miniblocks the fixtures do
/// not, so problem 5.1 cannot pass on the fixtures' shapes alone.
#[test]
fn generated_deltas_need_many_widths() {
    let bytes = encode_delta(&[0, 1, 1_000_000, 3, 3, 3, -7], 128, 4);
    assert!(bytes.len() > 8);
    assert!(columns("encodings.parquet")
        .iter()
        .any(|c| c.0 == "order_id"));
}
