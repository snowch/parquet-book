//! Grades ch07's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test compression -- --ignored
//! ```
//!
//! The expected output of every page comes from `codec-none.parquet`: the same pages that pyarrow
//! wrote without compressing them. The book's own decompressor is not the oracle.

use std::path::PathBuf;

use exercises::compression::{lz4_raw_decompress, snappy_decompress};
use parquet_lab::pages::walk_pages;

fn fixture(name: &str) -> Vec<u8> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../fixtures")
        .join(name);
    std::fs::read(path).unwrap()
}

/// Every page body of every column chunk, with its uncompressed size.
fn pages(name: &str) -> Vec<(String, Vec<u8>, usize)> {
    let bytes = fixture(name);
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let mut out = Vec::new();
    for c in &md.row_groups[0].columns {
        let r = c.byte_range();
        for p in walk_pages(&bytes[r.start as usize..r.end as usize], r.start).unwrap() {
            out.push((
                format!("{name} {} page at {}", c.dotted_path(), p.span().start),
                bytes[p.body_span.start as usize..p.body_span.end as usize].to_vec(),
                p.uncompressed_page_size as usize,
            ));
        }
    }
    out
}

fn check(codec_file: &str, decompress: impl Fn(&[u8], usize) -> Result<Vec<u8>, String>) {
    let expected = pages("codec-none.parquet");
    let compressed = pages(codec_file);
    assert_eq!(expected.len(), compressed.len());
    for ((_, want, _), (label, body, size)) in expected.iter().zip(&compressed) {
        let got = decompress(body, *size).unwrap_or_else(|e| panic!("{label}: {e}"));
        assert_eq!(got.len(), want.len(), "{label}: output length");
        assert!(
            got == *want,
            "{label}: the bytes differ from the uncompressed file's page"
        );
    }
}

#[test]
#[ignore = "problem 7.1: fails until you solve it"]
fn problem_7_1_small_cases() {
    // "abababab": a two-byte literal, then six bytes copied from two back, overlapping.
    assert_eq!(
        snappy_decompress(&[8, 0x04, b'a', b'b', 0x09, 2]).unwrap(),
        b"abababab"
    );
    // A 100-byte literal, whose length needs the extra byte (tag 60 << 2).
    let mut long = vec![100, 60 << 2, 99];
    long.extend(0..100u8);
    assert_eq!(
        snappy_decompress(&long).unwrap(),
        (0..100u8).collect::<Vec<_>>()
    );
    // A copy with a two-byte offset: "xyz", then 3 bytes from 3 back.
    assert_eq!(
        snappy_decompress(&[6, 0x08, b'x', b'y', b'z', (2 << 2) | 0b10, 3, 0]).unwrap(),
        b"xyzxyz"
    );
}

#[test]
#[ignore = "problem 7.1: fails until you solve it"]
fn problem_7_1_decompresses_every_snappy_page() {
    check("codec-snappy.parquet", |b, _| snappy_decompress(b));
}

#[test]
#[ignore = "problem 7.2: fails until you solve it"]
fn problem_7_2_small_cases() {
    // "abcabcabcX": three literals, a match of six from three back, then one last literal.
    assert_eq!(
        lz4_raw_decompress(&[0x32, b'a', b'b', b'c', 3, 0, 0x10, b'X'], 10).unwrap(),
        b"abcabcabcX"
    );
    // A match of 4 + 15 + 255 + 10 = 284 bytes: its length continues over two extra bytes.
    let out = lz4_raw_decompress(&[0x1f, b'z', 1, 0, 255, 10, 0x10, b'!'], 286).unwrap();
    assert_eq!(out.len(), 286);
    assert!(out[..285].iter().all(|&b| b == b'z') && out[285] == b'!');
}

#[test]
#[ignore = "problem 7.2: fails until you solve it"]
fn problem_7_2_decompresses_every_lz4_page() {
    check("codec-lz4.parquet", lz4_raw_decompress);
}

/// Scaffolding, not a problem: the fixtures exercise the long forms, so the problems cannot pass
/// with only the short ones.
#[test]
fn the_fixtures_use_long_literals_and_long_matches() {
    let long_snappy_literal = pages("codec-snappy.parquet").iter().any(|(_, body, _)| {
        let d = parquet_lab::compress::snappy(body, 0).unwrap();
        d.tokens
            .iter()
            .any(|t| t.label == "literal" && t.output.len() > 60)
    });
    assert!(long_snappy_literal);
    let long_lz4_match = pages("codec-lz4.parquet").iter().any(|(_, body, size)| {
        let d = parquet_lab::compress::lz4_raw(body, 0, *size).unwrap();
        d.tokens
            .iter()
            .any(|t| t.label == "match" && t.output.len() > 19 + 255)
    });
    assert!(long_lz4_match);
}
