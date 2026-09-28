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

### Read the encodings yourself

`encodings.parquet` holds forty orders, and each column was written with the encoding that suits
its values. `dictionary.parquet` holds twelve orders written with the default, dictionary
encoding. [Appendix B](#the-fixtures) says how pyarrow wrote each.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name. Each step finds the footer as
[ch02](#anatomy-of-a-parquet-file) did, and the reader's `walk_pages` finds a column chunk's
pages as it did in [ch04](#nested-data). Every column in both files is required, so a data page's
body holds values and no levels.

**A run of deltas.** `ordered_at` is a plain `INT64` with no logical type: a count of seconds
since 1970, with rows about a minute apart. pyarrow wrote it as `DELTA_BINARY_PACKED`. Read the
start of its page by hand, with two small helpers for the varints: ULEB128, as in the run headers
of [ch04](#nested-data), and zigzag, as in the footer's Thrift fields in [ch03](#the-type-system):

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/encodings/delta_header.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/delta_header.rs
:language: rust
```
:::
::::

The page body is far smaller than the values written PLAIN, at eight bytes each. It opens with a
header of four varints: how many values a block holds, how many miniblocks a block is split into,
how many values the page holds, and the first value. No other value is stored whole: the rest of
the page is differences.

Then comes a block. It starts with the smallest difference between neighbouring values, and one
byte per miniblock giving a bit width. Each delta is stored as its excess over the smallest, in
that many bits. The first deltas the step unpacked are all close to a minute, so their excess
over the smallest fits in two bits. The page's deltas all fit in the first miniblock, and the
others hold none: their width bytes are zero.

Change `column` to 0, which is `order_id`. Its values go up by one, so every delta equals the
smallest. Look at the bit widths, and at how many bytes the page body takes.

**A dictionary.** `country` in `dictionary.parquet` repeats a handful of strings. Its column
chunk holds two pages. Read both:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/encodings/dictionary_by_hand.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/dictionary_by_hand.rs
:language: rust
```
:::
::::

The first page is a *dictionary page*: each distinct country once, written PLAIN, in the order
the writer first met it. The data page after it holds no strings at all. It holds one byte giving
a bit width, then a run of the RLE / bit-packing hybrid from [ch04](#nested-data), with the
position of each row's country in the dictionary. Four entries need two bits each, so the whole
column's values fit in the few bytes the step printed.

Change `slots` to `8 * (header >> 1)`, the number of slots the run's groups hold, and look at the
indices after the page's own.

**The reader, step by step.** The book's reader decodes every encoding the steps met, and a few
more. For each page it keeps a record of every step: a label, the bytes it read, and what it read
from them. Ask it for `url`, which pyarrow wrote as `DELTA_BYTE_ARRAY`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/encodings/decode_a_column.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/decode_a_column.rs
:language: rust
```
:::
::::

The page holds two runs of `DELTA_BINARY_PACKED` integers and then some bytes. The first run is
the *prefix lengths*: how many leading bytes each URL shares with the URL before it. The first
URL shares none, and the deltas after it say that most of the others share all but their last
character. The second run is the lengths of what is left of each URL, and the bytes are those
suffixes, back to back. Only the first URL is stored in full.

Change `name` to `"order_id"`, `"sku"` or `"weight_kg"` and run the step again. `order_id` is the
first step's other column, read by the reader. `sku`'s strings are all the same length, and its
lengths take no bytes beyond their header and block. `weight_kg` is a float, split into four
streams; look at how few different bytes the last stream holds. Then open `dictionary.parquet`
and ask for `"country"`: the reader finds the same dictionary and indices as the second step.

### What each encoding saved

The same measurement for every column of both files:

```{include} _generated/encodings-sizes.md
```

Every saving in the table comes from a pattern in the values, and so does the one loss. The
dictionary made `order_id` larger than PLAIN: every value is distinct, so the dictionary holds
all of them, and the indices come on top.

pyarrow falls back from a dictionary on its size, not on what it saves. It caps the dictionary's
size, and when a column chunk's dictionary outgrows the cap it writes the remaining pages with
another encoding. `order_id`'s dictionary is far below the default cap, so pyarrow kept it, and
the loss stands. A column of distinct values escapes its dictionary only once there are enough of
them to fill the cap. parquet-java also checks what the dictionary saves: after the first
page, it drops the dictionary if the dictionary and its indices are not smaller than the
plain values would be.

### Dictionary encoding

Dictionary encoding replaces each value with a small integer: its position in a list of the
column chunk's distinct values. The list is written once, as PLAIN, in a dictionary page at the
start of the column chunk. The data page then holds the indices, packed with the RLE /
bit-packing hybrid, after one byte giving their bit width. That is the layout the second step
read.

The run header `05` that the step printed is binary `101`: a bit-packed run of two groups of
eight. The page has twelve rows, so the run ends with four slots of padding. Dictionary encoding
also helps a reader: to find rows where `country` is `UK`, it can look `UK` up once in the
dictionary and then compare small integers, and if `UK` is not in the dictionary it can skip the
whole column chunk. Some readers do both. The reader in this book does neither, as
[ch09](#skipping-data) notes.

The data page's encoding is named `RLE_DICTIONARY`. Files from format version 1 name it
`PLAIN_DICTIONARY`, which is decoded the same way.

### DELTA_BINARY_PACKED

For integers that are sorted or change slowly, storing the differences between values is far
cheaper than storing the values. `DELTA_BINARY_PACKED` writes a header, then blocks. Each block
subtracts its smallest delta from all of its deltas, so every adjusted delta is zero or more, and
splits them into miniblocks, each bit-packed at the width its largest adjusted delta needs. The
block starts with its smallest delta and one byte per miniblock giving that miniblock's width.
This is `ordered_at`'s page, as the reader decodes it:

```{include} _generated/delta-ordered-at.md
```

The values are about a minute apart, so the smallest delta is large, but the adjusted deltas
are all small and fit in two bits. Deltas that never vary, like `order_id`'s, adjust to zero and
pack into a width of zero: a miniblock with no bytes at all.

### The delta encodings for strings

Two encodings apply the same idea to byte arrays.

**`DELTA_LENGTH_BYTE_ARRAY`** writes every value's length first, as `DELTA_BINARY_PACKED`, then
all the values' bytes back to back. The `sku` column's values are all the same length, so the
lengths cost almost nothing, and the bytes are stored without a length in front of each.

**`DELTA_BYTE_ARRAY`** writes, for each value, how many leading bytes it shares with the value
before it, then only the rest. Sorted strings with common prefixes, such as URLs, paths and
hierarchical keys, shrink the most. These are the first of `url`'s prefix lengths and suffixes,
added up from the deltas the third step printed:

```{include} _generated/delta-urls.md
```

A URL that carries into a new digit, such as the step from `109` to `110`, shares one byte fewer
and stores two.

### BYTE_STREAM_SPLIT

`BYTE_STREAM_SPLIT` does not make anything smaller. It rearranges a column of fixed-width values
into one stream per byte position: every value's first byte, then every value's second byte, and
so on. Each byte position varies in its own way:

```{include} _generated/split-weights.md
```

The last stream holds the sign and most of the exponent, and has almost no variety. The stream
before it, the top of the mantissa, varies most. The two low streams repeat a few bytes, because
these weights go up in steps of a twentieth, and the mantissa of such a fraction repeats one bit
pattern. In measured data the low bytes usually vary far more. Written PLAIN, the exponent bytes
are scattered one in every four. Written split, they sit together, where a compressor can
find the repetition. [ch07](#compression) measures what that is worth.

### Which encodings writers use

Most writers try dictionary encoding first for every column, and fall back when a dictionary
grows too large. Repetition and definition levels always use the RLE / bit-packing hybrid. The
delta encodings and `BYTE_STREAM_SPLIT` are usually opt-in, set per column; pyarrow wrote
`encodings.parquet` only because the generator asked, and only with dictionary encoding turned
off. The encodings a column chunk used are recorded in its metadata, so a reader never has to
guess.

## Building it

The steps read a delta header and a dictionary by hand, then asked the reader to decode a column.
This section builds the reader's parts they used: the dictionary page and its indices, the delta
decoder, and the loop that rebuilds strings from shared prefixes. The tabs switch every excerpt
on the page between the two languages.

### A dictionary page, then indices

The column reader decodes a dictionary page, when the column chunk has one, before any data page,
and keeps its entries with the bytes each came from:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/column.py
:language: python
:start-at: if page.page_type == "DICTIONARY_PAGE":
:end-before: if page.page_type not in (
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: "DICTIONARY_PAGE" => {
:end-before: other => return err(format!("unexpected page type
```
:::
::::

A data page's indices are the hybrid from [ch04](#nested-data), with the bit width in the byte
before them. Each decoded value keeps two spans: its dictionary entry, and the run that held its
index. The bit width and each run become a step, which the third step prints for `country`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/decode.py
:language: python
:start-at: # One byte of bit width, then the indices
:end-before: end = runs[-1].body.end if runs else base + 1
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/decode.rs
:language: rust
:start-at: // One byte of bit width, then the indices
:end-before: let end = runs.last().map(|r| r.body.end)
```
:::
::::

### Deltas

The delta decoder reads the header's four varints, as the first step did, then block after block
until it has the value count. Each block opens with its smallest delta and the miniblocks' bit
widths:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/delta.py
:language: python
:start-at: def binary_packed(data: bytes, base: int)
:end-before: for m, w in enumerate(widths):
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/delta.rs
:language: rust
:start-at: pub fn binary_packed(
:end-before: for (m, &w) in widths.iter().enumerate() {
```
:::
::::

Each miniblock holds a fixed number of deltas at its own width. The decoder unpacks each one's
bits, lowest first, adds the smallest delta back, and adds the result to the previous value. A
miniblock past the value count has a width byte and no body:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/delta.py
:language: python
:start-at: for m, w in enumerate(widths):
:end-before: block += 1
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/delta.rs
:language: rust
:start-at: for (m, &w) in widths.iter().enumerate() {
:end-before: block += 1;
```
:::
::::

`DELTA_BYTE_ARRAY` is two decoders and one loop. The prefix lengths are read with
`binary_packed`, the suffixes with the decoder for `DELTA_LENGTH_BYTE_ARRAY`, and each value is
the previous value's prefix followed by its suffix:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/delta.py
:language: python
:start-at: prev = b""
:end-before: def byte_stream_split(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/delta.rs
:language: rust
:start-at: let mut prev: Vec<u8> = Vec::new();
:end-before: /// One BYTE_STREAM_SPLIT value
```
:::
::::

### Checking it

Every column of both fixtures is decoded from its bytes, reassembled into records, and compared
with the rows pyarrow reported:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests -k records_rebuilt
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures records_rebuilt
```
:::
::::

### Ask a library

A library decodes every encoding for you, and records in the metadata which ones each column
chunk used. pyarrow can also keep a dictionary-encoded column as a dictionary when it reads it.
The `parquet` crate reads a column chunk page by page, and says each page's type and encoding:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/encodings/encodings_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/encodings_with_a_library.rs
:language: rust
```
:::
::::

Both list each column chunk's encodings from its metadata. `RLE` appears beside the encoding of the
values because a data page's header names an encoding for its levels, and pyarrow records it even
for a required column that stores none. pyarrow's `read_dictionary` hands back an Arrow
`DictionaryArray`, whose dictionary and indices are the ones the second step read by hand. The
crate's metadata gives the offset of the dictionary page, and its page reader returns that page
first, then the data page with its count of values.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin encodings_with_a_library
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
- **A library decodes every encoding for you.** pyarrow and the `parquet` crate list each column
  chunk's encodings, and pyarrow can hand a dictionary-encoded column back as its dictionary and
  indices.
:::

## Problems

Four, in `exercises/python/encodings.py`, or in Rust in
`exercises/src/encodings.rs`. The first three have tests. The fourth has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: encodings
```

**5.1 DELTA_BINARY_PACKED.** Decode it. The test uses the fixture's integer columns and hundreds of
generated encodings with other block sizes, miniblock counts and bit widths.

**5.2 Shared prefixes.** Rebuild `DELTA_BYTE_ARRAY`'s values from their prefix lengths and
suffixes. The test uses the fixture's URLs and generated sorted strings.

**5.3 Dictionary indices.** Read a dictionary-encoded page's bit width and indices, and return the
values. You may use your hybrid decoder from problem 4.1.

**5.4 Your own columns.** No test: the columns are yours. Pick a Parquet file your systems write
and run `PYTHONPATH=python python3 -m parquet_lab encodings FILE COLUMN` or
`cargo run -p pqlab -- encodings FILE COLUMN` for each column. For each, record the
encoding the writer chose and the stored size against PLAIN. Then name one column where a
different encoding would suit the values better, and say what pattern in the values makes you
think so. A good answer checks the claim by rewriting that column with the other encoding and
measuring; if the saving does not appear, say what the values do that you did not expect.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_5_1` in Python, or `problem_5_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_encodings.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test encodings -- --ignored
```
:::
::::

## Where to go next

- Every encoding is specified in the format repository's
  [Encodings.md](https://github.com/apache/parquet-format/blob/master/Encodings.md).
- The delta encoding's block and miniblock layout follows Lemire and Boytsov's
  [Decoding billions of integers per second through vectorization](https://arxiv.org/abs/1209.2137).
- [ch06](#pages) looks at the pages these values live in, and [ch07](#compression) at what a
  compressor adds after encoding.
