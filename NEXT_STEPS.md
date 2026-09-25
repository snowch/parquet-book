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

## Next: ch03, the type system

1. Reader: build the schema tree from the flattened `SchemaElement` list (`num_children`),
   with max definition and repetition levels per leaf. Expose logical types fully (decimal scale
   and precision, timestamp unit and UTC flag).
2. Fixture: `types.parquet`, one column per physical type and the common logical types, a handful
   of rows. Nullable and required columns side by side.
3. Experiment: a schema panel over the footer: select a leaf, see its `SchemaElement`s' bytes, its
   physical and logical type, and its path.
4. Problems: rebuild the tree from the flat list; compute max levels.

## Then

- **ch04**: `nested.parquet`; decode levels by hand, then with the RLE hybrid from ch05 (write the
  level decoder in ch04 and reuse it).
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
