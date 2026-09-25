//! Grades ch02's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test anatomy_of_a_parquet_file -- --ignored
//! ```

use std::path::PathBuf;

use exercises::anatomy_of_a_parquet_file::{footer_length, footer_range, gets_to_open};
use parquet_lab::json::Json;
use parquet_lab::object_store::{MemoryStore, Method, NetworkModel, TracingStore};
use parquet_lab::reader::{read_footer, FooterOptions, SizeSource};

/// The fixtures, each with what pyarrow said about it when it wrote it.
fn fixtures() -> Vec<(String, Vec<u8>, Json)> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let mut out = Vec::new();
    for entry in std::fs::read_dir(&dir).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|e| e.to_str()) == Some("parquet") {
            let manifest =
                Json::parse(&std::fs::read_to_string(path.with_extension("json")).unwrap())
                    .unwrap();
            out.push((
                path.display().to_string(),
                std::fs::read(&path).unwrap(),
                manifest,
            ));
        }
    }
    assert!(!out.is_empty());
    out
}

fn last8(bytes: &[u8]) -> [u8; 8] {
    bytes[bytes.len() - 8..].try_into().unwrap()
}

/// A spread of 32-bit values that exercises every byte position, generated rather than listed.
fn samples() -> Vec<u32> {
    let mut x: u32 = 0x9e37_79b9;
    let mut v = vec![0, 1, 255, 256, 65_535, 65_536, u32::MAX];
    for _ in 0..200 {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        v.push(x);
    }
    v
}

#[test]
#[ignore = "problem 2.1: fails until you solve it"]
fn problem_2_1_footer_length_agrees_with_pyarrow() {
    for (name, bytes, manifest) in fixtures() {
        let expected = manifest
            .get("footer_length")
            .and_then(Json::as_u64)
            .unwrap();
        assert_eq!(u64::from(footer_length(last8(&bytes))), expected, "{name}");
    }
}

#[test]
#[ignore = "problem 2.1: fails until you solve it"]
fn problem_2_1_every_byte_position_counts() {
    for v in samples() {
        let b = v.to_le_bytes();
        let trailer = [b[0], b[1], b[2], b[3], b'P', b'A', b'R', b'1'];
        assert_eq!(
            footer_length(trailer),
            v,
            "bytes {b:02x?}: if you got {:#x}, you read them most significant first",
            u32::from_be_bytes(b)
        );
    }
}

#[test]
#[ignore = "problem 2.2: fails until you solve it"]
fn problem_2_2_footer_range_matches_the_fixtures() {
    for (name, bytes, manifest) in fixtures() {
        let size = bytes.len() as u64;
        let len = manifest
            .get("footer_length")
            .and_then(Json::as_u64)
            .unwrap();
        let (start, end) = footer_range(size, len as u32).expect("a real file has a real footer");
        assert_eq!(
            end,
            size - 8,
            "{name}: the footer ends where the trailer starts"
        );
        assert_eq!(end - start, len, "{name}: the range is footer_length long");
    }
}

#[test]
#[ignore = "problem 2.2: fails until you solve it"]
fn problem_2_2_impossible_footers_are_refused() {
    // The largest footer a 100-byte file can hold runs from byte 4 to byte 92.
    assert_eq!(footer_range(100, 88), Some((4, 92)));
    assert_eq!(footer_range(100, 89), None, "overlaps the opening magic");
    assert_eq!(footer_range(12, 0), Some((4, 4)));
    assert_eq!(footer_range(11, 0), None, "too small for magic and trailer");
    assert_eq!(footer_range(0, 0), None);
    assert_eq!(footer_range(20, u32::MAX), None, "must not overflow");
}

#[test]
#[ignore = "problem 2.3: fails until you solve it"]
fn problem_2_3_gets_match_the_traced_reader() {
    for (name, bytes, _) in fixtures() {
        for prefetch in (0..=bytes.len() as u64 + 16)
            .step_by(7)
            .chain([8, 64 * 1024])
        {
            let mut store = MemoryStore::new();
            store.put("f", bytes.clone());
            let mut traced = TracingStore::new(store, NetworkModel::default());
            let options = FooterOptions {
                size: SizeSource::Known(bytes.len() as u64),
                prefetch,
            };
            let read = read_footer(&mut traced, "f", options).unwrap();
            let gets = traced
                .requests
                .iter()
                .filter(|r| r.method == Method::Get)
                .count();
            assert_eq!(
                gets_to_open(read.footer.len(), prefetch),
                gets,
                "{name} with prefetch {prefetch}: the footer is {} bytes",
                read.footer.len()
            );
        }
    }
}

/// Scaffolding, not a problem: problem 2.3's cases include both answers.
#[test]
fn prefetch_cases_include_one_and_two_gets() {
    let (_, bytes, _) = fixtures().remove(0);
    let count = |prefetch| {
        let mut store = MemoryStore::new();
        store.put("f", bytes.clone());
        let mut traced = TracingStore::new(store, NetworkModel::default());
        let options = FooterOptions {
            size: SizeSource::Known(bytes.len() as u64),
            prefetch,
        };
        read_footer(&mut traced, "f", options).unwrap();
        traced.requests.len()
    };
    assert_eq!(count(8), 2);
    assert_eq!(count(1 << 16), 1);
}
