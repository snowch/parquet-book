---
title: Anatomy of a Parquet file
---

(anatomy-of-a-parquet-file)=
# Anatomy of a Parquet file

## The question

Given only a file's bytes, how does a reader find anything in it?

[ch01](#why-parquet-exists) showed why a table is worth storing one column at a time. It also
left a problem. A column layout scatters each row across the file, so a reader cannot scan from
the start and pick values up as it goes. It needs a map: which bytes hold which column, for
which rows. A Parquet file carries that map, and it carries it at the end.

This chapter follows a reader that knows one thing: the name of an object in object storage. You
will watch every request it makes, see the bytes each request returns, and then build the code
that made those requests.

## The experiment

### Open a file from its last byte

The panel below runs the book's reader on `tiny.parquet`, a real Parquet file written by pyarrow.
The reader sees the file only through a simulated object store, which logs every request. The
file holds four orders from a sales table, and [Appendix B](#the-fixtures) says exactly how it
was written.

```lab
experiment: footer
fixture: tiny.parquet
fixtures: tiny.parquet, multiple-row-groups.parquet
```

Nothing on the panel is drawn from a script of what should happen. Each control runs the book's
reader again and the panel shows what it returned. The reader is the Rust one compiled to
WebAssembly, or, if you choose Python above the panel, the Python one run in your browser by
Pyodide; they return the same answers. Try these, in order:

1. **Click the footer-length bytes** in the step list. The byte view marks four bytes near the
   end of the file. Select the first of them in the byte view: the inspector shows the same four
   bytes read as a little-endian integer, with the weight of each byte.
2. **Look at the dim bytes.** Everything dim is a byte the reader never asked for. Most of the
   file is dim. The reader has learned the schema, the row count and the position of every
   column without reading a single value.
3. **Move the first-read slider** to the right. At some point the third request disappears: the
   first read now covers the footer as well as the trailer. The trace shows the cost of that
   change in bytes and in time.
4. **Choose the suffix range.** The `HEAD` request disappears, because a suffix range response
   says how large the object is.
5. **Damage the file.** Select the very last byte and change it to `32`. The reader stops at the
   magic check and says why. Restore the file, then change the second footer-length byte to
   `ff`. Now the trailer claims a footer larger than the file, and the reader refuses it before
   asking the store for a byte of it.

### What the trailer says

A Parquet file ends with eight bytes: a four-byte footer length, then the four ASCII bytes `PAR1`.
These are the last eight bytes of `tiny.parquet`:

```{include} _generated/tiny-trailer.md
```

The footer ends where the trailer begins, and it is as long as the trailer says. That is all a
reader needs to find it.

### Why the reader made the requests it did

With the default settings the reader follows the procedure literally. It does not know how large
the file is, so it asks. It cannot know how long the footer is until it has read the trailer, so
it reads the trailer. Only then can it ask for the footer:

```{include} _generated/tiny-trace.md
```

Every request waits for the one before it, because each needs a number the previous one
returned. On object storage the wait is the expensive part. A request takes a long time to start
and then moves bytes quickly, so three small requests cost far more than one large one.

Real readers shorten the chain in two ways, and the experiment has a control for each:

- **The size is often known already.** A directory listing or a table format's manifest records
  each file's size ([ch14](#lakehouse-and-beyond)). A suffix range, `Range: bytes=-n`, asks for
  the last `n` bytes without knowing the size, and the response reports it.
- **Read more than the trailer.** If the first read is large enough to hold the footer too, the
  third request never happens. The cost is bytes the reader may not use.

Here is what each combination costs on both fixtures, computed by the same reader:

```{include} _generated/footer-strategies.md
```

The last row for each file is the pattern most production readers use: one suffix read of a few
tens of kilobytes, on the bet that the footer fits. For these files it does. [ch08](#metadata-and-statistics)
shows files where it does not.

### The whole file

The footer is a map. This second panel draws what it describes: every region of the file, as the
reader parsed it. Click a region in the structure view to see its bytes, or click a byte to see
which structure it belongs to.

```lab
experiment: anatomy
fixture: tiny.parquet
fixtures: tiny.parquet, multiple-row-groups.parquet
```

The same regions, measured by the reader:

```{include} _generated/tiny-regions.md
```

Read the structure view from the top, and the file's design appears:

- **The opening magic** is the same four bytes as the closing one. It lets a tool that reads
  from the front recognise the file. A reader working from the end does not need it, and the
  reader in this book does not request it.
- **A row group** is a horizontal slice of the table: some number of rows, all columns. A writer
  holds one row group in memory at a time, arranges it by column, and writes it out. Row groups
  are also the unit a reader can skip or hand to another worker. `tiny.parquet` has one row
  group. Switch the panel to `multiple-row-groups.parquet` to see several.
- **A column chunk** is one column's data within one row group. It is contiguous, so reading one
  column of one row group is one range request.
- **A page** is the unit a column chunk is divided into for encoding and compression. Each page
  starts with a header that says how long its body is. In `tiny.parquet` each column chunk is a
  single page, and the body holds the four values in plain little-endian form. Select the first
  value byte of `order_id`'s page body and read it as a 64-bit integer.
- **The footer** is a `FileMetaData` structure: the schema, the row count, and for every column
  chunk its offsets, sizes, encodings, compression and statistics.

The footer is at the end because the writer does not know those offsets until it has written the
data. Putting the map last lets a writer stream row groups out in one pass, remembering where each
landed, and write the map when it is finished. Nothing is ever rewritten, which matters on object
storage, where an object cannot be modified in place. The cost is paid by the reader, who must
start at the end.

A file whose writer crashed before the footer was written has no map. Its data is all present and
none of it can be read.

## Building it

The reader in the panels is the book's reader, which exists in Python (`python/parquet_lab`) and
in Rust (`crates/parquet-lab`). The panels run the Rust one unless you switch them to Python; the
tests hold the two to the same answers. This section builds the part of the reader the experiment
used, in the order it ran. Each piece is quoted from the source, so what you read here is what ran
above, and the tabs switch every excerpt on the page between the languages.

### Little-endian integers

% number-ok: 256 is the base of a byte-wise integer, a definition rather than a measurement.
The footer length is a little-endian unsigned integer: the first byte is the least significant.
Reading one is a sum of each byte times a power of 256:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/bytes.py
:language: python
:start-at: def read_le_u32(data: bytes)
:end-before: def le_terms(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/bytes.rs
:language: rust
:start-at: pub fn read_le_u32(bytes: [u8; 4])
:end-before: /// Each byte of a little-endian integer
```
:::
::::

Parquet uses little-endian order everywhere it stores a fixed-width number: the footer length,
and every integer and float in a page ([ch05](#encodings)).

### The trailer

Parsing the trailer checks the magic first, and only then trusts the length:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/format.py
:language: python
:start-at: def parse_trailer(
:end-before: def footer_span(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/format.rs
:language: rust
:start-at: pub fn parse_trailer(
:end-before: /// Where the footer is
```
:::
::::

`PARE` is the closing magic of a file whose footer is encrypted. The reader recognises it and says
so, rather than misreading ciphertext as a footer length. [ch13](#modular-encryption) reads those
files.

### Where the footer is

The footer ends where the trailer starts, and starts `footer_length` bytes earlier. It cannot start
inside the opening magic, so a length that would put it there means the file is damaged:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/format.py
:language: python
:start-at: def footer_span(
:end-before: def check_header(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/format.rs
:language: rust
:start-at: pub fn footer_span(
:end-before: /// Check the opening magic
```
:::
::::

A span here is half-open: `start` is included and `end` is not. An HTTP range is inclusive at both
ends. The object store converts one to the other in one place, a span's `http_range`, because
getting it wrong by one byte is the most common range-request bug there is.

### The object store

The reader asks for bytes through an interface: a protocol in Python, a trait in Rust. `head` and
`get` are all this chapter needs; later chapters list a table's files and group requests into
phases. `why` is instrumentation: the reader says what it wants the bytes for, and the trace
records it.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/object_store.py
:language: python
:start-at: class ObjectStore(Protocol):
:end-before: class MemoryStore:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/object_store.rs
:language: rust
:start-at: pub trait ObjectStore {
:end-before: /// Objects held in memory
```
:::
::::

`MemoryStore` serves ranges the way S3 does: a range that runs past the end of the object is cut
short rather than refused, and a suffix range longer than the object returns all of it.
`TracingStore` wraps any store, records each request, and charges it a simulated cost from a
`NetworkModel`: a fixed latency per request, plus bytes over bandwidth. The model is simple on
purpose. It captures the one property that shapes Parquet readers, that a request is expensive and
a byte is cheap, and it gives the same numbers every time the book is built.

### Opening a file

The whole procedure, with both shortcuts:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/reader.py
:language: python
:start-at: def read_footer(
:end-before: def tail_range(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/reader.rs
:language: rust
:start-at: pub fn read_footer<S: ObjectStore>(
:end-before: /// The last `want` bytes
```
:::
::::

When the first read did not cover the footer, the reader requests only the part it is missing and
joins it to the tail it already has. It never requests a byte twice.

### Reading the footer

The footer is serialised with Apache Thrift's compact protocol. Every field starts with a header
byte: the high four bits are the difference between this field's id and the previous one, and the
low four bits are its type.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/thrift.py
:language: python
:start-at: delta = byte >> 4
:end-before: header = Span(header_start, r.offset())
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/thrift.rs
:language: rust
:start-at: let delta = byte >> 4;
:end-before: let header = Span::new(header_start, r.offset());
```
:::
::::

Because every field names itself, the decoder can walk a footer without knowing Parquet's schema,
and a field it has never heard of still decodes. The `parquet_thrift` module then gives the fields
their names. Select any byte of the footer in the second panel and the inspector
reads it as a field header, so you can check the decoder by hand. [ch03](#the-type-system) reads
the schema out of this structure.

### Checking it

The reader is tested against the fixtures, and the expected values come from pyarrow, not from
the reader. When pyarrow wrote each fixture it also wrote a manifest of what it wrote: sizes,
offsets, encodings and the footer length. The tests compare the reader with pyarrow:

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

A further test holds the Python and Rust readers to each other: every call a lab can make, on every
fixture and on damaged copies of one, must return the same JSON from both.

```bash
python3 -m pytest tests/test_python.py
```

## What this cannot tell you

**How a real network behaves.** The simulated store charges a fixed latency and a fixed
bandwidth. Real object stores have variable latency, a long tail of slow requests, throttling, and
connection setup costs. The simulation shows why readers minimise round trips; it cannot tell you
how long your reads will take.

**Whether a prefetch fits a real footer.** The fixtures have footers smaller than a kilobyte. A
footer grows with the number of row groups times the number of columns, and a wide table's footer
can be far larger than any sensible prefetch. [ch08](#metadata-and-statistics) measures that.

**What lies between the data and the footer.** Page indexes and Bloom filters, when a writer
includes them, sit after the row groups and before the footer. The fixtures have neither, so here
the footer follows the last column chunk directly. [ch09](#skipping-data) adds them.

**What an encrypted file looks like.** The reader stops at `PARE`. [ch13](#modular-encryption)
goes further.

## Key takeaways

:::{div}
:class: takeaways

- **A reader starts at the end.** The last eight bytes are the only part of a file whose position
  is known in advance: a footer length and the closing magic.
- **The footer is the file's only map.** It is written last so a writer can stream data out in one
  pass, and without it the data cannot be read.
- **Opening a file is a chain of dependent requests.** Size, then trailer, then footer. Each needs
  a number the previous one returned, so on object storage the latency adds up.
- **Readers shorten the chain.** They take the size from a listing or a suffix range, and read
  enough of the tail to hold the footer too.
- **A file is row groups of column chunks of pages.** Each column chunk is contiguous, so reading
  one column of one row group is one range request.
:::

## Problems

Four, in `exercises/python/anatomy_of_a_parquet_file.py`, or in Rust in
`exercises/src/anatomy_of_a_parquet_file.rs`. The first three have tests that fail until you solve
them. Each test compares your function with the book's reader or with pyarrow, across
many cases, so a hard-coded answer does not pass. The fourth has no test, and says why.

**2.1 The footer length.** Decode the footer length from the last eight bytes of a file, writing
the little-endian arithmetic yourself.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_anatomy_of_a_parquet_file.py --problems -k problem_2_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test anatomy_of_a_parquet_file problem_2_1 -- --ignored
```
:::
::::

**2.2 Where the footer is.** Given a file size and a footer length, return the footer's byte
range, or refuse when no valid file could have them.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_anatomy_of_a_parquet_file.py --problems -k problem_2_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test anatomy_of_a_parquet_file problem_2_2 -- --ignored
```
:::
::::

**2.3 How many requests.** A reader that knows the file size reads some number of bytes from the
end, then fetches whatever part of the footer it missed. Predict how many `GET` requests it makes.
The test runs the traced reader and counts.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_anatomy_of_a_parquet_file.py --problems -k problem_2_3
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test anatomy_of_a_parquet_file problem_2_3 -- --ignored
```
:::
::::

**2.4 Your own files.** No test: the files are yours, and nothing here can see them. Take a
Parquet file your systems write. Read its last eight bytes (any hex viewer will do) and work out
its footer length. Compare it with the prefetch size of the engine that reads it, which is usually
in the engine's documentation or configuration. A good answer states the file's size, its footer
length, the engine's prefetch, and how many round trips you therefore expect the engine to make
when it opens the file. If you can trace the engine's requests, check your prediction against the
trace. A disagreement means the engine does something this chapter has not described, and finding
out what is the useful result.

```problems
chapter: anatomy_of_a_parquet_file
```

## Where to go next

- The file layout, magic and footer are specified in the
  [Apache Parquet format specification](https://parquet.apache.org/docs/file-format/), and every
  footer structure is defined in
  [`parquet.thrift`](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift).
- The Thrift compact protocol is specified in the
  [Apache Thrift repository](https://github.com/apache/thrift/blob/master/doc/specs/thrift-compact-protocol.md).
- Range requests, including suffix ranges, are defined in
  [RFC 9110, section 14](https://www.rfc-editor.org/rfc/rfc9110#section-14).
- [ch03](#the-type-system) reads the schema out of the footer you decoded here.
