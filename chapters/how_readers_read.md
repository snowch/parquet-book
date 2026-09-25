---
title: How readers read
---

(how-readers-read)=
# How readers read

## The question

Why does a reader issue exactly the requests it does?

[ch09](#skipping-data) decided which bytes a query needs. Knowing the bytes is not the same as
fetching them well. Each request to an object store costs a round trip before the first byte
arrives, and that cost does not shrink with the request. A reader that needs twenty small ranges
can make twenty requests, one large request that covers them all, or something between, and it
can make several at once. This chapter builds the reader's read path and measures those choices.

## The experiment

### One query, many ways to fetch it

The panel runs a query against a fixture held in the simulated object store from
[ch02](#anatomy-of-a-parquet-file). Every request the reader makes is on the timeline, in the lane
of the connection that carried it. The rows at the bottom were decoded from the bytes those
requests returned, and from nothing else.

```lab
experiment: scan
fixture: pruning-sorted.parquet
fixtures: pruning-sorted.parquet, pruning-shuffled.parquet, tiny.parquet
column: 0
op: =
value: 431
```

Try these:

% number-ok: the panel's own settings, named as its controls name them; nothing here is measured.
1. **As loaded.** Three sequential requests find the footer. Then come the page indexes for the
   one row group the statistics keep, then the pages. Each phase waits for the one before it.
2. **Read 8 KiB for the footer.** The indexes sit immediately before the footer, so the larger tail
   brings them too, and their phase disappears.
3. **Merge ranges within 4 KiB.** The pages of the four columns become one request, with a few
   unwanted bytes between them.
4. **Four connections.** Requests in the same phase now overlap. Requests in different phases
   still cannot.
5. **Read 64 KiB for the footer.** The file is smaller than that, so the tail read brings all
   of it, and no other request is needed.
6. **Change the network.** Set the latency to 1 ms and the bandwidth to 1 MB/s, and compare the
   last two strategies again.

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

### What each choice costs

The same query, with each change made in turn:

```{include} _generated/scan-strategies.md
```

The first rows follow [ch09](#skipping-data): skipping row groups by statistics cuts both bytes
and requests. Then the page index cuts bytes further but adds requests, one for each index and
each page, and the query gets slower. Bytes were not the problem. At twenty milliseconds a
request, the number of requests decides the time, and every row below that attacks it: a larger
tail brings the indexes with the footer, merging turns neighbouring pages into one request, and
connections run requests side by side.

For a file this small, the fastest strategy is the crudest: read all of it. That is a real
answer: a reader that knows a file is small can fetch all of it before parsing anything.

### Reading everything

A query with no condition must read every column chunk. How long that takes depends on how the
requests are made:

```{include} _generated/scan-full.md
```

One request per column chunk, one at a time, pays the latency sixteen times. More connections
overlap them, and the footer's three requests remain, since each depends on the last. Merging
chunks that touch needs no extra bytes at all: a row group's chunks are written end to end, so
the whole data region is one range.

### When bytes matter

Latency favours few large requests; bandwidth favours fetching only what is needed. Which wins
depends on the network:

```{include} _generated/scan-networks.md
```

On a fast network with high latency, reading the whole file wins even though it moves many times
the bytes. On a slow link with low latency, the careful plan wins, because moving the extra bytes
takes longer than the round trips it saves. Real files are far larger than this one, which moves
the balance toward the careful plan: nobody reads a gigabyte to find one row. Readers therefore
merge ranges up to a threshold, and choose the threshold from the latency and bandwidth they
expect.

### Only what was fetched

The reader keeps a copy of the file that starts empty, and fills in each response. It plans from
that copy and decodes from it. A range it forgot to request reads as zeros, which fails to decode.
The tests run every query under every strategy and compare the rows with a plain read of the
whole file, so a missed range cannot pass unnoticed.

## Building it

### Merging ranges

```{literalinclude} ../crates/parquet-lab/src/scan.rs
:language: rust
:start-at: pub fn coalesce(
:end-before: /// Fetch every range the reader does not already have
```

### A clock for every connection

The simulated store gives each request the connection that is free first, and never starts it
before its phase:

```{literalinclude} ../crates/parquet-lab/src/object_store.rs
:language: rust
:start-at: // The connection that is free first
:end-before: self.requests.push(Request {
```

### Reading chosen pages

With the page index, the reader parses each wanted page where the OffsetIndex says it starts,
without walking the pages before it:

```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: pub fn read_column_pages(
:end-before: /// Decode pages already located
```

### Checking it

Over two hundred combinations of fixture, condition and strategy, the reader's rows must equal a
plain read's:

```bash
cargo test -p parquet-lab --test fixtures every_strategy
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

Three, in `exercises/src/how_readers_read.rs`. The first two have tests. The third has none.

**10.1 Merge ranges.** Turn byte ranges into requests, merging those within a gap. The test
compares your requests with the reader's on thousands of generated cases.

```bash
cargo test -p exercises --test how_readers_read problem_10_1 -- --ignored
```

**10.2 Time the requests.** Given each phase's request durations and a number of connections,
say when the last request finishes. The test compares your answer with the simulated store's
clock.

```bash
cargo test -p exercises --test how_readers_read problem_10_2 -- --ignored
```

**10.3 Your own network.** No test: the network is yours. Time a hundred small range requests
and a few large ones against the object store your files live in, and estimate its latency and
bandwidth. Then run `cargo run -p pqlab -- scan FILE --where ... --latency-us N --bandwidth N`
on one of your files, with a few gaps and connection counts. A good answer names the gap and
connection count you would choose, and checks the prediction against a real query's timing.

## Where to go next

- Amazon's guidance on
  [range requests and parallel connections](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html)
  describes the behaviour this chapter models.
- Production readers expose these choices as options. The Arrow project's
  [Rust Parquet reader](https://github.com/apache/arrow-rs/tree/main/parquet), for one, takes a
  hint for how much of the tail to read for the footer, and merges nearby ranges.
- [ch11](#writing-parquet-well) turns from reading to writing: how a writer's choices decide what
  any reader can skip.
