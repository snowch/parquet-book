//! ch02's problems. Edit this file; `exercises/tests/anatomy_of_a_parquet_file.rs` grades it.

/// Problem 2.1: the footer length.
///
/// `trailer` is the last eight bytes of a Parquet file. Return the footer length they encode.
///
/// The first four bytes are an unsigned 32-bit integer, least significant byte first. Do not use
/// `u32::from_le_bytes`: write the arithmetic, one byte and one power of 256 at a time, so that
/// you can say what each byte contributes.
pub fn footer_length(trailer: [u8; 8]) -> u32 {
    let _ = trailer;
    todo!("problem 2.1")
}

/// Problem 2.2: where the footer is.
///
/// Given the file size and the footer length from its trailer, return the footer's byte range as
/// `Some((start, end))`, with `end` excluded. Return `None` when no valid file could have this
/// size and footer length: when the footer would overlap the four-byte opening magic, or when the
/// file is too small to hold the magic and the trailer at all.
pub fn footer_range(file_size: u64, footer_length: u32) -> Option<(u64, u64)> {
    let _ = (file_size, footer_length);
    todo!("problem 2.2")
}

/// Problem 2.3: how many `GET`s it takes to open a file.
///
/// A reader already knows the file size (from a directory listing). It reads the last `prefetch`
/// bytes of the file in one `GET`, never fewer than the eight-byte trailer, and fetches whatever
/// part of the footer that did not cover in a second `GET`.
///
/// Return how many `GET` requests it makes to have the whole footer. The test runs the book's
/// reader against a traced object store for many values of `prefetch` and counts.
pub fn gets_to_open(footer_length: u64, prefetch: u64) -> usize {
    let _ = (footer_length, prefetch);
    todo!("problem 2.3")
}
