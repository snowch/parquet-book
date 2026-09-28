---
title: Changing a table
---

(changing-a-table)=
# Changing a table

## The question

What does it cost to find one row, or change one, in a table of Parquet files?

[ch14](#lakehouse-and-beyond) read a table that never changed. Real tables do. An order is
cancelled, a refund corrects an amount, a customer asks to be forgotten, and late data arrives
in small batches all day. A Parquet file cannot absorb any of that: its column chunks are
encoded and compressed, and its footer records the offset of every one, so changing a value in
the middle would move bytes the footer points at. Every change to a table of Parquet files is
therefore a new file. This chapter measures what that costs, for the reads and the writes, and
what the usual repair, compaction, costs in its turn. It starts with the operation Parquet was
never built for: finding one row.

## The experiment

### A table and its history

`fixtures/changes/` holds the orders from [ch11](#writing-parquet-well), written by pyarrow in
four files sorted by `order_id`, each with row groups, small pages and a page index. Then the
table was changed, and every version was recorded as a *snapshot*: the list of data files, and
of delete files, that make up the table at that moment. Table formats such as Apache Iceberg and
Delta Lake keep exactly this list. Here it is one JSON file, `_snapshots.json`, beside the data:

```{include} _generated/changes-snapshots.md
```

`copy-on-write` deleted an order by writing its file again without it. The `merge-on-read`
snapshots deleted orders by writing small *position delete files* instead, each naming one row of
one data file. `after-a-day` adds new orders the way a stream of small batches does, one file per
batch, and `compacted` is what a compaction job made of it.

Before the reader looks anything up, read the table's metadata yourself: in Python with the
`json` module, in Rust with the reader's `changes::read_snapshots`, which parses the same file.
The steps below run in the page in Python, and in a Codespace or at a desk in Rust. First, what
the latest snapshot holds:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/changing_a_table/table_files.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/table_files.rs
:language: rust
```
:::
::::

Compare the bytes a row costs in the original files with the bytes a row costs in the
appended ones. Each small file carries its own footer, page headers and magic numbers for a
handful of rows, so a row in a small file costs several times what it costs in a large one.

Next, the files a lookup of one order has to open. The snapshot records each data file's range of
`order_id`, as an Iceberg manifest does, so the reader can rule files out before opening them:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/changing_a_table/find_the_file.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/find_the_file.rs
:language: rust
```
:::
::::

One data file can hold order `300`, because the files are sorted by `order_id`. But every delete
file that names that data file might remove the order, so each of them must be read too.

Last, a delete file itself. It is an ordinary Parquet file with two columns, `file_path` and
`pos`, as Iceberg defines them. The book's reader, as you built it, reads it like any other file:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/changing_a_table/read_a_delete_file.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/read_a_delete_file.rs
:language: rust
```
:::
::::

The delete file names a position, not an order: the row's place in its data file, counting from
zero. The data file still holds the order; the delete file says it is gone. Change the path to
another delete file and run it again.

### Find one order

Now let the book's reader look up order `300` in `after-a-day`, as a query engine would, through
the simulated object store. The step prints every request, grouped by round trip: the requests
in one round trip go out together, and each round trip waits for the one before it.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/changing_a_table/look_up_an_order.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/look_up_an_order.rs
:language: rust
```
:::
::::

Read the round trips from the top. The snapshots come first, since nothing else can be chosen
without them. Then the delete files that name the one data file the order can be in, alongside
that file's trailer. Then its footer, which the trailer located; then the page indexes the
footer located; then the pages the index chose in every column, to put the whole row back
together. Each round trip needed a number the last one returned, so none could be sent sooner.

Change the order to `250`. The reader finds it in its data file, decodes it, and only then finds
that a delete file removes it: it read the data to learn that the answer is nothing. Then change
the snapshot to `written`, which has no delete files, and set `prefetch` to `65536`. The first
read of the data file now asks for that much of its tail, which is the whole file: the chain
shrinks to two round trips, and the bytes grow to the whole file, for one row.

The panel draws the same lookup's requests over time, one lane per connection. Change the
snapshot and the order. Whenever a file can hold the order, the chain has the same steps, and
delete files widen only the second. Order `805` is past the end of `written`, so the snapshots
alone answer; in `after-a-day` it is in a small append, and the whole chain is paid for a file of
a few rows.

```lab
experiment: changes
fixture: changes.json
```

### What one lookup costs

The same lookups, and what a key-value store would pay for the same row:

```{include} _generated/changes-lookup.md
```

A Parquet table has no index from a key to a row. Statistics narrow the search to a file, a row
group and a page, and each narrowing is a round trip that needs the one before it. Then the
pages are decoded, and to return the whole row the reader needs the matching page of every
column, which is [ch01](#why-parquet-exists)'s cost of reconstructing a row, paid in requests.

This is the best case. The files are sorted by `order_id`, so one file and one page of each
column hold the answer. On a table written in arrival order, every file's range would span most
keys, and a lookup would open every file. A key-value store answers the same question in one
request of about one row's bytes. That gap is the price of a layout built for scans, and no
reader setting closes it.

### Delete one order, two ways

A table format can delete a row in two ways. *Copy-on-write* rewrites the row's file without it.
*Merge-on-read* writes a small delete file that names the row, and leaves the reader to take it
out. Both first find the row, which is the lookup above:

```{include} _generated/changes-writes.md
```

Copy-on-write writes a whole file to change one row: its *write amplification* is the file's
size over the row's. Nothing is left for readers to do afterwards, so every later scan costs what
it did before. Merge-on-read writes far less, though still many times the row's size, because
the delete file is a Parquet file with its own footer. It moves the work to every reader: each
later scan of that data file must fetch the delete file and apply it. That is *read
amplification*, and it grows with every delete.

### What deletes and small files do to every scan

A scan of every row reads the snapshots, then every data file and every delete file at once,
since none depends on another:

```{include} _generated/changes-scans.md
```

Each delete file is one more request for every scan. While the requests fit the connections, the
extra requests overlap and cost little; once they do not, the scan takes another round of the
store's latency. The small appends of `after-a-day` are worse: each file is a request, and each
brings its own footer, so the table carries many more bytes for a few more rows. And a position
delete file removes a row only after the reader has decoded its page, so the deleted rows are
decoded all the same.

### Compaction

Compaction repairs both. It reads the files that have deletes, and runs of small files, and
writes them back as a few whole files with the deleted rows gone. The reader's planner chooses
the files for `after-a-day`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/changing_a_table/plan_a_compaction.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/plan_a_compaction.rs
:language: rust
```
:::
::::

Each data file with deletes is a group of its own, with its delete files, since two of them
together would pass the target. The small appends go together into one group. Lower the target to
`100` rows, and the appends split into two groups. Then set the small size to `10` rows instead:
no append is small any more, and only the files with deletes are rewritten. On `merge-on-read-8`
the plan rewrites the files its delete files name and nothing else.

What carrying out the first plan costs, from the files pyarrow wrote for `compacted`:

```{include} _generated/changes-compaction.md
```

The compaction is one large read and one large write, paid once. Every later scan is cheaper, and
after enough scans the compaction has paid for itself. That arithmetic decides how often a table
should be compacted: a table scanned all day repays it quickly, and one read once a week may
never do so. The job also has to run somewhere, at some time, and it competes with the writers:
if a writer deletes from `data/part-1.parquet` while compaction is rewriting it, one of the two
commits must fail and retry.

## Building it

The reader's `changes` module (`python/parquet_lab/changes.py`, or
`crates/parquet-lab/src/changes.rs`) reads a table through its snapshots, which
`read_snapshots` parses out of `_snapshots.json`. A snapshot is two lists, and the rows a data
file still holds are its rows less the rows its delete files name:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/changes.py
:language: python
:start-at: class Snapshot:
:end-before: def read_snapshots(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/changes.rs
:language: rust
:start-at: pub struct Snapshot {
:end-before: /// Every snapshot in a
```
:::
::::

### Reading a delete file

A position delete file is read with the reader's query engine
([ch12](#what-a-query-engine-does)), since it is a Parquet file like any other:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/changes.py
:language: python
:start-at: def read_position_deletes(
:end-before: def _find(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/changes.rs
:language: rust
:start-at: pub fn read_position_deletes(
:end-before: /// The snapshot a table's snapshots file names
```
:::
::::

### Applying the deletes in a scan

A scan fetches every delete file and every data file at once, since none depends on another.
Then it decodes each data file's rows in order, and skips each position a delete file names:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/changes.py
:language: python
:start-at: deleted: set[tuple[str, int]] = set()
:end-before: return TableScan(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/changes.rs
:language: rust
:start-at: let mut deleted: Vec<(String, i64)> = Vec::new();
:end-before: Ok(TableScan {
```
:::
::::

### Finding one row

A lookup reads the snapshots, then the delete files that name the files the key could be in,
in the same round trip as the first read of the data file:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/changes.py
:language: python
:start-at: deleted: list[tuple[str, int, str]] = []
:end-before: found = deleted_by = None
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/changes.rs
:language: rust
:start-at: let mut deleted: Vec<(String, i64, String)> = Vec::new();
:end-before: let (mut found, mut deleted_by
```
:::
::::

Then each candidate data file is read the way [ch10](#how-readers-read) reads any file: its size
known from the snapshot, statistics and the page index to find the page, and the matching pages
of every column. `scan_in` is ch10's scan, sharing the store with the requests before it, so the
trace shows the whole chain. The row is found by its position, and a delete file naming that
position removes it:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/changes.py
:language: python
:start-at: strategy = Strategy(
:end-before: s.next_phase()
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/changes.rs
:language: rust
:start-at: let strategy = Strategy {
:end-before: s.next_phase();
```
:::
::::

Which files a lookup opens, and how the compaction planner groups files, are the problems below;
the reader's own versions, which the steps ran, are in the same module.

### Checking it

The tests hold the reader to pyarrow: for every snapshot, the rows and the sum of `amount_cents`
must be what pyarrow counts after applying the same deletes with its own compute functions. They
look up orders across the whole range in five snapshots, and check that the planner rewrites
exactly the files the `compacted` snapshot replaced:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests -k "snapshot or lookup or compaction or position_delete"
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures -- snapshot lookup compaction position_delete
```
:::
::::

### Ask a library

pyarrow and the `parquet` crate read Parquet files, not tables. Neither knows that a delete file
is anything but a file of paths and numbers, so applying one is yours to do, as the book's reader
does. Here both read `data/part-1.parquet` and every delete file, and take out the rows the delete
files name:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/changing_a_table/deletes_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/deletes_with_a_library.rs
:language: rust
```
:::
::::

The live rows and their sum are the ones the book's reader reports for that file. A table
format's own libraries apply delete files for you when they read a snapshot; the work they do is
this. Change the path to `data/part-2.parquet`, and the other delete files apply instead.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin deletes_with_a_library
```

## What this cannot tell you

**How deep real metadata is.** This table's metadata is one file. Iceberg's is a chain: a
metadata file points to a manifest list, which points to manifests, which list the files. Each
link is another round trip before the first data request, unless a reader caches it.

**Other ways to delete.** Iceberg also has *equality deletes*, which name values instead of
positions (`order_id = 250`), and are cheaper to write and dearer to read. Newer formats use
*deletion vectors*: a bitmap of deleted positions per data file, which is smaller and faster to
apply than a Parquet file of positions. The costs move, and the shape stays: every form of
merge-on-read is work that each reader repeats until compaction.

**Concurrent writers.** One writer changed this table. Two writers, or a writer and a compaction,
commit through the table format's optimistic concurrency: each writes its files, then tries to
make its snapshot current, and one fails if the other got there first. A compaction that loses
that race has done all its work for nothing.

**What old snapshots cost.** Every snapshot here stays readable, so the files of `written` are
still stored after `compacted` replaced them. Real tables *expire* old snapshots and delete the
files no snapshot needs, which ends time travel to those versions.

**What a write costs.** The store prices a write like a read of the same size. A real rewrite
also decodes and re-encodes every row, and a table's compaction usually runs on a cluster whose
cost is the real bill.

## Key takeaways

:::{div}
:class: takeaways

- **A Parquet file never changes.** Its footer records every offset, so each change to a table is
  a new file, and a new snapshot listing it.
- **Finding one row is a chain of dependent requests.** Snapshots, trailer, footer, index, pages:
  each needs the last one's answer, and the row is reassembled from a page of every column. A
  key-value store does it in one request.
- **Copy-on-write pays when it writes.** One changed row costs a whole file, and reads stay cheap.
- **Merge-on-read pays whenever anyone reads.** A delete file is cheap to write, and every later
  scan fetches and applies it, until the table is compacted.
- **Small files cost per file, not per row.** Each brings a request and a footer, so a stream of
  small appends makes every scan slower.
- **Compaction trades one large read and write for cheaper scans.** It pays for itself after
  enough scans, and has to be scheduled around the writers it competes with.
:::

## Problems

Three, in `exercises/python/changing_a_table.py`, or in Rust in
`exercises/src/changing_a_table.rs`. The first two have tests. The third has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: changing_a_table
```

**15.1 The files a lookup opens.** Given a snapshot and an `order_id`, return the data files whose
range holds it and the delete files that name them. The test compares your answer with the
reader's for every order in every snapshot, and for made-up snapshots whose ranges overlap.

**15.2 Plan a compaction.** Choose the files to rewrite, those with deletes and those too small,
and pack them into groups of at most a target number of rows, in order of `order_id`. The rules
are in the stub. The test compares your plan with the reader's across many targets and
snapshots, and checks that for `after-a-day` it rewrites exactly the files `compacted` replaced.

**15.3 Your own table.** No test: the table is yours. Take a table you write to every day. Count
its files, how many are small, and, if it uses merge-on-read, how many delete files it holds.
Estimate how many times a day it is scanned, and what one compaction of it would read and write.
A good answer says whether copy-on-write or merge-on-read suits the table's mix of writes and
reads, how often to compact it, and how many scans a compaction takes to pay for itself. If most
of the table's reads are lookups of single rows, it should say which store would serve those
better.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_15_1` in Python, or `problem_15_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_changing_a_table.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test changing_a_table -- --ignored
```
:::
::::

## Where to go next

- The [Apache Iceberg table specification](https://iceberg.apache.org/spec/) defines snapshots,
  manifests, position and equality delete files, and deletion vectors.
- The [Delta Lake protocol](https://github.com/delta-io/delta/blob/master/PROTOCOL.md) describes
  its deletion vectors and how a writer commits against others.
- O'Neil and others, *The Log-Structured Merge-Tree*, Acta Informatica, 1996, is where writing
  changes aside and merging them later began; compaction is its merge.
- pyarrow's [compute functions](https://arrow.apache.org/docs/python/compute.html) are what the
  library step used to take out deleted rows.
- The [appendices](#glossary) collect the book's terms.
