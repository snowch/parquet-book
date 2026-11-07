---
title: Lakehouse and beyond
---

(lakehouse-and-beyond)=
# Lakehouse and beyond

## The question

How does one Parquet file become one part of a larger analytical system?

Every chapter so far read one file. A table that grows every day is not one file: it is many,
written at different times by different writers, in one directory of an object store. Before a
reader can use anything from [Skipping data](#skipping-data) or [How readers read](#how-readers-read), it has to know
which files there are, and it would rather not open the ones that cannot hold an answer. This
chapter queries a table of nine files, and compares three ways of finding them.

:::{div}
:class: reading-guide

**What you will learn:** Explain what table metadata adds above individual files, including file discovery and pruning before footer reads.

Read the explanations, worked results and diagrams; the code is optional.
:::

## The experiment

```lesson
read-partition-paths
```

### A table of nine files

`fixtures/table/` holds the orders from [Writing Parquet well](#writing-parquet-well), written by pyarrow's
dataset writer. The writer split the rows by `country` into one directory per value, and wrote at
most a hundred rows to a file.

Each step shows its worked result first. Open **Read or run the code** if you want to inspect
or change it. Python runs in the page; Rust runs in a Codespace or at a desk as described in
[Appendix A](#running-the-lab).

**List the table.** Walk the directories and print each Parquet file with the directory it sits
in and its size:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/lakehouse_and_beyond/list_the_table.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/list_the_table.rs
:language: rust
```
:::
::::

Every file sits in a directory named for one country, and every directory name has the same
shape. Most countries have one file. `UK` has three, since it has more orders than one file holds,
and `US` has a second file of only a few orders. Keep only the paths whose value is `UK`: that
filter is the whole of what the next section calls ruling out by path.

### Partitions are in the paths

A **partition** groups rows by a shared value. Here the writer groups by `country`.
The directory `country=UK` is a **Hive-style partition**: a name, an equals sign and a value. The
files under it do not hold a `country` column at all. The dataset writer removed it, since every
row in the directory has the same value, and a reader restores it from the path. Ask the book's
reader for `country` from one file alone:

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

The reader answers with an error: the file has no column `country`. Ask for `order_id` instead,
and it answers.

A condition on a partition column is answered before any file is opened. A `LIST` request returns
object names, or **object keys**, under the table's **prefix**, the shared beginning of those names, and `country = 'UK'` keeps the keys whose path says
`country=UK`. That is the cheapest skipping in the book: it costs nothing beyond the listing, and
it never reads a byte of a file it rules out.

A condition on any other column learns nothing from a path. Listing can only find files; it cannot
say what is in them.

This model reads country partition values as text. A production table also needs partition types, escaping and null conventions.

```practice
question: A file under country=FR has no stored country column. Can a dataset reader still answer country for its rows? Would an arbitrary city predicate be answered by that path?
answer: The dataset can supply FR from the partition path under that partitioning contract. The path says nothing about a different column such as city, so that predicate needs other metadata or data.
```

```lesson
prune-files-before-footers
```

### A log that lists the files

A **table format** keeps, beside the data files, a record of which files make up the table. Delta
Lake's is a **transaction log**: a directory of numbered JSON files, each a list of actions. An
`add` action puts a file in the table, with its partition values, its size, and statistics about
its columns. A `remove` action takes one out. The table is whatever the actions add up to.

`fixtures/table/` is the country-partitioned orders dataset from
[Read partition values from paths](read-partition-paths.html). Its `_delta_log/` directory
holds one log file in the shape Delta Lake uses. The path-only listing skips that directory
because its name has no equals sign.

**Read the log.** Parse each line, and for each `add`, print the file and the statistics the log
records for `order_id`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/lakehouse_and_beyond/read_the_log.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/read_the_log.rs
:language: rust
```
:::
::::

The first two lines say which version of the protocol the log follows and what the table's schema
is. Every line after them adds one of the files shown by the
[partition-path listing](read-partition-paths.html). The
statistics are the same kind [Metadata and statistics](#metadata-and-statistics) read from footers, a minimum and a
maximum for each column, copied into the log when the file was written. A reader of the log knows
each file's range of `order_id` without opening it.

Change `order_id` to `status`, or print `stats["nullCount"]`: the log records every column.

The `UK` files show what the writer's order gives the reader. The dataset writer wrote rows in the
order it received them, by `order_id`, and started a new file every hundred rows, so the three `UK`
files hold three separate ranges. The other countries have one file each, spanning the whole
range:

```{include} _generated/table-log.md
```

### Querying the table

**Query the table.** The book's reader does both kinds of ruling out, then fetches the files that
survive through the simulated object store from [Anatomy of a Parquet file](#anatomy-of-a-parquet-file) and queries them
together. Put the table's files in a store, and ask it for the `UK` orders below `200`, with the
files found from the log:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/lakehouse_and_beyond/query_the_table.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/query_the_table.rs
:language: rust
```
:::
::::

Every file has its reason. The paths rule out the files outside `country=UK`. The log's
statistics rule out two of the three `UK` files, whose ranges of `order_id` start too high. The
reader fetches the log, then one file, and the count comes from that file alone.

Change `Discovery.LOG` to `Discovery.LIST_AND_PRUNE` (`Discovery::ListAndPrune` in Rust). The
reader now lists the keys instead of reading the log, and rules out by path alone, so all three
`UK` files are read, and the count is the same. With `Discovery.LIST` it reads every file. Then
change the connections from `4` to `1` and to `8`, and watch the times: whole files are small, so
the time is almost all waiting for first bytes, and connections decide it.

### Three ways to find the files

The tables below run five queries with the files found each of the three ways. The first reads
the whole table. With no condition, every way reads every file, and the log costs more bytes than
listing, since it is fetched in full, for the same number of requests:

```{include} _generated/table-every-order.md
```

A condition on the partition column is answered by the path. Listing and pruning by path reads
exactly the files the log reads:

```{include} _generated/table-by-country.md
```

A condition on any other column needs the log. Listing reads every file for a range of
`order_id`. The log rules out the files whose ranges miss it: two of the `UK` files and the small
`US` file.

```{include} _generated/table-by-order-id.md
```

Statistics rule out files for any column they cover. For `status = 'refunded'` the log skips the
small `US` file, whose few rows are all `paid`. That skip is luck, a property of one file's
contents, not of the table's design.

```{include} _generated/table-by-status.md
```

The two combine. For the step's query, `country = 'UK' AND order_id < 200`, the path rules out six
files and the log's statistics rule out two more:

```{include} _generated/table-by-both.md
```

Time follows requests. Each file is fetched whole in one request, as [How readers read](#how-readers-read)
found best for small files, and with four connections the table's files arrive in rounds of four.
Fewer files means fewer rounds.

The model uses one log file. It does not implement the full Delta Lake protocol, summaries of
earlier log versions, or reading a history of multiple log files.

```practice
question: A country path survives a filter, but the log’s trustworthy order-id range rules the file out. Must a reader fetch its Parquet footer to discover the same range again?
answer: No. Table metadata can justify skipping before any file read. A surviving range is still only a possible match; the query must inspect retained data as needed.
```

```lesson
resolve-table-membership
```

### What the log adds beyond skipping

**Table membership** says which stored files belong to the selected table version. A **commit**
publishes a complete table change, such as adding replacement files and removing their predecessors
together. Files can remain in storage without belonging to the latest version.

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

### Replay a small complete history

Consider a schematic log: add `north.parquet`, add `south.parquet`, then remove `north.parquet`.
After the first action the table contains north. After the second it contains both. After the
third it contains only south, even if north's bytes remain in storage. A later add of
`replacement.parquet` makes south and replacement active. Each version is the result of the
actions through that version, not a fresh listing of all objects.

This schematic history teaches membership semantics. The [file-pruning walkthrough](prune-files-before-footers.html)
uses `fixtures/table/_delta_log/` with one log file containing adds; it does not implement a
complete versioned Delta Lake history.

```practice
question: A fresh history adds east.parquet and west.parquet, then removes east.parquet. Storage still contains both plus an orphan file never added. Which files are active at that version?
answer: Only west.parquet. Physical presence does not imply membership, and removing a file from a version does not require immediately deleting its stored bytes. Historical readers may still need them.
```

```lesson
build-table-reader
```

## Building it

:::{div}
:class: optional-section

**Optional implementation.** Read this section to see how the reader is built.
For the conceptual path, continue to [What this cannot tell you](#lakehouse-and-beyond-limits),
then the takeaways and the understanding check.
:::

This lab implements the [table-pruning example](prune-files-before-footers.html) over
`fixtures/table/`, a country-partitioned orders dataset with one Delta-shaped log file.
The reader's `table` module reads partition paths and log actions, rules out files, and runs
the [query engine](separate-scan-and-filter.html) over the files that survive.

### Partition values from a path

Every directory of the form `name=value` supplies a partition value. **Percent-encoding** writes
a byte as `%` followed by two hexadecimal digits when it cannot appear directly in a path.
The reader decodes those escapes before using the value:

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

Each line is one action. A `remove` takes out a file an earlier `add` put in, and an `add`
carries the file's path, partition values and statistics. The statistics are JSON inside a JSON
string, so they are parsed twice, as the [log walkthrough](prune-files-before-footers.html) shows:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/table.py
:language: python
:start-at: remove = action.get("remove")
:end-before: size = add.get("size")
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/table.rs
:language: rust
:start-at: if let Some(remove) = action.get("remove") {
:end-before: files.push(TableFile {
```
:::
::::

The file's size comes from the `add` too. A line of the schema, `metaData`, gives the table's
columns, which the reader needs when every file is ruled out and there is nothing to read them
from.

### Ruling out a file

A condition is tried against the file's partition values first. A partition value is text, and
compared as text:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/table.py
:language: python
:start-at: def rules_out(
:end-before: s = file.stats
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/table.rs
:language: rust
:start-at: fn rules_out(
:end-before: let s = file.stats
```
:::
::::

A column that is not a partition is tried against the statistics the log records for the file,
with the comparison [Skipping data](#skipping-data) made against a footer's statistics. There is one more
rule: a JSON number and a JSON string prove nothing about each other, so a comparison across kinds
rules nothing out.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/table.py
:language: python
:start-at: if not _comparable(v, low)
:end-before: def query(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/table.rs
:language: rust
:start-at: if !comparable(&v, &min)
:end-before: /// Answer `sql` from the table
```
:::
::::

### Querying the files together

The reader's query engine, from [What a query engine does](#what-a-query-engine-does), reads the files that survive
as one table. A column named in a partition, rather than in the files' schema, takes its value
from the path, the same value for every row of the file:

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

### Ask a library

At work a library finds the files. pyarrow's dataset module reads a directory as one table: with
Hive partitioning it reads `country` from the paths, and it skips `_delta_log`, as it skips every
name that starts with an underscore. It does not read Delta logs. It rules out files by path, and
then row groups by the statistics in each file's footer, so it opens every file the path keeps.
The `parquet` crate reads files, not tables: you walk the directories, split each name on `=`,
and read each footer yourself:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/lakehouse_and_beyond/table_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/table_with_a_library.rs
:language: rust
```
:::
::::

pyarrow's schema has a `country` column that no file holds. Its filter on the path keeps the
three `UK` files, and the condition on `order_id` keeps a row group only in the first, from its
footer: the plan the log made, paid for with a read of each footer rather than one read of the
log. The count is the reader's. The crate prints every file's range of `order_id` from its
footer, and the ranges are the ones the log recorded. Change the limit to `300` in either, and the
second `UK` file is kept too.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin table_with_a_library
```

```lesson
reference
```

(lakehouse-and-beyond-limits)=
## What this cannot tell you

These notes qualify the [partition-path example](read-partition-paths.html) and
[log-based pruning comparison](prune-files-before-footers.html) over `fixtures/table/`.
The fixture has country-partitioned orders and one Delta-shaped log file; the reader compares
listing all files, pruning by path, and pruning with log statistics.

**How a real log grows.** This reader reads one log file. A real Delta log has one file per
version, and a checkpoint, a Parquet file of its own, that summarises many versions so a reader
need not replay them all. Apache Iceberg keeps the same information differently: a metadata file
points to manifest lists, which point to manifests, which list the data files with their
statistics. The [Iceberg metadata lesson](follow-iceberg-metadata.html) describes that
manifest-list layout. Both approaches locate a table version's files without opening each footer.

**Typed partitions.** Partition values in a path are text. This reader compares them as text,
which is right for `country` and wrong for a numeric partition such as `year` compared with a
number of a different length. A table format records each partition column's type in its schema.

**Concurrent writers.** The log's value is that two writers cannot both commit the same version.
That needs the object store to refuse the second write, and this simulated store has one reader
and no writers.

**What a real table costs.** Nine small files make the differences between the three ways easy to
see. A table with millions of files can make listing expensive because `LIST` returns keys a
page at a time. Table metadata can avoid that listing, but its own size and organisation matter too.

## Key takeaways

:::{div}
:class: takeaways

- **A table is many Parquet files, and finding them is the first cost of a query.** Listing and
  reading a log each cost a request before any data is read.
- **This Hive-style dataset stores country in its paths.** A condition on that partition
  column rules files out by name, without opening them.
- **Log statistics can rule out files for columns they describe.** The fixture log records
  bounds for its data columns. A listing provides names, not those bounds.
- **The log's statistics help only as much as the layout allows.** Files that each hold a narrow
  range of a column can be skipped; files that span the whole range cannot.
- **Table formats change what a reader trusts, not what the files are.** A log makes a set of
  files a table, with versions; every file is still Parquet.
:::

```checkpoint
question: Why can table-level statistics save work even when every Parquet footer already contains statistics?
answer: Table metadata can rule out files before opening their footers. Without it, the engine must discover candidates and fetch their metadata first. The table layer also records which files belong to the current table, which individual footers cannot tell you.
```

## Problems

The coding exercises are optional. You can also reason through the question about your own data
without writing a program.

Three, in `exercises/python/lakehouse_and_beyond.py`, or in Rust in
`exercises/src/lakehouse_and_beyond.rs`. The first two have tests. The third has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: lakehouse_and_beyond
```

**14.1 Partition values.** Read the partition values in a Hive-style path, percent-encoding
included. The test compares your answer with the reader's for every file in the table and a set
of awkward paths.

**14.2 Plan from the log.** Given a log and a range of `order_id`, return the files that could
hold a row in it. The test compares your files with the reader's decisions for many ranges,
checks against the files themselves that no file with a matching row is dropped, and runs a log
that removes a file and adds one with no statistics.

**14.3 Your own table.** No test: the data is yours. Pick a table you query, and the three
conditions its queries use most. Decide which column to partition by, and in what order to write
the rows within each partition. For each condition, say whether the path, the log's statistics,
or neither would rule files out. A good answer names one condition neither helps, and says what
it would cost to change the layout so that one did.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_14_1` in Python, or `problem_14_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_lakehouse_and_beyond.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test lakehouse_and_beyond -- --ignored
```
:::
::::

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
- [Changing a table](#changing-a-table) changes this kind of table: lookups, deletes and compaction.
- The [appendices](#glossary) collect the book's terms.
