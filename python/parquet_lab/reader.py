"""Opening a Parquet file that lives in an object store: finding and reading its footer.

The procedure, and the only one there is, because the footer is the only map of the file:

1. Find out how large the file is.
2. Read its last eight bytes: the footer length and the closing magic.
3. Work out where the footer starts: ``file_size - 8 - footer_length``.
4. Read the footer, and decode it.

Done literally, that is up to three round trips before a single value has been read. The
options below are the two ways real readers cut it down, and each changes the trace:

- **Where the size comes from.** A directory listing already has it, so no request is needed. A
  ``HEAD`` costs one. A suffix range (``bytes=-n``) returns the size in its response, so the size
  arrives with the tail.
- **How much tail to read.** Reading the last eight bytes exactly is the minimum. Reading more
  costs a few bytes and, when the footer fits inside what was read, saves the second ``GET``
  entirely. Readers call this prefetching the footer.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import Span
from .format import TRAILER_LEN, TooShort, Trailer, footer_span, parse_trailer
from .metadata import FileMetaData, decode_file_metadata
from .object_store import Bounded, GetRange, ObjectStore, Suffix


@dataclass(frozen=True)
class Head:
    """Ask the store with a ``HEAD`` request."""


@dataclass(frozen=True)
class Known:
    """Already known, from a directory listing or a table format's manifest (ch14)."""

    size: int


@dataclass(frozen=True)
class SuffixRange:
    """Do not ask: read the tail with a suffix range, and take the size from the response."""


SizeSource = Head | Known | SuffixRange
"""Where a reader learns the size of the file."""


@dataclass(frozen=True)
class FooterOptions:
    """The defaults are the literal procedure: ``HEAD``, then exactly the trailer, then exactly
    the footer."""

    size: SizeSource = Head()
    prefetch: int = TRAILER_LEN
    """How many bytes to read from the end of the file in the first ``GET``. Never less than the
    eight-byte trailer, whatever is asked for."""


@dataclass
class FooterRead:
    """Everything learned while opening the file, in the order it was learned."""

    file_size: int
    tail: Span
    """The bytes the first ``GET`` returned: the trailer and whatever was prefetched before it."""
    trailer: Trailer
    footer: Span
    footer_was_prefetched: bool
    """True when the footer was already inside the prefetched tail, so no second ``GET`` was
    made."""
    footer_bytes: bytes
    metadata: FileMetaData


def read_footer(store: ObjectStore, key: str, options: FooterOptions) -> FooterRead:
    """Open ``key`` in ``store``: find the footer, fetch it, and decode it."""
    want = max(options.prefetch, TRAILER_LEN)

    # Steps 1 and 2: the size, and the tail.
    match options.size:
        case Head():
            size = store.head(key, "learn the file size, to know where the end is")
            store.next_phase()
            tail = store.get(key, tail_range(size, want), "read the trailer")
        case Known(size):
            tail = store.get(key, tail_range(size, want), "read the trailer")
        case SuffixRange():
            tail = store.get(key, Suffix(want), "read the trailer; the response carries the file size")
    file_size = tail.object_size
    if len(tail.data) < TRAILER_LEN:
        raise TooShort(file_size)
    trailer = parse_trailer(tail.data[-TRAILER_LEN:], file_size)

    # Step 3: where the footer is.
    footer = footer_span(file_size, trailer.footer_length)

    # Step 4: fetch whatever part of the footer the tail did not already hold.
    footer_was_prefetched = tail.span.start <= footer.start
    if footer_was_prefetched:
        start = footer.start - tail.span.start
        footer_bytes = tail.data[start : start + footer.length]
    else:
        missing = Span(footer.start, tail.span.start)
        store.next_phase()
        head = store.get(key, Bounded(missing), "read the footer: the trailer says where it starts")
        overlap = footer.end - tail.span.start
        footer_bytes = head.data + tail.data[:overlap]

    metadata = decode_file_metadata(footer_bytes, footer.start)
    return FooterRead(file_size, tail.span, trailer, footer, footer_was_prefetched, footer_bytes, metadata)


def tail_range(size: int, want: int) -> GetRange:
    """The last ``want`` bytes of a file of ``size`` bytes, as a bounded range."""
    return Bounded(Span(max(size - want, 0), size))
