---
title: How readers read
---

(how-readers-read)=
# How readers read

## The question

Why does a reader issue exactly the requests it does?

[Skipping data](#skipping-data) decided which bytes a query needs. Knowing the bytes is not the same as
fetching them well. Each request to an object store costs a round trip before the first byte
arrives, and that cost does not shrink with the request. A reader that needs many small ranges
can make one request for each, one large request that covers them all, or something between, and
it can make several at once. This chapter builds the reader's read path and measures those
choices.

:::{div}
:class: reading-guide

**What you will learn:** Explain the trade-off between bytes, requests and latency, and identify which reads can run in parallel.

Read the explanations, worked results and diagrams; the code is optional.
:::

## The experiment

```lesson
trace-a-complete-scan
```

### One query, request by request

A **scan** reads the columns and candidate rows a query needs. Its requests can cost more than
the bytes themselves: **latency** is the wait from sending a request until its first byte arrives.
A **connection** carries requests between the reader and the store; several connections can
have requests in flight at the same time.

The query is `SELECT * WHERE order_id = 431` on `pruning-sorted.parquet`.
The [pruning example](compose-a-pruning-plan.html) chooses its byte ranges from a local file.
Here `scan` fetches those ranges through a simulated object store, which logs every request,
its connection, and when it started and ended. A `Strategy` says how to make the requests: how to find the footer and
how much of the tail to read first, how close two ranges must be to merge into one request, and
how many connections to use. **Coalescing** merges nearby byte ranges into one request,
including any gap between them. **Concurrency** lets independent requests overlap in time.
Neither can remove a dependency on metadata that has not arrived yet.

The [footer-reading example](trace-footer-requests.html) ends when the footer arrives.
This fixture also has page indexes, so the trace continues through the index and data requests.
The worked result uses the example's starting settings.

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

The first three requests discover the size, then read the trailer and footer. Next come the indexes the
plan needs, one request each: `order_id`'s ColumnIndex for row group 2, the one row group the
statistics keep, and an OffsetIndex for each column. Last come the pages, one request each, with
`country`'s dictionary page apart from its data page. Every request starts when the one before
it ends. The bytes are a small share of the file, and they move in almost no time. The time is
the latency, paid once per request.

`rows matching` lists row positions counted from zero. Order ID `431` is at position `430` in
this fixture.

To try the same query with a different strategy, open **Read or run the code**. In Python,
select **Run** with the original code, then select **Edit**. Run after each edit below. Compare
`requests`, `bytes` and `ms` on the totals line. The individual request lines show what caused
any change. The reported time comes from the simulation.

- **Read more of the tail.** Find the footer with `SuffixRange()` and `prefetch=8192`
  (`SizeSource::SuffixRange` and `prefetch: 8192` in Rust). The first request brings the trailer,
  the footer and the indexes together, because the indexes sit immediately before the footer.
  Every index request disappears.
- **Merge ranges.** Set `coalesce_gap` to `4096` (`Some(4096)` in Rust). The pages of the four
  columns become one request, which also reads the bytes between them.
- **Use more connections.** Keep the suffix range and prefetch. Set `coalesce_gap` back to
  `None`, leave `connections` at `1`, and run the unmerged scan. Then change only
  the `connections` value to `4` and run again. Which totals stay the same? Which changes? Look
  at the request times to see which requests overlap. Separate connections can fetch pages in
  parallel once the reader knows where the pages are.
- **Read everything.** Set `prefetch=65536`, more than the file holds. The first request reads
  all of it, and there is nothing left to ask for.

### Phases

A reader cannot ask for everything at once, because it does not know what to ask for. The
requests fall into phases, each needing the answers to the one before:

1. **The footer.** The trailer says where the footer starts, so finding it takes one or two
   requests after the size is known: [Anatomy of a Parquet file](#anatomy-of-a-parquet-file)'s strategies.
2. **The indexes.** Which Bloom filters and page indexes to fetch depends on the footer: where
   they are, and which row groups the statistics have already ruled out.
3. **The data.** Which pages to fetch depends on the indexes.

Within a phase the requests are independent, and a reader with several connections sends them
together. This planner waits for a phase to finish before starting another. Adding
connections cannot remove a dependency on metadata that has not arrived.

### The phases on a timeline

The panel selects the page-index strategy automatically and draws its requests by connection.
Choose a different option under **Strategy** to update the timeline and totals. The options
match the rows in [Choose a read strategy](choose-a-read-strategy.html).

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

This is a deterministic simulated object store. It illustrates dependencies, not observed network timing.

```practice
question: Two selected data ranges are already known, but the index needed to locate a third has not arrived. Which reads can overlap, and why can the third not be scheduled at its final offset yet?
answer: The two known independent ranges can overlap if connections allow. A particular planner may wait for a whole phase to finish before starting the next. The unknown range depends on the index response; concurrency cannot remove that missing-information dependency.
```

```lesson
choose-a-read-strategy
```

### What each choice costs

Compare `SELECT * WHERE order_id = 431` on `pruning-sorted.parquet` under different request
strategies. [Trace a complete scan](trace-a-complete-scan.html) shows the starting strategy: find
the footer, fetch the indexes, then fetch selected pages. This table changes one choice at a time:

```{include} _generated/scan-strategies.md
```

The first rows follow [Skipping data](#skipping-data): skipping row groups by statistics cuts both bytes
and requests. Then the page index cuts bytes further but adds requests, one for each index and
each page, and the query gets slower. Bytes were not the problem. At the latency the table's
note gives, the number of requests decides the time, and every row below that attacks it: a
larger tail brings the indexes with the footer, merging turns neighbouring pages into one
request, and connections run requests side by side.

For a file this small, the fastest strategy is the crudest: read all of it. That is a real
answer: a reader that knows a file is small can fetch all of it before parsing anything.

### Reading everything

A `SELECT *` query with no condition must read every column chunk. How long that takes depends on how the
requests are made:

```{include} _generated/scan-full.md
```

One request per column chunk, one at a time, pays the latency for every request in turn: the
footer's three, then one per column chunk. More connections overlap the column chunks'
requests, but the footer's three stay in sequence, since each depends on the last. Merging chunks
that touch needs no extra bytes at all: a row group's chunks are written end to end, so the whole
data region is one range.

### When bytes matter

**Bandwidth** is the rate at which bytes can be transferred after a response starts.
Latency favours few large requests; limited bandwidth favours fetching only what is needed. Which wins
depends on the network:

```{include} _generated/scan-networks.md
```

For the simulated networks in the table, compare the elapsed time for a whole-file read and a
selective read. On the fast link with high latency, the whole-file read avoids round trips. On
the slower link with low latency, reading fewer bytes wins. The simulation does not measure a
storage service or your connection.

To reproduce the slower-link case, open the Python example in
[Trace a complete scan](trace-a-complete-scan.html) and select **Edit**. Set `FooterOptions` to
`FooterOptions(SuffixRange(), prefetch=8192)`. In the `result = scan(...)` call, replace
`NetworkModel()` with `NetworkModel(latency_us=1000, bandwidth_bytes_per_sec=1_000_000)`.
Select **Run**, then change only `prefetch` to `65536` and run again. Compare `bytes` and `ms`
in the two totals, and check that `rows matching` is unchanged. Which cost dominates now?

### Only what was fetched

The reader keeps a copy of the file that starts empty, and fills in each response. It plans from
that copy and decodes from it. A range it forgot to request reads as zeros, which fails to decode.
The tests run every query under every strategy and compare the rows with a plain read of the
whole file, so a missed range cannot pass unnoticed.

Latency and bandwidth are fixed model inputs. Decode time, caches, throttling and real network variability are not modelled.

```practice
question: A workload moves from a high-latency store to a bandwidth-limited connection. Must merging distant ranges remain the best choice?
answer: No. Merging saves request starts but fetches the gap. When those extra bytes are expensive, separate requests or more precise reads can win. Re-evaluate the stated network model and workload.
```

```lesson
build-scan-planner
```

## Building it

:::{div}
:class: optional-section

**Optional implementation.** Read this section to see how the reader is built.
For the conceptual path, continue to [What this cannot tell you](#how-readers-read-limits),
then the takeaways and the understanding check.
:::

The [complete scan trace](trace-a-complete-scan.html) runs `scan` on `pruning-sorted.parquet`.
It locates metadata with `read_footer`, chooses ranges with `prune.plan`, and fetches in phases. This section builds the fetching: how ranges merge, how one
phase is sent, how the store's clock prices it, and how the reader decodes only the pages it
fetched. Choose Python or Rust in an open code section. The same choice applies to the other code sections.

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
read it is asked for, using `pruning-sorted.parquet`. Ask the `parquet` crate for the footer
and page index from a tail of that file:

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

For a filtered read in Python, select **Edit** and replace the expression after `rows =` with
`pq.read_table(file, filters=[("order_id", "==", 431)]).num_rows`. Select **Run**. Compare the
number of rows returned and the byte lengths on the `read` lines. This pyarrow example can use
the footer statistics to skip row groups. It still reads chunks from the group holding the match.

The crate's `ParquetMetaDataReader` makes no requests of its own. Given the last eight bytes, it
answers `NeedMoreData` with the size of tail it needs: the footer and its trailer. Given that, it
parses the footer, finds the page index before it, and asks again, for a tail reaching back to the
first index. Given that, it has everything. Those are the chapter's first two phases, with each
answer needed before the next request can be made. Start from `8192` and it needs one read. The
crate's asynchronous reader takes the same number through `with_prefetch_hint`, and hands a row
group's ranges to the `object_store` crate's `get_ranges`, which merges ranges that lie close
together. It needs the crate's `arrow` and `async` features, which this workspace does not build.

To reproduce the Rust example locally, run this from the repository root.

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin reads_with_a_library
```

```lesson
reference
```

(how-readers-read-limits)=
## What this cannot tell you

These notes qualify the [request-strategy comparison](choose-a-read-strategy.html) on
`pruning-sorted.parquet`. The [complete scan trace](trace-a-complete-scan.html) shows its requests.
Their times come from a deterministic object-store model, not a live network.

**How a real store behaves.** The model charges a fixed latency and a fixed bandwidth. Real
stores vary from request to request, throttle busy prefixes, and limit connections. The model
keeps the shape of the problem and none of its noise, so its numbers compare strategies; they do
not predict a real query's time.

**Caching** keeps previously fetched bytes or decoded metadata for reuse. A reader that opens
the same file twice can keep its footer, and one that runs many queries can keep pages. This reader starts empty every time.

**Reading many files.** A table is usually many files, and a query engine reads them in parallel.
[Lakehouse and beyond](#lakehouse-and-beyond) turns to tables.

**Decoding time.** Every cost here is the network's. On a fast network, decompressing and decoding
can take longer than fetching, and a reader that overlaps the two gains most.

## Key takeaways

:::{div}
:class: takeaways

- **This planner groups requests by dependency.** It reads the footer, then the selected
  indexes, then the data. Missing metadata can prevent a later request from being planned.
- **High request latency can outweigh saved bytes.** In the high-latency model, skipping that
  adds requests can make the small-file query slower.
- **Merging ranges trades bytes for requests.** Ranges that touch merge for free; merging across
  a gap reads the gap.
- **This planner overlaps requests within a phase.** It waits for that phase to finish before
  starting another; a production scheduler can make different choices where dependencies allow.
- **The network decides the strategy.** High latency favours few large reads; low bandwidth
  favours reading only what is needed.
:::

```checkpoint
question: Why can fetching extra bytes make a query faster on object storage?
answer: A larger tail read or a merged range can replace several requests with one. Each avoided request saves a round trip. The extra transfer can cost less than that latency, though a slow link or a large file can reverse the trade-off.
```

## Problems

The coding exercises are optional. You can also reason through the question about your own data
without writing a program.

Three, in `exercises/python/how_readers_read.py`, or in Rust in
`exercises/src/how_readers_read.rs`. The first two have tests. The third has none.

Read the tasks below. To solve them in the browser, open **Edit Python solutions and run tests**.
The editor starts with unfinished functions. Edit the functions for the task and select **Run the tests**.
Read the failed checks to see which behavior is still missing.

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
- [Writing Parquet well](#writing-parquet-well) turns from reading to writing: how a writer's choices decide what
  any reader can skip.
