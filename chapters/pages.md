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
a reader must decode, and later decompress, to reach any value inside it. This chapter walks
column chunks page by page, and compares the two versions of the data page.

## The experiment

### Sixty orders in small pages

`pages.parquet` and `pages-v2.parquet` hold the same sixty orders. The writer was told to keep
pages small, so each column chunk holds several. Every seventh country is null. The first file
uses data page version 1; the second uses version 2 and puts a checksum in every page header.

```lab
experiment: pages
fixture: pages.parquet
fixtures: pages.parquet, pages-v2.parquet
column: 1
```

The panel lists the pages of one column chunk as the reader found them. Try these:

1. **Read the `country` column top to bottom.** A dictionary page comes first, then the data
   pages. The first-row column says which rows each page holds.
2. **Click a data page's `header`**, then look in the structure view. The header records the
   page's type, its sizes, its value count, its encodings and its own statistics.
3. **Click `def` and `values`** for the same page to see the two parts of its body.
4. **Switch to `pages-v2.parquet`.** The same pages now report their rows and nulls in the header,
   and their bodies are smaller.
5. **Damage a page.** In `pages-v2.parquet`, click a data page's `values`, then change its first
   byte in the inspector. The page's checksum no longer matches, and the panel says which page.

### What a page header says

Every page starts with a Thrift `PageHeader`. This is the first data page of `amount_cents`, read
field by field:

```{include} _generated/page-header-fields.md
```

`compressed_page_size` is the one a walker needs: the body's length, and so where the next header
starts. No index is needed to walk a column chunk, only each header in turn. Here the two sizes
are equal because the file is not compressed; [ch07](#compression) makes them differ.

The header also carries the page's own minimum, maximum and null count. They describe a few rows
rather than a whole row group, which makes them more selective, and [ch09](#skipping-data) uses
them to skip pages.

### A column chunk, page by page

These are the pages of `country` in version 1:

```{include} _generated/pages-country-v1.md
```

The dictionary page is first, and there is only one: every data page's indices point into it.
Each data page body holds three parts, in order, and the reader decoded them to count rows:

1. the repetition levels, with a four-byte length in front, if the column can repeat;
2. the definition levels, with a four-byte length in front, if the column can be null;
3. the values, in the page's encoding.

Under version 1, a page's whole body is compressed as one block. To count the nulls or the rows in a
compressed page, a reader must decompress all of it first.

### Data page version 2

Version 2 changes where things are, not what they mean. The same column chunk:

```{include} _generated/pages-country-v2.md
```

The differences, each visible in the tables:

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
from one whose values happen to be unusual. Writers leave it out by default; `pages-v2.parquet`
was written with it on. The panel's checksum column is the reader recomputing each body's CRC and
comparing it with the header's.

### How big a page should be

A writer ends a page when its encoded size passes a target, commonly around a megabyte, or when a
row count limit is reached. The fixtures use a tiny target so that pages are visible. The
trade-off is the same at any size:

- **Smaller pages** let a reader skip more precisely and decode less to reach one value, but cost
  more headers and compress slightly worse.
- **Larger pages** compress better and cost fewer headers, but make every read of one value
  decode more.

## Building it

### Walking the pages

The walker reads a header, reads the body it describes, and repeats until the column chunk ends.
A body that would run past the end of the chunk is an error: the chunk's size in the footer and
the sizes in its headers must agree.

```{literalinclude} ../crates/parquet-lab/src/pages.rs
:language: rust
:start-at: pub fn walk_pages(
```

### Version 2 bodies

The only change the column reader needs for version 2 is where the level lengths come from:

```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: // Version 2 moves the level lengths
:end-before: let rep_levels = if leaf.max_repetition_level
```

### The checksum

CRC-32, computed a bit at a time, which is slow and short enough to read in full:

```{literalinclude} ../crates/parquet-lab/src/bytes.rs
:language: rust
:start-at: pub fn crc32(
:end-before: /// A cursor over a slice of bytes
```

### Checking it

Both page fixtures decode to pyarrow's rows, and every stored checksum verifies and fails after a
flipped bit:

```bash
cargo test -p parquet-lab --test fixtures
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

**Index pages.** The format defines a third page type that no writer produces. The reader reports
one as unexpected rather than guessing at it.

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

Three, in `exercises/src/pages.rs`. The first two have tests. The third has none.

**6.1 Walk a column chunk.** Return the offset of every page, using the book's Thrift decoder for
the headers. The test walks every column chunk of every fixture.

```bash
cargo test -p exercises --test pages problem_6_1 -- --ignored
```

**6.2 Check a checksum.** Write CRC-32 yourself, and check the fixture's page checksums with it.
The test also damages the pages and expects your check to fail.

```bash
cargo test -p exercises --test pages problem_6_2 -- --ignored
```

**6.3 Your own pages.** No test: the files are yours. Run
`cargo run -p pqlab -- pages FILE COLUMN` on a column of a file your systems write. Record how
many pages its first column chunk holds, their sizes, and whether they are version 1 or 2. Then
find the writer's page-size setting in its configuration or documentation, and compare. A good
answer explains any gap between the setting and what the pages show; a page far smaller than the
target usually means a row count limit was reached first, and the answer should say which limit.

## Where to go next

- Page headers are defined in
  [`parquet.thrift`](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift),
  and data page version 2 is described in the format repository's
  [README](https://github.com/apache/parquet-format#data-pages).
- [ch07](#compression) compresses page bodies, and [ch09](#skipping-data) skips pages without
  walking to them.
