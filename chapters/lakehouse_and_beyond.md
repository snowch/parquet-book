---
title: Lakehouse and beyond
---

(lakehouse-and-beyond)=
# Lakehouse and beyond

## The question

How does one Parquet file become one part of a larger analytical system?

Every chapter so far read one file. A table that grows every day is not one file: it is many,
written at different times by different writers, in one directory of an object store. Before a
reader can use anything from [ch09](#skipping-data) or [ch10](#how-readers-read), it has to know
which files there are, and it would rather not open the ones that cannot hold an answer. This
chapter queries a table of nine files, and compares three ways of finding them.

## The experiment

### A table of nine files

`fixtures/table/` holds the orders from [ch11](#writing-parquet-well), written by pyarrow's
dataset writer. The writer split the rows by `country` into one directory per value, and wrote
at most a hundred rows to a file:

```text
table/
  _delta_log/00000000000000000000.json
  country=DE/part-0.parquet
  country=FR/part-0.parquet
  ...
  country=UK/part-0.parquet
  country=UK/part-1.parquet
  country=UK/part-2.parquet
  country=US/part-0.parquet
  country=US/part-1.parquet
```

Beside the files is a log, in the shape Delta Lake uses, that lists them. The experiment runs one
query over the whole table, with the files found in one of three ways, and fetches the files it
decides to read through the simulated object store from [ch02](#anatomy-of-a-parquet-file).

```lab
experiment: table
fixture: table.json
fixtures: table.json
```

Try these:

1. **As loaded.** `country = 'UK' AND order_id < 200`, with the files found from the log. The
   reader fetches the log, then one file, and every other file has the reason it was skipped.
2. **Switch to listing, and read them all.** The same answer, from every file.
3. **Switch to listing, and rule out by path.** The files outside `country=UK` are skipped by
   their names alone. The three `UK` files are all read.
4. **Example 3, a range of `order_id`.** Paths say nothing about `order_id`. Only the log's
   statistics rule files out.
5. **Try one connection, then eight.** Whole files are small, so the time is almost all waiting
   for first bytes, and connections decide it.

### Partitions are in the paths

The directory `country=UK` is a **Hive-style partition**: a name, an equals sign and a value. The
files under it do not hold a `country` column at all. The dataset writer removed it, since every
row in the directory has the same value, and a reader restores it from the path:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
PYTHONPATH=python python3 -m parquet_lab query "fixtures/table/country=UK/part-0.parquet" \
    "SELECT country FROM orders"
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo run -p pqlab -- query "fixtures/table/country=UK/part-0.parquet" "SELECT country FROM orders"
```
:::
::::

```text
"error": "no column country"
```

A condition on a partition column is answered before any file is opened. A `LIST` request returns
every key under the table's prefix, and `country = 'UK'` keeps the keys whose path says
`country=UK`. That is the cheapest skipping in the book: it costs nothing beyond the listing, and
it never reads a byte of a file it rules out.

A condition on any other column learns nothing from a path. Listing can only find files; it cannot
say what is in them.

### A log that lists the files

A **table format** keeps, beside the data files, a record of which files make up the table. Delta
Lake's is a **transaction log**: a directory of numbered JSON files, each a list of actions. An
`add` action puts a file in the table, with its partition values, its size, and statistics about
its columns. A `remove` action takes one out. The table is whatever the actions add up to.

```{include} _generated/table-log.md
```

The statistics are the same kind [ch08](#metadata-and-statistics) read from footers, a minimum
and a maximum for each column, copied into the log when the file was written. A reader that reads
the log knows each file's range of `order_id` without opening it.

The `UK` files show what the writer's order gives the reader. The dataset writer wrote rows in the
order it received them, by `order_id`, and started a new file every hundred rows, so the three `UK`
files hold three separate ranges. The other countries have one file each, spanning the whole
range.

### Three ways to find the files

```{include} _generated/table-discovery.md
```

Read down each group of three:

- **A query with no condition reads everything, whichever way it finds the files.** The log then
  costs more bytes than listing, since it is fetched in full, and the same number of requests.
- **A condition on the partition column is answered by the path.** Listing and pruning by path
  reads exactly the files the log reads.
- **A condition on any other column needs the log.** Listing reads every file for the range of
  `order_id`; the log rules out the files whose ranges miss it, two of the `UK` files and the
  small `US` file.
- **Statistics rule out files for any column they cover.** For `status = 'refunded'` the log
  skips the small `US` file, whose few rows are all `paid`. That skip is luck, a property of one
  file's contents, not of the table's design.
- **The two combine.** `country = 'UK' AND order_id < 200` keeps one file: the path rules out six,
  the log's statistics rule out two more.

Time follows requests. Each file is fetched whole in one request, as [ch10](#how-readers-read)
found best for small files, and with four connections the table's files arrive in rounds of
four. Fewer files means fewer rounds.

### What the log adds beyond skipping

A listing tells a reader what is in a directory now. A log tells it what is in the table, which is
not the same:

- **A half-written file is not in the table.** A writer adds a file to the log only after the
  file is complete, so a reader never sees a file that is still being written.
- **A replaced file stays readable.** A job that rewrites a partition adds the new files and
  removes the old ones in one log entry. A reader of the earlier entry keeps reading the old files,
  which are not deleted until no reader needs them.
- **The whole table has one history.** Each entry is a version of the table, and a reader can ask
  for any version the log still holds.

These are why table formats exist, and the files do not change for any of them. Each file is a
Parquet file exactly as the earlier chapters read it.

## Building it

### Partition values from a path

Every directory of the form `name=value` is a partition value, and values are percent-encoded
where a path could not hold them:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/table.py
:language: python
:start-at: def partition_values(path: str)
:end-before: def unescape(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/table.rs
:language: rust
:start-at: pub fn partition_values(
:end-before: fn unescape(
```
:::
::::

### Reading the log

Each line is one action. The statistics are JSON inside a JSON string, so they are parsed twice:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/table.py
:language: python
:start-at: def read_log(text: str)
:end-before: def _stats(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/table.rs
:language: rust
:start-at: pub fn read_log(
:end-before: /// A literal as the engine's value
```
:::
::::

### Ruling out a file

A condition is tried against the file's partition values first, then against the statistics the
log records for it. The comparison is the one [ch09](#skipping-data) made against a footer's
statistics, with one more rule: a JSON number and a JSON string prove nothing about each other, so
a comparison across kinds rules nothing out.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/table.py
:language: python
:start-at: def rules_out(
:end-before: def query(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/table.rs
:language: rust
:start-at: fn rules_out(
:end-before: /// Answer `sql` from the table
```
:::
::::

### Querying the files together

The query engine from [ch12](#a-tiny-query-engine) reads the files that survive as one table. A
column named in a partition, rather than in the files' schema, takes its value from the path,
the same value for every row of the file:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/engine.py
:language: python
:start-at: v = next((v for k, v in source.partition
:end-before: cols.append(cells)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/engine.rs
:language: rust
:start-at: Col::Partition(p) => {
:end-before: cols.push(cells);
```
:::
::::

### Checking it

The table's files were written by pyarrow, and pyarrow answered each query over the whole table
when the fixtures were generated. The tests hold the reader to those answers with every way of
finding the files, and check that the log lists exactly the files a listing finds:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests -k table
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures table
```
:::
::::

## What this cannot tell you

**How a real log grows.** This reader reads one log file. A real Delta log has one file per
version, and a checkpoint, a Parquet file of its own, that summarises many versions so a reader
need not replay them all. Apache Iceberg keeps the same information differently: a metadata file
points to manifest lists, which point to manifests, which list the data files with their
statistics. Both answer the same question this chapter asked.

**Typed partitions.** Partition values in a path are text. This reader compares them as text,
which is right for `country` and wrong for a numeric partition such as `year` compared with a
number of a different length. A table format records each partition column's type in its schema.

**Concurrent writers.** The log's value is that two writers cannot both commit the same version.
That needs the object store to refuse the second write, and this simulated store has one reader
and no writers.

**What a real table costs.** Nine small files make the differences between the three ways easy to
see. A table with millions of files makes `LIST` itself slow, since a `LIST` returns keys a page
at a time, and makes the log the only practical way to plan a query at all.

## Key takeaways

:::{div}
:class: takeaways

- **A table is many Parquet files, and finding them is the first cost of a query.** Listing and
  reading a log each cost a request before any data is read.
- **Partition values live in paths, not in files.** A condition on a partition column rules files
  out by name, without opening them.
- **A log carries each file's statistics, so it can rule out files for any column.** Listing
  cannot: it knows only names.
- **The log's statistics help only as much as the layout allows.** Files that each hold a narrow
  range of a column can be skipped; files that span the whole range cannot.
- **Table formats change what a reader trusts, not what the files are.** A log makes a set of
  files a table, with versions; every file is still Parquet.
:::

## Problems

Three, in `exercises/python/lakehouse_and_beyond.py`, or in Rust in
`exercises/src/lakehouse_and_beyond.rs`. The first two have tests. The third has none.

**14.1 Partition values.** Read the partition values in a Hive-style path, percent-encoding
included. The test compares your answer with the reader's for every file in the table and a set
of awkward paths.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_lakehouse_and_beyond.py --problems -k problem_14_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test lakehouse_and_beyond problem_14_1 -- --ignored
```
:::
::::

**14.2 Plan from the log.** Given a log and a range of `order_id`, return the files that could
hold a row in it. The test compares your files with the reader's decisions for many ranges,
checks against the files themselves that no file with a matching row is dropped, and runs a log
that removes a file and adds one with no statistics.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_lakehouse_and_beyond.py --problems -k problem_14_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test lakehouse_and_beyond problem_14_2 -- --ignored
```
:::
::::

**14.3 Your own table.** No test: the data is yours. Pick a table you query, and the three
conditions its queries use most. Decide which column to partition by, and in what order to write
the rows within each partition. For each condition, say whether the path, the log's statistics,
or neither would rule files out. A good answer names one condition neither helps, and says what
it would cost to change the layout so that one did.

```problems
chapter: lakehouse_and_beyond
```

## Where to go next

- The [Delta Lake protocol](https://github.com/delta-io/delta/blob/master/PROTOCOL.md) specifies
  the log, its actions and its checkpoints.
- The [Apache Iceberg table specification](https://iceberg.apache.org/spec/) describes manifests
  and how they carry statistics per file.
- Armbrust and others, *Delta Lake: High-Performance ACID Table Storage over Cloud Object
  Stores*, VLDB 2020, sets out why a log over object storage was needed.
- pyarrow's
  [dataset documentation](https://arrow.apache.org/docs/python/dataset.html) covers partitioned
  writing and reading, the way the fixture was written.
- The [appendices](#glossary) collect the book's terms.
