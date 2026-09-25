//! ch06's problems. Edit this file; `exercises/tests/pages.rs` grades it.

/// Problem 6.1: walk a column chunk.
///
/// `chunk` is a column chunk's bytes, whose first byte is at file offset `base`. It is a run of
/// pages, each a Thrift `PageHeader` followed by `compressed_page_size` bytes of body. Return the
/// file offset at which every page starts.
///
/// You may decode each header with the book's Thrift decoder:
/// `parquet_lab::thrift::read_struct(&mut parquet_lab::bytes::ByteReader::new(bytes, base))`
/// reads one struct and leaves the reader after it. `compressed_page_size` is field 3.
pub fn page_starts(chunk: &[u8], base: u64) -> Vec<u64> {
    let _ = (chunk, base);
    todo!("problem 6.1")
}

/// Problem 6.2: check a page's checksum.
///
/// Compute the CRC-32 (the IEEE polynomial, reflected, as zlib computes it) of `body`, and say
/// whether it equals `stored`, the signed 32-bit integer from the page header. Write the CRC
/// yourself; do not call `parquet_lab::bytes::crc32`.
pub fn crc_matches(body: &[u8], stored: i32) -> bool {
    let _ = (body, stored);
    todo!("problem 6.2")
}
