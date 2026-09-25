//! The reader against every fixture, checked against what pyarrow says about the same file.
//!
//! The manifests in `fixtures/*.json` were written by pyarrow, the implementation that wrote the
//! fixtures, when it wrote them. None of their numbers came from this crate. So every assertion
//! here compares two independent implementations reading the same bytes.

use std::path::PathBuf;

use parquet_lab::format::{footer_span, parse_trailer, MAGIC};
use parquet_lab::json::Json;
use parquet_lab::object_store::{MemoryStore, Method, NetworkModel, TracingStore};
use parquet_lab::reader::{read_footer, FooterOptions, SizeSource};
use parquet_lab::report;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// Every fixture, with its bytes and its manifest.
fn fixtures() -> Vec<(String, Vec<u8>, Json)> {
    let dir = root().join("fixtures");
    let mut out = Vec::new();
    for entry in std::fs::read_dir(&dir).expect("fixtures/ exists") {
        let path = entry.unwrap().path();
        if path.extension().and_then(|e| e.to_str()) != Some("parquet") {
            continue;
        }
        let manifest_path = path.with_extension("json");
        let manifest = Json::parse(
            &std::fs::read_to_string(&manifest_path).unwrap_or_else(|_| {
                panic!("{} has no manifest; run `make fixtures`", path.display())
            }),
        )
        .expect("manifest is JSON");
        let name = path.file_name().unwrap().to_string_lossy().into_owned();
        out.push((name, std::fs::read(&path).unwrap(), manifest));
    }
    out.sort_by(|a, b| a.0.cmp(&b.0));
    assert!(
        out.len() >= 2,
        "expected the committed fixtures, found {}",
        out.len()
    );
    out
}

fn num(j: &Json, key: &str) -> u64 {
    j.get(key)
        .and_then(Json::as_u64)
        .unwrap_or_else(|| panic!("manifest has no number {key}"))
}

#[test]
fn every_fixture_starts_and_ends_with_the_magic() {
    for (name, bytes, manifest) in fixtures() {
        assert_eq!(bytes.len() as u64, num(&manifest, "file_size"), "{name}");
        assert_eq!(bytes[..4], MAGIC, "{name}: opening magic");
        assert_eq!(bytes[bytes.len() - 4..], MAGIC, "{name}: closing magic");
    }
}

#[test]
fn the_footer_length_agrees_with_pyarrow() {
    for (name, bytes, manifest) in fixtures() {
        let last8: [u8; 8] = bytes[bytes.len() - 8..].try_into().unwrap();
        let t = parse_trailer(last8, bytes.len() as u64).unwrap();
        assert_eq!(
            u64::from(t.footer_length),
            num(&manifest, "footer_length"),
            "{name}: pyarrow's serialized_size is the footer length"
        );
    }
}

#[test]
fn the_footer_decodes_to_what_pyarrow_wrote() {
    for (name, bytes, manifest) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        assert_eq!(md.num_rows as u64, num(&manifest, "num_rows"), "{name}");
        assert_eq!(
            md.row_groups.len() as u64,
            num(&manifest, "num_row_groups"),
            "{name}"
        );
        assert_eq!(
            md.created_by.as_deref(),
            manifest.get("created_by").and_then(Json::as_str),
            "{name}"
        );
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        let leaves = parquet_lab::schema::leaves(&root);
        let expected = manifest.get("leaves").and_then(Json::as_array).unwrap();
        assert_eq!(leaves.len(), expected.len(), "{name}: one leaf per column");
        for (leaf, e) in leaves.iter().zip(expected) {
            let path = e.get("path").and_then(Json::as_str).unwrap();
            assert_eq!(leaf.dotted_path(), path, "{name}");
            assert_eq!(
                u64::from(leaf.max_definition_level),
                e.get("max_definition_level")
                    .and_then(Json::as_u64)
                    .unwrap(),
                "{name} {path}: max definition level"
            );
            assert_eq!(
                u64::from(leaf.max_repetition_level),
                e.get("max_repetition_level")
                    .and_then(Json::as_u64)
                    .unwrap(),
                "{name} {path}: max repetition level"
            );
            assert_eq!(
                leaf.physical_type.name(),
                e.get("physical_type").and_then(Json::as_str).unwrap(),
                "{name} {path}"
            );
        }
    }
}

#[test]
fn every_column_chunk_is_where_pyarrow_says_it_is() {
    for (name, bytes, manifest) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        let groups = manifest.get("row_groups").and_then(Json::as_array).unwrap();
        for (rg, expected) in md.row_groups.iter().zip(groups) {
            assert_eq!(rg.num_rows as u64, num(expected, "num_rows"), "{name}");
            let cols = expected.get("columns").and_then(Json::as_array).unwrap();
            for (c, e) in rg.columns.iter().zip(cols) {
                let path = e.get("path").and_then(Json::as_str).unwrap();
                assert_eq!(c.dotted_path(), path, "{name}");
                assert_eq!(
                    c.data_page_offset as u64,
                    num(e, "data_page_offset"),
                    "{name} {path}"
                );
                assert_eq!(
                    c.total_compressed_size as u64,
                    num(e, "total_compressed_size"),
                    "{name} {path}"
                );
                assert_eq!(c.num_values as u64, num(e, "num_values"), "{name} {path}");
                assert_eq!(
                    c.physical_type.name(),
                    e.get("physical_type").and_then(Json::as_str).unwrap(),
                    "{name} {path}"
                );
                assert_eq!(
                    c.codec,
                    e.get("compression").and_then(Json::as_str).unwrap()
                );
                let mut mine = c.encodings.clone();
                mine.sort();
                let theirs: Vec<String> = e
                    .get("encodings")
                    .and_then(Json::as_array)
                    .unwrap()
                    .iter()
                    .map(|x| x.as_str().unwrap().to_string())
                    .collect();
                assert_eq!(mine, theirs, "{name} {path}");
            }
        }
    }
}

#[test]
fn column_chunks_and_the_footer_tile_the_file() {
    // Opening magic, then the chunks end to end, then the footer, then the trailer: no gaps and
    // no overlaps, because these fixtures have no page indexes or Bloom filters between them.
    for (name, bytes, _) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        let mut at = 4;
        for rg in &md.row_groups {
            for c in &rg.columns {
                let r = c.byte_range();
                assert_eq!(
                    r.start,
                    at,
                    "{name}: {} starts where the last region ended",
                    c.dotted_path()
                );
                at = r.end;
            }
        }
        let last8: [u8; 8] = bytes[bytes.len() - 8..].try_into().unwrap();
        let t = parse_trailer(last8, bytes.len() as u64).unwrap();
        let footer = footer_span(bytes.len() as u64, t.footer_length).unwrap();
        assert_eq!(
            footer.start, at,
            "{name}: the footer follows the last chunk"
        );
    }
}

#[test]
fn the_exact_procedure_makes_three_requests_and_reads_only_the_tail() {
    for (name, bytes, manifest) in fixtures() {
        let mut store = MemoryStore::new();
        store.put(&name, bytes.clone());
        let mut traced = TracingStore::new(store, NetworkModel::default());
        let read = read_footer(&mut traced, &name, FooterOptions::default()).unwrap();
        let methods: Vec<Method> = traced.requests.iter().map(|r| r.method).collect();
        assert_eq!(methods, [Method::Head, Method::Get, Method::Get], "{name}");
        assert_eq!(
            traced.bytes_returned(),
            8 + num(&manifest, "footer_length"),
            "{name}: the trailer and the footer, and not one byte more"
        );
        assert!(!read.footer_was_prefetched);
    }
}

#[test]
fn a_large_enough_prefetch_saves_a_request() {
    for (name, bytes, manifest) in fixtures() {
        let footer = num(&manifest, "footer_length");
        let run = |prefetch| {
            let mut store = MemoryStore::new();
            store.put(&name, bytes.clone());
            let mut traced = TracingStore::new(store, NetworkModel::default());
            let options = FooterOptions {
                size: SizeSource::SuffixRange,
                prefetch,
            };
            let read = read_footer(&mut traced, &name, options).unwrap();
            (traced.requests.len(), read.footer_was_prefetched)
        };
        assert_eq!(run(footer + 8), (1, true), "{name}: exactly enough");
        assert_eq!(run(footer + 7), (2, false), "{name}: one byte short");
        assert_eq!(run(64 * 1024), (1, true), "{name}: more than the file");
    }
}

#[test]
fn the_structure_view_and_the_footer_lab_report_success() {
    for (name, bytes, _) in fixtures() {
        let s = report::structure(&bytes);
        assert_eq!(
            s.get("ok"),
            Some(&Json::Bool(true)),
            "{name}: {}",
            s.to_json()
        );
        let lab = report::footer_lab(
            &bytes,
            &name,
            FooterOptions::default(),
            NetworkModel::default(),
        );
        assert_eq!(
            lab.get("ok"),
            Some(&Json::Bool(true)),
            "{name}: {}",
            lab.to_json()
        );
    }
}

#[test]
fn damage_is_reported_not_papered_over() {
    let (name, bytes, _) = fixtures()
        .into_iter()
        .find(|f| f.0 == "tiny.parquet")
        .unwrap();
    let run = |bytes: &[u8]| {
        report::footer_lab(
            bytes,
            &name,
            FooterOptions::default(),
            NetworkModel::default(),
        )
    };
    // The closing magic.
    let mut bad = bytes.clone();
    let n = bad.len();
    bad[n - 1] = b'2';
    let j = run(&bad);
    assert_eq!(j.get("ok"), Some(&Json::Bool(false)));
    assert!(j
        .get("error")
        .and_then(Json::as_str)
        .unwrap()
        .contains("PAR1"));
    // A footer length larger than the file.
    let mut bad = bytes.clone();
    bad[n - 5] = 0x7f;
    let j = run(&bad);
    assert!(j
        .get("error")
        .and_then(Json::as_str)
        .unwrap()
        .contains("footer"));
    // Requests made before the damage was found are still in the trace.
    assert_eq!(j.get("requests").and_then(Json::as_array).unwrap().len(), 2);
}

#[test]
fn logical_types_read_statistics_the_way_pyarrow_does() {
    // pyarrow reports statistics already converted through the logical type. The reader applies
    // the logical type itself, to the raw bytes, and must arrive at the same values. Only the
    // spelling differs: pyarrow prints a UTC timestamp with a space and "+00:00", and strings
    // without quotes.
    let normalise = |s: &str| {
        s.trim_matches('"')
            .replacen(' ', "T", 1)
            .replace("+00:00", "Z")
    };
    let mut compared = 0;
    for (name, bytes, manifest) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        let leaves = parquet_lab::schema::leaves(&parquet_lab::schema::build(&md.schema).unwrap());
        let groups = manifest.get("row_groups").and_then(Json::as_array).unwrap();
        for (rg, expected) in md.row_groups.iter().zip(groups) {
            let cols = expected.get("columns").and_then(Json::as_array).unwrap();
            for ((c, e), leaf) in rg.columns.iter().zip(cols).zip(&leaves) {
                let (Some(logical), Some(stats)) = (&leaf.logical_type, &c.statistics) else {
                    continue;
                };
                let theirs = e.get("statistics").unwrap();
                for (mine, key) in [(&stats.min_value, "min"), (&stats.max_value, "max")] {
                    let (Some(raw), Some(want)) = (mine, theirs.get(key).and_then(Json::as_str))
                    else {
                        continue;
                    };
                    let got = parquet_lab::logical::interpret(c.physical_type, logical, raw)
                        .unwrap_or_else(|| {
                            panic!("{name} {}: no reading of {raw:?}", c.dotted_path())
                        });
                    assert_eq!(
                        normalise(&got),
                        normalise(want),
                        "{name} {} {key}",
                        c.dotted_path()
                    );
                    compared += 1;
                }
            }
        }
    }
    assert!(
        compared >= 10,
        "only {compared} values compared; the types fixture should give more"
    );
}
