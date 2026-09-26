//! Grades ch03's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test the_type_system -- --ignored
//! ```

use std::path::PathBuf;

use exercises::the_type_system::{decimal_from_bytes, leaf_paths, max_levels};
use parquet_lab::json::Json;
use parquet_lab::logical::{be_twos_complement, decimal};
use parquet_lab::metadata::{PhysicalType, SchemaElement};
use parquet_lab::schema::{self, Repetition};

/// The fixtures, each with pyarrow's own description.
fn fixtures() -> Vec<(String, Vec<u8>, Json)> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../fixtures");
    let mut out = Vec::new();
    for entry in std::fs::read_dir(&dir).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|e| e.to_str()) == Some("parquet") {
            let manifest =
                Json::parse(&std::fs::read_to_string(path.with_extension("json")).unwrap())
                    .unwrap();
            // ch13's encrypted fixtures need keys for most of what these problems read.
            if manifest
                .get("generator")
                .and_then(|g| g.get("encryption"))
                .is_some()
            {
                continue;
            }
            out.push((
                path.display().to_string(),
                std::fs::read(&path).unwrap(),
                manifest,
            ));
        }
    }
    out
}

/// A small deterministic generator, so the tests need no dependencies and every run is the same.
struct Rng(u64);
impl Rng {
    fn next(&mut self, n: u64) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0 % n
    }
}

/// A random schema, flattened depth-first, as the footer would store it.
fn random_schema(rng: &mut Rng) -> Vec<SchemaElement> {
    fn node(rng: &mut Rng, depth: u32, out: &mut Vec<SchemaElement>, count: &mut u32) {
        let is_group = depth < 4 && rng.next(3) == 0;
        let rep = ["REQUIRED", "OPTIONAL", "REPEATED"][rng.next(3) as usize];
        let at = out.len();
        *count += 1;
        out.push(element(
            &format!("f{count}"),
            None,
            Some(rep),
            (!is_group).then_some(1),
        ));
        if is_group {
            let n = 1 + rng.next(3) as usize;
            out[at].num_children = Some(n as i64);
            for _ in 0..n {
                node(rng, depth + 1, out, count);
            }
        }
    }
    let n = 1 + rng.next(4) as usize;
    let mut out = vec![element("schema", Some(n as i64), None, None)];
    let mut count = 0;
    for _ in 0..n {
        node(rng, 1, &mut out, &mut count);
    }
    out
}

fn element(
    name: &str,
    children: Option<i64>,
    rep: Option<&str>,
    physical: Option<i64>,
) -> SchemaElement {
    SchemaElement {
        name: name.into(),
        physical_type: physical.map(PhysicalType),
        type_length: None,
        repetition: rep.map(str::to_string),
        num_children: children,
        converted_type: None,
        logical_type: None,
        scale: None,
        precision: None,
        field_id: None,
        span: parquet_lab::bytes::Span::new(0, 0),
    }
}

fn flat(elements: &[SchemaElement]) -> Vec<(&str, usize)> {
    elements
        .iter()
        .map(|e| (e.name.as_str(), e.num_children.unwrap_or(0) as usize))
        .collect()
}

#[test]
#[ignore = "problem 3.1: fails until you solve it"]
fn problem_3_1_leaf_paths_match_pyarrow() {
    for (name, bytes, manifest) in fixtures() {
        let md = parquet_lab::report::open_bytes(&bytes).unwrap();
        let expected: Vec<String> = manifest
            .get("leaves")
            .and_then(Json::as_array)
            .unwrap()
            .iter()
            .map(|l| l.get("path").and_then(Json::as_str).unwrap().to_string())
            .collect();
        assert_eq!(leaf_paths(&flat(&md.schema)), expected, "{name}");
    }
}

#[test]
#[ignore = "problem 3.1: fails until you solve it"]
fn problem_3_1_leaf_paths_match_the_reader_on_generated_schemas() {
    let mut rng = Rng(0x2545_f491_4f6c_dd1d);
    for _ in 0..500 {
        let elements = random_schema(&mut rng);
        let root = schema::build(&elements).unwrap();
        let expected: Vec<String> = schema::leaves(&root)
            .iter()
            .map(|l| l.dotted_path())
            .collect();
        assert_eq!(
            leaf_paths(&flat(&elements)),
            expected,
            "schema {:?}: a group's children are the next num_children subtrees, not the next \
             num_children elements",
            flat(&elements)
        );
    }
}

#[test]
#[ignore = "problem 3.2: fails until you solve it"]
fn problem_3_2_max_levels_for_every_path_up_to_five_deep() {
    let all = [
        Repetition::Required,
        Repetition::Optional,
        Repetition::Repeated,
    ];
    for len in 0..=5u32 {
        for code in 0..3u32.pow(len) {
            let path: Vec<Repetition> = (0..len)
                .map(|i| all[((code / 3u32.pow(i)) % 3) as usize])
                .collect();
            assert_eq!(max_levels(&path), schema::max_levels(&path), "{path:?}");
        }
    }
}

#[test]
#[ignore = "problem 3.2: fails until you solve it"]
fn problem_3_2_max_levels_match_pyarrow() {
    for (name, bytes, manifest) in fixtures() {
        let md = parquet_lab::report::open_bytes(&bytes).unwrap();
        let leaves = schema::leaves(&schema::build(&md.schema).unwrap());
        for (leaf, e) in leaves
            .iter()
            .zip(manifest.get("leaves").and_then(Json::as_array).unwrap())
        {
            let want = (
                e.get("max_definition_level")
                    .and_then(Json::as_u64)
                    .unwrap() as u32,
                e.get("max_repetition_level")
                    .and_then(Json::as_u64)
                    .unwrap() as u32,
            );
            assert_eq!(
                max_levels(&leaf.repetitions),
                want,
                "{name} {}",
                leaf.dotted_path()
            );
        }
    }
}

#[test]
#[ignore = "problem 3.3: fails until you solve it"]
fn problem_3_3_the_fixture_decimals_match_pyarrow() {
    let (_, bytes, manifest) = fixtures()
        .into_iter()
        .find(|f| f.0.ends_with("types.parquet"))
        .unwrap();
    let md = parquet_lab::report::open_bytes(&bytes).unwrap();
    let chunk = md.row_groups[0]
        .columns
        .iter()
        .find(|c| c.dotted_path() == "amount")
        .unwrap();
    let stats = chunk.statistics.as_ref().unwrap();
    let expected = manifest.get("row_groups").and_then(Json::as_array).unwrap()[0]
        .get("columns")
        .and_then(Json::as_array)
        .unwrap()
        .iter()
        .find(|c| c.get("path").and_then(Json::as_str) == Some("amount"))
        .unwrap()
        .get("statistics")
        .unwrap()
        .clone();
    assert_eq!(
        decimal_from_bytes(stats.min_value.as_ref().unwrap(), 2),
        expected.get("min").and_then(Json::as_str).unwrap()
    );
    assert_eq!(
        decimal_from_bytes(stats.max_value.as_ref().unwrap(), 2),
        expected.get("max").and_then(Json::as_str).unwrap()
    );
}

#[test]
#[ignore = "problem 3.3: fails until you solve it"]
fn problem_3_3_generated_decimals() {
    let mut rng = Rng(0x9e37_79b9_7f4a_7c15);
    for _ in 0..2000 {
        let len = 1 + rng.next(16) as usize;
        let bytes: Vec<u8> = (0..len).map(|_| rng.next(256) as u8).collect();
        let scale = 1 + rng.next(6) as u32;
        let want = decimal(be_twos_complement(&bytes).unwrap(), i64::from(scale));
        assert_eq!(
            decimal_from_bytes(&bytes, scale),
            want,
            "bytes {bytes:02x?}, scale {scale}: if the sign is wrong, check the top bit of the \
             first byte; if the digits are, check you read most significant first"
        );
    }
}

/// Scaffolding, not a problem: the generated schemas include groups, nesting and every
/// repetition, so problem 3.1 cannot pass by treating the list as flat.
#[test]
fn generated_schemas_are_varied() {
    let mut rng = Rng(0x2545_f491_4f6c_dd1d);
    let (mut nested, mut repeated) = (false, false);
    for _ in 0..500 {
        let elements = random_schema(&mut rng);
        let root = schema::build(&elements).unwrap();
        for l in schema::leaves(&root) {
            nested |= l.path.len() > 2;
            repeated |= l.max_repetition_level > 1;
        }
    }
    assert!(nested && repeated);
}
