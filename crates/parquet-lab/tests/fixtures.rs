//! The reader against every fixture, checked against what pyarrow says about the same file.
//!
//! The manifests in `fixtures/*.json` were written by pyarrow, the implementation that wrote the
//! fixtures, when it wrote them. None of their numbers came from this crate. So every assertion
//! here compares two independent implementations reading the same bytes.

use std::cmp::Ordering;
use std::path::PathBuf;

use parquet_lab::bytes::Span;
use parquet_lab::format::{footer_span, parse_trailer, MAGIC};
use parquet_lab::json::Json;
use parquet_lab::metadata::Statistics;
use parquet_lab::object_store::{MemoryStore, Method, NetworkModel, TracingStore};
use parquet_lab::reader::{read_footer, FooterOptions, SizeSource};
use parquet_lab::report;
use parquet_lab::stats::{self, Comparator};

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
                // pyarrow calls codec 7 "LZ4"; parquet.thrift calls it LZ4_RAW, and uses "LZ4"
                // for codec 5, the older framing that pyarrow no longer writes.
                let theirs = match e.get("compression").and_then(Json::as_str).unwrap() {
                    "LZ4" => "LZ4_RAW",
                    other => other,
                };
                assert_eq!(c.codec, theirs, "{name} {path}");
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
    // Opening magic, then the chunks end to end, then any Bloom filters and page indexes, then
    // the footer, then the trailer: no gaps and no overlaps.
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
        // Between the last chunk and the footer: Bloom filters, then the page index, each where
        // the footer says, end to end.
        let mut extra = Vec::new();
        for rg in &md.row_groups {
            for c in &rg.columns {
                if let Some(b) = parquet_lab::bloom::read(&bytes, c).unwrap() {
                    extra.push(Span::new(b.header_span.start, b.bitset_span.end));
                }
                extra.extend(c.column_index);
                extra.extend(c.offset_index);
            }
        }
        extra.sort();
        for span in extra {
            assert_eq!(
                span.start, at,
                "{name}: an index or filter starts where the last region ended"
            );
            at = span.end;
        }
        let last8: [u8; 8] = bytes[bytes.len() - 8..].try_into().unwrap();
        let t = parse_trailer(last8, bytes.len() as u64).unwrap();
        let footer = footer_span(bytes.len() as u64, t.footer_length).unwrap();
        assert_eq!(
            footer.start, at,
            "{name}: the footer follows the last chunk, filter or index"
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

/// A pyarrow row, reduced to the one leaf a column holds: the same shape, with only the keys on
/// the leaf's path. Lists stay lists, structs keep one key, and nulls stay null.
fn project(value: &Json, keys: &[String]) -> Json {
    match value {
        Json::Null => Json::Null,
        Json::Arr(items) => Json::Arr(items.iter().map(|v| project(v, keys)).collect()),
        Json::Obj(_) if !keys.is_empty() => Json::Obj(vec![(
            keys[0].clone(),
            project(value.get(&keys[0]).unwrap_or(&Json::Null), &keys[1..]),
        )]),
        // pyarrow prints a UTC timestamp with a space and "+00:00"; the reader uses ISO 8601.
        Json::Str(s) if s.ends_with("+00:00") => {
            Json::Str(s.replacen(' ', "T", 1).replace("+00:00", "Z"))
        }
        other => other.clone(),
    }
}

/// A manifest's rows. A fixture that holds another's rows in another order names that fixture
/// and lists its rows' order_id in file order.
fn manifest_rows(manifest: &Json) -> Vec<Json> {
    if let Some(rows) = manifest.get("rows").and_then(Json::as_array) {
        return rows.clone();
    }
    let other = manifest.get("rows_same_as").and_then(Json::as_str).unwrap();
    let text =
        std::fs::read_to_string(root().join("fixtures").join(format!("{other}.json"))).unwrap();
    let base = Json::parse(&text).unwrap();
    let rows = base.get("rows").and_then(Json::as_array).unwrap().clone();
    let id = |r: &Json| r.get("order_id").and_then(Json::as_u64).unwrap();
    manifest
        .get("row_order")
        .and_then(Json::as_array)
        .unwrap()
        .iter()
        .map(|want| {
            let want = want.as_u64().unwrap();
            rows.iter().find(|r| id(r) == want).unwrap().clone()
        })
        .collect()
}

#[test]
fn records_rebuilt_from_levels_match_pyarrows_rows() {
    let mut checked = 0;
    for (name, bytes, manifest) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        let leaves = parquet_lab::schema::leaves(&root);
        let rows = &manifest_rows(&manifest);
        for leaf in &leaves {
            let fields = parquet_lab::nested::path_fields(&root, leaf);
            // The keys a pyarrow row uses: a LIST's repeated group and its element are not keys.
            let keys: Vec<String> = fields
                .iter()
                .enumerate()
                .filter(|(i, _)| {
                    let under_list = *i > 0 && fields[i - 1].is_list;
                    let element = *i > 1 && fields[i - 2].is_list;
                    !under_list && !element
                })
                .map(|(_, f)| f.name.clone())
                .collect();
            let mut records = Vec::new();
            for rg in &md.row_groups {
                let chunk = &rg.columns[leaf.column];
                if !parquet_lab::compress::supported(&chunk.codec) {
                    // ZSTD and BROTLI: the reader must say it cannot, not return anything.
                    let e = parquet_lab::column::read_column(&bytes, chunk, leaf).unwrap_err();
                    assert!(e.0.contains("does not decompress"), "{name}: {e}");
                    continue;
                }
                let data = parquet_lab::column::read_column(&bytes, chunk, leaf)
                    .unwrap_or_else(|e| panic!("{name} {}: {e}", leaf.dotted_path()));
                records.extend(parquet_lab::nested::assemble(&fields, leaf, &data.triples));
            }
            if records.is_empty() && !md.row_groups.is_empty() {
                let codec = &md.row_groups[0].columns[leaf.column].codec;
                if !parquet_lab::compress::supported(codec) {
                    continue;
                }
            }
            assert_eq!(
                records.len(),
                rows.len(),
                "{name} {}: one record per row",
                leaf.dotted_path()
            );
            for (i, (mine, row)) in records.iter().zip(rows).enumerate() {
                let theirs = project(row, &keys);
                assert_eq!(
                    mine.to_json(),
                    theirs.to_json(),
                    "{name} {} record {i}",
                    leaf.dotted_path()
                );
                checked += 1;
            }
        }
    }
    assert!(checked > 40, "only {checked} records compared");
}

#[test]
fn page_checksums_verify_and_catch_damage() {
    let (name, bytes, _) = fixtures()
        .into_iter()
        .find(|f| f.0 == "pages-v2.parquet")
        .unwrap();
    let md = report::open_bytes(&bytes).unwrap();
    let mut checked = 0;
    for rg in &md.row_groups {
        for c in &rg.columns {
            let r = c.byte_range();
            let pages =
                parquet_lab::pages::walk_pages(&bytes[r.start as usize..r.end as usize], r.start)
                    .unwrap();
            for p in &pages {
                assert_eq!(
                    p.crc_ok,
                    Some(true),
                    "{name} {} page at {}",
                    c.dotted_path(),
                    p.span()
                );
                checked += 1;
            }
            // Flip one bit in the first page's body: its checksum must now fail.
            let mut damaged = bytes[r.start as usize..r.end as usize].to_vec();
            let at = (pages[0].body_span.start - r.start) as usize;
            damaged[at] ^= 1;
            let again = parquet_lab::pages::walk_pages(&damaged, r.start).unwrap();
            assert_eq!(
                again[0].crc_ok,
                Some(false),
                "{name} {}: damage undetected",
                c.dotted_path()
            );
        }
    }
    assert!(checked > 8, "only {checked} pages carried a checksum");
}

#[test]
fn every_codec_decompresses_to_the_same_pages() {
    // The codec-* fixtures differ only in their codec, so every page, decompressed, must be the
    // uncompressed file's page byte for byte.
    let all = fixtures();
    let body_of = |bytes: &[u8], column: usize| -> Vec<(String, Vec<u8>)> {
        let md = report::open_bytes(bytes).unwrap();
        let c = &md.row_groups[0].columns[column];
        let r = c.byte_range();
        let pages =
            parquet_lab::pages::walk_pages(&bytes[r.start as usize..r.end as usize], r.start)
                .unwrap();
        pages
            .iter()
            .map(|p| {
                let body = &bytes[p.body_span.start as usize..p.body_span.end as usize];
                let size = p.uncompressed_page_size as usize;
                let d = parquet_lab::compress::decompress(&c.codec, body, p.body_span.start, size);
                (c.codec.clone(), d.map(|d| d.bytes).unwrap_or_default())
            })
            .collect()
    };
    let none = &all.iter().find(|f| f.0 == "codec-none.parquet").unwrap().1;
    let mut checked = 0;
    for codec in ["snappy", "gzip", "lz4"] {
        let file = format!("codec-{codec}.parquet");
        let bytes = &all.iter().find(|f| f.0 == file).unwrap().1;
        for column in 0..7 {
            let expected = body_of(none, column);
            let got = body_of(bytes, column);
            assert_eq!(
                expected.len(),
                got.len(),
                "{file} column {column}: page count"
            );
            for ((_, e), (c, g)) in expected.iter().zip(&got) {
                assert_ne!(c, "UNCOMPRESSED", "{file} should be compressed");
                assert_eq!(e, g, "{file} column {column}");
                checked += 1;
            }
        }
    }
    assert!(checked >= 21, "only {checked} pages compared");
}

/// A column chunk's path, row group, the comparator the reader picks for it, its values as PLAIN
/// bytes, and its statistics.
type ChunkValues = (String, usize, Comparator, Vec<Vec<u8>>, Option<Statistics>);

fn chunk_values(bytes: &[u8]) -> Vec<ChunkValues> {
    let md = report::open_bytes(bytes).unwrap();
    let root = parquet_lab::schema::build(&md.schema).unwrap();
    let mut out = Vec::new();
    for leaf in parquet_lab::schema::leaves(&root) {
        let converted = md.schema[leaf.element].converted_type.clone();
        let comparator = Comparator::for_leaf(&leaf, converted.as_deref());
        for (g, rg) in md.row_groups.iter().enumerate() {
            let chunk = &rg.columns[leaf.column];
            let Ok(data) = parquet_lab::column::read_column(bytes, chunk, &leaf) else {
                continue; // a codec the reader does not decode
            };
            let values = data
                .triples
                .iter()
                .filter_map(|t| t.value.as_ref())
                .map(|v| v.to_plain_bytes(leaf.physical_type))
                .collect();
            out.push((
                leaf.dotted_path(),
                g,
                comparator,
                values,
                chunk.statistics.clone(),
            ));
        }
    }
    out
}

#[test]
fn the_readers_sort_orders_reproduce_pyarrows_statistics() {
    // pyarrow computed min_value and max_value from the values it wrote. The reader decodes the
    // same values and finds their minimum and maximum in the order it chose for the column. The
    // two must agree for every column chunk of every fixture that has statistics.
    let mut checked = 0;
    for (name, bytes, _) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        assert!(
            md.column_orders.is_some(),
            "{name}: pyarrow writes column_orders"
        );
        for (path, g, comparator, values, stats) in chunk_values(&bytes) {
            let Some(s) = stats else { continue };
            let (Some(min), Some(max)) = (&s.min_value, &s.max_value) else {
                continue;
            };
            let (lo, hi) = comparator
                .min_max(values.iter().map(|v| &v[..]))
                .unwrap_or_else(|| panic!("{name} {path}: statistics but no comparable values"));
            // Equal in the column's order: -0.0 and +0.0 are the same number, and a writer
            // stores a zero minimum as -0.0 and a zero maximum as +0.0.
            let same = |a: &[u8], b: &[u8]| comparator.compare(a, b) == Some(Ordering::Equal);
            assert!(same(lo, min), "{name} {path} row group {g}: minimum");
            assert!(same(hi, max), "{name} {path} row group {g}: maximum");
            let b = stats::bounds(&s, comparator, true).unwrap();
            assert_eq!(b.source, stats::Source::MinMaxValue);
            checked += 1;
        }
    }
    assert!(checked > 60, "only {checked} column chunks checked");
}

#[test]
fn the_statistics_fixture_catches_every_mistaken_order() {
    let (_, bytes, _) = fixtures()
        .into_iter()
        .find(|f| f.0 == "statistics.parquet")
        .unwrap();
    let mut caught = Vec::new();
    for (path, _, comparator, values, stats) in chunk_values(&bytes) {
        let (Some((wrong, _)), Some(s)) = (comparator.mistake(), stats) else {
            continue;
        };
        let (Some(min), Some(max)) = (&s.min_value, &s.max_value) else {
            continue;
        };
        let got = wrong.min_max(values.iter().map(|v| &v[..]));
        if got.map(|(lo, hi)| (lo != &min[..], hi != &max[..])) != Some((false, false))
            && !caught.contains(&path)
        {
            caught.push(path);
        }
    }
    caught.sort();
    assert_eq!(caught, ["amount", "city", "customer_id", "delta", "temp_c"]);
}

#[test]
fn deprecated_fields_are_used_only_where_signed_order_is_right() {
    let (_, bytes, _) = fixtures()
        .into_iter()
        .find(|f| f.0 == "statistics.parquet")
        .unwrap();
    for (path, _, comparator, _, stats) in chunk_values(&bytes) {
        let Some(mut s) = stats else { continue };
        if s.min_value.is_none() {
            continue;
        }
        // Pretend the file is old: only min and max, holding what min_value and max_value hold.
        s.min = s.min_value.take();
        s.max = s.max_value.take();
        let usable = stats::bounds(&s, comparator, true).is_ok();
        let signed_scalar = matches!(
            comparator,
            Comparator::I32 | Comparator::I64 | Comparator::F64
        );
        assert_eq!(
            usable,
            signed_scalar,
            "{path}: {:?}",
            stats::bounds(&s, comparator, true)
        );
    }
}

#[test]
fn the_page_index_agrees_with_the_pages() {
    // The OffsetIndex must list the data pages the walker finds, with the rows each starts at;
    // the ColumnIndex must hold each page's own minimum, maximum and null count, which the reader
    // computes from the values it decodes.
    let mut pages_checked = 0;
    for (name, bytes, _) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        for leaf in parquet_lab::schema::leaves(&root) {
            let cmp =
                Comparator::for_leaf(&leaf, md.schema[leaf.element].converted_type.as_deref());
            for rg in &md.row_groups {
                let chunk = &rg.columns[leaf.column];
                let Some(oi) = parquet_lab::page_index::offset_index(&bytes, chunk).unwrap() else {
                    continue;
                };
                let data = parquet_lab::column::read_column(&bytes, chunk, &leaf).unwrap();
                let walked: Vec<Span> = data.pages.iter().map(|p| p.page.span()).collect();
                let listed: Vec<Span> = oi.pages.iter().map(|p| p.span()).collect();
                assert_eq!(
                    listed,
                    walked,
                    "{name} {}: page locations",
                    leaf.dotted_path()
                );
                let reps: Vec<Vec<u32>> = (0..data.pages.len())
                    .map(|i| {
                        let first = usize::from(data.dictionary.is_some());
                        data.triples
                            .iter()
                            .filter(|t| t.page == i + first)
                            .map(|t| t.rep)
                            .collect()
                    })
                    .collect();
                let firsts: Vec<i64> = parquet_lab::column::first_rows(&reps)
                    .iter()
                    .map(|&r| r as i64)
                    .collect();
                let listed: Vec<i64> = oi.pages.iter().map(|p| p.first_row_index).collect();
                assert_eq!(listed, firsts, "{name} {}: first rows", leaf.dotted_path());
                let ci = parquet_lab::page_index::column_index(&bytes, chunk)
                    .unwrap()
                    .unwrap();
                for i in 0..data.pages.len() {
                    let page_no = i + usize::from(data.dictionary.is_some());
                    let values: Vec<Vec<u8>> = data
                        .triples
                        .iter()
                        .filter(|t| t.page == page_no)
                        .filter_map(|t| t.value.as_ref())
                        .map(|v| v.to_plain_bytes(leaf.physical_type))
                        .collect();
                    let nulls = data
                        .triples
                        .iter()
                        .filter(|t| t.page == page_no && t.value.is_none())
                        .count();
                    assert_eq!(
                        ci.null_counts.as_ref().map(|n| n[i]),
                        Some(nulls as i64),
                        "{name} {}: page {i} nulls",
                        leaf.dotted_path()
                    );
                    match cmp.min_max(values.iter().map(|v| &v[..])) {
                        None => assert!(
                            ci.null_pages[i],
                            "{name}: page {i} has no values, so it is a null page"
                        ),
                        Some((lo, hi)) => {
                            assert!(!ci.null_pages[i]);
                            assert_eq!(
                                cmp.compare(lo, &ci.min_values[i]),
                                Some(Ordering::Equal),
                                "{name} {} page {i} min",
                                leaf.dotted_path()
                            );
                            assert_eq!(
                                cmp.compare(hi, &ci.max_values[i]),
                                Some(Ordering::Equal),
                                "{name} {} page {i} max",
                                leaf.dotted_path()
                            );
                        }
                    }
                    pages_checked += 1;
                }
            }
        }
    }
    assert!(pages_checked > 100, "only {pages_checked} pages checked");
}

#[test]
fn bloom_filters_hold_every_value_and_few_others() {
    let mut present = 0;
    let (mut absent, mut false_positives) = (0, 0);
    for (name, bytes, _) in fixtures() {
        let md = report::open_bytes(&bytes).unwrap();
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        for leaf in parquet_lab::schema::leaves(&root) {
            for rg in &md.row_groups {
                let chunk = &rg.columns[leaf.column];
                let Some(filter) = parquet_lab::bloom::read(&bytes, chunk).unwrap() else {
                    continue;
                };
                let data = parquet_lab::column::read_column(&bytes, chunk, &leaf).unwrap();
                let values: Vec<Vec<u8>> = data
                    .triples
                    .iter()
                    .filter_map(|t| t.value.as_ref())
                    .map(|v| v.to_plain_bytes(leaf.physical_type))
                    .collect();
                for v in &values {
                    assert!(
                        filter.probe(v).may_contain,
                        "{name} {}: a value in the chunk must pass",
                        leaf.dotted_path()
                    );
                    present += 1;
                }
                // Integers the chunk does not hold: the filter may pass a few, never most.
                for candidate in (100_000i64..1_000_000).step_by(997) {
                    let bytes = candidate.to_le_bytes().to_vec();
                    if !values.contains(&bytes) {
                        absent += 1;
                        false_positives += usize::from(filter.probe(&bytes).may_contain);
                    }
                }
            }
        }
    }
    assert!(present >= 800, "only {present} values probed");
    let rate = false_positives as f64 / absent as f64;
    assert!(
        rate < 0.15,
        "false positive rate {rate} for {absent} absent values"
    );
}

#[test]
fn skipping_never_loses_a_matching_row() {
    use parquet_lab::prune::{plan, Mechanisms, Op, Predicate};
    let ops = [
        Op::Eq,
        Op::NotEq,
        Op::Lt,
        Op::LtEq,
        Op::Gt,
        Op::GtEq,
        Op::IsNull,
        Op::IsNotNull,
    ];
    let mut plans = 0;
    let mut skipped_something = 0;
    // The ch11 variants differ from their baseline in ways that do not change the logic under
    // test, except sort order; two of them are enough and keep the test quick.
    let slow = |n: &str| {
        n.starts_with("writing-")
            && !matches!(
                n,
                "writing-by-country.parquet" | "writing-small-groups.parquet"
            )
    };
    for (name, bytes, _) in fixtures().into_iter().filter(|f| !slow(&f.0)) {
        let md = report::open_bytes(&bytes).unwrap();
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        let leaves = parquet_lab::schema::leaves(&root);
        let flat: Vec<_> = leaves
            .iter()
            .filter(|l| l.max_repetition_level == 0)
            .collect();
        let projection: Vec<usize> = flat.iter().map(|l| l.column).collect();
        for leaf in &flat {
            let converted = md.schema[leaf.element].converted_type.clone();
            // Candidate values: a spread of the column's own values, as text the parser reads.
            let Ok(first) = parquet_lab::column::read_column(
                &bytes,
                &md.row_groups[0].columns[leaf.column],
                leaf,
            ) else {
                continue;
            };
            let mut texts: Vec<String> = first
                .triples
                .iter()
                .filter_map(|t| t.value.as_ref())
                .step_by(7)
                .map(|v| match v.to_json() {
                    Json::Str(s) => s,
                    other => other.to_json(),
                })
                .take(6)
                .collect();
            texts.push("0".into());
            for op in ops {
                for text in &texts {
                    let Ok(p) = Predicate::new(leaf, converted.as_deref(), op, text) else {
                        continue;
                    };
                    let pl = plan(&bytes, &md, leaf, &p, &projection, Mechanisms::ALL).unwrap();
                    plans += 1;
                    for (g, rg) in md.row_groups.iter().enumerate() {
                        let data = parquet_lab::column::read_column(
                            &bytes,
                            &rg.columns[leaf.column],
                            leaf,
                        )
                        .unwrap();
                        let gp = &pl.row_groups[g];
                        if gp.skipped || gp.rows.len() != 1 || gp.rows[0] != (0, rg.num_rows) {
                            skipped_something += 1;
                        }
                        for (row, t) in data.triples.iter().enumerate() {
                            let v = t
                                .value
                                .as_ref()
                                .map(|v| v.to_plain_bytes(leaf.physical_type));
                            if !p.row_matches(v.as_deref()) {
                                continue;
                            }
                            let row = row as i64;
                            let kept = gp.rows.iter().any(|&(a, b)| a <= row && row < b);
                            assert!(kept, "{name} {} {} {text}: row {row} of row group {g} matches but was skipped: {:?}", leaf.dotted_path(), op.symbol(), gp.steps);
                            // And every projected column reads the page holding that row.
                            for r in &gp.reads {
                                let c = &rg.columns[r.column];
                                if let Some(oi) =
                                    parquet_lab::page_index::offset_index(&bytes, c).unwrap()
                                {
                                    let ranges = oi.row_ranges(rg.num_rows);
                                    let page = ranges
                                        .iter()
                                        .position(|&(a, b)| a <= row && row < b)
                                        .unwrap();
                                    assert!(r.spans.iter().any(|s| s.contains(oi.pages[page].span())), "{name}: column {} does not read the page holding row {row}", r.column);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    assert!(plans > 500, "only {plans} plans checked");
    assert!(
        skipped_something > 100,
        "the plans skipped almost nothing: {skipped_something}"
    );
}

#[test]
fn every_strategy_returns_the_rows_a_full_read_finds() {
    use parquet_lab::object_store::NetworkModel;
    use parquet_lab::prune::{Mechanisms, Op, Predicate};
    use parquet_lab::reader::{FooterOptions, SizeSource};
    use parquet_lab::scan::{scan, Query, Strategy};
    let strategies = [
        Strategy {
            footer: FooterOptions::default(),
            connections: 1,
            coalesce_gap: None,
            whole_chunks: true,
            mechanisms: Mechanisms::NONE,
        },
        Strategy {
            footer: FooterOptions {
                size: SizeSource::SuffixRange,
                prefetch: 8192,
            },
            connections: 1,
            coalesce_gap: Some(0),
            whole_chunks: false,
            mechanisms: Mechanisms::ALL,
        },
        Strategy {
            footer: FooterOptions::default(),
            connections: 4,
            coalesce_gap: Some(1024),
            whole_chunks: false,
            mechanisms: Mechanisms::ALL,
        },
        Strategy {
            footer: FooterOptions {
                size: SizeSource::SuffixRange,
                prefetch: 1 << 20,
            },
            connections: 2,
            coalesce_gap: None,
            whole_chunks: false,
            mechanisms: Mechanisms::ALL,
        },
    ];
    let mut scans = 0;
    for (name, bytes, _) in fixtures() {
        if !(name.starts_with("pruning")
            || name == "statistics.parquet"
            || name == "tiny.parquet"
            || name == "pages-v2-snappy.parquet")
        {
            continue;
        }
        let md = report::open_bytes(&bytes).unwrap();
        let root = parquet_lab::schema::build(&md.schema).unwrap();
        let leaves: Vec<_> = parquet_lab::schema::leaves(&root)
            .into_iter()
            .filter(|l| l.max_repetition_level == 0)
            .collect();
        let columns: Vec<usize> = leaves.iter().map(|l| l.column).collect();
        let mut conditions: Vec<Option<(usize, Op, String)>> = vec![None];
        for leaf in &leaves {
            for (op, v) in [
                (Op::Eq, "431"),
                (Op::Gt, "100"),
                (Op::Lt, "9800"),
                (Op::IsNull, ""),
                (Op::Eq, "SE"),
                (Op::Eq, "424242"),
            ] {
                conditions.push(Some((leaf.column, op, v.to_string())));
            }
        }
        for condition in conditions {
            // The answer, from a plain read of every row.
            let expected: Option<Vec<u64>> = match &condition {
                None => Some((0..md.num_rows as u64).collect()),
                Some((c, op, v)) => {
                    let leaf = leaves.iter().find(|l| l.column == *c).unwrap();
                    let conv = md.schema[leaf.element].converted_type.clone();
                    Predicate::new(leaf, conv.as_deref(), *op, v).ok().map(|p| {
                        let mut out = Vec::new();
                        let mut row = 0u64;
                        for rg in &md.row_groups {
                            let d = parquet_lab::column::read_column(&bytes, &rg.columns[*c], leaf)
                                .unwrap();
                            for t in &d.triples {
                                let raw = t
                                    .value
                                    .as_ref()
                                    .map(|x| x.to_plain_bytes(leaf.physical_type));
                                if p.row_matches(raw.as_deref()) {
                                    out.push(row);
                                }
                                row += 1;
                            }
                        }
                        out
                    })
                }
            };
            let Some(expected) = expected else { continue };
            for s in strategies {
                let q = Query {
                    columns: columns.clone(),
                    condition: condition.clone(),
                };
                let r = scan(&bytes, "data.parquet", &q, s, NetworkModel::default())
                    .unwrap_or_else(|e| panic!("{name} {condition:?} {s:?}: {e}"));
                assert_eq!(r.matches, expected, "{name} {condition:?} {s:?}");
                // No byte is fetched twice, so no scan fetches more than the file.
                let mut got: Vec<Span> = r.requests.iter().filter_map(|q| q.returned).collect();
                got.sort();
                for pair in got.windows(2) {
                    assert!(
                        pair[0].end <= pair[1].start,
                        "{name} {condition:?} {s:?}: {} and {} overlap",
                        pair[0],
                        pair[1]
                    );
                }
                assert!(
                    r.bytes_fetched <= bytes.len() as u64,
                    "{name}: fetched more than the file"
                );
                scans += 1;
            }
        }
    }
    assert!(scans > 200, "only {scans} scans");
}

#[test]
fn the_engine_answers_as_pyarrow_does() {
    // fixtures/queries.json holds queries and pyarrow's answers to them, computed by pyarrow's own
    // compute functions when the fixtures were written.
    let text = std::fs::read_to_string(root().join("fixtures/queries.json")).unwrap();
    let queries = Json::parse(&text).unwrap();
    let mut checked = 0;
    for q in queries.as_array().unwrap() {
        let file = q.get("file").and_then(Json::as_str).unwrap();
        let sql = q.get("sql").and_then(Json::as_str).unwrap();
        let bytes = std::fs::read(root().join("fixtures").join(file)).unwrap();
        let a = parquet_lab::engine::run(&bytes, sql).unwrap_or_else(|e| panic!("{sql}: {e}"));
        let columns: Vec<String> = q
            .get("columns")
            .and_then(Json::as_array)
            .unwrap()
            .iter()
            .map(|c| c.as_str().unwrap().to_string())
            .collect();
        assert_eq!(a.columns, columns, "{sql}");
        let expected = q.get("rows").and_then(Json::as_array).unwrap();
        assert_eq!(a.rows.len(), expected.len(), "{sql}: row count");
        for (mine, theirs) in a.rows.iter().zip(expected) {
            for (m, t) in mine.iter().zip(theirs.as_array().unwrap()) {
                let same = match (m.to_json(), t) {
                    (Json::Float(x), Json::Float(y)) => (x - y).abs() < 1e-9,
                    (Json::Float(x), Json::Int(y)) => (x - *y as f64).abs() < 1e-9,
                    (m, t) => m.to_json() == t.to_json(),
                };
                assert!(same, "{sql}: {:?} against {}", m, t.to_json());
            }
        }
        checked += 1;
    }
    assert!(checked >= 10);
}
