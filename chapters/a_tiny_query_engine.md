---
title: A tiny query engine
---

(a-tiny-query-engine)=
# A tiny query engine

## The question

What does it take to answer SQL from Parquet bytes?

The reader can now find a footer, trust its statistics, skip row groups and pages, decode any
encoding, decompress pages, and fetch bytes carefully. A query engine is what turns a question
into those steps. This chapter answers one query by hand, then builds the smallest engine worth
the name: a parser for a little SQL, and a pipeline of stages that runs it, every stage a loop
over rows that says what it did.

## The experiment

### One query, by hand

The query counts the first orders by country:

```sql
SELECT country, count(*) FROM orders WHERE order_id < 300 GROUP BY country
```

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name.

**A query by hand.** `writing-baseline.parquet` holds the orders of [ch11](#writing-parquet-well),
sorted by `order_id`. Answer the query with pieces the reader already has: the footer, each row
group's statistics from [ch08](#metadata-and-statistics), and the column reader from
[ch04](#nested-data). Skip a row group whose smallest order is too large, read the two columns of
the others, keep the rows that pass, and count them by country:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/a_tiny_query_engine/a_query_by_hand.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/a_query_by_hand.rs
:language: rust
```
:::
::::

The last two row groups were skipped without reading a page: their smallest `order_id` is already
too large. The first row group passed every row it read, the second fewer than half. The counts
are the answer. The step did four things, in order: it read the columns the query needs, skipping
what the statistics rule out; it kept the rows the condition accepts; it folded them into a count
per country; and it sorted the countries.

Change `limit` to `450`: the third row group is read too, and only some of its rows pass. Then try
`1`: every row group is skipped, and the answer is empty without a page read.

### The same query in SQL

**Run a query.** The book's reader has an engine that does those four things for any query in a
small language. It parses the text, runs the query as a pipeline of stages, and records what each
stage did. Run the same query through it:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/a_tiny_query_engine/run_a_query.py
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

The answer is the one you counted by hand, and the stages are the loops you wrote. The scan read
two row groups of the two columns and skipped the others on their statistics. The filter kept the
rows below the limit, the aggregate counted each country, and the sort ordered them.

Add `AND status = 'refunded'` after the condition. The scan still skips on `order_id`, but no
statistics rule out a status, so the filter does the rest. Add `LIMIT 3` at the end, and a Limit
stage cuts the answer. Misspell a keyword, or leave out a value: the engine reports where it
stopped rather than guess.

The language is small:

```text
SELECT *  |  item, item, ...          item: column, count(*), count(c), sum(c), min(c),
FROM name                                   max(c) or avg(c)
[WHERE condition AND condition ...]   condition: column op value, column IS [NOT] NULL
[GROUP BY column, ...]
[ORDER BY column [ASC|DESC], ...]
[LIMIT n]
```

### A query is a pipeline

The engine runs a query as a fixed sequence of stages, each consuming the rows of the one before:

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

The first step answered one query with the reader's footer, statistics and column reader. The
engine writes the same loops once, for any query: a parser turns the text into a plan, the scan
skips and decodes, and the stages after it fold the rows.

### Parsing

The parser is a tokeniser and a recursive-descent parser, one function per piece of the grammar.
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
out, and records which. This is the first step's test on the minimum, for every condition and
every column order:

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

Each aggregate keeps a running state per group. `count(*)` counts every row, and the others skip
nulls, as SQL requires:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/engine.py
:language: python
:start-at: def add(self, v: object, star: bool = False)
:end-before: elif self.kind == "sum":
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/engine.rs
:language: rust
:start-at: /// Fold in one value.
:end-before: Acc::Sum(s) => {
```
:::
::::

The other aggregates fold a value the same way. A sum adds it. A minimum or a maximum keeps it if
it comes first or last in the column's order. An average keeps a total and a count, and is null
for a group with no values.

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

### Ask a library

At work a library runs the query. pyarrow's dataset module takes the condition, keeps the row
groups whose statistics allow it, reads only the columns the query needs, filters and groups. The
`parquet` crate has no query language: you give it a predicate on each row group's statistics, as
in [ch09](#skipping-data), and a projection of the columns to read, and filter and count the rows
yourself:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/a_tiny_query_engine/query_with_a_library.py
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

Both keep the two row groups the engine's scan read, and both count the same orders per country.
pyarrow's `subset` says which row groups a condition keeps from the statistics alone, before any
page is read. The crate's predicate is the first step's test on the minimum, written for the
crate, and its row iterator decodes only the projected columns. Change the limit to `450` in
either, and both keep a third row group.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin query_with_a_library
```

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

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: a_tiny_query_engine
```

**12.1 A hash aggregate.** Sum values by group. The test compares your sums with pyarrow's for
the baseline file's statuses, and with many generated cases.

**12.2 The top `n`.** Return the `n` largest amounts, ties broken by order number. The test
compares your answer with pyarrow's sort, and with many generated cases.

**12.3 Your own queries.** No test: the queries are yours. Run three queries you use against one
of your files with `PYTHONPATH=python python3 -m parquet_lab query FILE "SQL"` or
`cargo run -p pqlab -- query FILE "SQL"`, and the same queries in an engine you
trust. Record whether the answers agree and how many row groups the scan read. Then pick the one
that read the most, and say how page-level skipping from [ch09](#skipping-data) would change its
scan. A good answer estimates the rows it would no longer decode, using the page index.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_12_1` in Python, or `problem_12_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_a_tiny_query_engine.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test a_tiny_query_engine -- --ignored
```
:::
::::

## Where to go next

- The pipeline here is the iterator model Goetz Graefe described in *Volcano, an Extensible and
  Parallel Query Evaluation System*; the batch-at-a-time alternative is Boncz, Zukowski and Nes,
  *MonetDB/X100: Hyper-Pipelining Query Execution*.
- [DuckDB](https://duckdb.org/) and [Apache DataFusion](https://datafusion.apache.org/) are
  query engines over Parquet whose source rewards reading next to this chapter.
- [ch13](#modular-encryption) asks what a reader can still do when parts of a file are encrypted.
