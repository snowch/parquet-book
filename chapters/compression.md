---
title: Compression
---

(compression)=
# Compression

## The question

What does compression add on top of encoding, and what does it cost?

[ch05](#encodings) made values compact using what they are: integers that go up by one, strings
that share prefixes, a few countries repeated. [ch06](#pages) showed that every page header
carries two sizes, and that in the fixtures so far they were equal. They differ once a writer
compresses its pages.

A **codec** is a general-purpose compressor applied to each page after encoding. It knows
nothing about types. It sees bytes, finds repetition in them, and writes it more briefly. The
column chunk's metadata names the codec, and a reader must undo it before it can decode anything
the page holds.

## The experiment

### One table, six codecs

The `codec-*.parquet` files hold the same orders, encoded the same way: PLAIN, no dictionary.
Only the codec differs, so their pages are identical before compression, and any difference in
size is the codec's. [Appendix B](#the-fixtures) lists how each was written.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name. Each step finds the footer as
[ch02](#anatomy-of-a-parquet-file) did, decodes it with the reader's `decode_file_metadata` from
[ch03](#the-type-system), and finds a column chunk's page with `walk_pages` from [ch06](#pages).

**Snappy by hand.** A Snappy page starts with a varint, the length of what comes out. Then come
elements, each opening with a tag byte whose low two bits say what it is. `00` is a literal:
bytes to copy from the input as they are. The other three are copies: bytes to repeat from
earlier in the output, given how far back they start and how many there are. Undo the `country`
page of `codec-snappy.parquet`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/compression/snappy_by_hand.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/snappy_by_hand.rs
:language: rust
```
:::
::::

A PLAIN string is a four-byte length and then its bytes, so the page starts `02 00 00 00`, then
`UK`. The first element is a literal: those six bytes, as they are. The next country's length
prefix is the same four bytes, and Snappy writes it as a copy from six bytes back, in two bytes.
The country code itself is a literal, because Snappy's compressor never copies fewer than four
bytes. The last line checks the result: the elements wrote exactly as many bytes as the varint
promised and the page header says.

Print `tokens[-6:]` instead (`tokens.iter().rev()` in Rust, which lists them last first). Once the
five countries have all appeared, the page repeats with a fixed period, and from there every
element is a copy from one period back, longer than the distance it reaches. A copy may overlap
the bytes it writes, which is why the step copies a byte at a time. Then change the column to
`5`, `distance_km`: noisy floating point, mostly long literals with short copies between them.

This is the **LZ77** idea every codec here shares: replace a run of bytes the output already
holds with how far back it is and how long. The codecs differ in how they write those references
down, and in what else they do.

**Three codecs, one page.** The reader's `compress.decompress` takes a codec's name from the
footer, a page's compressed bytes and the size its header promises. Give it the `country` page
from three files, and compare each result with the same page in `codec-none.parquet`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/compression/every_codec_one_page.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/every_codec_one_page.rs
:language: rust
```
:::
::::

Every codec gives back the uncompressed file's page, byte for byte, and each gets there in a
different number of bytes and tokens. The reader counts the Snappy varint as a token, so its
count is one more than the first step's. The GZIP tokens include the stream's header and trailer.

Change the column to `5`, `distance_km`: every codec saves far less, and needs hundreds of tokens.
Add `"zstd"` to the list: the reader refuses, because it does not decode ZSTD. In Python, compare
`out.data` with `zlib.decompress(body, 31)`, which inflates a GZIP page with the standard library.

The reader also counted what each token wrote:

```{include} _generated/codec-country-page.md
```

% number-ok: format constants of Snappy and DEFLATE, fixed by their specifications.
**Snappy** limits a copy to 64 bytes, so a long repeat is many copies in a row. **LZ4** writes a
match's length in a nibble and extends it a byte at a time, so one match covers nearly the whole
page. **GZIP** wraps DEFLATE, whose copies stop at 258 bytes, but whose tokens are Huffman codes:
the literals and lengths that occur most get the fewest bits. That second step, **entropy
coding**, is what the smaller codecs add. ZSTD and Brotli do it too, with more elaborate
machinery.

### Step through the tokens

The panel runs the same decompressors on one page, and draws what each token did. Each token
highlights the compressed bytes it read and, in the decompressed page, the bytes it wrote. A copy
also outlines the earlier bytes it repeated.

```lab
experiment: compression
fixture: codec-snappy.parquet
fixtures: codec-snappy.parquet, codec-lz4.parquet, codec-gzip.parquet, pages-v2-snappy.parquet
column: 1
```

Step through the `country` page under Snappy, and watch a copy's outline stay a period behind
what it writes. Switch to `codec-lz4.parquet` and find the one token that writes most of the
page. Switch to `codec-gzip.parquet`: the tokens do the same work, but each is written in a few
bits rather than whole bytes, so neighbouring tokens share a byte. Then open
`pages-v2-snappy.parquet` and pick `country`. In version 2 data pages the levels sit in front of
the compressed section, untouched.

### What each codec saved

The whole file under each codec:

```{include} _generated/codec-files.md
```

The codecs fall into two groups. Snappy and LZ4 land close together. GZIP, ZSTD and Brotli all
land smaller, and Brotli is smallest here. The two groups differ in method: Snappy and LZ4 only
replace repeated bytes with references to earlier ones, and the other three also give common
bytes shorter codes.

The same measurement column by column says more. The first table holds the codecs that only
copy, the second the codecs that also code:

```{include} _generated/codec-columns.md
```

The columns differ far more than the codecs do. `country` and `note` repeat a few values, and
every codec shrinks them to a small fraction. `distance_km` is noisy floating point, and every
codec saves least on it. `order_id` is a counter: no value repeats, and Snappy and LZ4 find only
the runs of zero bytes between the low bytes. The codecs that also give frequent bytes short
codes do much better, because most of each value's bytes are zero. A delta encoding would store
it in almost nothing, as [ch05](#encodings) showed.

Encoding and compression are not rivals. An encoding uses what it knows about the type; a codec
finds whatever repetition is left.

### Encoding before compression

[ch05](#encodings) said that `BYTE_STREAM_SPLIT` does not shrink anything by itself, and that a
compressor might find more in its output. `codec-zstd-split.parquet` is `codec-zstd.parquet`
with both float columns split:

```{include} _generated/codec-split.md
```

Splitting helped `distance_km` and hurt `weight_kg`. The noisy floats behave as [ch05](#encodings)
described: the sign and exponent bytes barely change, and once they sit together the compressor
finds them. The weights are different. Each is a number of kilograms to two decimal places, and a
decimal fraction has no exact binary form: its mantissa is a repeating bit pattern. Set the
second step's column to `4`, `weight_kg`, and print the page it decompressed (`out.data.hex(" ")`
in Python, or `{:02x?}` of `out.bytes` in Rust). The same byte sequences recur, `33 33 33` and
`14 ae 47 e1 7a` among them. In PLAIN order a compressor matches them as whole runs. Split, each
run is scattered over eight streams.

Neither result is a rule. What an encoding is worth to a codec depends on the values, and the
only way to know is to measure both on real data.

### What it costs

A codec's saving is paid for when the file is read.

- **A reader decompresses whole pages.** Compressed bytes cannot be decoded from the middle: a
  copy refers to bytes earlier in the output. To read one value, a reader decompresses every
  byte of its page before it.
- **The page header says how much memory to set aside.** `uncompressed_page_size` is known
  before decompression starts, and the reader checks the output against it.
- **Version 2 leaves the levels alone.** A reader can count rows and nulls, or skip to a
  row, without decompressing anything, as [ch06](#pages) described.
- **Decompression takes time.** Faster codecs usually compress less. Whether the time or the
  bytes matter more depends on where the file lives: bytes fetched over a network cost more than
  bytes read from a local disk. [ch10](#how-readers-read) weighs the two.

### Codec names

The footer stores a codec as a number, and `parquet.thrift` names each one. Two names need care.
`LZ4` is an early codec whose framing implementations disagreed about, and it is deprecated.
`LZ4_RAW` is its replacement: a plain LZ4 block. pyarrow writes `LZ4_RAW` when asked for `lz4`,
and reports it as `LZ4` in its own metadata, which is why the book's fixture tests map one name
to the other. *Ask a library*, at the end of *Building it*, shows both names. `LZO` is defined
and rarely written.

## Building it

The steps undid Snappy by hand, then called the reader's `decompress` on three codecs. This
section builds the Snappy decoder, says where the other two are, and shows where the column
reader calls them. The tabs switch every excerpt on the page between the two languages.

### Snappy

`snappy` reads the varint as the first step did, then decodes elements until the input ends,
recording each as a token. A literal copies bytes from the input:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/compress.py
:language: python
:start-at: out = bytearray()
:end-before: if tag & 0b11 == 0b01:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/compress.rs
:language: rust
:start-at: let mut out = Vec::with_capacity(size);
:end-before: kind => {
```
:::
::::

A copy reads its length and distance from the tag and the bytes after it, in one of three
layouts, and repeats earlier output:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/compress.py
:language: python
:start-at: if tag & 0b11 == 0b01:
:end-before: if len(out) != size:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/compress.rs
:language: rust
:start-at: kind => {
:end-before: if out.len() != size {
```
:::
::::

`copy_back` copies byte by byte, because a copy may overlap the bytes it writes: a distance of
one repeats the last byte. It also checks that the distance points into the output.

:::::{note} LZ4 and DEFLATE
The same file decodes the other two codecs, `lz4_raw` and `gzip`, and records the same tokens.

% number-ok: LZ4's block format, fixed by its specification.
An LZ4 block is a run of sequences, each some literals and then one match. A sequence's first
byte holds both lengths, four bits each, and a length of 15 continues in the bytes that follow:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/compress.py
:language: python
:start-at: def more(n: int) -> int:
:end-before: while i < len(data):
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/compress.rs
:language: rust
:start-at: // A length of 15 continues in the bytes that follow
:end-before: while i < input.len() {
```
:::
::::

`gzip` checks the gzip header, then `inflate` decodes the DEFLATE stream. DEFLATE describes each
block's Huffman codes by their lengths alone. The codes of each length are consecutive integers,
so a decoder can read a code a bit at a time and know, after each bit, whether the code is
complete. This is the approach of Mark Adler's `puff`, a reference inflater written to be read:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/compress.py
:language: python
:start-at: def decode(self, bits: Bits) -> int:
:end-before: # Lengths 3..258 and distances
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/compress.rs
:language: rust
:start-at: /// Read one code a bit at a time.
:end-before: /// Lengths 3..258 and distances
```
:::
::::

The rest of `inflate` reads block headers, builds these tables, and turns length and distance
codes into the same copies Snappy and LZ4 make. After the stream, the gzip trailer holds the
output's CRC-32, and the reader checks it with the function from [ch06](#pages).
:::::

### In the column reader

Version 1 compresses the whole body, so the reader decompresses it first and reads the levels
and values from the copy:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/column.py
:language: python
:start-at: # Version 1 compresses the whole body
:end-before: r = ByteReader(levels_bytes, levels_base)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: // Version 1 compresses the whole body
:end-before: let mut r = ByteReader::new(levels_bytes
```
:::
::::

Version 2 compresses only the values:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/column.py
:language: python
:start-at: # Version 2 compresses only the values
:end-before: encoding = page.encoding or
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: // Version 2 compresses only the values
:end-before: let encoding = page.encoding.clone()
```
:::
::::

Values decoded from a decompressed copy have no position in the file, so the reader reports the
compressed bytes that hold them. It can say which compressed page a value came from, but not
which of its bytes.

### Checking it

Every page of every Snappy, LZ4 and GZIP fixture decompresses to the uncompressed file's page,
byte for byte, and every column reassembles to pyarrow's rows. A ZSTD or Brotli page is refused
with a message rather than misread:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures
```
:::
::::

### Ask a library

pyarrow and the `parquet` crate both read the codec and the two sizes from the footer. Ask each
for the `country` column chunk in the three files the second step decompressed:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/compression/compression_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/compression_with_a_library.rs
:language: rust
```
:::
::::

Both report the sizes the tables above were made from. Each counts the page header in both, and
the header is never compressed, so the difference between them is what the codec saved. The
names differ. The file names `LZ4_RAW`, and the crate says so, where pyarrow prints `LZ4`, as
*Codec names* described. The crate's `compression()` answers with a writer's setting rather than
the file's field: for GZIP it adds a compression level, which the file does not record. The level
is the crate's default, the one it would write with. `compression_codec()` gives the name the file
stores. No reader needs the level: a DEFLATE stream decodes the same way whatever level wrote it.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin compression_with_a_library
```

## What this cannot tell you

**How fast each codec is.** The book's numbers come from files, not clocks, so they are the same
on every machine. Speed depends on the implementation, the hardware and the data. Measure it
with the reader you use, on files like yours.

**How ZSTD and Brotli work inside.** Their sizes are measured here, and their pages are not
decoded. Both add entropy coding to LZ77, as DEFLATE does, with larger windows and more careful
modelling. Their specifications are listed below.

**How compression levels change the result.** Each fixture uses pyarrow's default level for its
codec. Most codecs can trade more compression time for smaller output, and decompressing usually
costs about the same whichever level wrote the file.

**How real pages behave.** The fixtures hold one small page per column chunk. A compressor finds
more repetition in a larger input, so production pages of a megabyte or so usually compress
better than these.

## Key takeaways

:::{div}
:class: takeaways

- **A codec compresses each page after encoding, and knows nothing about types.** It finds
  whatever repetition the encoding left.
- **The data decides more than the codec.** Across the fixtures' columns, sizes differ far more
  between columns than between codecs.
- **Every codec here replaces repeats with references to earlier bytes.** The smaller ones also
  give frequent symbols shorter codes.
- **Encoding and compression interact.** `BYTE_STREAM_SPLIT` helped noisy floats and hurt
  decimal-looking ones under the same codec. Measure both on your data.
- **A reader decompresses whole pages.** Version 2 leaves the levels uncompressed, so rows and
  nulls can be counted without decompressing.
:::

## Problems

Three, in `exercises/python/compression.py`, or in Rust in
`exercises/src/compression.rs`. The first two have tests. The third has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: compression
```

**7.1 Snappy.** Decompress a raw Snappy block. The test decompresses every page of
`codec-snappy.parquet` and compares it, byte for byte, with the same page in
`codec-none.parquet`.

**7.2 LZ4.** Decompress an LZ4 block. The fixture's pages include a match long enough to need
several extra length bytes.

**7.3 Your own codec.** No test: the data is yours. Take a Parquet file your systems write and
rewrite it with each codec your writer supports, keeping everything else the same. Record each
file's size and, with the reader you use in production, the time to read it end to end. Then say
which codec you would choose, and for which storage: local disk, a network file system, or an
object store. A good answer names the column that contributes most to the size, and says whether
a different encoding for that column would matter more than the codec.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_7_1` in Python, or `problem_7_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_compression.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test compression -- --ignored
```
:::
::::

## Where to go next

- The codecs Parquet allows, and the history of the two LZ4s, are in the format repository's
  [Compression.md](https://github.com/apache/parquet-format/blob/master/Compression.md).
- Snappy's [format description](https://github.com/google/snappy/blob/main/format_description.txt)
  and LZ4's [block format](https://github.com/lz4/lz4/blob/dev/doc/lz4_Block_format.md) are each
  a page long.
- DEFLATE is [RFC 1951](https://www.rfc-editor.org/rfc/rfc1951) and gzip
  [RFC 1952](https://www.rfc-editor.org/rfc/rfc1952). Mark Adler's
  [puff.c](https://github.com/madler/zlib/blob/develop/contrib/puff/puff.c) is an inflater written
  to be read.
- Zstandard is [RFC 8878](https://www.rfc-editor.org/rfc/rfc8878), and Brotli
  [RFC 7932](https://www.rfc-editor.org/rfc/rfc7932).
- [ch08](#metadata-and-statistics) turns to what the footer records about the values in each
  column chunk, so that a reader can decide not to decompress it at all.
