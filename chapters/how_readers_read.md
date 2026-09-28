---
title: How readers read
---

(how-readers-read)=
# How readers read

## The question

Why does a reader issue exactly the requests it does?

[ch09](#skipping-data) decided which bytes a query needs. Knowing the bytes is not the same as
fetching them well. Each request to an object store costs a round trip before the first byte
arrives, and that cost does not shrink with the request. A reader that needs many small ranges
can make one request for each, one large request that covers them all, or something between, and
it can make several at once. This chapter builds the reader's read path and measures those
choices.

## The experiment

### One query, request by request

The query is [ch09](#skipping-data)'s: `SELECT * WHERE order_id = 431` on
`pruning-sorted.parquet`. There the reader planned it from a copy of the file on disk. Here its
`scan` runs the plan against the simulated object store from
[ch02](#anatomy-of-a-parquet-file), which logs every request, the connection that carried it, and
when it started and ended. A `Strategy` says how to make the requests: how to find the footer and
how much of the tail to read first, how close two ranges must be to merge into one request, and
how many connections to use.

The step is a few lines of code. In Python, run it in the page, change it with **Edit**, and run
it again. In Rust, open it in a Codespace, or run it at a desk with
`cargo run -p walkthroughs --bin read_with_a_strategy`. It continues ch02's
`open_with_the_reader`, which stopped once the footer was read:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/how_readers_read/read_with_a_strategy.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/read_with_a_strategy.rs
:language: rust
```
:::
::::

The first three requests are ch02's: the size, the trailer, the footer. Next come the indexes the
plan needs, one request each: `order_id`'s ColumnIndex for row group 2, the one row group the
statistics keep, and an OffsetIndex for each column. Last come the pages, one request each, with
`country`'s dictionary page apart from its data page. Every request starts when the one before
it ends. The bytes are a small share of the file, and they move in almost no time. The time is
the latency, paid once per request.

Change the strategy one line at a time, and run the step after each change:

- **Read more of the tail.** Find the footer with `SuffixRange()` and `prefetch=8192`
  (`SizeSource::SuffixRange` and `prefetch: 8192` in Rust). The first request brings the trailer,
  the footer and the indexes together, because the indexes sit immediately before the footer.
  Every index request disappears.
- **Merge ranges.** Add `coalesce_gap=4096` (`Some(4096)`). The pages of the four columns become
  one request, which also reads the bytes between them.
- **Use more connections.** Put the gap back to `None` and set `connections=4`. The pages go out
  side by side, each on a connection of its own, but none starts before the footer has arrived.
- **Read everything.** Set `prefetch=65536`, more than the file holds. The first request reads
  all of it, and there is nothing left to ask for.

### Phases

A reader cannot ask for everything at once, because it does not know what to ask for. The
requests fall into phases, each needing the answers to the one before:

1. **The footer.** The trailer says where the footer starts, so finding it takes one or two
   requests after the size is known: [ch02](#anatomy-of-a-parquet-file)'s strategies.
2. **The indexes.** Which Bloom filters and page indexes to fetch depends on the footer: where
   they are, and which row groups the statistics have already ruled out.
3. **The data.** Which pages to fetch depends on the indexes.

Within a phase the requests are independent, and a reader with several connections sends them
together. Between phases it must wait. Latency is paid at least once per phase, however many
connections there are.

### The phases on a timeline

The panel runs the same query with the Rust reader and draws each request in the lane of the
connection that carried it. Pick a strategy from the list; the list is the rows of the table
under *What each choice costs*, below.

```lab
experiment: scan
fixture: pruning-sorted.parquet
column: 0
op: =
value: 431
```

Try these:

% number-ok: the panel's strategies, named as its list names them; nothing here is measured.
1. **… and pages by the page index.** The step as you first ran it. Grey finds the footer, orange
   fetches the indexes, blue fetches the pages, and each bar waits for the one before.
2. **HEAD, trailer, footer; every column chunk**, then **… skipping row groups by statistics.**
   Without the page index there is no orange phase. The statistics drop three row groups' chunks,
   and the blue phase shrinks with them.
3. **… with an 8 KiB suffix read for the footer.** The orange phase is gone: the tail read
   brought the indexes with the footer.
4. **… merging ranges within 4 KiB.** The blue phase is one bar.
5. **… on four connections, without merging.** The blue bars stack in four lanes, and the phase
   takes the time of the longest lane. The grey bar still comes first, alone.
6. **One suffix read of 64 KiB: the whole file.** One bar, and nothing after it.

### What each choice costs

The same query, with each change made in turn:

```{include} _generated/scan-strategies.md
```

The first rows follow [ch09](#skipping-data): skipping row groups by statistics cuts both bytes
and requests. Then the page index cuts bytes further but adds requests, one for each index and
each page, and the query gets slower. Bytes were not the problem. At the latency the table's
note gives, the number of requests decides the time, and every row below that attacks it: a
larger tail brings the indexes with the footer, merging turns neighbouring pages into one
request, and connections run requests side by side.

For a file this small, the fastest strategy is the crudest: read all of it. That is a real
answer: a reader that knows a file is small can fetch all of it before parsing anything.

### Reading everything

A query with no condition must read every column chunk. How long that takes depends on how the
requests are made:

```{include} _generated/scan-full.md
```

One request per column chunk, one at a time, pays the latency for every request in turn: the
footer's three, then one per column chunk. More connections overlap the column chunks'
requests, but the footer's three stay in sequence, since each depends on the last. Merging chunks
that touch needs no extra bytes at all: a row group's chunks are written end to end, so the whole
data region is one range.

### When bytes matter

Latency favours few large requests; bandwidth favours fetching only what is needed. Which wins
depends on the network:

```{include} _generated/scan-networks.md
```

On a fast network with high latency, reading the whole file wins even though it moves many times
the bytes. On a slow link with low latency, the careful plan wins, because moving the extra bytes
takes longer than the round trips it saves. Try it in the step: pass
`NetworkModel(latency_us=1000, bandwidth_bytes_per_sec=1_000_000)` (the same fields in Rust's
`NetworkModel { .. }`) and compare `prefetch=8192` with `prefetch=65536`. Real files are far
larger than this one, which moves the balance toward the careful plan: nobody reads a gigabyte to
find one row. Readers therefore merge ranges up to a threshold, and choose the threshold from the
latency and bandwidth they expect.

### Only what was fetched

The reader keeps a copy of the file that starts empty, and fills in each response. It plans from
that copy and decodes from it. A range it forgot to request reads as zeros, which fails to decode.
The tests run every query under every strategy and compare the rows with a plain read of the
whole file, so a missed range cannot pass unnoticed.

## Building it

The step called `scan`, which reads the footer with ch02's `read_footer`, plans with ch09's
`prune.plan`, and fetches in phases. This section builds the fetching: how ranges merge, how one
phase is sent, how the store's clock prices it, and how the reader decodes only the pages it
fetched. The tabs switch every excerpt on the page between the two languages.

### Merging ranges

`coalesce` sorts the ranges and merges each into the one before it when the gap between them is
at most `gap` bytes. With no gap it merges only ranges that overlap:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/scan.py
:language: python
:start-at: def coalesce(spans: list[Span], gap: int | None)
:end-before: def fetch(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/scan.rs
:language: rust
:start-at: pub fn coalesce(
:end-before: /// Fetch every range the reader does not already have
```
:::
::::

### One phase

`fetch` sends one phase. It drops the bytes the reader already holds, so a range the tail read
brought is not fetched twice, merges what is left, and tells the store a new phase has begun:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/scan.py
:language: python
:start-at: def fetch(
:end-before: class ScanError(ValueError):
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/scan.rs
:language: rust
:start-at: fn fetch<S: ObjectStore>(
:end-before: /// Run `query` against `object`
```
:::
::::

`scan` calls it twice, once for the indexes and once for the pages, after `read_footer` has made
the first phase's requests.

### A clock for every connection

The simulated store gives each request the connection that is free first, and never starts it
before its phase:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/object_store.py
:language: python
:start-at: # The connection that is free first
:end-before: self.requests.append(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/object_store.rs
:language: rust
:start-at: // The connection that is free first
:end-before: self.requests.push(Request {
```
:::
::::

### Reading chosen pages

With the page index, the reader parses each wanted page where the OffsetIndex says it starts,
without walking the pages before it. The bytes between the pages were never fetched, and
`read_column_pages` never looks at them:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/column.py
:language: python
:start-at: def read_column_pages(
:end-before: def refuse_encrypted(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: pub fn read_column_pages(
:end-before: /// An encrypted column chunk's pages are encrypted modules
```
:::
::::

### Checking it

Over two hundred combinations of fixture, condition and strategy, the reader's rows must equal a
plain read's:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests -k every_strategy
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures every_strategy
```
:::
::::

### Ask a library

A library makes the same choices, with its own defaults. Hand pyarrow a file that prints every
read it is asked for, and ask the `parquet` crate for the footer and the page index from a tail
of the file:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/how_readers_read/reads_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/reads_with_a_library.rs
:language: rust
```
:::
::::

% number-ok: pyarrow's default footer read size, a setting rather than a measurement.
To open the file, pyarrow reads a fixed amount from the end, 64 KiB by default. This file is
smaller, so that first read is the whole file. pyarrow keeps only the footer from it, and reading
row group 2 reads the row group's column chunks again.

With `pre_buffer=False`, pyarrow makes one read per column chunk, the whole chunk each time, since
it does not use the page index. With `pre_buffer=True`, its default, it merges the chunks, which
touch, into one read. The gap it merges across is `hole_size_limit` in `pyarrow.CacheOptions`,
which a dataset scan takes through `ParquetFragmentScanOptions(cache_options=...)`. The page runs
an older build of pyarrow for WebAssembly ([why](#two-pyarrows)), which reads a chunk at a time either way; run the step at a
desk to see the merged read.

In place of `read_row_groups`, try `pq.read_table(file, filters=[("order_id", "==", 431)])`. The
statistics skip three row groups, and the fourth is read whole: pyarrow does not use the page
index to skip pages.

The crate's `ParquetMetaDataReader` makes no requests of its own. Given the last eight bytes, it
answers `NeedMoreData` with the size of tail it needs: the footer and its trailer. Given that, it
parses the footer, finds the page index before it, and asks again, for a tail reaching back to the
first index. Given that, it has everything. Those are the chapter's first two phases, with each
answer needed before the next request can be made. Start from `8192` and it needs one read. The
crate's asynchronous reader takes the same number through `with_prefetch_hint`, and hands a row
group's ranges to the `object_store` crate's `get_ranges`, which merges ranges that lie close
together. It needs the crate's `arrow` and `async` features, which this workspace does not build.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin reads_with_a_library
```

## What this cannot tell you

**How a real store behaves.** The model charges a fixed latency and a fixed bandwidth. Real
stores vary from request to request, throttle busy prefixes, and limit connections. The model
keeps the shape of the problem and none of its noise, so its numbers compare strategies; they do
not predict a real query's time.

**Caching.** A reader that opens the same file twice can keep its footer, and one that runs many
queries can keep pages. This reader starts empty every time.

**Reading many files.** A table is usually many files, and a query engine reads them in parallel.
[ch14](#lakehouse-and-beyond) turns to tables.

**Decoding time.** Every cost here is the network's. On a fast network, decompressing and decoding
can take longer than fetching, and a reader that overlaps the two gains most.

## Key takeaways

:::{div}
:class: takeaways

- **Requests come in phases.** The footer, then the indexes, then the data: each needs the one
  before, and latency is paid at least once per phase.
- **Against object storage, requests cost more than bytes.** Skipping that adds requests can
  make a query slower.
- **Merging ranges trades bytes for requests.** Ranges that touch merge for free; merging across
  a gap reads the gap.
- **Connections overlap requests within a phase, never across phases.**
- **The network decides the strategy.** High latency favours few large reads; low bandwidth
  favours reading only what is needed.
:::

## Problems

Three, in `exercises/python/how_readers_read.py`, or in Rust in
`exercises/src/how_readers_read.rs`. The first two have tests. The third has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: how_readers_read
```

**10.1 Merge ranges.** Turn byte ranges into requests, merging those within a gap. The test
compares your requests with the reader's on thousands of generated cases.

**10.2 Time the requests.** Given each phase's request durations and a number of connections,
say when the last request finishes. The test compares your answer with the simulated store's
clock.

**10.3 Your own network.** No test: the network is yours. Time a hundred small range requests
and a few large ones against the object store your files live in, and estimate its latency and
bandwidth. Then run `PYTHONPATH=python python3 -m parquet_lab scan FILE --where ... --latency-us N --bandwidth N` or
`cargo run -p pqlab -- scan FILE --where ... --latency-us N --bandwidth N`
on one of your files, with a few gaps and connection counts. A good answer names the gap and
connection count you would choose, and checks the prediction against a real query's timing.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_10_1` in Python, or `problem_10_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_how_readers_read.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test how_readers_read -- --ignored
```
:::
::::

## Where to go next

- Amazon's guidance on
  [range requests and parallel connections](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html)
  describes the behaviour this chapter models.
- Production readers expose these choices as options. The Arrow project's
  [Rust Parquet reader](https://github.com/apache/arrow-rs/tree/main/parquet), for one, takes a
  hint for how much of the tail to read for the footer, and merges nearby ranges.
- [ch11](#writing-parquet-well) turns from reading to writing: how a writer's choices decide what
  any reader can skip.
