# Next steps

The working list. PLAN.md §2 has the phases; this is the order to do them in.

## Done: the first vertical slice

- Reader: byte primitives, trailer, footer range, Thrift compact decoding with spans, the names
  from `parquet.thrift`, typed `FileMetaData`, page-header walking, PLAIN scalars for statistics.
- Simulated object store with `HEAD`, bounded and suffix ranges, S3 semantics, a trace and a
  deterministic cost model; footer discovery with size-from-HEAD, size-from-listing, suffix range,
  and tail prefetch.
- WebAssembly build with a C ABI; the footer, anatomy and layouts laboratories.
- ch01 and ch02 written; problems 1.1, 2.1, 2.2, 2.3 with tests; generated figures.
- Checks: fixture reproducibility, figure staleness, numbers in prose, WASM/native parity, built
  links, headless-browser test of the experiments.

## Done: ch03, the type system

- Reader: full logical types (`logical.rs`) applied to values, the schema tree rebuilt from the
  flat list with maximum levels (`schema.rs`), statistics value spans.
- Fixture: `types.parquet`; every manifest now records pyarrow's reading of each leaf.
- Experiment: the schema panel (flat list, rebuilt tree, statistics read through logical types).
- Problems 3.1 to 3.3 with tests; 3.4 about the reader's own schema.

## Done: ch04, nested data

- Reader: the RLE / bit-packing hybrid with runs and spans (`rle.rs`), PLAIN values with spans
  (`plain.rs`), data page v1 bodies split into levels and values (`column.rs`), path levels,
  plain-English explanations of each triple, and record assembly (`nested.rs`), checked against
  pyarrow's rows for every column of every fixture.
- Fixture: `nested.parquet`. Experiment: the levels panel. Problems 4.1, 4.2 with tests; 4.3 open.

## Done: ch05, encodings

- Reader: dictionary pages and RLE_DICTIONARY indices, DELTA_BINARY_PACKED, DELTA_LENGTH_BYTE_ARRAY,
  DELTA_BYTE_ARRAY and BYTE_STREAM_SPLIT (`delta.rs`), behind one dispatcher that records every
  decode step with its bytes (`decode.rs`).
- Fixtures: `dictionary.parquet`, `encodings.parquet`. Experiment: the encodings stepper.
- Problems 5.1 to 5.3 with tests; 5.4 about the reader's own columns.

## Done: ch06, pages

- Reader: data page v2 bodies, v2 header fields, CRC-32 page checksums, rows per page
  (`column::first_rows`). Fixtures `pages.parquet` and `pages-v2.parquet`. The page walker panel.
- Problems 6.1 (walk a chunk) and 6.2 (CRC-32) with tests; 6.3 open.
- The Rust toolchain is pinned in `rust-toolchain.toml`, after a floating `stable` turned CI red.

## Done: ch07, compression

- Reader: Snappy, LZ4_RAW and GZIP (inflate) decompressors that record their tokens
  (`compress.rs`); the column reader decompresses v1 bodies, v2 values sections and dictionary
  pages. ZSTD and Brotli are refused by name (PLAN.md §4).
- Fixtures: `codec-{none,snappy,lz4,gzip,zstd,brotli}.parquet`, `codec-zstd-split.parquet`,
  `pages-v2-snappy.parquet`. Every decodable page matches `codec-none.parquet` byte for byte.
- Experiment: the compression panel (sizes per chunk, tokens stepped against the rebuilt page).
- Problems 7.1 (Snappy) and 7.2 (LZ4) with tests; 7.3 open.

## Done: ch08, metadata and statistics

- Reader: `stats.rs` (a comparator for every type, the mistaken order for each, and `bounds`,
  the rules for which statistics a reader may use); `Statistics` keeps the deprecated `min` and
  `max` apart from `min_value` and `max_value`; `column_orders` and `sorting_columns` decoded.
- Fixture `statistics.parquet`. The reader's orders reproduce pyarrow's bounds for every column
  chunk of every fixture. NaN is written to JSON as `"NaN"` instead of `null`.
- Experiment: the statistics panel. Problems 8.1 (sort orders) and 8.2 (which bounds); 8.3 open.

## Done: ch09, skipping data

- Reader: `prune.rs` (conditions judged against bounds, plans over statistics, Bloom filters and
  the page index, and the bytes of every column a plan reads); `page_index.rs` (ColumnIndex and
  OffsetIndex); `bloom.rs` (xxHash64 and split block Bloom filters). Indexes and filters appear
  in the structure view.
- Fixtures `pruning-sorted.parquet` and `pruning-shuffled.parquet`. Tests: the OffsetIndex
  matches the walked pages, the ColumnIndex matches each page's decoded values, every value
  passes its filter, and no plan skips a matching row, over hundreds of conditions.
- Experiment: the skipping panel. Problems 9.1 (can this be skipped?) and 9.2 (probe a filter);
  9.3 open.

## Next: ch10, how readers read

1. `TracingStore` gains a clock per connection, so concurrent requests overlap in time.
2. Reader: turn a plan into requests (one per page, coalesced within a gap, or whole chunks), and
   measure requests, bytes and simulated time under the network model.
3. Experiment: the same query under each strategy, with the request timeline.
4. The cost of large footers: a fixture with many columns and row groups.

## Then

- **ch11**: writing well, measured: row group and page sizes, sorting, dictionary fallback.
- **ch12**: a tiny query engine over the reader.

## Book infrastructure

- Search across pages (the reference book has one; this one does not yet).
- A figure of the file layout drawn as SVG by code, for readers without JavaScript.
- Hex view virtualisation for fixtures larger than a few kilobytes.
