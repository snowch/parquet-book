//! Grades ch08's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test metadata_and_statistics -- --ignored
//! ```
//!
//! Problem 8.1 is graded against pyarrow: the minimum and maximum your order finds among a
//! column chunk's values must be the ones pyarrow wrote in the footer.

use std::cmp::Ordering;
use std::path::PathBuf;

use exercises::metadata_and_statistics::{compare, usable_bounds, Kind};
use parquet_lab::metadata::Statistics;
use parquet_lab::stats::{self, Comparator};

fn fixture(name: &str) -> Vec<u8> {
    std::fs::read(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../fixtures")
            .join(name),
    )
    .unwrap()
}

fn kind_of(c: Comparator) -> Option<Kind> {
    Some(match c {
        Comparator::I32 => Kind::Int32,
        Comparator::U32 => Kind::UInt32,
        Comparator::I64 => Kind::Int64,
        Comparator::F64 => Kind::Double,
        Comparator::Bytes => Kind::String,
        Comparator::BigEndianSigned => Kind::Decimal,
        _ => return None,
    })
}

/// A column chunk's name, its kind, the comparator the book's reader uses, its values as PLAIN
/// bytes, and its statistics.
type Chunk = (String, Kind, Comparator, Vec<Vec<u8>>, Option<Statistics>);

/// Every column chunk of the fixture whose kind the problems cover.
fn chunks() -> Vec<Chunk> {
    let bytes = fixture("statistics.parquet");
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let root = parquet_lab::schema::build(&md.schema).unwrap();
    let mut out = Vec::new();
    for leaf in parquet_lab::schema::leaves(&root) {
        let c = Comparator::for_leaf(&leaf, md.schema[leaf.element].converted_type.as_deref());
        let Some(kind) = kind_of(c) else { continue };
        for (g, rg) in md.row_groups.iter().enumerate() {
            let chunk = &rg.columns[leaf.column];
            let data = parquet_lab::column::read_column(&bytes, chunk, &leaf).unwrap();
            let values = data
                .triples
                .iter()
                .filter_map(|t| t.value.as_ref())
                .map(|v| v.to_plain_bytes(leaf.physical_type))
                .collect();
            let name = format!("{} row group {g}", leaf.dotted_path());
            out.push((name, kind, c, values, chunk.statistics.clone()));
        }
    }
    out
}

#[test]
#[ignore = "problem 8.1: fails until you solve it"]
fn problem_8_1_finds_the_footers_minimum_and_maximum() {
    let mut checked = 0;
    for (name, kind, _, values, stats) in chunks() {
        let Some(s) = stats else { continue };
        let (Some(min), Some(max)) = (s.min_value, s.max_value) else {
            continue;
        };
        let placed: Vec<&Vec<u8>> = values
            .iter()
            .filter(|v| compare(kind, v, v).is_some())
            .collect();
        let lo = placed.iter().copied().reduce(|a, b| {
            if compare(kind, b, a) == Some(Ordering::Less) {
                b
            } else {
                a
            }
        });
        let hi = placed.iter().copied().reduce(|a, b| {
            if compare(kind, b, a) == Some(Ordering::Greater) {
                b
            } else {
                a
            }
        });
        let (lo, hi) = (lo.unwrap(), hi.unwrap());
        assert_eq!(
            compare(kind, lo, &min),
            Some(Ordering::Equal),
            "{name}: minimum"
        );
        assert_eq!(
            compare(kind, hi, &max),
            Some(Ordering::Equal),
            "{name}: maximum"
        );
        checked += 1;
    }
    assert!(checked >= 15);
}

#[test]
#[ignore = "problem 8.1: fails until you solve it"]
fn problem_8_1_agrees_with_the_reader_on_every_pair() {
    for (name, kind, reader, values, _) in chunks() {
        for a in &values {
            for b in &values {
                assert_eq!(
                    compare(kind, a, b),
                    reader.compare(a, b),
                    "{name}: {a:?} against {b:?}"
                );
            }
        }
    }
}

#[test]
#[ignore = "problem 8.2: fails until you solve it"]
fn problem_8_2_applies_the_rules() {
    for (name, kind, reader, _, stats) in chunks() {
        let Some(s) = stats else { continue };
        // The footer as it is, as if it had no column_orders, and as if it came from an old
        // writer that set only the deprecated fields.
        let mut old = s.clone();
        old.min = old.min_value.take();
        old.max = old.max_value.take();
        let mut nan = s.clone();
        if kind == Kind::Double {
            nan.max_value = Some(f64::NAN.to_le_bytes().to_vec());
        }
        for (case, st, type_order) in [
            ("as written", &s, true),
            ("no column_orders", &s, false),
            ("old writer", &old, true),
            ("NaN maximum", &nan, true),
        ] {
            let expected = stats::bounds(st, reader, type_order)
                .ok()
                .map(|b| (b.min, b.max));
            assert_eq!(
                usable_bounds(st, kind, type_order),
                expected,
                "{name}, {case}"
            );
        }
    }
}
