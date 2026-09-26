---
title: A tiny query engine
---

(a-tiny-query-engine)=
# A tiny query engine

## The question

What does it take to answer SQL from Parquet bytes?

The reader can now find a footer, trust its statistics, skip row groups and pages, decode any
encoding, decompress pages, and fetch bytes carefully. A query engine is what turns a question
into those steps. This chapter builds the smallest one worth the name: a parser for a little SQL,
and a pipeline of stages that runs it, every stage a loop over rows that the laboratory shows.

## The experiment

### SQL, stage by stage

Type a query, or pick an example. The engine answers it from the file's bytes, and shows each
stage with the rows it took in, the rows it produced, and the first few of them.

```lab
experiment: engine
fixture: writing-baseline.parquet
fixtures: writing-baseline.parquet, statistics.parquet
```

The language is small:

```text
SELECT *  |  item, item, ...          item: column, count(*), count(c), sum(c), min(c),
FROM name                                   max(c) or avg(c)
[WHERE condition AND condition ...]   condition: column op value, column IS [NOT] NULL
[GROUP BY column, ...]
[ORDER BY column [ASC|DESC], ...]
[LIMIT n]
```

Try these:

1. **Run the first example.** A scan, an aggregate and a sort: counting orders by country reads
   every row group, because nothing rules any out.
2. **Add `WHERE order_id < 300`.** The scan now skips the row groups whose smallest order is too
   large, and says so.
3. **Switch to `statistics.parquet` and run the second example.** Customer numbers above `2^31`
   are compared as the unsigned integers they are, as [ch08](#metadata-and-statistics) required.
4. **Break the query.** A misspelled keyword or a missing value is reported, not guessed at.

### A query is a pipeline

The engine runs a query as a fixed sequence of stages:

```{include} _generated/engine-stages.md
```

Each stage consumes the rows of the one before:

- **Scan** reads the columns the query mentions, and nothing else: [ch01](#why-parquet-exists)'s
  projection. Before reading a row group, it asks each condition whether the footer's statistics
  rule it out, using [ch09](#skipping-data)'s rules. It decodes the rest.
- **Filter** keeps the rows every condition accepts. It compares values in their column's own
  order, so the same code that judged the statistics judges the rows.
- **Aggregate** groups rows by the `GROUP BY` columns and folds each group's values into its
  counts, sums, minimums, maximums and averages. With aggregates and no `GROUP BY`, all rows are
  one group.
- **Project** keeps the requested columns, when there is nothing to aggregate.
- **Sort** and **Limit** order and cut the result.

The scan does most of the work. Everything after it touches only rows already decoded, and the
fewer rows the scan passes on, the less work remains. That is why every earlier chapter's
skipping matters to a query engine: it shrinks the first stage.

### Answers checked against pyarrow

A query engine that returns plausible numbers is easy to write. One that returns correct numbers
needs checking. When the fixtures were written, pyarrow answered a set of queries with its own
compute functions, and stored the answers in `fixtures/queries.json`. The engine answers the
same queries from the bytes:

```{include} _generated/engine-answers.md
```

The queries cover grouping, every aggregate, conditions that skip row groups and conditions
that cannot, strings compared byte by byte, unsigned and negative integers, and nulls.

## Building it

### Parsing

The parser is a tokenizer and a recursive-descent parser, one function per piece of the grammar.
A condition, for example:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/engine.py
:language: python
:start-at: def condition(self) -> Condition
:end-before: def list(self, one)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/engine.rs
:language: rust
:start-at: fn condition(&mut self)
:end-before: fn list<T>(
```
:::
::::

### Scanning with the statistics

The scan skips a row group if any condition's comparison against the footer's bounds rules it
out, and records which:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/engine.py
:language: python
:start-at: # Skip the row group if any condition's comparison
:end-before: read += 1
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/engine.rs
:language: rust
:start-at: // Skip the row group if any condition's comparison
:end-before: read += 1;
```
:::
::::

### Aggregating

Each aggregate keeps a running state per group, and nulls are skipped, as SQL requires:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/engine.py
:language: python
:start-at: def add(self, v: object, star: bool = False)
:end-before: def result(self)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/engine.rs
:language: rust
:start-at: /// Fold in one value.
:end-before: fn result(&self) -> Value {
```
:::
::::

### Checking it

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests -k engine
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures engine
```
:::
::::

## What this cannot tell you

**How real engines are fast.** This engine handles one row at a time, keeps every decoded row in
memory, and groups by searching a list. Production engines process columns in batches with
vectorised code, decode only the rows a filter keeps, spill to disk when memory runs out, and
run stages in parallel.

**Most of SQL.** There are no joins, no expressions beyond a column compared with a value, no
`OR`, no subqueries, and no types beyond integers, floats and strings. Decimals, dates and
timestamps are compared by the reader's orders in the filter, but sorted and grouped as the text
they display as.

**Page-level skipping in queries.** The engine skips row groups only. [ch09](#skipping-data) and
[ch10](#how-readers-read) showed how to skip pages and fetch less; joining them to this pipeline
is the natural next step, and problem 12.3 asks what it would change.

## Key takeaways

:::{div}
:class: takeaways

- **A query engine is a parser and a pipeline.** Scan, filter, aggregate or project, sort and
  limit, each consuming the rows of the one before.
- **The scan is where Parquet pays.** Projection and skipping decide how many rows every later
  stage sees.
- **Filters and statistics must use the same order.** Otherwise the statistics can rule out rows
  the filter would keep.
- **Aggregates skip nulls; `count(*)` counts rows.**
- **Check answers against an independent implementation.** A plausible number is not a correct
  one.
:::

## Problems

Three, in `exercises/python/a_tiny_query_engine.py`, or in Rust in
`exercises/src/a_tiny_query_engine.rs`. The first two have tests. The third has none.

**12.1 A hash aggregate.** Sum values by group. The test compares your sums with pyarrow's for
the baseline file's statuses, and with many generated cases.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_a_tiny_query_engine.py --problems -k problem_12_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test a_tiny_query_engine problem_12_1 -- --ignored
```
:::
::::

**12.2 The top `n`.** Return the `n` largest amounts, ties broken by order number. The test
compares your answer with pyarrow's sort, and with many generated cases.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_a_tiny_query_engine.py --problems -k problem_12_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test a_tiny_query_engine problem_12_2 -- --ignored
```
:::
::::

**12.3 Your own queries.** No test: the queries are yours. Run three queries you use against one
of your files with `PYTHONPATH=python python3 -m parquet_lab query FILE "SQL"` or
`cargo run -p pqlab -- query FILE "SQL"`, and the same queries in an engine you
trust. Record whether the answers agree and how many row groups the scan read. Then pick the one
that read the most, and say how page-level skipping from [ch09](#skipping-data) would change its
scan. A good answer estimates the rows it would no longer decode, using the page index.

## Where to go next

- The pipeline here is the iterator model Goetz Graefe described in *Volcano, an Extensible and
  Parallel Query Evaluation System*; the batch-at-a-time alternative is Boncz, Zukowski and Nes,
  *MonetDB/X100: Hyper-Pipelining Query Execution*.
- [DuckDB](https://duckdb.org/) and [Apache DataFusion](https://datafusion.apache.org/) are
  query engines over Parquet whose source rewards reading next to this chapter.
- [ch13](#modular-encryption) asks what a reader can still do when parts of a file are encrypted.
