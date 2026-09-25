//! Grades ch04's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test nested_data -- --ignored
//! ```

use std::path::PathBuf;

use exercises::nested_data::{decode_hybrid, list_from_levels};
use parquet_lab::column::{read_column, Triple};
use parquet_lab::json::Json;
use parquet_lab::nested::{assemble, path_fields};
use parquet_lab::plain::PlainValue;
use parquet_lab::schema::{build, leaves, Leaf, SchemaNode};

fn nested() -> (Vec<u8>, Json) {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let bytes = std::fs::read(dir.join("nested.parquet")).unwrap();
    let manifest = Json::parse(&std::fs::read_to_string(dir.join("nested.json")).unwrap()).unwrap();
    (bytes, manifest)
}

fn tags(bytes: &[u8]) -> (SchemaNode, Leaf) {
    let md = parquet_lab::report::open_bytes(bytes).unwrap();
    let root = build(&md.schema).unwrap();
    let leaf = leaves(&root)
        .into_iter()
        .find(|l| l.dotted_path() == "tags.list.element")
        .unwrap();
    (root, leaf)
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

/// Write a hybrid stream the way a writer might: runs of repeats as RLE, the rest bit-packed.
/// Encoding is not the problem; decoding is.
fn encode(values: &[u32], bit_width: u32, rng: &mut Rng) -> Vec<u8> {
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
    let mut out = Vec::new();
    let mut i = 0;
    while i < values.len() {
        if rng.next(2) == 0 {
            let mut n = 1;
            while i + n < values.len() && values[i + n] == values[i] && n < 300 {
                n += 1;
            }
            uleb((n as u64) << 1, &mut out);
            let bytes = bit_width.div_ceil(8) as usize;
            out.extend_from_slice(&values[i].to_le_bytes()[..bytes]);
            i += n;
        } else {
            let groups = 1 + rng.next(3) as usize;
            let chunk: Vec<u32> = (0..groups * 8)
                .map(|k| values.get(i + k).copied().unwrap_or(0))
                .collect();
            uleb(((groups as u64) << 1) | 1, &mut out);
            let mut bits = vec![0u8; groups * bit_width as usize];
            for (k, v) in chunk.iter().enumerate() {
                for b in 0..bit_width as usize {
                    if v >> b & 1 == 1 {
                        let at = k * bit_width as usize + b;
                        bits[at / 8] |= 1 << (at % 8);
                    }
                }
            }
            out.extend_from_slice(&bits);
            i += groups * 8;
        }
    }
    out
}

#[test]
#[ignore = "problem 4.1: fails until you solve it"]
fn problem_4_1_decodes_the_fixture_levels() {
    let (bytes, _) = nested();
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let root = build(&md.schema).unwrap();
    for leaf in leaves(&root) {
        let data = read_column(&bytes, &md.row_groups[0].columns[leaf.column], &leaf).unwrap();
        for page in &data.pages {
            for (stream, max) in [
                (&page.rep_levels, leaf.max_repetition_level),
                (&page.def_levels, leaf.max_definition_level),
            ] {
                let Some((span, runs)) = stream else { continue };
                // Skip the four-byte length: the problem is the runs after it.
                let body = &bytes[span.start as usize + 4..span.end as usize];
                let expected = parquet_lab::rle::values(runs);
                let width = parquet_lab::rle::bit_width(max);
                assert_eq!(
                    decode_hybrid(body, width, expected.len()),
                    expected,
                    "{} levels {body:02x?}",
                    leaf.dotted_path()
                );
            }
        }
    }
}

#[test]
#[ignore = "problem 4.1: fails until you solve it"]
fn problem_4_1_decodes_generated_streams() {
    let mut rng = Rng(0xdead_beef_cafe_f00d);
    for _ in 0..1000 {
        let width = 1 + rng.next(12) as u32;
        let n = 1 + rng.next(60) as usize;
        let values: Vec<u32> = (0..n)
            .map(|_| {
                if rng.next(3) == 0 {
                    0
                } else {
                    rng.next(1 << width) as u32
                }
            })
            .collect();
        let bytes = encode(&values, width, &mut rng);
        assert_eq!(
            decode_hybrid(&bytes, width, n),
            values,
            "width {width}, bytes {bytes:02x?}: check the header's low bit, the RLE value's byte \
             count, and that bits are read least significant first"
        );
    }
}

fn reader_answer(
    root: &SchemaNode,
    leaf: &Leaf,
    rep: &[u32],
    def: &[u32],
    values: &[String],
) -> Vec<Json> {
    let mut next = values.iter();
    let triples: Vec<Triple> = rep
        .iter()
        .zip(def)
        .map(|(&r, &d)| Triple {
            rep: r,
            def: d,
            value: (d == 3).then(|| PlainValue::Bytes(next.next().unwrap().as_bytes().to_vec())),
            value_span: None,
            page: 0,
        })
        .collect();
    assemble(&path_fields(root, leaf), leaf, &triples)
}

fn as_json(records: &[Option<Vec<Option<String>>>]) -> Vec<Json> {
    records
        .iter()
        .map(|r| {
            let list = match r {
                None => Json::Null,
                Some(items) => Json::Arr(
                    items
                        .iter()
                        .map(|v| v.clone().map(Json::Str).unwrap_or(Json::Null))
                        .collect(),
                ),
            };
            Json::Obj(vec![("tags".into(), list)])
        })
        .collect()
}

#[test]
#[ignore = "problem 4.2: fails until you solve it"]
fn problem_4_2_rebuilds_the_fixture_tags_like_pyarrow() {
    let (bytes, manifest) = nested();
    let (_, leaf) = tags(&bytes);
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let data = read_column(&bytes, &md.row_groups[0].columns[leaf.column], &leaf).unwrap();
    let rep: Vec<u32> = data.triples.iter().map(|t| t.rep).collect();
    let def: Vec<u32> = data.triples.iter().map(|t| t.def).collect();
    let values: Vec<String> = data
        .triples
        .iter()
        .filter_map(|t| match &t.value {
            Some(PlainValue::Bytes(b)) => Some(String::from_utf8(b.clone()).unwrap()),
            _ => None,
        })
        .collect();
    let mine = as_json(&list_from_levels(&rep, &def, &values));
    let theirs: Vec<Json> = manifest
        .get("rows")
        .and_then(Json::as_array)
        .unwrap()
        .iter()
        .map(|row| {
            Json::Obj(vec![(
                "tags".into(),
                row.get("tags").cloned().unwrap_or(Json::Null),
            )])
        })
        .collect();
    assert_eq!(
        mine.iter().map(Json::to_json).collect::<Vec<_>>(),
        theirs.iter().map(Json::to_json).collect::<Vec<_>>()
    );
}

#[test]
#[ignore = "problem 4.2: fails until you solve it"]
fn problem_4_2_agrees_with_the_reader_on_generated_levels() {
    let (bytes, _) = nested();
    let (root, leaf) = tags(&bytes);
    let mut rng = Rng(0x0123_4567_89ab_cdef);
    for _ in 0..500 {
        // Random levels that a writer could produce for this column: each record starts at
        // r = 0, and continues at r = 1 only after a d that shows the list has elements.
        let (mut rep, mut def, mut values) = (Vec::new(), Vec::new(), Vec::new());
        for _ in 0..1 + rng.next(6) {
            let d = rng.next(4) as u32;
            rep.push(0);
            def.push(d);
            if d == 3 {
                values.push(format!("v{}", values.len()));
            }
            if d >= 2 {
                for _ in 0..rng.next(4) {
                    let d = 2 + rng.next(2) as u32;
                    rep.push(1);
                    def.push(d);
                    if d == 3 {
                        values.push(format!("v{}", values.len()));
                    }
                }
            }
        }
        let expected = reader_answer(&root, &leaf, &rep, &def, &values);
        let mine = as_json(&list_from_levels(&rep, &def, &values));
        assert_eq!(
            mine.iter().map(Json::to_json).collect::<Vec<_>>(),
            expected.iter().map(Json::to_json).collect::<Vec<_>>(),
            "rep {rep:?} def {def:?}: d = 0 is a null list, 1 an empty list, 2 a null element, 3 a value"
        );
    }
}

/// Scaffolding, not a problem: the fixture's tag column has every case problem 4.2 names.
#[test]
fn the_fixture_tags_cover_every_case() {
    let (bytes, _) = nested();
    let (_, leaf) = tags(&bytes);
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let data = read_column(&bytes, &md.row_groups[0].columns[leaf.column], &leaf).unwrap();
    let mut defs: Vec<u32> = data.triples.iter().map(|t| t.def).collect();
    defs.sort();
    defs.dedup();
    assert_eq!(defs, [0, 1, 2, 3]);
}
