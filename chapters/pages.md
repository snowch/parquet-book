---
title: Pages
---

(pages)=
# Pages

## The question

What is inside a column chunk, and how does a reader walk it?

[ch04](#nested-data) and [ch05](#encodings) decoded the values in a page, and every column chunk
they read held one data page, or a dictionary page and one data page. Real column chunks hold
many pages. A writer ends a page when it reaches a size limit, and each page is the smallest unit
a reader must decode, and later decompress, to reach any value inside it. Here you walk column
chunks page by page, and compare the two versions of the data page.

## The experiment

### Walk the pages yourself

`pages.parquet` and `pages-v2.parquet` hold the same sixty orders. The writer was told to keep
pages small, so each column chunk holds several. Every seventh country is null. The first file
uses data page version 1; the second uses version 2 and puts a checksum in every page header.
[Appendix B](#the-fixtures) says how pyarrow wrote both.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name. Each step finds the footer as
[ch02](#anatomy-of-a-parquet-file) did.

**A column chunk, header by header.** The footer says where `country`'s column chunk starts and
how many bytes it takes, headers included. Walk it with the reader's `read_page`. It decodes one
page header with the Thrift decoder from [ch03](#the-type-system), then takes as many bytes of
body as the header says:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/pages/walk_the_pages.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/walk_the_pages.rs
:language: rust
```
:::
::::

The first page is a dictionary page, and the data pages follow it. Each header starts where the
body before it ended, and the last body ends where the footer said the column chunk ends. The loop
needs no index and no count of pages, because each header's body size says where the next header
is.

Change `pages.parquet` to `pages-v2.parquet` and run the step again. The same rows sit in the
same number of pages, but each data page is now a `DATA_PAGE_V2`, its body is smaller, and its
header counts the page's rows and nulls. Then change the column to 2, which is `amount_cents`. It
has no dictionary page, and its headers are longer. Each carries the page's minimum and maximum,
which for this column are eight-byte integers, where `country`'s are two-letter strings.

**A damaged page.** Every page header in `pages-v2.parquet` carries a CRC-32 of the page's body.
Recompute it for the last page of `country`, then flip one bit of the body and recompute it:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/pages/damage_a_page.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/damage_a_page.rs
:language: rust
```
:::
::::

The body as written gives the header's checksum. One flipped bit gives a different one, so the
page no longer matches its header. The reader checks every page it walks, and its walk agrees:
only the damaged page fails. Python computed the checksum with `zlib` and Rust with the book's
reader. They agree because CRC-32 is one fixed algorithm.

Change the byte the step flips, or flip two bits, and look at the checksum each time. Then change
`[-1]` to `[1]` in Python, or `last()` to `get(1)` in Rust, to damage the first data page
instead, and see which page the reader's walk marks.

### What a page header says

Every page starts with a Thrift `PageHeader`. This is the first data page of `amount_cents`, the
column the first step walked when you changed it, read field by field:

```{include} _generated/page-header-fields.md
```

`compressed_page_size` is the field a walker needs: the body's length, and so where the next
header starts. Here the two sizes are equal because the file is not compressed;
[ch07](#compression) makes them differ.

The header also carries the page's own minimum, maximum and null count. They describe a few rows
rather than a whole row group, which makes them more selective, and [ch09](#skipping-data) uses
them to skip pages.

### Data page version 1

These are the pages of `country` in version 1, with the rows each holds:

```{include} _generated/pages-country-v1.md
```

The dictionary page is first, and there is only one: every data page's indices point into it.
Each data page body holds three parts, in order:

1. the repetition levels, with a four-byte length in front, if the column can repeat;
2. the definition levels, with a four-byte length in front, if the column can be null;
3. the values, in the page's encoding.

A version 1 header counts the page's values, not its rows, so the reader counted the rows by
decoding each page's levels. Under version 1, a page's whole body is compressed as one block. To
count the nulls or the rows in a compressed page, a reader must decompress all of it first.

### Data page version 2

Version 2 changes where things are, not what they mean. The same column chunk:

```{include} _generated/pages-country-v2.md
```

The first step showed the differences when you ran it on this file, and the two tables set them
side by side:

- **The level lengths moved into the header.** The levels have no four-byte prefix in the body,
  which is why every body is smaller than its version 1 counterpart.
- **The levels are never compressed.** Only the values section may be, and the header says
  whether it is. A reader can count nulls or find row boundaries without decompressing anything.
- **The header counts rows and nulls.** A reader skipping to a row knows which page holds it from
  the headers alone.
- **A page always starts a new row.** In version 1 a row of a repeated column can begin in one
  page and continue in the next; version 2 forbids that, so pages can be skipped cleanly.

Writers adopted version 2 slowly, and many still write version 1 by default for compatibility.
Every reader a file will meet must support version 2 before a writer should produce it.

### Checksums

A page header can carry a CRC-32 of the page body. When it does, a reader can tell a damaged page
from one whose values happen to be unusual. Whether a writer includes it depends on the
implementation. pyarrow leaves it out unless asked, and the Rust `parquet` crate never writes it;
parquet-java writes it by default. `pages-v2.parquet` was written by pyarrow with it on.

A checksum helps only a reader that checks it, and checking costs a pass over every body. The bit
the second step flipped turns one country into another, and the damaged index still points into
the dictionary. A reader that skips the check reads the wrong country without complaint, as the
library step at the end of *Building it* shows.

### How big a page should be

A writer ends a page when its encoded size passes a target, commonly around a megabyte, or when a
row count limit is reached. The fixtures use a tiny target so that pages are visible. The
trade-off is the same at any size:

- **Smaller pages** let a reader skip more precisely and decode less to reach one value, but cost
  more headers and compress slightly worse.
- **Larger pages** compress better and cost fewer headers, but make every read of one value
  decode more.

## Building it

The steps looped the reader's `read_page` over a column chunk and compared a body with its
checksum. This section builds the reader's parts they used: the walk, the body and its checksum,
the version 2 level lengths, and CRC-32 itself. The tabs switch every excerpt on the page between
the two languages.

### Walking the pages

The walker reads a page, then the next, until the column chunk ends. It is the first step's loop:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/pages.py
:language: python
:start-at: def walk_pages(
:end-before: def read_page(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/pages.rs
:language: rust
:start-at: pub fn walk_pages(
:end-before: /// Read one page:
```
:::
::::

`read_page` decodes the header, finds the sub-header that matches the page type, and then takes
the body. A body that would run past the end of the chunk is an error: the chunk's size in the
footer and the sizes in its headers must agree. Then it compares the body with the header's
checksum, when there is one, as the second step did:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/pages.py
:language: python
:start-at: # A negative size cannot be read
:end-before: v2 = None
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/pages.rs
:language: rust
:start-at: let (body, body_span) = r
:end-before: let v2 = match (page_type, sub)
```
:::
::::

### Version 2 bodies

The only change the column reader needs for version 2 is where the level lengths come from:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/column.py
:language: python
:start-at: # Version 2 moves the level lengths
:end-before: rep_levels = (
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: // Version 2 moves the level lengths
:end-before: let rep_levels = if leaf.max_repetition_level
```
:::
::::

### The checksum

CRC-32, computed a bit at a time, which is slow and short enough to read in full. It gives the
same answer as `zlib.crc32`, which the Python step used:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/bytes.py
:language: python
:start-at: def crc32(data: bytes)
:end-before: class ByteReader:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/bytes.rs
:language: rust
:start-at: pub fn crc32(
:end-before: /// A cursor over a slice of bytes
```
:::
::::

### Checking it

Both page fixtures decode to pyarrow's rows, and every stored checksum verifies and fails after a
flipped bit:

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

pyarrow has no API for pages. Its metadata gives a column chunk's offsets and size, and it checks
every page's checksum while it reads when you ask it to. The `parquet` crate reads a column chunk
page by page. It checks each checksum when it is built with its `crc` feature, as the book's copy
is. Both read the file with the bit the second step flipped:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/pages/pages_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/pages_with_a_library.rs
:language: rust
```
:::
::::

pyarrow finds the column chunk where the first step did. Read without the check, the damaged file
gives one row a different country, and nothing says so. With `page_checksum_verification`, pyarrow
refuses the file and names the page. The crate prints each version 2 header's rows, nulls and
level bytes, which agree with the version 2 table, and refuses the damaged page when it reaches it.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin pages_with_a_library
```

## What this cannot tell you

**What compressed pages look like.** Every page here is uncompressed, so a header's two sizes are
equal. [ch07](#compression) compresses them.

**How a reader finds a page without walking.** Walking is linear: to reach the last page, a reader
reads every header before it. The page index, stored outside the column chunk, lists every page's
offset and row range so a reader can go straight to one. [ch09](#skipping-data) reads it.

**What page size suits your data.** The fixtures' pages are tiny to be visible. The right size for
real data depends on how it compresses and how selectively it is read, which
[ch11](#writing-parquet-well) measures.

**Index pages.** Besides the two data page versions and the dictionary page, the format defines
an `INDEX_PAGE` type that no writer produces. The reader reports one as unexpected rather than
guessing at it.

## Key takeaways

:::{div}
:class: takeaways

- **A column chunk is a run of pages, each a header and a body.** The header says how long the
  body is, so a reader walks a chunk one header at a time.
- **A dictionary page, when there is one, comes first.** Every data page's indices point into it.
- **A version 1 body is levels then values, compressed together.** Counting rows or nulls means
  decompressing the whole page.
- **Version 2 keeps the levels uncompressed and counts rows and nulls in the header.** A page
  always starts a new row, so pages can be skipped cleanly.
- **A header can carry a checksum of its body.** A reader that checks it can tell damage from
  unusual data.
:::

## Problems

Three, in `exercises/python/pages.py`, or in Rust in
`exercises/src/pages.rs`. The first two have tests. The third has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: pages
```

**6.1 Walk a column chunk.** Return the offset of every page, using the book's Thrift decoder for
the headers. The test walks every column chunk of every fixture.

**6.2 Check a checksum.** Write CRC-32 yourself, and check the fixture's page checksums with it.
The test also damages the pages and expects your check to fail.

**6.3 Your own pages.** No test: the files are yours. Run
`PYTHONPATH=python python3 -m parquet_lab pages FILE COLUMN` or
`cargo run -p pqlab -- pages FILE COLUMN` on a column of a file your systems write. Record how
many pages its first column chunk holds, their sizes, and whether they are version 1 or 2. Then
find the writer's page-size setting in its configuration or documentation, and compare. A good
answer explains any gap between the setting and what the pages show; a page far smaller than the
target usually means a row count limit was reached first, and the answer should say which limit.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_6_1` in Python, or `problem_6_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_pages.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test pages -- --ignored
```
:::
::::

## Where to go next

- Page headers are defined in
  [`parquet.thrift`](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift),
  and data page version 2 is described in the format repository's
  [README](https://github.com/apache/parquet-format#data-pages).
- [ch07](#compression) compresses page bodies, and [ch09](#skipping-data) skips pages without
  walking to them.
