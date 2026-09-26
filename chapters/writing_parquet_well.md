---
title: Writing Parquet well
---

(writing-parquet-well)=
# Writing Parquet well

## The question

Which writer settings decide how cheap a file is to read?

Every chapter since [ch08](#metadata-and-statistics) has been about what a reader can avoid. It
can avoid only what the file lets it. Row groups, their order, pages, encodings and indexes are
all fixed when the file is written, and no reader can undo a writer's choice. This chapter writes
the same rows seven ways and measures each by what queries against it cost.

## The experiment

### Seven files, one table

The `writing-*.parquet` files hold the same eight hundred orders. `writing-baseline.parquet` is
sorted by `order_id`, dictionary-encoded, compressed with Snappy, and written in four row groups
of small pages with a page index. Each other file changes one of those settings.
[Appendix B](#the-fixtures) lists them.

```lab
experiment: writing
fixture: writing-baseline.parquet
fixtures: writing-baseline.parquet, writing-one-group.parquet, writing-small-groups.parquet, writing-by-country.parquet, writing-shuffled.parquet, writing-plain.parquet, writing-no-index.parquet
column: 0
op: =
value: 431
```

The panel runs one query against every file, with the same reader each time, and reports what
it read after the footer. Try these:

1. **As loaded, a lookup by `order_id`.** Compare the sorted files with the shuffled one and the
   one sorted by country.
2. **`country = FR`.** Now the file sorted by country reads least.
3. **`status = refunded`.** No file does well. Refunds are rare and spread through every row
   group, and no single sort order serves every column.
4. **No condition.** Every file reads everything. Compare the sizes and the footers instead.

### What each setting changed

The files themselves, before any query:

```{include} _generated/writing-files.md
```

Every setting has a price somewhere:

- **Row group size.** Each row group repeats the metadata for every column: a column chunk entry
  in the footer, statistics, page index entries, and a dictionary page per column. Twenty row
  groups made the footer many times larger than one row group did, and the file larger with it.
- **Dictionary encoding.** It shrank `country`, which repeats a few values, and grew `order_id`,
  whose values are all different: [ch05](#encodings)'s lesson, at the scale of a file.
- **Sort order.** Sorting by country gathered each country's rows together, and the country
  column shrank, because its dictionary indices now repeat in long runs.
- **The page index.** Turning it off made the column chunks larger, not smaller. pyarrow writes
  each page's statistics into the page index when there is one, and into every page header when
  there is not.

### How many row groups a lookup reads

For a query on one value, a reader reads every row group whose footer range includes it. Averaged
over every value of two columns:

```{include} _generated/writing-lookups.md
```

A lookup by `order_id` reads one row group in every file sorted by `order_id`, however many row
groups there are. Shuffle the rows, or sort them by something else, and a lookup reads nearly
every row group. `customer_id` was never sorted, so its lookups read nearly every row group in
every file. Smaller row groups do not help a column nobody sorted by; they only add row groups to
read.

### What queries cost

The same five queries against every file, counting what the reader fetched after the footer:

```{include} _generated/writing-queries.md
```

Some results were expected. Sorting decides which lookups are cheap, and only for the column
sorted by. A rare value spread through every row group, such as a refund, costs nearly a full
read whatever the layout.

Two were not:

- **Dictionaries make point lookups dearer.** To decode one page of a dictionary-encoded column,
  the reader must first read that column's dictionary page, which for a column of unique values
  holds every value in the row group. The lookup by `order_id` read several times more from the
  dictionary-encoded baseline than from the file without dictionaries.
- **The page index trades bytes for requests.** Without it the reader fetched whole column
  chunks in one request; with it, fewer bytes in more requests. Against object storage, as
  [ch10](#how-readers-read) measured, the requests can cost more than the bytes saved.

### Choosing

No setting is right for every table, but the measurements point one way:

- **Sort by the column queries filter on most**, and expect other columns to gain little from
  statistics.
- **Make row groups large.** Small row groups multiply the footer and the per-chunk overhead,
  and help only a sorted column. Production writers commonly aim for tens to hundreds of megabytes
  per row group.
- **Let dictionary encoding fall back** for columns of mostly distinct values, or turn it off for
  them. Writers fall back when a dictionary grows too large, and a column of unique identifiers
  gains nothing from one.
- **Write the page index for tables queried selectively** on a sorted column, and expect it to
  help most when requests are cheap.
- **Add Bloom filters for equality lookups on unsorted, high-cardinality columns**, as
  [ch09](#skipping-data) showed for customer numbers.

## Building it

### The writer's settings

The fixtures are written by pyarrow, never by this repository's code. These are the settings
every `writing-*` file starts from:

```{literalinclude} ../fixtures/generate.py
:language: python
:start-at: WRITING_OPTIONS = {
:end-before: def _writing(
```

### Measuring a file by its queries

Each figure runs the query through the read path from [ch10](#how-readers-read), and counts the
requests after the footer:

```{literalinclude} ../crates/pqlab/src/figures.rs
:language: rust
:start-at: /// Bytes and requests after the footer
:end-before: fn writing_files(
```

### Checking it

Every file reassembles to the same rows, and every query returns the same matches from every
file, whatever the layout:

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

**How the settings behave at scale.** Eight hundred rows make every row group small, and the
proportions change with size: a footer that is a fifth of a small file is a rounding error in a
large one. The direction of each effect holds; the sizes do not.

**What the settings cost the writer.** Larger row groups need more memory while writing, and
sorting needs the rows first. This chapter measures only readers.

**Other writers.** pyarrow's defaults, and the way it places statistics, are pyarrow's. Other
writers choose differently, and a file's `created_by` says which one wrote it.

## Key takeaways

:::{div}
:class: takeaways

- **A reader can skip only what the writer's layout allows.** Every setting is fixed when the
  file is written.
- **Sort order decides which lookups are cheap.** A lookup on the sorted column reads one row
  group; on any other, nearly all.
- **Small row groups cost metadata and help only a sorted column.**
- **Dictionaries help repeated values and hurt unique ones.** For point lookups they add a
  dictionary page per column read.
- **Indexes trade bytes for requests.** Whether that pays depends on the storage.
:::

## Problems

Three, in `exercises/python/writing_parquet_well.py`, or in Rust in
`exercises/src/writing_parquet_well.rs`. The first two have tests. The third has none.

**11.1 Row groups per lookup.** From each row group's bounds, count the row groups a lookup for a
value must read. The test compares your count with the reader's plans for values in every file.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_writing_parquet_well.py --problems -k problem_11_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test writing_parquet_well problem_11_1 -- --ignored
```
:::
::::

**11.2 What order costs.** From a column's values in file order and a row group size, compute the
mean number of row groups a lookup reads. The test checks every ch11 file's integer columns.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_writing_parquet_well.py --problems -k problem_11_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test writing_parquet_well problem_11_2 -- --ignored
```
:::
::::

**11.3 Your own writer.** No test: the data is yours. Rewrite one of your files three ways,
changing one setting each time: the sort column, the row group size, or dictionary encoding for
one column. Measure each with `PYTHONPATH=python python3 -m parquet_lab scan FILE --where ...` or
`cargo run -p pqlab -- scan FILE --where ...` on a query you run
often. A good answer reports the file sizes, what each query read, and which setting you would
change in production, with the cost that change puts on writing.

## Where to go next

- pyarrow's [`write_table`](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html)
  documents every setting used here.
- The format's [configuration notes](https://parquet.apache.org/docs/file-format/configurations/)
  discuss row group and page sizes.
- [ch12](#a-tiny-query-engine) builds a query engine on the reader, so that questions can be
  asked in SQL rather than one condition at a time.
