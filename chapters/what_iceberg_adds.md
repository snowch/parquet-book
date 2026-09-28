---
title: What Iceberg adds to Parquet
---

(what-iceberg-adds)=
# What Iceberg adds to Parquet

## The question

What does Apache Iceberg add on top of Parquet, and which of it has this book already shown?

Parquet describes one file. Its footer knows the file's row groups, columns and statistics, and
nothing about any other file. A table is many files, written over years, and it changes.
[ch14](#lakehouse-and-beyond) found a table's files through a log, and
[ch15](#changing-a-table) changed a table with snapshots, delete files and compaction. Apache
Iceberg is an open specification for that layer: metadata, kept beside the data files, that makes
them one table with a history. Most of what it adds, the book has already shown in some form.
This chapter maps each feature to the chapter that shows it, and describes briefly the pieces no
chapter does. It reads one of them out of a footer: the number by which a table names each
column. It builds nothing new.

## The experiment

### Above the files

Iceberg does not change a Parquet file. A table's data files are ordinary Parquet files, and
everything the earlier chapters read in them still holds: the footer, the row groups, the
statistics and the page index. What Iceberg adds is a set of metadata files above them, and rules
that writers and readers follow. A reader that knows those rules can plan a query over millions
of files without listing a directory, read the table as it was last week, and keep reading while
writers change it.

### A map of the features

Each feature, the problem it solves, what it changes in the Parquet files, and where the book
shows it:

| Feature | Solves | In the Parquet files | Shown in |
|---|---|---|---|
| Metadata tree | Finding a version's files without listing | Nothing | Here; [ch14](#lakehouse-and-beyond) lists and reads a log |
| Statistics in manifests | Ruling files out without opening footers | Copied out of each file | [ch14](#lakehouse-and-beyond), [ch09](#skipping-data) |
| Snapshots and time travel | A consistent version, and older ones | Nothing: files never change | [ch15](#changing-a-table) |
| Copy-on-write, merge-on-read | Changing rows in files that cannot change | New files; delete files are Parquet | [ch15](#changing-a-table) |
| Compaction, snapshot expiry | Small files, delete files, old versions | Whole files rewritten or deleted | [ch15](#changing-a-table) |
| Schema evolution | Renaming and adding columns without rewrites | A field id on every column | Here |
| Hidden partitioning | Partitions a query uses without naming them | The column stays in the file | Here; [ch14](#lakehouse-and-beyond) for paths |
| Sort orders | Files whose statistics rule out well | Sorted rows, narrow ranges | [ch11](#writing-parquet-well), [ch09](#skipping-data) |
| Commits and catalogs | Writers that do not overwrite each other | Nothing | Beyond this book |

The rest of this section takes the rows in order.

### The metadata tree

Iceberg keeps a table's metadata as a tree of files, read from the top:

- **A metadata file**, in JSON, holds the table's schemas, its partition specs and sort orders,
  every snapshot it still keeps, and which snapshot is current. Each commit writes a new one.
- **A manifest list**, one per snapshot, lists the snapshot's manifests, with the range of
  partition values each one covers.
- **A manifest** lists data files, or delete files, one entry per file: its path, its partition
  values, its row count and size, and statistics for each column.
- **A catalog** holds one pointer per table, to its current metadata file.

Manifest lists and manifests are Avro files, a row format. Each is written once, in one pass, and
read one whole entry at a time, so a row layout suits them ([ch01](#why-parquet-exists)).

A reader walks the tree from the top: the catalog, the metadata file, the snapshot's manifest
list, then the manifests. Each level needs the one above it, so each is a round trip before the
first data file is read, as [ch15](#changing-a-table) warned. ch15's `_snapshots.json` flattens
the same tree into one file: a list of snapshots, each listing its data and delete files. The
levels exist so that nothing is rewritten that did not change. A commit that adds one file writes
one new manifest, and a new manifest list that reuses every old manifest.

### Statistics in manifests

Each manifest entry carries the file's statistics: for every column, the number of values and of
nulls, and a lower and an upper bound. A writer usually takes them from the footer it wrote
([ch08](#metadata-and-statistics)). A planner reads the manifests, and opens only the files whose
bounds allow the query's condition.

[ch14](#lakehouse-and-beyond) showed the same idea in Delta Lake's log, where each `add` action
carries a file's statistics as JSON, and measured it: the log ruled out files that a listing had
to open. [ch09](#skipping-data) showed it one level down, in a footer that rules out row groups.
Together they form a ladder: manifests rule out files, footers rule out row groups, and the page
index rules out pages. Each level helps only as far as the layout lets it. A file whose bounds
span every value is opened whatever its manifest says.

Two details differ from a footer. The bounds are keyed by each column's field id, not its name,
for the reason *Columns by id* below reads out of a file. And a writer may shorten a long string's
bounds, as a Parquet writer may ([ch08](#metadata-and-statistics)), so a bound is a limit on the
values and not always one of them.

### Snapshots, changes and upkeep

[ch15](#changing-a-table) built all of this on its own table, and Iceberg's versions differ
mainly in detail:

- **Snapshots and time travel.** Every commit makes a new snapshot, and the old ones stay
  readable, so a reader can ask for the table by snapshot or as it was at a time. A query that
  started on one snapshot keeps reading it while writers commit others.
- **Copy-on-write and merge-on-read.** A table chooses one for its deletes, updates and merges.
  Iceberg's position delete files are the ones ch15 read, with the same `file_path` and `pos`.
  It also has *equality delete files*, which name values rather than positions, and, in its
  third format version, *deletion vectors*: a bitmap of deleted positions per data file.
- **Compaction and snapshot expiry.** Compaction rewrites small files and files with deletes, as
  ch15 planned, and commits the result as a new snapshot. Expiry removes old snapshots, then
  deletes the files no remaining snapshot needs. Until then, time travel to those snapshots
  works, and their files are paid for.

None of these touches the inside of a Parquet file. They change which files a snapshot lists.

### Columns by id

A table's schema changes too. A column is renamed, a new one is added, an old one is dropped. The
files already written keep the schema they were written with, and nobody rewrites a table for a
rename. So a reader must match the table's columns today with the columns of a file written long
before.

Matching by name breaks on the first rename. Iceberg matches by number instead. Each column in the
table's schema has a *field id*, assigned when the column is added and never changed or reused.
An Iceberg writer records each column's id in every data file's footer, in the schema element's
`field_id` ([ch03](#the-type-system) met the field). ch15's data files carry them. Read them with
the book's reader, then resolve the file's columns through a table schema in which one column
has been renamed and another added:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/what_iceberg_adds/field_ids_by_hand.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/field_ids_by_hand.rs
:language: rust
```
:::
::::

In Python, run the step in the page, change it with **Edit**, and run it again. In Rust, open it
in a Codespace, or run it at a desk with `cargo run -p walkthroughs --bin field_ids_by_hand`.

The footer names each column twice: by the name the writer used, and by its id. The table's
schema is keyed by id, so the step turns each id into this file's name, and asks the reader's
engine for those columns. `order_number` is id 1, so it reads the file's `order_id`, although no
file has a column of that name. `channel`, id 7, was added after the file was written. The file
has no column with that id, so every row of the file reads it as null. By name, the file has
neither column. A reader that matched names would lose the renamed column's values, and treat it
as a column that was never written.

Change the id of `channel` to 5 and run it again. `channel` now reads the file's `status`: values
that were never channels. That is why an id is never reused. The table's metadata records the
highest id it has assigned, and a new column takes the next one. Then take `country` out of the
table: the file still holds it, and the step no longer asks for it. Dropping a column changes the
table's metadata and no file.

Iceberg's other schema changes work the same way. Reordering columns changes only the schema.
Widening a type, from a 32-bit to a 64-bit integer for example, is allowed where every stored
value reads correctly as the new type. Nested fields carry ids too, as do the elements of a list
and the keys and values of a map ([ch04](#nested-data)). A file written without ids, such as a
Parquet file brought into a table from elsewhere, is matched through a *name mapping* that the
table keeps, from names to ids.

### Field ids in a library

pyarrow and the `parquet` crate read field ids too. pyarrow puts each in its field's metadata,
under the key `PARQUET:field_id`, and writes one when that key is set: that is how the fixture
generator gave ch15's files their ids. The crate keeps it in each field's basic information.
Neither resolves a table's columns by id. Both read columns by name or by position, so turning an
id into a column is yours to do, as the step before did. An Iceberg library does it for every
file it reads.

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/what_iceberg_adds/field_ids_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/field_ids_with_a_library.rs
:language: rust
```
:::
::::

Both find the ids the book's reader found, and both read id 1 from the file's `order_id`. Change
`wanted` to 4 in either, and both read `country`. Change it to 7, and both stop: the file has no
column with that id, and neither library knows that the table's answer is null.

In Python, the first run loads pyarrow into the page, a much larger download than the other
step. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin field_ids_with_a_library
```

### Hidden partitioning

[ch14](#lakehouse-and-beyond)'s table was partitioned by path. The directory `country=UK` held
the UK orders, the files did not hold `country` at all, and a query ruled files out only when it
named `country`. A table partitioned by day works the same way, with one catch: a query must
filter on the day column, which a writer computed from the timestamp. A query that filters on the
timestamp itself rules nothing out.

Iceberg's partitions are *hidden*. A table's *partition spec* derives each partition value from a
column, by a *transform*: the column's value itself, its year, month, day or hour, a bucket from a
hash of it, or a truncation of it. A writer computes each row's partition value, groups rows by
it, and records it in the file's manifest entry. The column stays in the file, and
readers never read a value from a path. A query filters on the column, `ordered_at`, and the
planner turns that condition into one on the partition value, `day(ordered_at)`, before it reads
the manifests.

A spec can change. A table partitioned by day can be partitioned by hour from today on: new files
are written under the new spec, and old files keep the spec they were written under. Planning
reads each manifest under its own spec, so a query over both periods rules out old files by day
and new files by hour, and nothing is rewritten. A spec refers to its source column by field id,
so renaming `ordered_at` breaks neither spec.

### Sort orders

A table can declare a sort order, and writers then sort the rows of each file by it. Each data
file records the order it was written in. [ch11](#writing-parquet-well) wrote the same orders
sorted and shuffled, and [ch09](#skipping-data) measured what sorting buys: each row group's
statistics span a narrow range, so a condition on the sort key rules most of them out. At the
table's level the same holds for files. Sorted files have narrow bounds in their manifests, and a
planner can rule them out. Compaction can sort as it rewrites, so a table written in arrival
order becomes cheaper to filter over time.

### Commits and catalogs

A commit writes new data files, new manifests, a new manifest list and a new metadata file, and
then asks the catalog to move the table's pointer from the metadata file it started from to the
new one. The move succeeds only if nobody moved it first. If another writer did, the commit reads
the new metadata, checks whether the two changes conflict, and tries again. A catalog can be a
service, a database table, or a filesystem that offers an atomic rename; Iceberg's REST catalog
specification defines one as an HTTP API. How writers conflict, and how catalogs keep the pointer
safe, is beyond this book: its store has one reader and no writers.

### Delta Lake and Apache Hudi

Two other open table formats solve the same problems over Parquet files. They keep the list of
files differently, and they arrange changes differently.

**Delta Lake** keeps a transaction log beside the data, which [ch14](#lakehouse-and-beyond) read:
a directory of numbered JSON files, one per commit, of `add` and `remove` actions, with each
file's statistics inside its `add`. Every so often a writer summarises the log so far in a
*checkpoint*, a Parquet file, so a reader need not replay every commit. A commit creates the next
numbered file, and fails if another writer created it first. Deletes rewrite files or, with
*deletion vectors*, mark rows in a small file beside the data file. Partitions are columns whose
values each `add` records. Columns are matched by name unless the table enables *column mapping*,
which gives each column an id or a physical name in the files.

**Apache Hudi** is built around records with keys, and around changing them. It keeps a
*timeline* of actions on the table (commits, compactions, cleanings), each with its state. A
table's files are organised in *file groups*, and an index maps each record key to its file group,
so an update finds its file without scanning. A copy-on-write table rewrites a file group's
Parquet *base file*. A merge-on-read table appends changes to *log files* beside the base file,
which a reader merges in and a compaction folds into a new base file. An internal *metadata
table* holds the file listing, column statistics and Bloom filters, so planning need not list
directories or open footers.

All three keep the Parquet files as the earlier chapters read them. They differ in how they
record which files make a table, how they commit, and where they put the cost of a change.

## What this cannot tell you

**Iceberg's own files.** The book's table is not an Iceberg table. Its metadata is one JSON file
of snapshots, and its table schema lives in the step's code. The book reads no metadata file, no
manifest list and no Avro manifest, and nothing measures the round trips the tree costs.

**Everything Iceberg specifies.** Its specification has three format versions, and features this
chapter leaves out: branches and tags that name snapshots, default values for added columns, row
lineage, and statistics files kept beside the manifests. What an engine supports differs between
engines and versions.

**Nested ids and name mappings.** The step resolves the flat columns of one file. It shows
neither the ids of nested fields nor the name mapping that matches files written without ids.

**Other formats in depth.** The comparison with Delta Lake and Apache Hudi describes their
designs in a paragraph each. Each has a specification of its own, and each has changed since this
was written.

**Concurrency.** Commits, conflicts and retries need writers, and the simulated store has none.

## Key takeaways

:::{div}
:class: takeaways

- **Iceberg adds metadata above Parquet files, not inside them.** Every data file is a Parquet
  file as the earlier chapters read it; the table is a tree of files that list them.
- **Most of what it adds, the book has shown in another form.** Statistics that rule out files
  ([ch14](#lakehouse-and-beyond)), snapshots, delete files and compaction
  ([ch15](#changing-a-table)), and sorted files ([ch11](#writing-parquet-well)).
- **A table names its columns by field id.** Each data file's footer records the ids, so a
  rename changes only metadata, and a column added later reads as null from older files.
- **An id is never reused.** A reused id would read an old column's values as a new column's.
- **Partitions are derived from columns, not read from paths.** A query filters on the column,
  the planner applies the transform, and the spec can change without rewriting a file.
- **Delta Lake and Hudi solve the same problems differently.** A log of actions, or a timeline
  with keyed file groups, over the same Parquet files.
:::

## Problems

Four, all for reasoning. No test grades them: the chapter builds nothing.

**16.1 Rename by name.** No test. A table's column `order_id` is renamed `order_number`, and new
files are written after the rename. Say what a reader that matches columns by name returns for
`order_number` from files written before the rename, and from files written after, and what a
query that sums a column across both returns. Then say what changes when the reader matches by
field id. A good answer says that, by name, the older files have no `order_number`, so it reads
as null there, and a sum or a count over the whole table silently covers only the newer files.
Matching by id reads the older files' `order_id` as `order_number`, because both carry the same
id. It also says that adding a new column called `order_id` after the rename is safe only by id:
by name, the new column would read the older files' values as its own.

**16.2 What a planner opens.** No test. A table has a hundred manifests of a thousand files each.
Every manifest entry carries lower and upper bounds for `order_id`, and the files are sorted by
it, each covering its own narrow range. Say what a planner reads, and which files it opens, for
`order_id = 300`, for `order_id < 300`, and for `status = 'refunded'`. Then say what changes if
the files were written in arrival order. A good answer says the planner reads the manifest list,
then manifests, and opens no data file until the manifests have ruled files out. For the
equality it opens the one file whose range holds the value, and for the range the files whose
ranges start below it. For `status` it opens every file whose bounds include the value, which is
likely all of them. With files in arrival order every file spans most of `order_id`, so the
bounds rule out little, as the shuffled file did in [ch09](#skipping-data). It also says the
manifest list's partition ranges could skip whole manifests if the table were partitioned on a
column the query names.

**16.3 Partition evolution.** No test. A table partitioned by `day(ordered_at)` changes its spec
to `hour(ordered_at)` on the first of a month. Say what happens to the files written before the
change, and how a planner handles `ordered_at` between the tenth and the eleventh of the previous
month, and within one hour of today. A good answer says that nothing happens to the old files:
they keep their day partitions and their old spec. The planner reads each manifest under its own
spec, turns the condition into days for old files and hours for new ones, and rules out files on
either. It also says the old files do not become hourly unless something rewrites them, such as a
compaction under the new spec, so a query of one hour last month still opens that whole day's
files.

**16.4 Your own table.** No test: the table is yours. Take a table you write to, in whatever
table format it uses, and find in its metadata how it names columns, how it partitions, and how
many files a typical query opens. A good answer says whether columns are matched by id or by
name, and what a rename would do to the files already written. It says whether the partitions are
derived from a column or written into paths, and whether the queries you run most filter on the
partition column itself or on the column it was derived from. It ends with one change, to the
partitioning or to the sort order, that would let the metadata rule out more files. If renames
would break the table, that is the first thing to fix.

## Where to go next

- The [Apache Iceberg table specification](https://iceberg.apache.org/spec/) defines the metadata
  tree, field ids and schema evolution, partition transforms and evolution, sort orders, delete
  files and the commit protocol.
- The [Delta Lake protocol](https://github.com/delta-io/delta/blob/master/PROTOCOL.md) specifies
  the transaction log, checkpoints, column mapping and deletion vectors.
- The [Apache Hudi technical specification](https://hudi.apache.org/tech-specs/) describes the
  timeline, file groups, base and log files, and the metadata table.
- Iceberg in depth, from its catalogs to its engines' planners, is a subject for a book of its
  own. This book stops at the Parquet files beneath it.
- The [appendices](#glossary) collect the book's terms.
