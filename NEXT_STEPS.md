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

## Next: ch04, nested data

1. Fixture: `nested.parquet` with a list of structs containing a list (the sales `items` example),
   nullable at every level, a handful of records including an empty list and a null list.
2. Reader: the RLE/bit-packing hybrid decoder for levels (written here, reused by ch05), data page
   v1 bodies split into repetition levels, definition levels and values.
3. Record assembly: levels and values back into records, checked against pyarrow's rows.
4. Experiment: a levels panel stepping through (r, d, value) triples with the bytes of each.

## Then

- **ch05**: `dictionary.parquet`; decoders for PLAIN, RLE/bit-packing, dictionary, delta; a
  stepper panel that decodes one run at a time from the page body bytes.
- **ch06**: data page v1 and v2 bodies, split into levels and values.
- **ch07**: decompression. Snappy and ZSTD decoders are large; decide whether to write teaching
  decoders (Snappy is small enough) and gate ZSTD behind a comparison with a production crate,
  kept out of the zero-dependency reader. Record the decision in PLAN.md §4.
- **ch08 to ch10**: `statistics.parquet`, `pruning.parquet`; pruning decisions, page indexes, Bloom
  filters; request coalescing and concurrency in `TracingStore` (a clock per connection).
- **ch12**: a tiny query engine over the reader.

## Book infrastructure

- Search across pages (the reference book has one; this one does not yet).
- A figure of the file layout drawn as SVG by code, for readers without JavaScript.
- Hex view virtualisation for fixtures larger than a few kilobytes.
