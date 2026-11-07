---
title: What a query engine does
---

(what-a-query-engine-does)=
# What a query engine does

## The question

What does a query engine do with a Parquet file, and what does each kind of query cost?

The reader can now find a footer, trust its statistics, skip row groups and pages, decode every
encoding and fetch bytes carefully. [Writing Parquet well](#writing-parquet-well) showed how a writer's choices
decide what a reader can skip. At work nobody calls those pieces one at a time. You write SQL or
a dataframe expression, and a query engine decides which pieces to use. How an engine works
inside would take a book of its own. This chapter is about its role: what it asks of a Parquet
file, and what the common operations cost against one. It builds nothing new.

:::{div}
:class: reading-guide

**What you will learn:** Separate file pruning from row filtering, and explain which queries can be answered from metadata.

Read the explanations, worked results and diagrams; the code is optional.
:::

## The experiment

```lesson
separate-scan-and-filter
```

### Who does what

A **query engine** turns a query into operations that produce its answer. Its **query plan**
orders those operations and the data passed between them. A **scan** reads data from storage;
a **filter** tests decoded rows against a condition and keeps the matching rows.
**Projection** selects the columns needed by the query, including columns used only by a condition.

A Parquet file is data and metadata, and nothing more. It holds column chunks, and a footer that
says where each one is and what range its values span ([Anatomy of a Parquet file](#anatomy-of-a-parquet-file),
[Metadata and statistics](#metadata-and-statistics)). It runs nothing, and it cannot tell which of its bytes a query
needs.

The engine does everything else. **Predicate pushdown** gives a condition to the scan so it
can apply it close to the data. Metadata **pruning** is one possible benefit: ruling out a
region before reading its values. The scan may also filter decoded rows; pushing a condition
down does not mean metadata alone can decide which individual rows match.

- **It plans the query.** It parses the text, checks the names against the file's schema, and
  works out which columns and which conditions each part of the query needs.
- **It pushes the projection and the filter down into the scan.** The scan is the part of the
  plan that reads the file. Told which columns to read and which conditions must hold, it can
  rule out parts of the file from the footer before it fetches them.
- **It schedules the reads.** It decides which byte ranges to request, merges neighbouring ones,
  and runs requests side by side ([How readers read](#how-readers-read)).
- **It decodes.** It decompresses pages and turns encoded values back into values
  ([Encodings](#encodings), [Compression](#compression)).
- **It runs everything after the scan.** Filtering rows, grouping, sorting, joining and limiting
  work on values already decoded. The file takes no part in them.

The file's part ends at the scan. This experiment measures the bytes that scan fetches and
the values it decodes. Every later stage sees only what the scan passed on; its own processing
cost is outside those measurements.

### What a scan can skip

Earlier chapters showed four ways for a scan to avoid reading, each decided before a page is
fetched:

- **Columns the query does not name.** Each column chunk is a separate range of the file
  ([Why Parquet exists](#why-parquet-exists)).
- **Row groups whose statistics rule a condition out.** Each column chunk's minimum and maximum
  are in the footer ([Metadata and statistics](#metadata-and-statistics), [Skipping data](#skipping-data)).
- **Pages the page index rules out**, inside the row groups that remain
  ([Skipping data](#skipping-data)).
- **Row groups whose Bloom filter says a value is absent**, for an equality on a column whose
  ranges rule nothing out ([Skipping data](#skipping-data)).

[How readers read](#how-readers-read) turned what remained into requests. None of these changes the answer.
They decide only how much of the file the answer costs.

### The book's engine

An **aggregate** combines several values into a result, such as a count or a sum.
The following query counts orders for each country.

**Run a query.** The book's reader includes a small engine. It runs a query as a few stages and
reports what each stage did. Its [limitations](what-a-query-engine-does-notes.html) describe
what production engines do differently. This example uses `writing-baseline.parquet`, sorted
by `order_id`, and counts orders per country where `order_id < 300`, then sorts the countries:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/what_a_query_engine_does/run_a_query.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/run_a_query.rs
:language: rust
```
:::
::::

In Python, run the step in the page, change it with **Edit**, and run it again. In Rust, open it
in a Codespace, or run it at a desk with `cargo run -p walkthroughs --bin run_a_query`.

The Scan stage is the only one that touched the file. It skipped two of the four row groups on
their `order_id` statistics, and read the two columns the query names from the others. The
Filter stage kept the rows whose `order_id` passes the condition, the Aggregate stage counted each country, and the
Sort stage ordered the countries. Each of them worked on rows the scan had already decoded.

Follow the same query through its stages below. The scan admits possible matches; the filter checks
the decoded rows before grouping.

```{include} _generated/visual-query-stages.md
```

Change the query to `SELECT count(*) FROM orders`, and the scan reads no column at all. The optional module notes compare further query shapes. The following lessons examine their individual mechanisms.

### Projection

`SELECT *` read every column chunk of every row group. Naming two of the six columns read a
small part of those bytes and decoded a third of the values. Pushing a projection down costs an
engine nothing, but only the query can ask for it: an engine cannot know you want two columns if you
write `SELECT *`. A dataframe that loads a whole file and then selects two columns has already
paid for all six, unless its library waits to read until it knows which columns are wanted.

### Filters

`order_id < 300` skipped half the row groups. The file is sorted by `order_id`, so each row
group's statistics span a narrow range, and two of the ranges lie wholly above the limit.
`status = 'refunded'` skipped nothing. Refunds occur in every row group, so every row group's
range includes the value, and the engine decoded every row to find them. The two conditions have
the same shape. What differs is how the file is laid out against each one
([Writing Parquet well](#writing-parquet-well)).

A pushed-down filter skips only what the metadata rules out; the engine still checks every row
it decodes. The statistics decide which row groups to read, the page index narrows those to
pages, and a Bloom filter can rule out an equality on a column such as `customer_id`, whose values
are spread through every row group ([Skipping data](#skipping-data)). The book's engine stops at row
groups. A scan that also uses the page index reads fewer pages of the row groups it keeps, as
[Skipping data](#skipping-data) measured.

This teaching engine judges only comparisons of a stored column with a constant against a
minimum and a maximum. A function of the column, such as `lower(country) = 'fr'`, needs the function's
effect on the range, which an engine rarely knows. A comparison of two columns needs both
columns' values, row by row. Engines that cannot push a condition down still apply it, after
decoding every row. Where you can, write conditions on the stored columns themselves.

This small engine prunes row groups and decodes retained values. It does not implement every page-index or production-optimizer technique.

### The same query in a library

At work a library or an engine runs the query. pyarrow's dataset module pushes the condition
down into its scan, keeps the row groups whose statistics allow it, reads only the columns the
query needs, then filters and groups. The `parquet` crate has no query language. You give it a
predicate on each row group's statistics, as in [Skipping data](#skipping-data), and a projection of the
columns to read, then filter and count the rows yourself:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/what_a_query_engine_does/query_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/query_with_a_library.rs
:language: rust
```
:::
::::

Both keep the two row groups the book's engine read, and both count the same orders per country.
pyarrow's `subset` says which row groups a condition keeps, from the statistics alone, before any
page is read. The crate's predicate tests each row group's minimum, and its row iterator decodes
only the projected columns. Change the limit to `450` in either, and both keep a third row group.

In Python, the first run loads pyarrow into the page, a much larger download than the engine's
step. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin query_with_a_library
```

```practice
question: A row group’s range admits a predicate, but only one of its rows really matches. Can the scan pass all its rows through as final matches without checking them?
answer: No. Metadata admits possible matches. The engine must evaluate the predicate on decoded rows before grouping or returning results. A retained row group does not prove every row passes.
```

```lesson
answer-from-metadata
```

### Answers from the footer

The [query-cost comparison](what-a-query-engine-does-comparison.html) runs the teaching engine
on `writing-baseline.parquet`, an orders file sorted by `order_id`. Use its count and minimum
rows to distinguish metadata-only answers from answers that require decoding values.

`count(*)` read no bytes after the footer. The footer records each row group's row count, and
the engine added them up. With a condition, `count(*)` needs the condition's column, except in
row groups whose statistics show that every row passes, or that none does.

`min(order_id)` and `max(order_id)` are in the footer too, as each row group's statistics, and
the file's minimum is the smallest of them. The book's engine does not use them: it read the
column and decoded every value. An engine that answers from the footer must first check three
things:

- **Every row group has statistics for the column.** They are optional.
- **They are exact.** A writer may shorten a long string's bounds, and says so in the exact flags
  of [Metadata and statistics](#metadata-and-statistics).
- **No condition removes rows.** The statistics describe every row, not the rows a filter keeps.

`count(column)` works the same way: the row count, less the null count from the statistics.

```practice
question: An unfiltered file has row counts, but a new query asks count(*) where status is refunded. May the engine always reuse the whole-file count?
answer: No. Whole-file counts include rows the predicate can remove. The engine must inspect the predicate column unless metadata proves that every or no row passes. Missing or inexact bounds also prevent some metadata-only answers.
```

```lesson
group-dictionary-values
```

### Grouping

**Grouping** puts rows with the same key values together, such as all orders for one country.
An aggregate can then compute one count or sum for each group. The dictionary indices below
are compact labels for stored values, not shared identities across all chunks.

In the [query-cost comparison](what-a-query-engine-does-comparison.html), `GROUP BY country`
on `writing-baseline.parquet` reads one column, and a cheap one, because it is dictionary-encoded
([Encodings](#encodings)). It holds a few distinct values, so each chunk is a small dictionary page and
a run of short indices. The same rows of `order_id`, whose values are all distinct, cost several
times as many bytes.

An engine can go further. It can group on the dictionary's indices instead of the strings, and
look up each string once per group. pyarrow's `read_dictionary` option keeps a column in that
form, as indices into a dictionary, rather than as strings. `DISTINCT` is a `GROUP BY` without
aggregates, and the same holds for it. There are two catches. A dictionary belongs to one column chunk, so the
same index means different strings in different row groups, and an engine must merge the
dictionaries. And a writer that fell back to plain encoding, because a dictionary grew too
large, leaves some pages with no indices at all ([Encodings](#encodings)). The book's engine decodes
every string and groups by comparing them.

Two schematic chunk dictionaries illustrate the problem. Chunk A has `[UK, FR]` and one
index of zero; chunk B has `[FR, UK]` and one index of zero. Resolve each locally: the rows
are UK and FR, so grouping produces one row in each country group, not two UK rows.

```practice
question: A fresh chunk’s dictionary is [FR, DE], while another is [DE, FR]. Both return index one. Do those rows belong to the same country group?
answer: No. Index one is DE in the first chunk and FR in the second. Resolve or unify the chunk-local dictionaries before treating the indices as shared group identities.
```

```lesson
limit-a-sorted-query
```

### Sorting with a limit

A **top-k** query asks for the first *k* rows under an ordering, such as the five largest amounts.
Keeping only the best candidates found so far limits memory use. It does not prove that unread
rows contain no better candidate.

The [query-cost comparison](what-a-query-engine-does-comparison.html) uses
`writing-baseline.parquet`, sorted by `order_id`. Its `ORDER BY amount_cents DESC LIMIT 5` query
returns order numbers and amounts, and reads both columns for every row. The largest amounts could be in any row group, and without safe bounds or known order, a stage cannot know it has the top five
until it has examined every candidate row. An engine keeps only the best rows found so far, so its memory stays
small, but its scan reads everything. It can still skip a row group whose maximum amount is below
the fifth largest found so far, which the statistics allow and some engines do. The book's engine
does not.

`ORDER BY order_id LIMIT 5` cost exactly the same, although the file is sorted by `order_id` and
the answer lies in its first row group. The book's engine does not know the order. An engine can
learn it from the footer: a writer may record it in each row group's `sorting_columns`
([Metadata and statistics](#metadata-and-statistics)), and the statistics show whether row groups' ranges overlap.
An engine that knows the order can read the first row group and stop. So sorting a file on the
key that queries order by, or filter on, makes both kinds of query cheap.

```practice
question: A top-k operator keeps only its best candidates so far in memory over an unsorted file. Does that alone let it stop before later row groups?
answer: No. A later row may beat the current candidates. Early stopping or skipping needs ordering or safe bounds that rule out better rows; small working memory alone does not provide that proof.
```

```lesson
use-join-derived-filters
```

### Joins

A **join** matches rows from two inputs using a condition. For the equality joins here, that
condition is equal key values. An **inner join** returns only matching pairs.

A **hash join** uses a **hash table**, a lookup structure that uses a key's hash to find its
possible matches, then checks key equality. The engine stores one input, the **build side**,
in that table. It reads the other, the **probe side**, and looks up each row's key.
For a join that fits in memory, the smaller input is usually the build side; the probe side
can stream past it without being held whole.

The build side is read first, so its keys are known before the probe side's scan starts. An
engine can turn them into a filter on that scan: the keys' smallest and largest value as a range
condition, a Bloom filter of the keys, or the list of keys if it is short. The probe side's scan
then skips row groups as any filtered scan does. **Dynamic filtering** uses values learned
while running one part of a query to restrict another part's scan. Trino uses that name; Spark has
*runtime filters* and *dynamic partition pruning*. The book's engine has no joins. Its scan can
run the range condition a join would push down. The comparison uses the sorted and shuffled
orders fixtures, `writing-baseline.parquet` and `writing-shuffled.parquet`, as probe inputs. Its build keys come from the UK and German partitions in
`fixtures/table/` and a small append in `fixtures/changes/`, identified in the table:

```{include} _generated/engine-join.md
```

Each row makes one point:

- **A narrow key range skips row groups of a sorted probe side.** The UK file's keys span a part
  of the orders, so the sorted probe side skips the row groups outside that part. The shuffled
  one skips none, because each of its row groups spans nearly every order.
- **The range matters, not the number of keys.** The German file holds as many keys, but they
  span almost every order, so the range rules nothing out on either layout. A list of the keys,
  checked against each row group's Bloom filter where the file has them, could still skip some.
- **Keys outside the probe side's range skip everything.** The appended orders come after every
  existing order, so no row group of either probe side could match. The scan reads nothing, and
  the join is empty before a page is read.

A **partition** groups rows by a shared key or derived value. Partitions and sort orders help
a join in a second way. When both inputs are partitioned on the
key, or sorted by it, an engine can join them piece by piece. It joins each partition of one side
with the matching partition of the other, or merges the two sorted inputs in step. No hash table
then holds a whole side. The partitioned table of [Lakehouse and beyond](#lakehouse-and-beyond) is one such
layout.

The figure runs a probe-side scan with a join-derived range. The book’s engine does not execute a join.

```practice
question: An inner join’s build keys are ten and twenty, and the probe scan keeps the whole interval between them. Is a probe row with key fifteen necessarily a join match?
answer: No. The range is a conservative filter and can retain gaps between actual keys. The join must still test membership in the build side. Dynamic pruning reduces scan work, not the need to perform the join.
```

```lesson
reference
```

### Wide tables and many small files

This comparison brings together the [scan and filter example](separate-scan-and-filter.html)
and the lessons on metadata-only answers, grouping and sorted limits. The cost table below
uses the teaching engine on `writing-baseline.parquet`, an orders file sorted by `order_id`.
The discussion of wide tables and many files describes how the trade-offs can change at scale.

A table with hundreds of columns makes projection matter more, not less: a query still reads only
the columns it names. The footer still describes every column chunk of every row group, so a
wide file can have a large footer. Opening an uncached file requires fetching and decoding that
metadata before planning its data reads ([Metadata and statistics](#metadata-and-statistics)).
`SELECT *` on a wide table also reads every column.

A query over many small files pays opening costs for each file it needs. Each uncached file
requires metadata work before its data can be read, with fewer rows over which to spread that
cost ([Why Parquet exists](#why-parquet-exists), [Changing a table](#changing-a-table)). Engines
can overlap requests, and table statistics can rule out files before opening them
([Lakehouse and beyond](#lakehouse-and-beyond)). Compacting small files into larger ones reduces
this per-file overhead; it does not eliminate metadata or reading costs
([Changing a table](#changing-a-table)).



### What each query read

The teaching engine ran each query below on `writing-baseline.parquet`. The table counts
bytes and decoded values, not execution time:

```{include} _generated/engine-costs.md
```

The core lessons explain [metadata-only answers](answer-from-metadata.html),
[grouping](group-dictionary-values.html) and [sorted limits](limit-a-sorted-query.html).
They distinguish the work shown here from optimisations that the teaching engine does not implement.

## What this cannot tell you

These notes qualify the teaching engine's [scan and filter walkthrough](separate-scan-and-filter.html)
and [query-cost comparison](what-a-query-engine-does-comparison.html) on `writing-baseline.parquet`.
The separate [join-filter comparison](use-join-derived-filters.html) models only a probe-side scan.

**How engines work inside.** The book's engine handles one row at a time, keeps every decoded row
in memory, and groups by searching a list. Production engines can process batches of values
with vectorised code, decode only the rows a filter keeps, and write temporary data to disk when
memory runs out. They can run stages in parallel and choose plans by estimated cost. Each of those is a subject
of its own.

**Time.** The [query-cost table](what-a-query-engine-does-comparison.html) counts bytes and values, not time. The engine reads from memory. Against an
object store, the number of requests can matter more than the bytes they fetch, as
[How readers read](#how-readers-read) measured.

**Pages and Bloom filters in the engine.** The book's engine skips row groups on their statistics
alone. The page index and Bloom filters of [Skipping data](#skipping-data) skip more, and
[How readers read](#how-readers-read)'s scan uses both. Whether a given engine uses them, and whether by
default, differs between engines and versions.

**A join.** The [join-filter table](use-join-derived-filters.html) runs only the probe side's scan, with the build side's key range as
its condition. It builds no hash table and measures no join.

**Other files.** The query-cost table uses one small orders file sorted by `order_id`; the
join-filter table compares sorted and shuffled probe inputs. The proportions depend on the file. On a table with hundreds of columns and many row
groups, projection and skipping save far more.

## Key takeaways

:::{div}
:class: takeaways

- **The file holds data and metadata; the engine does the rest.** It plans, pushes the
  projection and the filter down, schedules the reads, decodes, and runs every stage after the
  scan.
- **The scan determines which file bytes are read.** The required columns and retained row
  groups decide the bytes read and values decoded in this model; later stages also cost work.
- **Projection is only as good as the query.** `SELECT *` reads every column, because nothing
  tells the engine which ones you need.
- **A filter skips only what the layout lets it.** A condition on the sort key skips row groups;
  one on a value spread through every row group skips none.
- **Some answers need no data pages.** `count(*)` comes from the footer's row counts, and `min`
  and `max` from exact statistics when no condition removes rows.
- **`ORDER BY` with `LIMIT` needs a reason to stop reading.** Known ordering or safe bounds can
  rule out better candidates. Small working memory alone cannot.
- **A join's build side becomes a filter on its probe side.** Its keys' range skips the probe
  side's row groups when the probe side is sorted on the key and the keys are close together.
:::

```checkpoint
question: A row group's bounds overlap a filter. Does that mean every row in the group passes?
answer: No. Overlap means the scan cannot rule the group out. The filter must check decoded rows, unless metadata proves the condition true for every row. Pruning selects candidate regions; filtering decides which individual rows match.
```

## Problems

These questions apply the [query-cost comparison](what-a-query-engine-does-comparison.html)
to new cases. Unless a question gives another table, use its `writing-baseline.parquet` fixture:
orders sorted by `order_id`, with dictionary-encoded countries. The [metadata-answer lesson](answer-from-metadata.html)
and [join-filter example](use-join-derived-filters.html) provide preparation. These are reasoning
questions; no code or automated grading is required.

**12.1 From the footer alone.** No test. Say whether an engine could answer each of these queries
on the orders file with no data page read, and why: `SELECT count(*) FROM orders`;
`SELECT count(*) FROM orders WHERE order_id < 300`; `SELECT max(amount_cents) FROM orders`; and
`SELECT count(*) FROM orders WHERE country = 'FR'`. A good answer says that the first needs only
the row counts. The second can count the row groups whose whole range passes from their row
counts, and skip those whose range fails, but must read `order_id` in the row group that
straddles the limit. The third needs every row group to have an exact maximum for the column.
The fourth needs the data, because statistics give ranges, not counts of a value, except in a
row group whose range starts and ends at `FR`.

**12.2 A sorted file and a limit.** No test. `ORDER BY order_id LIMIT 5` read every row group of
a file sorted by `order_id`. Say what an engine must know to read only the first row group, and
where in the footer it could learn it. Then say what changes for `ORDER BY order_id DESC`, and
for `ORDER BY amount_cents`. A good answer says the engine must know the row groups hold ordered
ranges of `order_id` that do not overlap: from `sorting_columns`, if the writer recorded it, or
by comparing each row group's statistics. It then reads the row group with the smallest minimum,
and the next only if that one held fewer than five rows. Descending reads from the last row group
instead. `amount_cents` is not sorted, so every row group may hold an answer, although an engine
can skip a row group whose minimum is above the fifth smallest amount found so far.

**12.3 Which side to build.** No test. A table of a billion orders, sorted by `order_id` in row
groups of about a million rows, is joined on `order_id` with a table of a few thousand refunds,
all of orders placed last week. Say which side to build, what the probe side's scan reads, and
what changes if the refunds span the whole history, or if the orders are sorted by
`customer_id` instead. Check the shape of your answer against the
[join-filter comparison](use-join-derived-filters.html). A good answer
builds the refunds, the smaller side, so the hash table is small. It says their keys span a
narrow range at the end of the orders, so the probe side's scan skips every row group but the
last few. It says refunds spanning the whole history give a range that rules nothing out, like
the German file, so the scan reads every row group unless the engine pushes the keys themselves
and the orders have Bloom filters. And it says orders sorted by `customer_id` give every row
group a wide range of `order_id`, like the shuffled file, so no range skips anything.

**12.4 Your own queries.** No test: the queries are yours. Take three queries you often run
against Parquet, and ask your engine for each one's plan (`EXPLAIN` in most SQL engines). Find
what it pushed down into the scan: the columns, the conditions, and whatever it reports about
row groups or files skipped. You can also run a query on one of your files with the book's
engine, `cargo run -p pqlab -- query FILE "SQL"`, and read its Scan stage. A good answer lists,
for each query, the columns read against the columns named, and the conditions pushed down
against those applied after the scan, with a reason for each condition that was not pushed
down. If an expected condition was not pushed down, inspect that engine's supported conditions
and the expression's form. A comparison against a stored column may help; check the plan again.

## Where to go next

- What a scan can read before the data is in the format itself: the statistics in
  [`parquet.thrift`](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift),
  the [page index](https://github.com/apache/parquet-format/blob/master/PageIndex.md) and
  [Bloom filters](https://github.com/apache/parquet-format/blob/master/BloomFilter.md).
- How engines work inside is a subject of its own. Goetz Graefe's survey *Query Evaluation
  Techniques for Large Databases* (1993) covers scans, sorting, hashing and joins. His *Volcano,
  an Extensible and Parallel Query Evaluation System* describes the row-at-a-time model the
  book's engine uses. Boncz, Zukowski and Nes, *MonetDB/X100: Hyper-Pipelining Query Execution*,
  describes the batch-at-a-time alternative.
- [Modular encryption](#modular-encryption) asks what a reader can still see when parts of a file are
  encrypted.
