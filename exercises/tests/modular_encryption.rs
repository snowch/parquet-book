//! Grades ch13's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test modular_encryption -- --ignored
//! ```

use std::path::PathBuf;

use exercises::modular_encryption::{footer_mode, modules, FooterMode};
use parquet_lab::json::Json;

fn fixtures() -> Vec<(String, Vec<u8>, Json)> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let mut out: Vec<(String, Vec<u8>, Json)> = std::fs::read_dir(&dir)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().and_then(|e| e.to_str()) == Some("parquet"))
        .map(|p| {
            let m =
                Json::parse(&std::fs::read_to_string(p.with_extension("json")).unwrap()).unwrap();
            (
                p.file_name().unwrap().to_string_lossy().into_owned(),
                std::fs::read(&p).unwrap(),
                m,
            )
        })
        .collect();
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}

#[test]
#[ignore = "problem 13.1: fails until you solve it"]
fn problem_13_1_finds_the_modules_the_reader_finds() {
    let (_, bytes, _) = fixtures()
        .into_iter()
        .find(|f| f.0 == "plaintext-footer.parquet")
        .unwrap();
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let mut checked = 0;
    for c in md.row_groups[0]
        .columns
        .iter()
        .filter(|c| c.crypto.is_some())
    {
        let r = c.byte_range();
        let expected: Vec<(usize, usize)> = parquet_lab::crypto::chunk_modules(&bytes, r)
            .unwrap()
            .iter()
            .map(|m| ((m.span.start - r.start) as usize, m.span.len() as usize))
            .collect();
        assert_eq!(
            modules(&bytes[r.start as usize..r.end as usize]),
            expected,
            "{}",
            c.dotted_path()
        );
        checked += 1;
    }
    assert_eq!(checked, 2);
    // Generated runs of modules of every size from the smallest possible.
    let mut chunk = Vec::new();
    let mut expected = Vec::new();
    for len in 28u32..60 {
        expected.push((chunk.len(), 4 + len as usize));
        chunk.extend(len.to_le_bytes());
        chunk.extend(vec![0xab; len as usize]);
    }
    assert_eq!(modules(&chunk), expected);
}

#[test]
#[ignore = "problem 13.2: fails until you solve it"]
fn problem_13_2_tells_the_three_modes_apart() {
    for (name, bytes, manifest) in fixtures() {
        let expected = match manifest.get("generator").and_then(|g| g.get("encryption")) {
            None => FooterMode::NotEncrypted,
            Some(e) if matches!(e.get("plaintext_footer"), Some(Json::Bool(true))) => {
                FooterMode::PlaintextFooter
            }
            Some(_) => FooterMode::EncryptedFooter,
        };
        assert_eq!(footer_mode(&bytes), expected, "{name}");
    }
}
