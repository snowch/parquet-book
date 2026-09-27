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

The `writing-*.parquet` files hold the same orders. `writing-baseline.parquet` is
sorted by `order_id`, dictionary-encoded, compressed with Snappy, and written in four row groups
of small pages with a page index. Each other file changes one of those settings: one row group,
many small ones, sorted by country, shuffled, no dictionary, or no page index.
[Appendix B](#the-fixtures) lists them.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name.

**Row groups a lookup reads.** The query is `order_id = 431`. A reader reads every row group whose
footer range could hold the value. Read each file's footer, as [ch09](#skipping-data) did, and
count those row groups:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/writing_parquet_well/row_groups_per_lookup.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/row_groups_per_lookup.rs
:language: rust
```
:::
::::

Every file sorted by `order_id` sends the lookup to one row group, however many row groups it
has. The file sorted by country and the shuffled one send it to all of theirs, because each of
their row groups spans nearly every order number. The footers differ too: the file of small row
groups has one many times larger than the file of one row group.

Change `column` to `2`, which is `customer_id`, and `wanted` to `500000`. Nobody sorted by
customer, so every file sends that lookup to every row group it has. Small row groups do not
help a column nobody sorted by; they only add row groups to read.

One value can be lucky. Averaged over every value of the two columns, the reader counted:

```{include} _generated/writing-lookups.md
```

### What a query reads

**One query, every file.** The book's reader from [ch10](#how-readers-read) runs
`SELECT * WHERE order_id = 431` against each file in turn. It finds the footer exactly, uses
every skipping mechanism, and merges only ranges that touch. What it reads after the footer is
then what the file's layout made it read:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/writing_parquet_well/query_every_file.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/query_every_file.rs
:language: rust
```
:::
::::

Every file returns the same order. What it cost differs:

- **Sorting decides.** The file sorted by country and the shuffled one read most of their bytes,
  as the first step predicted. The small row groups read least, since the one row group they
  read is small.
- **Dictionaries make point lookups dearer.** To decode one page of a dictionary-encoded column,
  the reader must first read that column's dictionary page, which for a column of unique values
  holds every value in the row group. The baseline read several times more than the file without
  dictionaries.
- **The page index trades bytes for requests.** The file without one read its whole row group in
  one request. The baseline read fewer bytes in more requests. Against object storage, as
  [ch10](#how-readers-read) measured, the requests can cost more than the bytes saved.

Change the condition to `country = 'FR'`, with column `3` and `"FR"`: now the file sorted by
country reads least. Then try `status = 'refunded'`, with column `4`. No file does well. Refunds
are rare and spread through every row group, and no single sort order serves every column. The
reader ran those conditions, and one on amounts, against every file:

```{include} _generated/writing-queries.md
```

Sorting makes lookups cheap only for the column sorted by. A rare value spread through every row
group, such as a refund, costs nearly a full read whatever the layout.

### What each setting changed

The files themselves, before any query:

```{include} _generated/writing-files.md
```

Every setting has a price somewhere:

- **Row group size.** Each row group repeats the metadata for every column: a column chunk entry
  in the footer, statistics, page index entries, and a dictionary page per column. The first
  step printed the footer of the small row groups many times larger than the footer of one row
  group, and the file is larger with it.
- **Dictionary encoding.** It shrank `country`, which repeats a few values, and grew `order_id`,
  whose values are all different: [ch05](#encodings)'s lesson, at the scale of a file.
- **Sort order.** Sorting by country gathered each country's rows together, and the country
  column shrank, because its dictionary indices now repeat in long runs.
- **The page index.** Turning it off made the column chunks larger, not smaller. pyarrow writes
  each page's statistics into the page index when there is one, and into every page header when
  there is not.

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

The steps read each footer by hand, then called the reader's `scan`, which
[ch10](#how-readers-read) built. The reader is the same for every file; only the files differ.
This section shows the settings the files were written with, and the two places in the reader
where a file's layout turns into bytes read: the indexes a lookup fetches, and the dictionary
page it cannot skip.

### The writer's settings

The fixtures are written by pyarrow, never by this repository's code. These are the settings
every `writing-*` file starts from:

```{literalinclude} ../fixtures/generate.py
:language: python
:start-at: WRITING_OPTIONS = {
:end-before: def _writing(
```

### The indexes a lookup fetches

Before it reads any data, `scan` fetches the indexes its plan will consult. A row group the
footer's statistics rule out needs none. For every other row group, it fetches the condition
column's Bloom filter if the writer wrote one, that column's ColumnIndex, and the OffsetIndex of
every column the query touches:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/scan.py
:language: python
:start-at: # Phase 2: the indexes the plan will consult.
:end-before: # Phase 3: the data.
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/scan.rs
:language: rust
:start-at: // Phase 2: the indexes the plan will consult.
:end-before: // Phase 3: the data.
```
:::
::::

A file sorted by the condition's column leaves one row group, and so fetches one row group's
indexes. A shuffled file leaves every row group and fetches every row group's indexes, before it
reads a page. A file without a page index has nothing to fetch here, and reads whole column
chunks instead.

### The dictionary page a lookup cannot skip

The plan then reads the pages of each column that hold the kept rows. [ch09](#skipping-data)'s
`column_read` adds the chunk's dictionary page to any read of its data pages, since a
dictionary-encoded page cannot be decoded without it:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/prune.py
:language: python
:start-at: # The dictionary page sits before the first data page
:end-before: spans += [oi.pages[i].span() for i in wanted]
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/prune.rs
:language: rust
:start-at: // The dictionary page sits before the first data page
:end-before: spans.extend(wanted.iter().map(|&i| oi.pages[i].span()));
```
:::
::::

For `country`, the dictionary page is a few values. For `order_id`, whose values are all
different, it is every value in the row group, which is why the lookup read more from the
dictionary-encoded baseline than from the plain file.

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

### Ask a library

At work you choose these settings in a writer, and read them back from the footer. pyarrow
writes the baseline's rows again with the fixtures' settings, then with one changed at a time.
The `parquet` crate reads the choices back from each file's footer:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/writing_parquet_well/writing_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/writing_with_a_library.rs
:language: rust
```
:::
::::

With the fixtures' settings, pyarrow writes `writing-baseline.parquet` again, to the byte: the
same size and the same footer. The pyarrow the page loads is older than the one that wrote the
fixtures, and has no `max_rows_per_page`, so the step cuts its pages another way, as its comment
says. Each change shows in the footer as the steps found it: more row
groups and a larger footer, no dictionary page, no ColumnIndex. The last change declares the
sort. `sorting_columns` records in each row group that it is sorted by `order_id`, for a few
bytes of footer. The fixtures do not declare it, so the crate finds no sort order in any of
them. A reader can infer the order from the statistics, but the footer never states it.

The crate writes too. Its `WriterProperties` set the same choices: `set_max_row_group_row_count`,
`set_dictionary_enabled`, `set_statistics_enabled` with `EnabledStatistics::Page` for the page
index, `set_sorting_columns` and `set_column_bloom_filter_enabled`. Writing rows with it needs
either a column writer fed value by value, or the `arrow` feature's `ArrowWriter`, which this
workspace does not build, so the step reads instead.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin writing_with_a_library
```

## What this cannot tell you

**How the settings behave at scale.** The fixtures hold few enough rows that every row group is
small, and the proportions change with size. A footer that is a large share of a small file, as
the first step printed, is a rounding error in a large one. The direction of each effect
holds; the sizes do not.

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

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: writing_parquet_well
```

**11.1 Row groups per lookup.** From each row group's bounds, count the row groups a lookup for a
value must read. The test compares your count with the reader's plans for values in every file.

**11.2 What order costs.** From a column's values in file order and a row group size, compute the
mean number of row groups a lookup reads. The test checks every ch11 file's integer columns.

**11.3 Your own writer.** No test: the data is yours. Rewrite one of your files three ways,
changing one setting each time: the sort column, the row group size, or dictionary encoding for
one column. Measure each with `PYTHONPATH=python python3 -m parquet_lab scan FILE --where ...` or
`cargo run -p pqlab -- scan FILE --where ...` on a query you run
often. A good answer reports the file sizes, what each query read, and which setting you would
change in production, with the cost that change puts on writing.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_11_1` in Python, or `problem_11_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_writing_parquet_well.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test writing_parquet_well -- --ignored
```
:::
::::

## Where to go next

- pyarrow's [`write_table`](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html)
  documents every setting used here.
- The format's [configuration notes](https://parquet.apache.org/docs/file-format/configurations/)
  discuss row group and page sizes.
- [ch12](#a-tiny-query-engine) builds a query engine on the reader, so that questions can be
  asked in SQL rather than one condition at a time.
