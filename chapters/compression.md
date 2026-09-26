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

```lab
experiment: compression
fixture: codec-snappy.parquet
fixtures: codec-snappy.parquet, codec-lz4.parquet, codec-gzip.parquet, codec-zstd.parquet, codec-brotli.parquet, codec-none.parquet, codec-zstd-split.parquet, pages-v2-snappy.parquet
column: 1
```

The panel shows every column chunk's size before and after the codec, taken from the footer.
Below it, the reader decompresses one page and records each step as a token. Try these:

1. **Step through the `country` page in `codec-snappy.parquet`.** Each token highlights the
   compressed bytes it read, and in the decompressed page, the bytes it wrote. A copy also
   outlines the earlier bytes it repeated.
2. **Switch to `codec-lz4.parquet`.** The same page takes far fewer tokens. Find the one that
   writes most of the page.
3. **Switch to `codec-gzip.parquet`.** The tokens do the same work, but each is written in a few
   bits rather than whole bytes, so neighbouring tokens share a byte.
4. **Pick `distance_km`.** Most of the page is written as literals, and the copies between
   them are short: the compressor found little to repeat.
5. **Switch to `codec-zstd.parquet`.** The sizes are there, because every footer has them. The
   tokens are not, because this reader does not decode ZSTD, and the panel says so.
6. **Open `pages-v2-snappy.parquet`** and pick `country`. In version 2 data pages the levels sit
   in front of the compressed section, untouched.

### What each codec saved

The whole file under each codec:

```{include} _generated/codec-files.md
```

The codecs fall into pairs. Snappy and LZ4 land close together. GZIP and ZSTD land close
together and smaller. Brotli is smallest here. The two groups differ in method, which the next
sections take apart: the first pair only replaces repeated bytes with references to earlier
ones, and the others also give common bytes shorter codes.

The same measurement column by column says more:

```{include} _generated/codec-columns.md
```

The columns differ far more than the codecs do. `country` and `note` repeat a few values, and
every codec shrinks them to a small fraction. `distance_km` is noisy floating point, and every
codec saves least on it. `order_id` is a counter: no value repeats, and Snappy and LZ4 find only
the runs of zero bytes between the low bytes. The codecs that also give frequent bytes short
codes do much better, because most of each value's bytes are zero. A delta encoding would store it in almost nothing, as [ch05](#encodings) showed.
Encoding and compression are not rivals. An encoding uses what it knows about the type; a codec
finds whatever repetition is left.

### What a codec sees

A codec reads the encoded page as bytes. These are the first tokens of the `country` page under
Snappy:

```{include} _generated/snappy-tokens-country.md
```

A PLAIN string is a four-byte length and then its bytes, so the page starts `02 00 00 00`, then
`UK`. The first token after the length is a literal: those six bytes, copied as they are. The
next value's length prefix is the same four bytes, and Snappy writes it as a copy from six bytes
back, in two bytes. The country code itself is a literal, because a Snappy copy is at least four
bytes long. Once the five countries have all appeared, the page repeats with a fixed period, and
from there on every token is a copy.

This is the **LZ77** idea every codec here shares: replace a run of bytes the output already
holds with how far back it is and how long. The codecs differ in how they write those references
down, and in what else they do.

### Three decoders, one page

The same page, decompressed from each file:

```{include} _generated/codec-country-page.md
```

% number-ok: format constants of Snappy and DEFLATE, fixed by their specifications.
**Snappy** limits a copy to 64 bytes, so a long repeat is many copies in a row. **LZ4** writes a
match's length in a nibble and extends it a byte at a time, so one match covers nearly the whole
page. **GZIP** wraps DEFLATE, whose copies stop at 258 bytes, but whose tokens are Huffman codes:
the literals and lengths that occur most get the fewest bits. That second step, **entropy
coding**, is what the smaller codecs add. ZSTD and Brotli do it too, with more elaborate
machinery.

### Encoding before compression

[ch05](#encodings) said that `BYTE_STREAM_SPLIT` does not shrink anything by itself, and that a
compressor might find more in its output. `codec-zstd-split.parquet` is `codec-zstd.parquet`
with both float columns split:

```{include} _generated/codec-split.md
```

Splitting helped `distance_km` and hurt `weight_kg`. The noisy floats behave as [ch05](#encodings)
described: the sign and exponent bytes barely change, and once they sit together the compressor
finds them. The weights are different. Each is a number of kilograms to two decimal places, and a
decimal fraction has no exact binary form: its mantissa is a repeating bit pattern. Look at
`weight_kg`'s decompressed page in the panel and the same byte sequences recur, `33 33 33` and
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
to the other. `LZO` is defined and rarely written.

## Building it

### Snappy

The whole decompressor: a varint for the output length, then tagged elements until the input
ends.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/compress.py
:language: python
:start-at: def snappy(data: bytes, base: int)
:end-before: def lz4_raw(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/compress.rs
:language: rust
:start-at: pub fn snappy(
:end-before: /// An LZ4 block:
```
:::
::::

The copy is byte by byte because a copy may overlap the bytes it writes: a distance of one
repeats the last byte. `copy_back` does it, and checks that the distance points into the output.

### LZ4

The same two operations in a different layout:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/compress.py
:language: python
:start-at: def lz4_raw(
:end-before: def gzip(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/compress.rs
:language: rust
:start-at: pub fn lz4_raw(
:end-before: /// A gzip member:
```
:::
::::

### DEFLATE's Huffman codes

DEFLATE describes each block's codes by their lengths alone. The codes of each length are
consecutive integers, so a decoder can read a code a bit at a time and know, after each bit,
whether the code is complete. This is the approach of Mark Adler's `puff`, a reference inflater
written to be read:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/compress.py
:language: python
:start-at: class Huffman:
:end-before: # Lengths 3..258 and distances
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/compress.rs
:language: rust
:start-at: /// A canonical Huffman code
:end-before: /// Lengths 3..258 and distances
```
:::
::::

The rest of `inflate` reads block headers, builds these tables, and turns length and distance
codes into the same copies Snappy and LZ4 make. After the stream, the gzip trailer holds the
output's CRC-32, and the reader checks it with the function from [ch06](#pages).

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

**7.1 Snappy.** Decompress a raw Snappy block. The test decompresses every page of
`codec-snappy.parquet` and compares it, byte for byte, with the same page in
`codec-none.parquet`.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_compression.py --problems -k problem_7_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test compression problem_7_1 -- --ignored
```
:::
::::

**7.2 LZ4.** Decompress an LZ4 block. The fixture's pages include a match long enough to need
several extra length bytes.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_compression.py --problems -k problem_7_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test compression problem_7_2 -- --ignored
```
:::
::::

**7.3 Your own codec.** No test: the data is yours. Take a Parquet file your systems write and
rewrite it with each codec your writer supports, keeping everything else the same. Record each
file's size and, with the reader you use in production, the time to read it end to end. Then say
which codec you would choose, and for which storage: local disk, a network file system, or an
object store. A good answer names the column that contributes most to the size, and says whether
a different encoding for that column would matter more than the codec.

```problems
chapter: compression
```

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
