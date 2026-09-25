//! Opening a Parquet file that lives in an object store: finding and reading its footer.
//!
//! The procedure, and the only one there is, because the footer is the only map of the file:
//!
//! 1. Find out how large the file is.
//! 2. Read its last eight bytes: the footer length and the closing magic.
//! 3. Work out where the footer starts: `file_size - 8 - footer_length`.
//! 4. Read the footer, and decode it.
//!
//! Done literally, that is up to three round trips before a single value has been read. The
//! options below are the two ways real readers cut it down, and each changes the trace:
//!
//! - **Where the size comes from.** A directory listing already has it, so no request is
//!   needed. A `HEAD` costs one. A suffix range (`bytes=-n`) returns the size in its response,
//!   so the size arrives with the tail.
//! - **How much tail to read.** Reading the last eight bytes exactly is the minimum. Reading
//!   more costs a few bytes and, when the footer fits inside what was read, saves the second
//!   `GET` entirely. Readers call this prefetching the footer.

use std::fmt;

use crate::bytes::Span;
use crate::format::{footer_span, parse_trailer, FormatError, Trailer, TRAILER_LEN};
use crate::metadata::{decode_file_metadata, FileMetaData, MetadataError};
use crate::object_store::{GetRange, ObjectStore, StoreError};

/// Where a reader learns the size of the file.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SizeSource {
    /// Ask the store with a `HEAD` request.
    Head,
    /// Already known, from a directory listing or a table format's manifest (ch14).
    Known(u64),
    /// Do not ask: read the tail with a suffix range, and take the size from the response.
    SuffixRange,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FooterOptions {
    pub size: SizeSource,
    /// How many bytes to read from the end of the file in the first `GET`. Never less than the
    /// eight-byte trailer, whatever is asked for.
    pub prefetch: u64,
}

impl Default for FooterOptions {
    /// The literal procedure: `HEAD`, then exactly the trailer, then exactly the footer.
    fn default() -> Self {
        FooterOptions {
            size: SizeSource::Head,
            prefetch: TRAILER_LEN,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReadError {
    Store(StoreError),
    Format(FormatError),
    Metadata(MetadataError),
}

impl fmt::Display for ReadError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ReadError::Store(e) => write!(f, "{e}"),
            ReadError::Format(e) => write!(f, "{e}"),
            ReadError::Metadata(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for ReadError {}

impl From<StoreError> for ReadError {
    fn from(e: StoreError) -> Self {
        ReadError::Store(e)
    }
}
impl From<FormatError> for ReadError {
    fn from(e: FormatError) -> Self {
        ReadError::Format(e)
    }
}
impl From<MetadataError> for ReadError {
    fn from(e: MetadataError) -> Self {
        ReadError::Metadata(e)
    }
}

/// Everything learned while opening the file, in the order it was learned.
#[derive(Clone, Debug, PartialEq)]
pub struct FooterRead {
    pub file_size: u64,
    /// The bytes the first `GET` returned: the trailer and whatever was prefetched before it.
    pub tail: Span,
    pub trailer: Trailer,
    pub footer: Span,
    /// True when the footer was already inside the prefetched tail, so no second `GET` was made.
    pub footer_was_prefetched: bool,
    pub footer_bytes: Vec<u8>,
    pub metadata: FileMetaData,
}

/// Open `key` in `store`: find the footer, fetch it, and decode it.
pub fn read_footer<S: ObjectStore>(
    store: &mut S,
    key: &str,
    options: FooterOptions,
) -> Result<FooterRead, ReadError> {
    let want = options.prefetch.max(TRAILER_LEN);

    // Steps 1 and 2: the size, and the tail.
    let tail = match options.size {
        SizeSource::Head => {
            let size = store.head(key, "learn the file size, to know where the end is")?;
            store.next_phase();
            store.get(key, tail_range(size, want), "read the trailer")?
        }
        SizeSource::Known(size) => store.get(key, tail_range(size, want), "read the trailer")?,
        SizeSource::SuffixRange => store.get(
            key,
            GetRange::Suffix(want),
            "read the trailer; the response carries the file size",
        )?,
    };
    let file_size = tail.object_size;
    if tail.bytes.len() < TRAILER_LEN as usize {
        return Err(FormatError::TooShort { file_size }.into());
    }
    let t = &tail.bytes[tail.bytes.len() - TRAILER_LEN as usize..];
    let trailer = parse_trailer([t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7]], file_size)?;

    // Step 3: where the footer is.
    let footer = footer_span(file_size, trailer.footer_length)?;

    // Step 4: fetch whatever part of the footer the tail did not already hold.
    let footer_was_prefetched = tail.span.start <= footer.start;
    let footer_bytes = if footer_was_prefetched {
        let from = (footer.start - tail.span.start) as usize;
        tail.bytes[from..from + footer.len() as usize].to_vec()
    } else {
        let missing = Span::new(footer.start, tail.span.start);
        store.next_phase();
        let head = store.get(
            key,
            GetRange::Bounded(missing),
            "read the footer: the trailer says where it starts",
        )?;
        let mut bytes = head.bytes;
        let overlap = (footer.end - tail.span.start) as usize;
        bytes.extend_from_slice(&tail.bytes[..overlap]);
        bytes
    };

    let metadata = decode_file_metadata(&footer_bytes, footer.start)?;
    Ok(FooterRead {
        file_size,
        tail: tail.span,
        trailer,
        footer,
        footer_was_prefetched,
        footer_bytes,
        metadata,
    })
}

/// The last `want` bytes of a file of `size` bytes, as a bounded range.
fn tail_range(size: u64, want: u64) -> GetRange {
    GetRange::Bounded(Span::new(size.saturating_sub(want), size))
}
