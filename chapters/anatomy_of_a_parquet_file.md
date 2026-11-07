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

First follow a file's bytes, a few at a time. Then follow the book's reader, which starts with
only the name of an object in storage. The worked results show every request and the bytes it
returns. You can inspect or run the code behind them, and build it yourself if you wish.

:::{div}
:class: reading-guide

**What you will learn:** Interpret byte notation, locate the footer from the trailer, use a column’s byte range, and explain which storage requests a reader needs.

Read the explanations, worked results and diagrams; the code is optional.
:::

## The experiment

```lesson
recognise-parquet
```

### Recognise the format

A filename ending in `.parquet` is a hint about its contents. The bytes provide a stronger check:
many file formats use a fixed pattern called a **magic number**, or **file signature**, to help a
reader recognise them. The Parquet file we will inspect uses `PAR1`.

Start by looking for that signature. Once we recognise the expected format, we can ask how its
reader finds the columns. A matching signature alone does not prove that the rest of a file is
valid; the reader must check its structure too.

### Before reading the bytes

A **bit** is a binary digit, zero or one. A **byte** holds eight bits. A file is a sequence of
bytes; an **offset** is a byte’s position in the file, counted from zero. The file size counts bytes, so the final byte’s offset is one
less than the size.

% number-ok: byte range and hexadecimal place values are definitions, not measurements.
A byte can hold a value from 0 to 255. **Hexadecimal** writes that value with two digits in base
16: the digits zero through nine, then the letters a through f for ten through fifteen. An
**ASCII** character is a text interpretation of a byte. The characters you see in a hex viewer
are a way of displaying stored values; the file format decides what those values mean.

### Read the bytes yourself

A **fixture** is a known input file used in examples and tests. `tiny.parquet` is a real Parquet
fixture written by pyarrow: four orders from a sales table, and
[Appendix B](#the-fixtures) says exactly how it was written. The results below show what its
first and last bytes reveal. Open **Read or run the code** to inspect or change an example;
[Appendix A](#running-the-lab) explains how to run Python and Rust.

**The first bytes.** A file format usually announces itself at the start.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/first_bytes.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/first_bytes.rs
:language: rust
```
:::
::::

The first bytes spell `PAR1` in ASCII: the signature we were looking for. The same stored bytes
can be shown as letters or as hexadecimal numbers; neither representation changes their value.

```learning
byte
```


Encrypted-footer files use `PARE` as the closing signature. That is a different supported format variant, not a misspelling of `PAR1`. Encryption is covered later.

```practice
question: A file is named report.parquet and begins with PAR1. Is its table necessarily readable? Explain what the signature does and does not establish.
answer: No. The name is a hint and the signature recognises the expected format. It does not check the rest of the bytes. A file cut short can retain its opening signature while losing the information needed to read its table.
```

```lesson
locate-the-footer
```

### Locate the footer

**The last bytes.** Now the other end of the file.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/last_bytes.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/last_bytes.rs
:language: rust
```
:::
::::

The same four letters appear at the end. We have recognised the signature; now we need to find
the file’s map.

A Parquet file’s **footer** is metadata: information about the table and where its data is stored.
The **trailer** is the last eight bytes: a four-byte footer length followed by the closing
signature. These are different regions. The closing magic identifies the expected format; the
length beside it locates the footer.

```{include} _generated/visual-footer.md
```

We inspected the beginning first to recognise the format. A reader opening a file from storage
can instead start with the closing signature and length, avoiding a separate read of the opening
magic. The book’s reader below does that.

% number-ok: 256 possible byte values define the byte-wise integer radix, not a measurement.
**The four bytes before them.** The format says to interpret these as a length, not as text.
They form a **little-endian** unsigned integer: the first byte has the smallest place value.
There are 256 possible byte values, so each position to the right has 256 times the previous
weight. Unsigned means the length cannot be negative.

The table below separates the displayed hex byte, its decimal value, its weight and its
contribution. Try adding the contributions before revealing the explanation.

```learning
length
```

The optional example reads the same bytes and checks that sum:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/footer_length.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/footer_length.rs
:language: rust
```
:::
::::

That number is the length of the footer: the file's map of everything else in it.

**Where the footer is.** Work backwards from the file size. Subtract the trailer’s length to
find where the footer ends, then subtract the decoded footer length to find where it starts.

A byte span here is **half-open**: it includes its start and excludes its end. Its length is
therefore the end minus the start. A **range request** asks storage for part of a file. When sent
over HTTP, the web request protocol, its range includes both endpoints. Its last included byte
is therefore one less than a half-open span’s end.

```learning
start
```

The optional example performs that calculation:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/footer_start.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/footer_start.rs
:language: rust
```
:::
::::

### What the trailer says

A Parquet file ends with eight bytes: a four-byte footer length, then the four ASCII bytes `PAR1`.
These are the last eight bytes of `tiny.parquet`:

```{include} _generated/tiny-trailer.md
```

The footer ends where the trailer begins, and it is as long as the trailer says. That is all a
reader needs to find it.

The footer occupies the span we located, immediately before the trailer. Its bytes encode
fields that a reader decodes. The **schema** describes the column names, types and structure.
[ch03](#the-type-system) explores those types; the optional implementation below explains the footer’s binary encoding.

**Break it.** Change one byte of the length and do the same arithmetic:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/damaged_length.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/damaged_length.rs
:language: rust
```
:::
::::

The subtraction still produces a number, but that number is not a valid offset: it puts the footer before the start of the
file. A reader has to check what it reads before it trusts it, and the book's reader below
refuses this very damage.

Try changes of your own with **Edit**: read the first eight bytes, print the whole footer, or
open another fixture, such as `fixtures/multiple-row-groups.parquet`.

```transfer
footer
```

```lesson
read-the-footer-map
```

### Use the footer as a map

The footer records column names and types, row counts, and column locations. It does not contain
the whole table’s values, although its statistics can contain summaries such as minimum values.

A **row group** is a slice of rows across all columns. A **column chunk** is one column within
one row group. A chunk contains **pages**, smaller units in which values are stored. Each page
has a **header** describing it and a **body** holding its data.
The same table row has a value in each column’s chunk; these values need not be next to each
other in the file. The metadata connects the logical table to those physical regions.

Here are the regions decoded by the reader. “Ends before” is the excluded boundary, not the last
byte to fetch.

```{include} _generated/tiny-regions.md
```

```learning
chunk
```

Knowing a chunk’s location lets a reader fetch it as a contiguous range. A real reader may fetch
only selected pages, split a range, or combine neighbouring ranges; a chunk does not imply a
fixed number of requests.

### The whole file

The footer is a map. This panel draws what it describes: every region of the file, as the reader
parsed it. Click a region in the structure view to see its bytes, or click a byte to see which
structure it belongs to. The dim bytes are the ones the reader never asked for when it opens
only the footer.

```lab
experiment: anatomy
fixture: tiny.parquet
fixtures: tiny.parquet, multiple-row-groups.parquet
```

Read the structure view from the top, and the file's design appears:

- **The opening magic** is the same four bytes as the closing one. It lets a tool that reads
  from the front recognise the file. A reader working from the end does not need it, and the
  reader in this book does not request it.
- **A row group** is a horizontal slice of the table: some number of rows, all columns. A writer
  arranges each group by column before writing it; how much it buffers depends on the writer.
  Row groups are also the unit a reader can skip or hand to another worker. `tiny.parquet` has one row
  group. Switch the panel to `multiple-row-groups.parquet` to see several.
- **A column chunk** is one column's data within one row group. Its pages occupy a contiguous region,
  so a reader can fetch the chunk without fetching the other columns.
- **A page** is the unit a column chunk is divided into for encoding and compression. Each page
  starts with a header that says how long its body is. In `tiny.parquet` each column chunk is a
  single page, and the body holds the four values in plain little-endian form. Select the first
  value byte of `order_id`'s page body and read it as a 64-bit integer.
- **The footer** is a `FileMetaData` structure: the schema, the row count, and for every column
  chunk its offsets, sizes, encodings, compression and statistics.

The table and the file have different shapes. Follow one row group into its column chunks, then
expand a chunk into pages.

```{include} _generated/visual-hierarchy.md
```

The footer is at the end because the writer does not know those offsets until it has written the
data. Putting the map last lets a writer stream row groups out in one pass, remembering where each
landed, and write the map when it is finished. Nothing is ever rewritten. That matters when
storage accepts a complete file but cannot modify its bytes in place. The cost is paid by the
reader, who must start at the end.

A file whose writer crashed before completing the footer has no valid map. Ordinary Parquet
readers cannot open it as a complete table. Some data pages may be present, but specialised
recovery requires extra information and is outside this chapter.

The fixtures here have no optional lookup structures between their column data and footer.
Other files can put page indexes and Bloom filters there; [ch09](#skipping-data) explains them.
The footer need not follow the last chunk directly.

```transfer
chunk
```

```lesson
trace-footer-requests
```

### Open a file with the book's reader

An **object store** keeps a file as an object addressed by a name. HTTP is the request protocol
used to ask this store for information or bytes. A `HEAD` request returns file information, such
as the size, without the file’s contents. It does not return the Parquet footer. A `GET` request returns file bytes; a **range request** asks for only a span of
them. A **round trip** is sending a request and waiting for its response.

Now let the book’s reader do what you have done, through a simulated store that logs every
request. The trace counts returned file bytes; HTTP response headers are outside that count.
A `HEAD` can therefore show no file bytes returned while still costing a round trip:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/open_with_the_reader.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/open_with_the_reader.rs
:language: rust
```
:::
::::

Three requests: the size, then the trailer, then the footer, each waiting for the one before.
Every byte the reader did not ask for is a byte it never saw, and that is most of the file: it has
learned the schema, the row count and where every column lives without reading the data pages.
The previous lesson interpreted that map; the next lesson shortens the request chain. You can also
open the code and try the reader’s size-source and prefetch options yourself.

The reader also checks what it reads before it trusts it. Hand it the damaged-length case from
the footer-location lesson:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/the_reader_refuses.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/the_reader_refuses.rs
:language: rust
```
:::
::::

It stops after the trailer, before asking the store for a byte of a footer that cannot exist, and
says why. Damage the magic instead, `data[-1]`, and it refuses for a different reason.

### Why the reader made the requests it did

With the default settings the reader follows the procedure literally. It does not know how large
the file is, so it asks. It cannot know how long the footer is until it has read the trailer, so
it reads the trailer. Only then can it ask for the footer:

```{include} _generated/tiny-trace.md
```

```{include} _generated/visual-footer-requests.md
```

Every request waits for the one before it, because each needs a number the previous one
returned. **Latency** is the wait from sending a request until its response begins. With high
latency, starting requests can cost more time than transferring these small ranges.
The simulated trace illustrates that case; a larger request can also return unnecessary bytes.

```practice
question: A directory listing already supplied the file size, but no file bytes have been read. Can the exact trailer and exact footer GETs start together? Why?
answer: No. Knowing the size locates the trailer, but the footer length is still unknown until the trailer arrives. A speculative larger tail read can cover both regions; that is a different strategy, introduced next.
```

```lesson
choose-a-tail-read
```

### Choose a tail strategy

Real readers shorten the chain in two ways:

- **The size is often known already.** A directory listing or a catalogue of the table's files
  can record each file's size ([ch14](#lakehouse-and-beyond)). A **suffix range**, `Range: bytes=-n`, asks for
  the last `n` bytes without knowing the size, and the response reports it.
- **Read more than the trailer.** If the first read is large enough to hold the footer too, the
  third request never happens. The cost is bytes the reader may not use.

Try the size-source and prefetch options below. **Prefetching** means reading more of the file’s
tail than the trailer alone, in case the footer fits inside that first read. A suffix range
returns the file size with the bytes, so it does not need a preceding `HEAD`.

```learning
requests
```

Here is what each combination costs on both fixtures, computed by the same reader:

```{include} _generated/footer-strategies.md
```

The last row for each file is the pattern most production readers use: one suffix read of a few
tens of kilobytes, on the bet that the footer fits. For these files it does. A footer grows with
every row group, and [ch11](#writing-parquet-well) writes one table with small row groups and
shows its footer many times larger than with one row group.

```practice
question: A suffix response contains the closing signature and length, but the decoded footer starts before the returned bytes. Has the suffix request eliminated every later metadata read?
answer: No. It eliminated a separate size request, but the reader must fetch the missing prefix of the footer before decoding all metadata. The trailer itself is not the metadata map. A larger first read might have avoided that extra GET, at a cost in transferred bytes.
```

```lesson
build-footer-reader
```

## Building it

:::{div}
:class: optional-section

**Optional implementation.** Read this section to see how the reader is built.
For the conceptual path, continue to [What this cannot tell you](#anatomy-of-a-parquet-file-limits),
then the takeaways and the understanding check.
:::

The reader you called above is the book's reader, which exists in Python (`python/parquet_lab`)
and in Rust (`crates/parquet-lab`), and the tests hold the two to the same answers. This section
builds the part of it the experiment used, in the order it ran. Each piece is quoted from the source, so what you read here is what ran
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
ends. The object store converts one to the other in one place, a span's `http_range`, so
converting between them must subtract one from the excluded end.

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
`NetworkModel`: a fixed latency per request, plus bytes over **bandwidth**, the number of bytes
the connection can transfer per unit of time. The model is simple on
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

**Serialisation** turns a structured value into bytes that another reader can decode. The
footer uses Apache Thrift's compact protocol, which gives each field a numeric identifier and
a type. Every field starts with a header byte: the high four bits are the difference between this field's id and the previous one, and the
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
their names. Select any byte of the footer in the panel above and the inspector
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

### Ask a library

You will rarely open a file with the book's reader. At work you ask a library, and every library
opens a file the way you have: it reads the trailer, then the footer, and hands you what the
footer says. pyarrow's `read_metadata` and the `parquet` crate's `ParquetMetaDataReader` do that
here:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/anatomy_of_a_parquet_file/footer_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/footer_with_a_library.rs
:language: rust
```
:::
::::

The footer length and the bytes of each column chunk are the ones you found by hand at the start
of the chapter, and the ones in the table of regions. The test that runs these steps checks both
against pyarrow's manifest. From here on a chapter that builds something ends by asking a library
the same question, so that you know where each fact lives in the tools you already use.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. The page's pyarrow is an older version than the desk's, for a reason
[Appendix A](#two-pyarrows) gives; for this step the two print the same. In Rust the step needs
the `parquet` crate, which lives in `walkthroughs/libraries`, a
workspace of its own so that the book's reader keeps no dependencies. Run it in a Codespace, or at
a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin footer_with_a_library
```

```lesson
reference
```

(anatomy-of-a-parquet-file-limits)=
## What this cannot tell you

**How a real network behaves.** The simulated store charges a fixed latency and a fixed
bandwidth. Real object stores have variable latency, a long tail of slow requests, throttling, and
connection setup costs. The simulation shows why readers minimise round trips; it cannot tell you
how long your reads will take.

**Whether a prefetch fits a real footer.** The fixtures have footers smaller than a kilobyte. A
footer grows with the number of row groups times the number of columns, and a wide table's footer
can be far larger than any sensible prefetch. No fixture in this book has a footer that large.
[ch11](#writing-parquet-well) shows how fast one grows with the number of row groups.

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
  pass. Ordinary readers need a valid footer to open the table.
- **Opening a file is a chain of dependent requests.** Size, then trailer, then footer. Each needs
  a number the previous one returned, so on object storage the latency adds up.
- **Readers shorten the chain.** They take the size from a listing or a suffix range, and read
  enough of the tail to hold the footer too.
- **A file is row groups of column chunks of pages.** Each chunk is contiguous, so a reader can fetch
  one column’s chunk without fetching all the others.
- **A library opens a file the same way.** pyarrow's `read_metadata` and the `parquet` crate read
  the trailer and then the footer, and report the offsets you can find by hand.
:::

```checkpoint
question: If a suffix request includes both the trailer and the entire footer, must the reader make another request to discover the schema?
answer: No. The trailer locates the footer, and the returned bytes already contain it. The reader can decode the schema from that response. It must still validate the magic and bounds before trusting those bytes.
```

## Problems

The coding exercises are optional. You can also reason through the question about your own data
without writing a program.

Four, in `exercises/python/anatomy_of_a_parquet_file.py`, or in Rust in
`exercises/src/anatomy_of_a_parquet_file.rs`. The first three have tests that fail until you solve
them. Each test compares your function with the book's reader or with pyarrow, across
many cases, so a hard-coded answer does not pass. The fourth has no test, and says why.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: anatomy_of_a_parquet_file
```

**2.1 The footer length.** Decode the footer length from the last eight bytes of a file, writing
the little-endian arithmetic yourself.

**2.2 Where the footer is.** Given a file size and a footer length, return the footer's byte
range, or refuse when no valid file could have them.

**2.3 How many requests.** A reader that knows the file size reads some number of bytes from the
end, then fetches whatever part of the footer it missed. Predict how many `GET` requests it makes.
The test runs the traced reader and counts.

**2.4 Your own files.** No test: the files are yours, and nothing here can see them. Take a
Parquet file your systems write. Read its last eight bytes (any hex viewer will do) and work out
its footer length. Compare it with the prefetch size of the engine that reads it, which is usually
in the engine's documentation or configuration. A good answer states the file's size, its footer
length, the engine's prefetch, and how many round trips you therefore expect the engine to make
when it opens the file. If you can trace the engine's requests, check your prediction against the
trace. A disagreement means the engine does something this chapter has not described, and finding
out what is the useful result.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_2_1` in Python, or `problem_2_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_anatomy_of_a_parquet_file.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test anatomy_of_a_parquet_file -- --ignored
```
:::
::::

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
