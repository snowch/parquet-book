---
title: Encodings
---

(encodings)=
# Encodings

## The question

How do values become compact bytes before any compressor sees them?

[ch04](#nested-data) read values that were stored PLAIN: each one written out in full,
little-endian, back to back. PLAIN is always correct and rarely small. A column of country codes
repeats a handful of strings. A column of order ids goes up by one each row. A column of URLs
shares most of every value with the value before it. PLAIN stores all of that repetition in full.

An **encoding** is a type-aware way of writing a column's values that exploits patterns like
these. It happens before compression ([ch07](#compression)), it knows what the values are, and a
reader can decode it quickly. This chapter reads the encodings a writer chooses between, from
their bytes.

## The experiment

### One column per encoding

`encodings.parquet` holds forty orders, and each column was written with the encoding that suits
its values. `dictionary.parquet` holds twelve orders written with the default, dictionary
encoding. [Appendix B](#the-fixtures) says how each was written.

```lab
experiment: encodings
fixture: encodings.parquet
fixtures: encodings.parquet, dictionary.parquet
```

The panel shows, for one column, what the encoding saved against PLAIN, and the decoder's own
record of how it read the values: every step, with the bytes it read. Step through each column:

1. **`order_id`** goes up by one each row. Step through it: a header, one block, and miniblocks
   with a bit width of zero. The values take no bytes at all beyond the header and the block's
   smallest delta.
2. **`ordered_at`** is a timestamp about a minute apart each row. The deltas vary a little, and a
   miniblock packs them in two bits each.
3. **`url`** shares a long prefix with the previous value. Look at the prefix lengths, then the
   suffixes: most suffixes are a single character.
4. **`weight_kg`** is a float. Its encoding stores the same number of bytes as PLAIN. Look at the
   last stream, and at how few different bytes it contains.
5. **Switch the file to `dictionary.parquet` and pick `country`.** A dictionary page holds each
   distinct country once, and the data page holds two-bit indices into it.

### What each encoding saved

The same measurement for every column of both files:

```{include} _generated/encodings-sizes.md
```

Every saving in the table comes from a pattern in the values, and so does the one loss. The
dictionary made `order_id` larger than PLAIN: every value is distinct, so the dictionary holds
all of them, and the indices come on top. A writer avoids this by falling back. It caps the
dictionary's size, and when a column chunk exceeds the cap it writes the remaining pages with
another encoding. A column with many distinct values ends up without a dictionary.

### Dictionary encoding

Dictionary encoding replaces each value with a small integer: its position in a list of the
column chunk's distinct values. The list is written once, as PLAIN, in a **dictionary page** at
the start of the column chunk. The data page then holds the indices, packed with the RLE /
bit-packing hybrid from [ch04](#nested-data), after one byte giving their bit width:

```{include} _generated/dictionary-country.md
```

Four distinct countries need two bits each. The header `05` is binary `101`: a bit-packed run of
two groups of eight, so the twelve indices are packed with four slots of padding after them.
Dictionary encoding also helps a reader: to find rows where `country` is `UK`, it can look `UK` up once in
the dictionary and then compare small integers, and if `UK` is not in the dictionary it can skip
the whole column chunk. [ch09](#skipping-data) uses that.

The data page's encoding is named `RLE_DICTIONARY`. Files from format version 1 name it
`PLAIN_DICTIONARY`, which is decoded the same way.

### DELTA_BINARY_PACKED

For integers that are sorted or change slowly, storing the differences between values is far
cheaper than storing the values. `DELTA_BINARY_PACKED` writes a header, then blocks. Each block
subtracts its smallest delta from all of its deltas, so every adjusted delta is zero or more, and
splits them into miniblocks, each bit-packed at the width its largest adjusted delta needs:

```{include} _generated/delta-ordered-at.md
```

The timestamps are about a minute apart, so the smallest delta is large, but the adjusted deltas
are all small and fit in two bits. Deltas that never vary, like `order_id`'s, adjust to zero and
pack into a width of zero: a miniblock with no bytes at all.

### The delta encodings for strings

Two encodings apply the same idea to byte arrays.

**`DELTA_LENGTH_BYTE_ARRAY`** writes every value's length first, as `DELTA_BINARY_PACKED`, then
all the values' bytes back to back. The `sku` column's values are all the same length, so the
lengths cost almost nothing, and the bytes are stored without a length in front of each.

**`DELTA_BYTE_ARRAY`** writes, for each value, how many leading bytes it shares with the value
before it, then only the rest. Sorted strings with common prefixes, such as URLs, paths and
hierarchical keys, shrink the most:

```{include} _generated/delta-urls.md
```

### BYTE_STREAM_SPLIT

`BYTE_STREAM_SPLIT` does not make anything smaller. It rearranges a column of fixed-width values
into one stream per byte position: every value's first byte, then every value's second byte, and
so on. The low bytes of a float's mantissa look random; its sign and exponent byte barely changes:

```{include} _generated/split-weights.md
```

The last stream holds the sign and exponent, and has almost no variety. Written PLAIN, those
bytes are scattered one in every four. Written split, they sit together, where a compressor can
find the repetition. [ch07](#compression) measures what that is worth.

### Which encodings writers use

Most writers try dictionary encoding first for every column, and fall back when a dictionary
grows too large. Repetition and definition levels always use the RLE / bit-packing hybrid. The
delta encodings and `BYTE_STREAM_SPLIT` are usually opt-in, set per column; pyarrow wrote
`encodings.parquet` only because the generator asked, and only with dictionary encoding turned
off. The encodings a column chunk used are recorded in its metadata, so a reader never has to
guess.

## Building it

### A dictionary page, then indices

The column reader decodes a dictionary page, when the column chunk has one, before any data page,
and keeps its entries with the bytes each came from:

```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: "DICTIONARY_PAGE" => {
:end-before: "DATA_PAGE_V2" =>
```

A data page's indices are the hybrid from [ch04](#nested-data), with the bit width in the byte
before them. Each decoded value keeps two spans: its dictionary entry, and the run that held its
index:

```{literalinclude} ../crates/parquet-lab/src/decode.rs
:language: rust
:start-at: "RLE_DICTIONARY" | "PLAIN_DICTIONARY" => {
:end-before: "DELTA_BINARY_PACKED" => {
```

### Deltas

The delta decoder reads the header, then block after block until it has the value count. It
records a step for the header, each block, and each miniblock it reads:

```{literalinclude} ../crates/parquet-lab/src/delta.rs
:language: rust
:start-at: pub fn binary_packed(
:end-before: /// DELTA_LENGTH_BYTE_ARRAY:
```

`DELTA_BYTE_ARRAY` is two decoders and one loop: the prefix lengths are `DELTA_BINARY_PACKED`,
the suffixes are `DELTA_LENGTH_BYTE_ARRAY`, and each value is the previous value's prefix
followed by its suffix:

```{literalinclude} ../crates/parquet-lab/src/delta.rs
:language: rust
:start-at: pub fn byte_array(
:end-before: /// One BYTE_STREAM_SPLIT value
```

### Checking it

Every column of both fixtures is decoded from its bytes, reassembled into records, and compared
with the rows pyarrow reported:

```bash
cargo test -p parquet-lab --test fixtures records_rebuilt
```

## What this cannot tell you

**How much encoding saves on your data.** The fixtures' columns were chosen to suit their
encodings. Real columns are messier: a sorted id column with gaps, a URL column in random order.
The savings in the table are what these values gave, and yours will differ.

**Which encoding a writer should choose.** That depends on what the values look like, on what the
compressor adds afterwards, and on which readers must open the file. [ch07](#compression) and
[ch11](#writing-parquet-well) weigh those.

**How fast decoding is.** This reader decodes one value at a time so that every step is visible.
Production readers decode whole miniblocks and runs with vectorised code, and their speed is a
property of their implementation, not of anything measured here.

**Every encoding and type pairing.** The reader decodes the encodings writers use for data pages.
It does not decode the deprecated `BIT_PACKED` level encoding, or `RLE` for boolean values, which
only data page version 2 uses; [ch06](#pages) returns to that.

## Key takeaways

:::{div}
:class: takeaways

- **Encoding is type-aware and happens before compression.** It exploits repetition, small ranges
  and sortedness that a byte-level compressor would miss or find expensively.
- **Dictionary encoding stores each distinct value once and indices for the rest.** It is the
  default, it suits columns with few distinct values, and writers fall back when it stops paying.
- **Delta encodings store differences.** Sorted or slowly changing integers, and strings with
  shared prefixes, shrink the most.
- **BYTE_STREAM_SPLIT rearranges rather than shrinks.** It puts the similar bytes of fixed-width
  values together for a compressor.
- **Every encoding is recorded in the metadata.** A reader decodes what the file says, never what
  it guesses.
:::

## Problems

Four, in `exercises/src/encodings.rs`. The first three have tests. The fourth has none.

**5.1 DELTA_BINARY_PACKED.** Decode it. The test uses the fixture's integer columns and hundreds of
generated encodings with other block sizes, miniblock counts and bit widths.

```bash
cargo test -p exercises --test encodings problem_5_1 -- --ignored
```

**5.2 Shared prefixes.** Rebuild `DELTA_BYTE_ARRAY`'s values from their prefix lengths and
suffixes. The test uses the fixture's URLs and generated sorted strings.

```bash
cargo test -p exercises --test encodings problem_5_2 -- --ignored
```

**5.3 Dictionary indices.** Read a dictionary-encoded page's bit width and indices, and return the
values. You may use your hybrid decoder from problem 4.1.

```bash
cargo test -p exercises --test encodings problem_5_3 -- --ignored
```

**5.4 Your own columns.** No test: the columns are yours. Pick a Parquet file your systems write
and run `cargo run -p pqlab -- encodings FILE COLUMN` for each column. For each, record the
encoding the writer chose and the stored size against PLAIN. Then name one column where a
different encoding would suit the values better, and say what pattern in the values makes you
think so. A good answer checks the claim by rewriting that column with the other encoding and
measuring; if the saving does not appear, say what the values do that you did not expect.

## Where to go next

- Every encoding is specified in the format repository's
  [Encodings.md](https://github.com/apache/parquet-format/blob/master/Encodings.md).
- The delta encoding's block and miniblock layout follows Lemire and Boytsov's
  [Decoding billions of integers per second through vectorization](https://arxiv.org/abs/1209.2137).
- [ch06](#pages) looks at the pages these values live in, and [ch07](#compression) at what a
  compressor adds after encoding.
