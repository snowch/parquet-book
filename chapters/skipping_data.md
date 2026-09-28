---
title: Skipping data
---

(skipping-data)=
# Skipping data

## The question

Given a predicate, which bytes can a reader prove it does not need?

[ch08](#metadata-and-statistics) established when a footer's minimum and maximum can be trusted.
This chapter puts them to work. A query arrives with a condition, such as `order_id = 431`. Before
the reader fetches a column chunk or a page, it asks whether the metadata proves that nothing
there can satisfy the condition. If it does, the reader skips it.

One rule governs every decision. **A skip must be certain.** A reader that skips a page holding a
matching row returns a wrong answer, silently. A reader that reads a page it could have skipped
only wastes bytes. So every mechanism here answers "skip" or "cannot rule it out", never "no
match" on a guess.

## The experiment

### The same orders, sorted and shuffled

`pruning-sorted.parquet` and `pruning-shuffled.parquet` hold the same orders, written the same
way: four row groups, pages of forty rows, a page index for every column, and a Bloom filter for
`customer_id`. The first is in `order_id` order; the second is shuffled.
[Appendix B](#the-fixtures) says how pyarrow wrote them.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name. Each step finds the footer as
[ch02](#anatomy-of-a-parquet-file) did, and decodes it with the reader's
`decode_file_metadata` from [ch03](#the-type-system).

**Ranges in the footer.** The query is `order_id = 431`. Every row group's statistics give the
smallest and largest `order_id` it holds. Read them, and ask of each row group whether `431` could
be in it:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/skipping_data/row_group_bounds.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/row_group_bounds.rs
:language: rust
```
:::
::::

Each row group covers its own band of order numbers, and only row group 2's band holds `431`. The
other three are skipped on the footer's word alone, before a byte of their data is fetched. The
test compares `431` with a minimum and a maximum, and nothing else.

Change `wanted` to `200`, then to `201`: each lands in one row group, the last of one band or the
first of the next. Then change the file to `pruning-shuffled.parquet`. Every row group now spans
nearly every order number, and every one must be read.

### When a range rules a condition out

A column chunk's statistics, or a page's, give a minimum, a maximum and a null count. Each
comparison is ruled out by a different fact about them:

| Condition | Skip when |
|---|---|
| `x = v` | `v` is below the minimum or above the maximum |
| `x != v` | the minimum and maximum both equal `v` |
| `x < v` | the minimum is `v` or more |
| `x > v` | the maximum is `v` or less |
| `x is null` | the null count is zero |
| `x is not null` | every value is null |

Null satisfies no comparison. A chunk whose values are all null is skipped for any condition but
`is null`, and it has no minimum or maximum to consult.

### Sorted data

The reader planned `SELECT *` on both files with each of the conditions below, using every
mechanism this chapter describes:

```{include} _generated/skipping-compare.md
```

Sorting is what makes statistics work. In the sorted file each row group covers a narrow band of
order numbers, and a condition on `order_id` rules out all but a few. In the shuffled file the
same statistics are true and useless: every band is almost the whole range. Columns nobody sorted
by, such as `customer_id` and `amount_cents`, behave alike in both files. This is why writers are
told to sort by the column queries filter on most, and why [ch11](#writing-parquet-well) returns
to it.

### The page index

Row group statistics decide whole row groups. The page index decides pages. It is written after
the row groups, in two structures per column chunk: a **ColumnIndex** with each page's minimum,
maximum and null count, and an **OffsetIndex** with each page's position, size and first row.
The reader's `page_index` module reads both. Ask them about `order_id` in row group 2, the one
row group the first step kept:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/skipping_data/pages_of_one_group.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/pages_of_one_group.rs
:language: rust
```
:::
::::

The row group's pages cover disjoint bands of forty order numbers, and only the first can hold
`431`. The ColumnIndex also records that its bounds are in `ASCENDING` order, which lets a reader
binary-search them rather than test every page. The OffsetIndex says where each page's bytes are
and which row it starts at, so the reader can fetch that page without the pages after it.

Change the file to `pruning-shuffled.parquet`. The boundary order is `UNORDERED`, each page
covers nearly every order number, and every page must be read.

A page skipped in the condition's column means rows skipped, not bytes skipped in every column.
The reader turns the kept pages into row ranges using their first rows, then asks each other
column's OffsetIndex which of its pages hold those rows. The fixtures cut every column's pages at
the same row counts, so the pages line up. Writers that cut pages by size give each column
different boundaries, and the row ranges are what connects them.

### Bloom filters

Statistics cannot rule out a value inside a chunk's range. Customer numbers fill most of their
range in every row group, so `customer_id = 424242` survives every minimum and maximum. A Bloom
filter answers a different question: was this exact value ever added?

The filter is a bitset of 32-byte blocks. To add a value, the writer hashes its PLAIN bytes with
xxHash64. The hash's high half picks a block; its low half, multiplied by eight fixed constants,
picks one bit in each of the block's eight 32-bit words; the writer sets those bits. To test a
value, the reader computes the same hash and checks the same bits. One clear bit proves the value
was never added. All set means it may have been: other values may have set those bits.

Probe each row group's filter in the shuffled file for customer `424242` with the reader's `bloom`
module:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/skipping_data/probe_a_bloom_filter.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/probe_a_bloom_filter.rs
:language: rust
```
:::
::::

Every row group gets the same hash and, since every filter has the same number of blocks, the
same block. The bits differ, because each row group's customers set different ones. In every row
group at least one of the eight bits is clear, so `424242` was never added to any of them, and the
reader skips the whole file for it.

Change `424242` to `426545`, the customer in the shuffled file's first row: row group 0's
filter has all eight bits set, as it must, since a filter never forgets a value it was given.
Then change the file to `pruning-sorted.parquet` and probe `424242` again. One row group's filter
has all eight bits set, although no order in the file is from that customer. That is a false
positive.

The reader measured how often that happens. It probed every filter in the shuffled file with
thousands of customer numbers its row group does not hold:

```{include} _generated/bloom-rate.md
```

The writer sized each filter for the false-positive rate the table's note gives, and the
measured rate is lower, because the filter's size is rounded up. False positives cost a read and
nothing else: the sorted file's false positive makes the reader read a row group with no match in
it. That is why, in the table under *Sorted data*, the sorted file reads bytes for
`customer_id = 424242` and the shuffled one reads none. A filter never produces a false negative, so it never costs a row.

### What each mechanism adds

The reader's `prune.plan` puts the three mechanisms together. It takes a condition, the columns
to read, and which mechanisms it may use, and decides row group by row group, saying why:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/skipping_data/plan_a_read.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/plan_a_read.rs
:language: rust
```
:::
::::

Statistics skip three row groups, as the first step did by hand. In row group 2, the page index
keeps one page of five, and the reader reads that page's rows from every column. The last line
counts the bytes of column chunks the plan reads, and the bytes of page index it fetched to
decide.

Set `page_index=False` (`page_index: false` in Rust): the reader keeps all of row group 2, and
reads several times as many bytes. Then take `leaves[1]`, which is `customer_id`, with `"424242"`
on `pruning-shuffled.parquet`. Statistics keep every row group, and the Bloom filters skip every
one, so the plan reads nothing but the filters. `prune.Op` has the other comparisons. Try
`amount_cents > 9800`, which is `leaves[3]` with `Op.GT` (`Op::Gt` in Rust), or `country is null`,
which is `leaves[2]` with `Op.IS_NULL` (`Op::IsNull`), whose value the reader ignores.

The same two conditions, with the mechanisms allowed one at a time:

```{include} _generated/skipping-mechanisms.md
```

Each mechanism costs bytes of its own: the page index and the filters are fetched before any data,
and in an object store each fetch is a request. Row group statistics are free, because they came
with the footer. Whether the others pay depends on how much they let the reader skip, and on how
many requests they add, which [ch10](#how-readers-read) measures.

## Building it

The steps read the statistics by hand, then asked the reader's `page_index` and `bloom` modules,
then called `prune.plan`. This section builds the parts of the plan: the test of a condition
against a range, the probe of a filter, and the step from kept rows to the pages of every column.
The tabs switch every excerpt on the page between the two languages.

### A condition against a range

`against_bounds` answers the null conditions first, from the null count alone, and skips a chunk
whose values are all null for any comparison:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/prune.py
:language: python
:start-at: def against_bounds(
:end-before: if p.value is None or found is None:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/prune.rs
:language: rust
:start-at: pub fn against_bounds(
:end-before: let (Some(x), Some((min, max))) = (&p.value, bounds) else {
```
:::
::::

For a comparison, `against_bounds` needs a usable minimum and maximum, which
[ch08](#metadata-and-statistics)'s `bounds` decided. It places the value against each, and rules
the comparison out by the fact in the table above:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/prune.py
:language: python
:start-at: if p.value is None or found is None:
:end-before: @dataclass(frozen=True)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/prune.rs
:language: rust
:start-at: let (Some(x), Some((min, max))) = (&p.value, bounds) else {
:end-before: /// Which mechanisms a plan may use.
```
:::
::::

The plan calls the same function in two places: with a column chunk's statistics, and with each
page's entry in the ColumnIndex.

### Probing a Bloom filter

The block and the eight bits come from the hash alone:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/bloom.py
:language: python
:start-at: def probe_hash(self, hash: int)
:end-before: def read(file: bytes, chunk: ColumnChunk)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/bloom.rs
:language: rust
:start-at: pub fn probe_hash(
:end-before: /// Read a column chunk's Bloom filter
```
:::
::::

xxHash64 itself is about fifty lines in the same file, checked against the reference hashes of short
strings.

### From kept rows to the pages of every column

A page's rows run from its first row to the next page's first row, or to the end of the row
group:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/page_index.py
:language: python
:start-at: def row_ranges(self, num_rows: int)
:end-before: def _read_at(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/page_index.rs
:language: rust
:start-at: impl OffsetIndex {
:end-before: fn read_at(
```
:::
::::

`column_read` then takes the rows the condition's column kept and one column chunk. With the
chunk's OffsetIndex, `oi`, it reads the dictionary page, if the chunk has one, and every data page
whose rows overlap the kept rows. Without an OffsetIndex, it reads the whole chunk, `whole`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/prune.py
:language: python
:start-at: spans = []
:end-before: def plan(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/prune.rs
:language: rust
:start-at: let mut spans = Vec::new();
:end-before: /// Plan a read of `projection`
```
:::
::::

### Checking it

Three kinds of test hold the reader to the data rather than to itself. The OffsetIndex must list
exactly the pages the walker from [ch06](#pages) finds. The ColumnIndex must hold each page's
own minimum, maximum and null count, as the reader computes them from the decoded values. And
for hundreds of conditions on every fixture, every row that matches must lie in a row range the
plan keeps, in a page every column reads. Every value in a chunk must also pass its Bloom filter.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures
```
:::
::::

### Ask a library

pyarrow and the `parquet` crate can both skip row groups. Ask each the questions the steps asked:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/skipping_data/skipping_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/skipping_with_a_library.rs
:language: rust
```
:::
::::

pyarrow's dataset reader splits the file into row groups and keeps those whose statistics leave
room for the condition. For `order_id = 431` on the sorted file it keeps row group 2, as the
first step did. For `customer_id = 424242` on the shuffled file it keeps all four, where the
reader's Bloom filters ruled out every one. pyarrow skips by statistics only. It uses neither the
Bloom filters nor the page index to skip, and its Python API cannot read either. It says whether a
column chunk has a ColumnIndex and an OffsetIndex, and versions newer than the one the page loads
([why the page's is older](#two-pyarrows)) also say where a chunk's Bloom filter is, but no more. Within a kept row group, it reads every
page of the columns it needs.

The crate does nothing unless you ask. Its row group predicate is a function you write, here one
that reads `order_id`'s minimum and maximum, and it keeps row group 2 as well. Asked for the page
index, it returns the kept row group's ColumnIndex: the order and the pages' bounds the second
step printed. Asked for the Bloom filters, its `check` says, for every row group, that `424242` is
not there. The crate's Arrow reader skips pages by the page index, with row selections and row
filters. It needs the crate's `arrow` feature, which this workspace does not build.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin skipping_with_a_library
```

## What this cannot tell you

**How conditions combine.** The reader's plan takes one condition. Each condition yields row
ranges, and `AND` intersects them while `OR` joins them; a row group is skipped only when the
combined ranges are empty.

**How to skip within repeated columns.** In a column that repeats, a page's values are not its
rows, and a reader needs the level histograms to map one to the other. This reader does not use
the page index for such columns.

**Whether skipping is faster.** Skipping saves bytes and decoding. It can cost requests: a plan
that reads five scattered pages makes five requests where a full scan could make one.
[ch10](#how-readers-read) weighs the two.

**Other ways to skip.** Some readers fetch a column's dictionary page and look the value up
there before reading any data page. This reader does not.

## Key takeaways

:::{div}
:class: takeaways

- **A skip must be certain; a read may be unnecessary.** Every mechanism answers "skip" or
  "cannot rule it out".
- **Statistics rule out ranges, so sorting decides their worth.** The same statistics skip
  most of a sorted file and almost none of a shuffled one.
- **The page index skips pages, and connects columns by row.** The OffsetIndex's first rows map
  kept rows to the pages of every other column.
- **A Bloom filter rules out single values inside a range.** It has false positives, which cost
  reads, and no false negatives, which would cost rows.
- **Every mechanism has its own cost in bytes and requests.** Only the footer's statistics come
  free.
:::

## Problems

Three, in `exercises/python/skipping_data.py`, or in Rust in
`exercises/src/skipping_data.rs`. The first two have tests. The third has none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: skipping_data
```

**9.1 Can this be skipped?** Decide from a range and a null count whether a page can hold a match
for four comparisons. The test checks every page of the pruning fixtures: you must never skip a
page holding a match, and must skip every page the metadata rules out.

**9.2 Probe a Bloom filter.** Given a filter's bitset and a value's hash, test the eight bits.
The test compares your answer with the reader's for thousands of customer numbers.

**9.3 Your own condition.** No test: the data is yours. Take a condition your queries use often
and a file they run against, and run `PYTHONPATH=python python3 -m parquet_lab skipping FILE COLUMN OP VALUE` or
`cargo run -p pqlab -- skipping FILE COLUMN OP VALUE`. Record
how many row groups and bytes it skips, and with which mechanisms. Then rewrite the file sorted by
that column and run it again. A good answer reports both, says what the sort cost the other
columns' compression, and names a condition the sort does not help.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_9_1` in Python, or `problem_9_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_skipping_data.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test skipping_data -- --ignored
```
:::
::::

## Where to go next

- The page index is specified in the format repository's
  [PageIndex.md](https://github.com/apache/parquet-format/blob/master/PageIndex.md), and Bloom
  filters in [BloomFilter.md](https://github.com/apache/parquet-format/blob/master/BloomFilter.md).
- Split block Bloom filters come from Putze, Sanders and Singler, *Cache-, Hash- and
  Space-Efficient Bloom Filters*, in the ACM Journal of Experimental Algorithmics.
- xxHash64 is specified in the
  [xxHash repository](https://github.com/Cyan4973/xxHash/blob/dev/doc/xxhash_spec.md).
- [ch10](#how-readers-read) turns these plans into requests against an object store.
