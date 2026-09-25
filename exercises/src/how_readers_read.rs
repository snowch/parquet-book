//! ch10's problems. Edit this file; `exercises/tests/how_readers_read.rs` grades it.

/// Problem 10.1: merge byte ranges into requests.
///
/// `ranges` are half-open `(start, end)` byte ranges, in any order, possibly overlapping. Return
/// the requests a reader should make, sorted: overlapping ranges always merge, and with
/// `Some(gap)`, ranges separated by `gap` bytes or fewer merge too, so a gap of zero merges
/// ranges that touch. `None` merges only what overlaps.
pub fn coalesce(ranges: &[(u64, u64)], gap: Option<u64>) -> Vec<(u64, u64)> {
    let _ = (ranges, gap);
    todo!("problem 10.1")
}

/// Problem 10.2: how long do requests take on several connections?
///
/// `phases` lists, phase by phase, how long each request takes, in the order the reader issues
/// them. Every request in a phase may start once the whole previous phase has finished. Each goes
/// on the connection that is free soonest (the lowest-numbered, on a tie), and starts when that
/// connection is free. Return when the last request finishes, with time starting at zero.
pub fn finish_time(phases: &[Vec<u64>], connections: usize) -> u64 {
    let _ = (phases, connections);
    todo!("problem 10.2")
}
