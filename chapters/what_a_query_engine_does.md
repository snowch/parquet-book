---
title: What a query engine does
---

(what-a-query-engine-does)=
# What a query engine does

## The question

What does a query engine do with a Parquet file, and what does each kind of query cost?

The reader can now find a footer, trust its statistics, skip row groups and pages, decode every
encoding and fetch bytes carefully. [ch11](#writing-parquet-well) showed how a writer's choices
decide what a reader can skip. At work nobody calls those pieces one at a time. You write SQL or
a dataframe expression, and a query engine decides which pieces to use. How an engine works
inside would take a book of its own. This chapter is about its role: what it asks of a Parquet
file, and what the common operations cost against one. It builds nothing new.

## The experiment

### Who does what

A Parquet file is data and metadata, and nothing more. It holds column chunks, and a footer that
says where each one is and what range its values span ([ch02](#anatomy-of-a-parquet-file),
[ch08](#metadata-and-statistics)). It runs nothing, and it cannot tell which of its bytes a query
needs.

The engine does everything else:

- **It plans the query.** It parses the text, checks the names against the file's schema, and
  works out which columns and which conditions each part of the query needs.
- **It pushes the projection and the filter down into the scan.** The scan is the part of the
  plan that reads the file. Told which columns to read and which conditions must hold, it can
  rule out parts of the file from the footer before it fetches them.
- **It schedules the reads.** It decides which byte ranges to request, merges neighbouring ones,
  and runs requests side by side ([ch10](#how-readers-read)).
- **It decodes.** It decompresses pages and turns encoded values back into values
  ([ch05](#encodings), [ch07](#compression)).
- **It runs everything after the scan.** Filtering rows, grouping, sorting, joining and limiting
  work on values already decoded. The file takes no part in them.

The file's part ends at the scan. So a query's cost against Parquet is mostly the cost of its
scan: the bytes it fetches and the values it decodes. Every later stage sees only what the scan
passed on.

### What a scan can skip

Earlier chapters showed four ways for a scan to avoid reading, each decided before a page is
fetched:

- **Columns the query does not name.** Each column chunk is a separate range of the file
  ([ch01](#why-parquet-exists)).
- **Row groups whose statistics rule a condition out.** Each column chunk's minimum and maximum
  are in the footer ([ch08](#metadata-and-statistics), [ch09](#skipping-data)).
- **Pages the page index rules out**, inside the row groups that remain
  ([ch09](#skipping-data)).
- **Row groups whose Bloom filter says a value is absent**, for an equality on a column whose
  ranges rule nothing out ([ch09](#skipping-data)).

[ch10](#how-readers-read) turned what remained into requests. None of these changes the answer.
They decide only how much of the file the answer costs.

### The book's engine

**Run a query.** The book's reader includes a small engine. It runs a query as a few stages and
reports what each stage did. It is simple where production engines are clever (see *What this
cannot tell you*), but it does the same jobs in the same order. Run it on the orders from
[ch11](#writing-parquet-well), which are sorted by `order_id`:

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

Change the query to `SELECT count(*) FROM orders`, and the scan reads no column at all. Then try
the queries in the table below, and watch the Scan line.

### What each query read

The engine ran one query of each kind this section goes through, on the same file:

```{include} _generated/engine-costs.md
```

The rest of this section takes the table a row or two at a time. For each kind of query it says
what the scan read, and what an engine can do that the book's engine does not.

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
([ch11](#writing-parquet-well)).

A pushed-down filter skips only what the metadata rules out; the engine still checks every row
it decodes. The statistics decide which row groups to read, the page index narrows those to
pages, and a Bloom filter can rule out an equality on a column such as `customer_id`, whose values
are spread through every row group ([ch09](#skipping-data)). The book's engine stops at row
groups. A scan that also uses the page index reads fewer pages of the row groups it keeps, as
[ch09](#skipping-data) measured.

Only a condition that compares a stored column with a constant can be judged against a minimum
and a maximum. A function of the column, such as `lower(country) = 'fr'`, needs the function's
effect on the range, which an engine rarely knows. A comparison of two columns needs both
columns' values, row by row. Engines that cannot push a condition down still apply it, after
decoding every row. Where you can, write conditions on the stored columns themselves.

### Answers from the footer

`count(*)` read no bytes after the footer. The footer records each row group's row count, and
the engine added them up. With a condition, `count(*)` needs the condition's column, except in
row groups whose statistics show that every row passes, or that none does.

`min(order_id)` and `max(order_id)` are in the footer too, as each row group's statistics, and
the file's minimum is the smallest of them. The book's engine does not use them: it read the
column and decoded every value. An engine that answers from the footer must first check three
things:

- **Every row group has statistics for the column.** They are optional.
- **They are exact.** A writer may shorten a long string's bounds, and says so in the exact flags
  of [ch08](#metadata-and-statistics).
- **No condition removes rows.** The statistics describe every row, not the rows a filter keeps.

`count(column)` works the same way: the row count, less the null count from the statistics.

### Grouping

`GROUP BY country` read one column, and a cheap one, because it is dictionary-encoded
([ch05](#encodings)). It holds a few distinct values, so each chunk is a small dictionary page and
a run of short indices. The same rows of `order_id`, whose values are all distinct, cost several
times as many bytes.

An engine can go further. It can group on the dictionary's indices instead of the strings, and
look up each string once per group. pyarrow's `read_dictionary` option keeps a column in that
form, as indices into a dictionary, rather than as strings. `DISTINCT` is a `GROUP BY` without
aggregates, and the same holds for it. There are two catches. A dictionary belongs to one column chunk, so the
same index means different strings in different row groups, and an engine must merge the
dictionaries. And a writer that fell back to plain encoding, because a dictionary grew too
large, leaves some pages with no indices at all ([ch05](#encodings)). The book's engine decodes
every string and groups by comparing them.

### Sorting with a limit

`ORDER BY amount_cents DESC LIMIT 5` returned five rows, and read both of its columns for every
row. The largest amounts could be in any row group, and no stage can know it has the top five
until it has seen every row. An engine keeps only the best rows found so far, so its memory stays
small, but its scan reads everything. It can still skip a row group whose maximum amount is below
the fifth largest found so far, which the statistics allow and some engines do. The book's engine
does not.

`ORDER BY order_id LIMIT 5` cost exactly the same, although the file is sorted by `order_id` and
the answer lies in its first row group. The book's engine does not know the order. An engine can
learn it from the footer: a writer may record it in each row group's `sorting_columns`
([ch08](#metadata-and-statistics)), and the statistics show whether row groups' ranges overlap.
An engine that knows the order can read the first row group and stop. So sorting a file on the
key that queries order by, or filter on, makes both kinds of query cheap.

### Joins

A join matches the rows of two inputs on a key. The usual plan for a join on equal keys is a
*hash join*. The engine reads one input, the *build side*, into a hash table on the key. Then it
reads the other, the *probe side*, and looks up each row's key in the table. The build side is
the smaller input, because its hash table must fit in memory, while the probe side streams past
it and is never held whole.

The build side is read first, so its keys are known before the probe side's scan starts. An
engine can turn them into a filter on that scan: the keys' smallest and largest value as a range
condition, a Bloom filter of the keys, or the list of keys if it is short. The probe side's scan
then skips row groups as any filtered scan does. Trino calls this *dynamic filtering*; Spark has
*runtime filters* and *dynamic partition pruning*. The book's engine has no joins. Its scan can
run the range condition a join would push down, though, with three small files from later
chapters' fixtures as build sides:

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

Partitions and sort orders help a join in a second way. When both inputs are partitioned on the
key, or sorted by it, an engine can join them piece by piece. It joins each partition of one side
with the matching partition of the other, or merges the two sorted inputs in step. No hash table
then holds a whole side. The partitioned table of [ch14](#lakehouse-and-beyond) is one such
layout.

### Wide tables and many small files

A table with hundreds of columns makes projection matter more, not less: a query still reads only
the columns it names. The cost moves to the footer. It describes every column chunk of every row
group, so a wide table's footer is large, and every query fetches and decodes it before anything
else ([ch08](#metadata-and-statistics)). `SELECT *` on a wide table pays for every column.

A table split into many small files makes an engine open each of them. Each file costs a footer
and a few requests before any data, and each holds too few rows to repay them
([ch01](#why-parquet-exists), [ch15](#changing-a-table)). An engine opens files in parallel, but
the cost stays a cost per file. Statistics in a table's log can rule out whole files before
they are opened ([ch14](#lakehouse-and-beyond)). Compacting small files into larger ones
removes the cost ([ch15](#changing-a-table)).

### The same query in a library

At work a library or an engine runs the query. pyarrow's dataset module pushes the condition
down into its scan, keeps the row groups whose statistics allow it, reads only the columns the
query needs, then filters and groups. The `parquet` crate has no query language. You give it a
predicate on each row group's statistics, as in [ch09](#skipping-data), and a projection of the
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

## What this cannot tell you

**How engines work inside.** The book's engine handles one row at a time, keeps every decoded row
in memory, and groups by searching a list. Production engines process columns in batches with
vectorised code, decode only the rows a filter keeps, spill to disk when memory runs out, run
stages in parallel, and choose between plans by their estimated cost. Each of those is a subject
of its own.

**Time.** The table counts bytes and values, not time. The engine reads from memory. Against an
object store, the number of requests can matter more than the bytes they fetch, as
[ch10](#how-readers-read) measured.

**Pages and Bloom filters in the engine.** The book's engine skips row groups on their statistics
alone. The page index and Bloom filters of [ch09](#skipping-data) skip more, and
[ch10](#how-readers-read)'s scan uses both. Whether a given engine uses them, and whether by
default, differs between engines and versions.

**A join.** The join table runs only the probe side's scan, with the build side's key range as
its condition. It builds no hash table and measures no join.

**Other files.** Every number here comes from one small file of a few row groups, sorted by one
key. The proportions depend on the file. On a table with hundreds of columns and many row
groups, projection and skipping save far more.

## Key takeaways

:::{div}
:class: takeaways

- **The file holds data and metadata; the engine does the rest.** It plans, pushes the
  projection and the filter down, schedules the reads, decodes, and runs every stage after the
  scan.
- **A query's cost against Parquet is mostly its scan.** The columns it names and the row groups
  its conditions rule out decide the bytes read and the values decoded.
- **Projection is only as good as the query.** `SELECT *` reads every column, because nothing
  tells the engine which ones you need.
- **A filter skips only what the layout lets it.** A condition on the sort key skips row groups;
  one on a value spread through every row group skips none.
- **Some answers need no data pages.** `count(*)` comes from the footer's row counts, and `min`
  and `max` from exact statistics when no condition removes rows.
- **`ORDER BY` with `LIMIT` reads every row, unless the engine knows the file is sorted on the
  key.** Only then can it stop after the first row group.
- **A join's build side becomes a filter on its probe side.** Its keys' range skips the probe
  side's row groups when the probe side is sorted on the key and the keys are close together.
:::

## Problems

Four, all for reasoning. No test grades them: the chapter builds nothing.

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
`customer_id` instead. Check the shape of your answer against the join table. A good answer
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
down. A condition you expected to be pushed down and was not means the engine did not see a
column compared with a constant. Rewrite it, and look at the plan again.

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
- [ch13](#modular-encryption) asks what a reader can still see when parts of a file are
  encrypted.
