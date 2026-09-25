//! A simulated object store: the subset of S3's semantics a Parquet reader depends on.
//!
//! Three operations, because a Parquet reader needs no more:
//!
//! - `HEAD` returns an object's size.
//! - `GET` with `Range: bytes=a-b` returns bytes `a` to `b` inclusive.
//! - `GET` with `Range: bytes=-n` returns the last `n` bytes, and the response says how large the
//!   whole object is. A reader can find a footer with no `HEAD` at all.
//!
//! [`MemoryStore`] holds the objects. [`TracingStore`] wraps any store, logs every request, and
//! charges each one a simulated cost from a [`NetworkModel`]. The trace the browser shows is
//! this log. Nothing is drawn that a request did not do.
//!
//! The costs are simulated on purpose. A real network would make every run of the book give
//! different numbers, and the book's rule is that every number it shows can be reproduced. The
//! model is deliberately simple: a fixed cost per request plus bytes over bandwidth. That
//! captures the property that shapes Parquet readers (a request is expensive, a byte is cheap)
//! and nothing else.

use std::collections::BTreeMap;
use std::fmt;

use crate::bytes::Span;

/// Which bytes a `GET` asks for.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GetRange {
    /// `bytes=start-(end-1)`: a span of absolute offsets.
    Bounded(Span),
    /// `bytes=-n`: the last `n` bytes, whatever the object's size.
    Suffix(u64),
}

impl GetRange {
    /// The value of the HTTP `Range` header for this request.
    pub fn header(&self) -> String {
        match self {
            GetRange::Bounded(span) => span.http_range(),
            GetRange::Suffix(n) => format!("bytes=-{n}"),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StoreError {
    NotFound {
        key: String,
    },
    /// HTTP 416: the range starts at or after the end of the object.
    RangeNotSatisfiable {
        key: String,
        range: String,
        size: u64,
    },
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StoreError::NotFound { key } => write!(f, "404: no object named {key}"),
            StoreError::RangeNotSatisfiable { key, range, size } => {
                write!(f, "416: {range} is outside {key}, which is {size} bytes")
            }
        }
    }
}

impl std::error::Error for StoreError {}

/// The body of a successful `GET`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GetResult {
    pub bytes: Vec<u8>,
    /// Which bytes of the object these are: the response's `Content-Range`.
    pub span: Span,
    /// The object's total size, which `Content-Range` also carries.
    pub object_size: u64,
}

/// What a Parquet reader needs from storage.
///
/// `why` is not part of any storage protocol. It is instrumentation: the reader says what it
/// wants the bytes for, the trace records it, and the browser can then answer "why did the
/// reader request these bytes?" from the reader's own words rather than from a caption.
pub trait ObjectStore {
    fn head(&mut self, key: &str, why: &str) -> Result<u64, StoreError>;
    fn get(&mut self, key: &str, range: GetRange, why: &str) -> Result<GetResult, StoreError>;
}

/// Objects held in memory: the book's fixtures, embedded in the page or read from disk.
#[derive(Clone, Debug, Default)]
pub struct MemoryStore {
    objects: BTreeMap<String, Vec<u8>>,
}

impl MemoryStore {
    pub fn new() -> MemoryStore {
        MemoryStore::default()
    }

    pub fn put(&mut self, key: &str, bytes: Vec<u8>) {
        self.objects.insert(key.to_string(), bytes);
    }

    fn object(&self, key: &str) -> Result<&Vec<u8>, StoreError> {
        self.objects.get(key).ok_or_else(|| StoreError::NotFound {
            key: key.to_string(),
        })
    }
}

impl ObjectStore for MemoryStore {
    fn head(&mut self, key: &str, _why: &str) -> Result<u64, StoreError> {
        Ok(self.object(key)?.len() as u64)
    }

    /// Serve a range the way S3 does: a range that runs past the end is cut short rather than
    /// refused, a suffix longer than the object returns the whole object, and only a range that
    /// starts at or beyond the end is an error.
    fn get(&mut self, key: &str, range: GetRange, _why: &str) -> Result<GetResult, StoreError> {
        let data = self.object(key)?;
        let size = data.len() as u64;
        let span = match range {
            GetRange::Bounded(s) => {
                if s.start >= size || s.is_empty() {
                    return Err(StoreError::RangeNotSatisfiable {
                        key: key.to_string(),
                        range: range.header(),
                        size,
                    });
                }
                Span::new(s.start, s.end.min(size))
            }
            GetRange::Suffix(n) => Span::new(size.saturating_sub(n), size),
        };
        Ok(GetResult {
            bytes: data[span.start as usize..span.end as usize].to_vec(),
            span,
            object_size: size,
        })
    }
}

/// What a request costs: a fixed latency, and the time to move its bytes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NetworkModel {
    /// Time from sending a request to the first byte of the response, in microseconds.
    pub latency_us: u64,
    /// Bytes per second once the response is flowing. Zero means unlimited.
    pub bandwidth_bytes_per_sec: u64,
}

impl NetworkModel {
    /// Microseconds to complete one request that returns `bytes` bytes.
    pub fn cost_us(&self, bytes: u64) -> u64 {
        let transfer = match self.bandwidth_bytes_per_sec {
            0 => 0,
            bw => (bytes * 1_000_000).div_ceil(bw),
        };
        self.latency_us + transfer
    }
}

impl Default for NetworkModel {
    /// A request that takes a while to start and then moves bytes quickly: the shape of object
    /// storage over a network. The two numbers are a scenario, not a measurement; the browser
    /// lets the reader change both.
    fn default() -> Self {
        NetworkModel {
            latency_us: 20_000,
            bandwidth_bytes_per_sec: 100_000_000,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Method {
    Head,
    Get,
}

impl Method {
    pub fn name(&self) -> &'static str {
        match self {
            Method::Head => "HEAD",
            Method::Get => "GET",
        }
    }
}

/// One entry in the trace: a request, what came back, and what it cost.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Request {
    pub seq: usize,
    pub method: Method,
    pub key: String,
    /// The `Range` header, if the request had one.
    pub range: Option<String>,
    pub why: String,
    /// 200 for a `HEAD`, 206 for a satisfied range, or the error status.
    pub status: u16,
    /// The bytes that came back, as offsets into the object.
    pub returned: Option<Span>,
    pub bytes_returned: u64,
    pub start_us: u64,
    pub end_us: u64,
}

/// Wraps a store, and records and prices every request that passes through it.
///
/// Requests are issued one after another, so each starts when the previous one ended. A
/// reader that issues requests concurrently is a later chapter's subject (ch10), and when it
/// arrives it will change this clock, not the requests.
#[derive(Debug)]
pub struct TracingStore<S> {
    inner: S,
    pub model: NetworkModel,
    pub requests: Vec<Request>,
    clock_us: u64,
}

impl<S: ObjectStore> TracingStore<S> {
    pub fn new(inner: S, model: NetworkModel) -> TracingStore<S> {
        TracingStore {
            inner,
            model,
            requests: Vec::new(),
            clock_us: 0,
        }
    }

    /// Total simulated time for every request so far.
    pub fn elapsed_us(&self) -> u64 {
        self.clock_us
    }

    pub fn bytes_returned(&self) -> u64 {
        self.requests.iter().map(|r| r.bytes_returned).sum()
    }

    fn record(
        &mut self,
        method: Method,
        key: &str,
        range: Option<String>,
        why: &str,
        status: u16,
        returned: Option<Span>,
    ) {
        let bytes = returned.map(|s| s.len()).unwrap_or(0);
        let start_us = self.clock_us;
        self.clock_us += self.model.cost_us(bytes);
        self.requests.push(Request {
            seq: self.requests.len() + 1,
            method,
            key: key.to_string(),
            range,
            why: why.to_string(),
            status,
            returned,
            bytes_returned: bytes,
            start_us,
            end_us: self.clock_us,
        });
    }
}

fn status_of(e: &StoreError) -> u16 {
    match e {
        StoreError::NotFound { .. } => 404,
        StoreError::RangeNotSatisfiable { .. } => 416,
    }
}

impl<S: ObjectStore> ObjectStore for TracingStore<S> {
    fn head(&mut self, key: &str, why: &str) -> Result<u64, StoreError> {
        let result = self.inner.head(key, why);
        let status = result.as_ref().map(|_| 200).unwrap_or_else(status_of);
        self.record(Method::Head, key, None, why, status, None);
        result
    }

    fn get(&mut self, key: &str, range: GetRange, why: &str) -> Result<GetResult, StoreError> {
        let result = self.inner.get(key, range, why);
        let (status, returned) = match &result {
            Ok(r) => (206, Some(r.span)),
            Err(e) => (status_of(e), None),
        };
        self.record(
            Method::Get,
            key,
            Some(range.header()),
            why,
            status,
            returned,
        );
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store() -> MemoryStore {
        let mut s = MemoryStore::new();
        s.put("data.parquet", (0u8..100).collect());
        s
    }

    #[test]
    fn a_bounded_range_returns_exactly_those_bytes() {
        let r = store()
            .get("data.parquet", GetRange::Bounded(Span::new(10, 14)), "")
            .unwrap();
        assert_eq!(r.bytes, [10, 11, 12, 13]);
        assert_eq!(r.span, Span::new(10, 14));
        assert_eq!(r.object_size, 100);
    }

    #[test]
    fn a_range_past_the_end_is_cut_short_not_refused() {
        let r = store()
            .get("data.parquet", GetRange::Bounded(Span::new(95, 200)), "")
            .unwrap();
        assert_eq!(r.span, Span::new(95, 100));
    }

    #[test]
    fn a_range_starting_past_the_end_is_416() {
        let e = store()
            .get("data.parquet", GetRange::Bounded(Span::new(100, 101)), "")
            .unwrap_err();
        assert!(matches!(
            e,
            StoreError::RangeNotSatisfiable { size: 100, .. }
        ));
    }

    #[test]
    fn a_suffix_range_needs_no_size_and_reports_it() {
        let r = store()
            .get("data.parquet", GetRange::Suffix(8), "")
            .unwrap();
        assert_eq!(r.span, Span::new(92, 100));
        assert_eq!(r.object_size, 100);
        let whole = store()
            .get("data.parquet", GetRange::Suffix(1000), "")
            .unwrap();
        assert_eq!(whole.span, Span::new(0, 100));
    }

    #[test]
    fn the_trace_records_every_request_and_its_cost() {
        let model = NetworkModel {
            latency_us: 1000,
            bandwidth_bytes_per_sec: 1_000_000,
        };
        let mut t = TracingStore::new(store(), model);
        t.head("data.parquet", "size").unwrap();
        t.get("data.parquet", GetRange::Suffix(8), "tail").unwrap();
        let _ = t.get("missing", GetRange::Suffix(8), "oops");
        assert_eq!(t.requests.len(), 3);
        assert_eq!(t.requests[0].method, Method::Head);
        assert_eq!(t.requests[1].range.as_deref(), Some("bytes=-8"));
        assert_eq!(t.requests[1].returned, Some(Span::new(92, 100)));
        assert_eq!(t.requests[2].status, 404);
        // 1000us per request, plus 8 bytes at a byte per microsecond for the GET.
        assert_eq!(t.requests[1].start_us, 1000);
        assert_eq!(t.requests[1].end_us, 2008);
        assert_eq!(t.elapsed_us(), 3008);
        assert_eq!(t.bytes_returned(), 8);
    }

    #[test]
    fn unlimited_bandwidth_costs_only_latency() {
        let m = NetworkModel {
            latency_us: 5,
            bandwidth_bytes_per_sec: 0,
        };
        assert_eq!(m.cost_us(1 << 30), 5);
    }
}
