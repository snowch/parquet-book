//! Grades ch10's problems. Run with:
//!
//! ```text
//! cargo test -p exercises --test how_readers_read -- --ignored
//! ```

use exercises::how_readers_read::{coalesce, finish_time};
use parquet_lab::bytes::Span;
use parquet_lab::object_store::{GetRange, MemoryStore, NetworkModel, ObjectStore, TracingStore};

/// A deterministic stream of numbers, so every run tests the same cases.
struct Lcg(u64);

impl Lcg {
    fn next(&mut self, below: u64) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        (self.0 >> 33) % below
    }
}

#[test]
#[ignore = "problem 10.1: fails until you solve it"]
fn problem_10_1_merges_as_the_reader_does() {
    let mut rng = Lcg(7);
    for case in 0..2000 {
        let n = 1 + rng.next(12) as usize;
        let ranges: Vec<(u64, u64)> = (0..n)
            .map(|_| {
                let start = rng.next(1000);
                (start, start + 1 + rng.next(80))
            })
            .collect();
        for gap in [None, Some(0), Some(1), Some(10), Some(100)] {
            let expected: Vec<(u64, u64)> = parquet_lab::scan::coalesce(
                ranges.iter().map(|&(a, b)| Span::new(a, b)).collect(),
                gap,
            )
            .iter()
            .map(|s| (s.start, s.end))
            .collect();
            assert_eq!(
                coalesce(&ranges, gap),
                expected,
                "case {case}: {ranges:?} with gap {gap:?}"
            );
        }
    }
}

#[test]
#[ignore = "problem 10.2: fails until you solve it"]
fn problem_10_2_matches_the_simulated_store() {
    // With no latency and a byte per microsecond, a request takes as long as it has bytes, so
    // the store's clock can time any list of durations.
    let model = NetworkModel {
        latency_us: 0,
        bandwidth_bytes_per_sec: 1_000_000,
    };
    let mut object = MemoryStore::new();
    object.put("f", vec![0; 10_000]);
    let mut rng = Lcg(11);
    for case in 0..500 {
        let phases: Vec<Vec<u64>> = (0..1 + rng.next(4))
            .map(|_| (0..1 + rng.next(9)).map(|_| 1 + rng.next(900)).collect())
            .collect();
        for connections in [1, 2, 3, 8] {
            let mut store = TracingStore::with_connections(object.clone(), model, connections);
            for (i, phase) in phases.iter().enumerate() {
                if i > 0 {
                    store.next_phase();
                }
                for &d in phase {
                    store
                        .get("f", GetRange::Bounded(Span::new(0, d)), "")
                        .unwrap();
                }
            }
            assert_eq!(
                finish_time(&phases, connections),
                store.elapsed_us(),
                "case {case}: {phases:?} on {connections}"
            );
        }
    }
}
