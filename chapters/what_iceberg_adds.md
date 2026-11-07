---
title: What Iceberg adds to Parquet
---

(what-iceberg-adds)=
# What Iceberg adds to Parquet

## The question

What does Apache Iceberg add on top of Parquet, and which of it has this book already shown?

Parquet describes one file. Its footer knows the file's row groups, columns and statistics, and
nothing about any other file. A table is many files, written over years, and it changes.
[Lakehouse and beyond](#lakehouse-and-beyond) found a table's files through a log, and
[Changing a table](#changing-a-table) changed a table with snapshots, delete files and compaction. Apache
Iceberg is an open specification for that layer: metadata, kept beside the data files, that makes
them one table with a history. Most of what it adds, the book has already shown in some form.
This chapter maps each feature to the chapter that shows it, and describes briefly the pieces no
chapter does. It reads one of them out of a footer: the number by which a table names each
column. It builds nothing new.

:::{div}
:class: reading-guide

**What you will learn:** Locate the boundary between Parquet files and Iceberg table metadata, and explain why schema evolution needs stable field identities.

Read the explanations, worked results and diagrams; the code is optional.
:::

## The experiment

```lesson
follow-iceberg-metadata
```

### The metadata tree

A Parquet footer maps one file. An Iceberg table needs another map to find the files belonging
to a snapshot. This schematic follows the manifest-list layout of Iceberg format versions one
to three. It explains the specification; it is not output from this book's reader opening a real
Iceberg table.

A **commit** publishes a new version of the table's metadata. Iceberg keeps that metadata as
a tree of files, followed from the top:

- A **catalog** records which metadata file is current for each table. Its pointer is a file
  location, not the contents of the table.
- A **metadata file**, in JSON, holds the table's schemas, partition rules and sort orders,
  retained snapshots and the current snapshot. Each commit writes a new metadata file.
- A **manifest list**, one per snapshot, lists the snapshot's manifests, with the range of
  partition values each one covers.
- A **manifest** lists data files, or delete files, one entry per file: its path, its partition
  values, its row count and size, and statistics for each column.

Follow the pointers below from the catalog to the data. Both snapshots refer to the shared manifest;
the append adds another branch.

```{include} _generated/visual-iceberg-tree.md
```

Manifest lists and manifests are Avro files, a row format. Each is written once, in one pass, and
read one whole entry at a time, so a row layout suits them ([Why Parquet exists](#why-parquet-exists)).

A reader walks the tree from the top: the catalog, the metadata file, the snapshot's manifest
list, then the manifests. Discovering the next location depends on the preceding metadata,
so this traversal can require dependent requests before choosing a data file. Caching can avoid them. The
[snapshot fixture](follow-snapshots-and-deletes.html) flattens this idea into `_snapshots.json`: a list of snapshots, each listing its data and delete files. The
levels exist so that nothing is rewritten that did not change. A commit that adds one file writes
one new manifest, and a new manifest list that reuses every old manifest.

### Statistics in manifests

Each manifest entry carries the file's statistics: for every column, the number of values and of
nulls, and a lower and an upper bound. A writer usually takes them from the footer it wrote
([Metadata and statistics](#metadata-and-statistics)). A planner reads the manifests, and opens only the files whose
bounds allow the query's condition.

[Lakehouse and beyond](#lakehouse-and-beyond) showed the same idea in Delta Lake's log, where each `add` action
carries a file's statistics as JSON, and measured it: the log ruled out files that a listing had
to open. [Skipping data](#skipping-data) showed it one level down, in a footer that rules out row groups.
Together they form a ladder: manifests rule out files, footers rule out row groups, and the page
index rules out pages. Each level helps only as far as the layout lets it. A file whose bounds
span every value is opened whatever its manifest says.

Two details differ from a footer. The bounds are keyed by each column's **field id**, a stable
number identifying a column, rather than its name. The next lesson shows why that identity
must survive a rename. A writer may shorten a long string's
bounds, as a Parquet writer may ([Metadata and statistics](#metadata-and-statistics)), so a bound is a limit on the
values and not always one of them.

This is a schematic explanation of Iceberg’s metadata hierarchy. The teaching reader does not execute a real Iceberg metadata-tree scan.

```practice
question: A manifest list rules out a manifest for a partition predicate. Must a planner open every data file listed in that skipped manifest to justify the same exclusion?
answer: No. Conservative table metadata can rule out the whole branch before data-file footers are fetched. Kept branches still require further planning and row filtering.
```

```lesson
keep-column-identity
```

### Columns by id

**Schema evolution** changes a table's columns or their types while retaining readable older files.
A table's schema can change while its older files remain stored. A column is renamed, a new one is added, an old one is dropped. The
files already written keep the schema they were written with, and nobody rewrites a table for a
rename. So a reader must match the table's columns today with the columns of a file written long
before.

Matching by name breaks on the first rename. Iceberg matches by number instead. Each column in the
table's schema has a *field id*, assigned when the column is added and never changed or reused.
An Iceberg writer records each column's id in every data file's footer, in the schema element's
`field_id` ([The type system](#the-type-system) introduces the schema). The fixture
`fixtures/changes/data/part-0.parquet` carries these IDs. Read them with the book's reader,
then resolve the file's columns through a small table schema with a rename and an added field:

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
engine for those columns. `order_number` is id 1, so it reads the file's `order_id`, although the
file has no column named `order_number`. `channel`, id 7, was added after the file was written. The file
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
and the keys and values of a map ([Nested data](#nested-data)). A file written without ids, such as a
Parquet file brought into a table from elsewhere, is matched through a *name mapping* that the
table keeps, from names to ids.

### Field ids in a library

pyarrow and the `parquet` crate read field ids too. pyarrow puts each in its field's metadata,
under the key `PARQUET:field_id`, and writes one when that key is set: that is how the fixture
generator gave the `fixtures/changes/` data files their ids. The crate keeps it in each field's basic information.
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

The example adds a nullable field without a non-null default, so missing old-file values become null. Defaults and other evolution rules require the table format’s semantics.

```practice
question: A table drops an old field named region, then adds a different field with the same name and a new ID. May old file values be attached to the new field by matching the name?
answer: No. A new ID means a different field. Match the intended field identity, not its current spelling. A rename preserves an ID; dropping and reusing a name does not.
```

```lesson
evolve-partition-specs
```

### Hidden partitioning

The [partition-path example](read-partition-paths.html) uses a Hive-style orders table. The directory `country=UK` held
the UK orders, the files did not hold `country` at all, and a query ruled files out only when it
named `country`. A table partitioned by day works the same way, with one catch: a query must
filter on the day column, which a writer computed from the timestamp. A query that filters on the
timestamp itself does not use that path-only partition test; other metadata may still help.

**Hidden partitioning** lets queries filter on source columns without naming a separate
partition column. A **partition spec** records the source columns and rules that derive the
partition values. A **partition transform** is one such rule: the column's value itself, its year, month, day or hour, a bucket from a
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
file records the order it was written in. [Writing Parquet well](#writing-parquet-well) wrote the same orders
sorted and shuffled, and [Skipping data](#skipping-data) measured what sorting buys: each row group's
statistics span a narrow range, so a condition on the sort key rules most of them out. At the
table's level, files covering narrow ranges can be ruled out by their manifest bounds. Sorting
within each file does not by itself make different files' ranges disjoint. Compaction that
reorganises rows into narrower file ranges can improve later pruning.

```practice
question: Old files partition an event time by day, while new files use month. Can a planner interpret every old partition value with the new month transform?
answer: No. Each file’s partition data belongs to its recorded spec. Apply the predicate under that spec, then combine candidate files. A new spec does not rewrite old files or globally sort their rows.
```

```lesson
commit-a-table-change
```

### Commits and catalogs

This specification-level example uses the [Iceberg metadata tree](follow-iceberg-metadata.html):
a catalog points to the current metadata file, which names the table's snapshots.
The teaching reader does not implement a catalog or concurrent writers.

A **commit** publishes a table metadata change. The **catalog** identifies the current metadata
file. **Atomicity** means that readers see the old location or the new one when that pointer
changes, never a partially written location. **Optimistic concurrency** lets writers prepare changes
independently, then check that publishing them will not overwrite a conflicting change.

A commit that appends data writes new data files, new manifests, a new manifest list and a new
metadata file, then asks the catalog to move the table's pointer from the metadata file it started from to the
new one. The move succeeds only if nobody moved it first. If another writer did, the commit reads
the new metadata, checks whether the two changes conflict, and tries again. A catalog can be a
service, a database table, or a filesystem that offers an atomic rename; Iceberg's REST catalog
specification defines one as an HTTP API. How writers conflict, and how catalogs keep the pointer
safe, is beyond this book: its store has one reader and no writers.

This is a specification-level concurrency example. The teaching reader does not run a catalog or concurrent writers; conflict rules depend on the operation.

```practice
question: Two writers plan from the same metadata version. After one commits, may the other overwrite the pointer with its stale plan without checking again?
answer: No. The second must detect the changed base and revalidate or retry under the table’s conflict rules. Otherwise it can lose a committed change. Atomic pointer replacement alone is not a reason to trust a stale plan.
```

```lesson
reference
```

### Above the files

Iceberg can store data in Parquet, Avro or ORC. This book follows its Parquet files, which keep
their ordinary footer, row groups, statistics and optional page indexes. What Iceberg adds is a set of metadata files above them, and rules
that writers and readers follow. A reader that knows those rules can plan a query over millions
of files without listing a directory, read the table as it was last week, and keep reading while
writers change it.

### A map of the features

This map compares Iceberg's table-level features with the book's teaching examples. Start
with [the metadata tree](follow-iceberg-metadata.html) for Iceberg's manifest-list layout.
The linked examples demonstrate related mechanisms; they are not a complete Iceberg reader:

| Feature | Solves | In the Parquet files | Shown in |
|---|---|---|---|
| Metadata tree | Finding a version's files without listing | Nothing | [Iceberg metadata tree](follow-iceberg-metadata.html); [log-based discovery](prune-files-before-footers.html) |
| Statistics in manifests | Ruling files out without opening footers | Copied out of each file | [File pruning](prune-files-before-footers.html); [row-group pruning](rule-out-row-groups.html) |
| Snapshots and time travel | A consistent version, and older ones | Nothing: files never change | [Snapshot history](follow-snapshots-and-deletes.html) |
| Copy-on-write, merge-on-read | Changing rows in files that cannot change | New data or delete information | [Update costs](compare-update-costs.html) |
| Compaction, snapshot expiry | Small files, delete files, old versions | Whole files rewritten or deleted | [Compaction](decide-when-to-compact.html); [expiry limits](changing-a-table-notes.html) |
| Schema evolution | Renaming and adding columns without rewrites | A field id on every column | [Stable column identity](keep-column-identity.html) |
| Hidden partitioning | Partitions a query uses without naming them | The column stays in the file | [Partition evolution](evolve-partition-specs.html); [partition paths](read-partition-paths.html) |
| Sort orders | Files whose statistics rule out well | Sorted rows; bounds depend on file layout | [Writer layouts](compare-writer-layouts.html); [pruning](compose-a-pruning-plan.html) |
| Commits and catalogs | Writers that do not overwrite each other | Nothing | [Commit model](commit-a-table-change.html), without an implementation |

The rest of this comparison covers snapshots and changes, then contrasts Delta Lake and Hudi.

### Snapshots, changes and upkeep

The [snapshot fixture](follow-snapshots-and-deletes.html) demonstrates data and position-delete
files; the [compaction experiment](decide-when-to-compact.html) measures a rewrite. Iceberg
adds its own metadata and commit rules around these mechanisms:

- **Snapshots and time travel.** A data change makes a new snapshot, and the old ones stay
  readable, so a reader can ask for the table by snapshot or as it was at a time. A query that
  started on one snapshot keeps reading it while writers commit others.
- **Copy-on-write and merge-on-read.** A table chooses one for its deletes, updates and merges.
  The teaching fixture uses Iceberg's `file_path` and `pos` position-delete columns.
  Iceberg also has *equality delete files*, which name values rather than positions, and, in its
  third format version, *deletion vectors*: a bitmap of deleted positions per data file.
- **Compaction and snapshot expiry.** Compaction rewrites small files and files with deletes, as
  the [compaction experiment](decide-when-to-compact.html) planned, and commits the result as a new snapshot. Expiry removes old snapshots, then
  deletes the files no remaining snapshot needs. Until then, time travel to those snapshots
  works, and their files are paid for.

None of these touches the inside of a Parquet file. They change which files a snapshot lists.

### Delta Lake and Apache Hudi

Two other open table formats solve the same problems over Parquet files. They keep the list of
files differently, and they arrange changes differently.

**Delta Lake** keeps a transaction log beside the data: numbered JSON files of `add` and
`remove` actions, with each file's statistics inside its `add`.
[Prune files before reading their footers](prune-files-before-footers.html) reads one
simplified log file in that shape, not a full multi-version Delta table. Every so often a writer summarises the log so far in a
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

These notes separate the module's specification explanations from its executable evidence.
The [metadata tree](follow-iceberg-metadata.html) and [commit example](commit-a-table-change.html)
are schematic. The [field-ID walkthrough](keep-column-identity.html) reads a real Parquet
fixture and resolves its columns through a small schema supplied in code.
[The feature comparison](what-iceberg-adds-comparison.html) connects these to other table formats.

**Iceberg's own files.** The `fixtures/changes/` teaching table is not an Iceberg table. Its
`_snapshots.json` lists snapshots, and the field-ID walkthrough's table schema lives in code. The book reads no metadata file, no
manifest list and no Avro manifest, and nothing measures the round trips the tree costs.

**Everything Iceberg specifies.** The metadata-tree example uses format versions one to three.
The specification continues to evolve and includes features omitted here: branches and tags that name snapshots, default values for added columns, row
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

- **Iceberg adds a table layer above data files.** This book follows the Parquet case;
  Iceberg also supports Avro and ORC data files. The metadata tree identifies the table's files.
- **Most of what it adds, the book has shown in another form.** Statistics that rule out files
  ([Lakehouse and beyond](#lakehouse-and-beyond)), snapshots, delete files and compaction
  ([Changing a table](#changing-a-table)), and sorted files ([Writing Parquet well](#writing-parquet-well)).
- **An Iceberg table names its columns by field id.** A rename preserves that identity.
  The walkthrough's added nullable field has no non-null default, so older files supply null.
  Other defaults require the table format's rules.
- **An id is never reused.** A reused id would read an old column's values as a new column's.
- **Partitions are derived from columns, not read from paths.** A query filters on the column,
  the planner applies the transform, and the spec can change without rewriting a file.
- **Delta Lake and Hudi solve the same problems differently.** A log of actions, or a timeline
  with keyed file groups, over the same Parquet files.
:::

```checkpoint
question: Why is a stable field id safer than a column name when a table renames a field?
answer: A rename changes the label but preserves the identity. An older file can still supply the field through its id even when its stored name differs. Reusing that id for a different field would silently select the old data, so ids must retain their meaning.
```

## Problems

These questions apply [stable field IDs](keep-column-identity.html), the
[metadata tree](follow-iceberg-metadata.html), and [partition evolution](evolve-partition-specs.html)
to new tables. The manifest questions use Iceberg's manifest-list layout from format versions
one to three. No code or automated grading is required.

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
bounds rule out little, as the shuffled file did in [Skipping data](#skipping-data). It also says the
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
