//! Grades ch06's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test pages -- --ignored
//! ```

use std::path::PathBuf;

use exercises::pages::{crc_matches, page_starts};
use parquet_lab::pages::walk_pages;

fn fixtures() -> Vec<(String, Vec<u8>)> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let mut out: Vec<(String, Vec<u8>)> = std::fs::read_dir(&dir)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().and_then(|e| e.to_str()) == Some("parquet"))
        .map(|p| (p.display().to_string(), std::fs::read(&p).unwrap()))
        .collect();
    out.sort();
    out
}

#[test]
#[ignore = "problem 6.1: fails until you solve it"]
fn problem_6_1_finds_every_page_of_every_fixture() {
    let mut chunks = 0;
    for (name, bytes) in fixtures() {
        let md = parquet_lab::report::open_bytes(&bytes).unwrap();
        for rg in &md.row_groups {
            for c in &rg.columns {
                let r = c.byte_range();
                let chunk = &bytes[r.start as usize..r.end as usize];
                let expected: Vec<u64> = walk_pages(chunk, r.start)
                    .unwrap()
                    .iter()
                    .map(|p| p.span().start)
                    .collect();
                assert_eq!(
                    page_starts(chunk, r.start),
                    expected,
                    "{name} {}: each page is its header's length plus compressed_page_size",
                    c.dotted_path()
                );
                chunks += 1;
            }
        }
    }
    assert!(chunks > 20);
}

#[test]
#[ignore = "problem 6.2: fails until you solve it"]
fn problem_6_2_checks_the_standard_value() {
    let check = 0xcbf4_3926u32 as i32;
    assert!(
        crc_matches(b"123456789", check),
        "the CRC-32 of \"123456789\" is 0xcbf43926"
    );
    assert!(!crc_matches(b"123456780", check));
}

#[test]
#[ignore = "problem 6.2: fails until you solve it"]
fn problem_6_2_verifies_the_fixture_pages_and_catches_damage() {
    let (_, bytes) = fixtures()
        .into_iter()
        .find(|f| f.0.ends_with("pages-v2.parquet"))
        .unwrap();
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    for c in &md.row_groups[0].columns {
        let r = c.byte_range();
        for p in walk_pages(&bytes[r.start as usize..r.end as usize], r.start).unwrap() {
            let stored = p.crc.unwrap() as i32;
            let mut body = bytes[p.body_span.start as usize..p.body_span.end as usize].to_vec();
            assert!(
                crc_matches(&body, stored),
                "page at {}: the body is unchanged",
                p.span().start
            );
            for i in [0, body.len() / 2, body.len() - 1] {
                body[i] ^= 0x10;
                assert!(
                    !crc_matches(&body, stored),
                    "page at {}: one flipped bit must fail",
                    p.span().start
                );
                body[i] ^= 0x10;
            }
        }
    }
}

/// Scaffolding, not a problem: the fixtures include chunks with several pages and a dictionary
/// page, so problem 6.1 cannot pass by reading one header.
#[test]
fn some_chunks_have_many_pages() {
    let (_, bytes) = fixtures()
        .into_iter()
        .find(|f| f.0.ends_with("/pages.parquet"))
        .unwrap();
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let r = md.row_groups[0].columns[1].byte_range();
    let pages = walk_pages(&bytes[r.start as usize..r.end as usize], r.start).unwrap();
    assert!(pages.len() > 3 && pages[0].page_type == "DICTIONARY_PAGE");
}
