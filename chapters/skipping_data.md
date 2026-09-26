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
way: four row groups, small pages, a page index for every column, and a Bloom filter for
`customer_id`. The first is in `order_id` order; the second is shuffled.
[Appendix B](#the-fixtures) says how they were written.

```lab
experiment: skipping
fixture: pruning-sorted.parquet
fixtures: pruning-sorted.parquet, pruning-shuffled.parquet
column: 0
op: =
value: 431
```

The panel plans `SELECT *` with the condition, row group by row group, and says what each
mechanism decided and why. It also reads the whole column to count the matching rows, so every
plan is checked against the answer. Try these:

1. **As loaded.** Statistics rule out three row groups. In the fourth, the page index keeps one
   page, and the reader reads that page of every column.
2. **Untick the page index.** The reader now reads the whole of the remaining row group.
3. **Switch to `pruning-shuffled.parquet`.** Every row group and every page covers nearly the
   whole range of order numbers, and nothing is skipped.
4. **Ask for `customer_id = 424242`** in the shuffled file. Statistics cannot help: customer
   numbers are random in both files. The Bloom filters rule out every row group. Look at the bits
   each probe tested.
5. **Try `country is null`.** Every page holds a few nulls, so nothing can be skipped.
6. **Try `amount_cents > 9800`.** Amounts are random too, but some pages happen to have no
   amount that high.

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

The same conditions, planned on both files:

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
This is the ColumnIndex of `order_id` in one row group of each file:

```{include} _generated/page-index-order-id.md
```

The sorted file's pages cover disjoint bands, and the index records that its bounds are in
ascending order, which lets a reader binary-search them. The shuffled file's pages each cover
nearly everything.

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
picks one bit in each of the block's eight words; the writer sets those bits. To test a value, the
reader computes the same hash and checks the same bits. One clear bit proves the value was never
added. All set means it may have been: other values may have set those bits.

```{include} _generated/bloom-rate.md
```

The writer sized each filter for a false-positive rate of one in twenty, and the measured rate is
lower, because the filter's size is rounded up. False positives cost a read and nothing else: in
the first table, the sorted file's filter passed `424242` in one row group, so the reader read a
row group with no match in it. A filter never produces a false negative, so it never costs a row.

### What each mechanism adds

The same two conditions, with the mechanisms allowed one at a time:

```{include} _generated/skipping-mechanisms.md
```

Each mechanism costs bytes of its own: the page index and the filters are fetched before any data,
and in an object store each fetch is a request. Row group statistics are free, because they came
with the footer. Whether the others pay depends on how much they let the reader skip, and on how
many requests they add, which [ch10](#how-readers-read) measures.

## Building it

### A condition against a range

Each comparison, and the fact that rules it out:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/prune.py
:language: python
:start-at: def against_bounds(
:end-before: @dataclass(frozen=True)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/prune.rs
:language: rust
:start-at: pub fn against_bounds(
:end-before: /// Which mechanisms a plan may use.
```
:::
::::

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

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/prune.py
:language: python
:start-at: def column_read(
:end-before: def plan(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/prune.rs
:language: rust
:start-at: /// The bytes of `chunk` needed for `rows`
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

## What this cannot tell you

**How conditions combine.** The panel takes one condition. Each condition yields row ranges, and
`AND` intersects them while `OR` joins them; a row group is skipped only when the combined ranges
are empty.

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

**9.1 Can this be skipped?** Decide from a range and a null count whether a page can hold a match
for four comparisons. The test checks every page of the pruning fixtures: you must never skip a
page holding a match, and must skip every page the metadata rules out.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_skipping_data.py --problems -k problem_9_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test skipping_data problem_9_1 -- --ignored
```
:::
::::

**9.2 Probe a Bloom filter.** Given a filter's bitset and a value's hash, test the eight bits.
The test compares your answer with the reader's for thousands of customer numbers.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_skipping_data.py --problems -k problem_9_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test skipping_data problem_9_2 -- --ignored
```
:::
::::

**9.3 Your own condition.** No test: the data is yours. Take a condition your queries use often
and a file they run against, and run `PYTHONPATH=python python3 -m parquet_lab skipping FILE COLUMN OP VALUE` or
`cargo run -p pqlab -- skipping FILE COLUMN OP VALUE`. Record
how many row groups and bytes it skips, and with which mechanisms. Then rewrite the file sorted by
that column and run it again. A good answer reports both, says what the sort cost the other
columns' compression, and names a condition the sort does not help.

## Where to go next

- The page index is specified in the format repository's
  [PageIndex.md](https://github.com/apache/parquet-format/blob/master/PageIndex.md), and Bloom
  filters in [BloomFilter.md](https://github.com/apache/parquet-format/blob/master/BloomFilter.md).
- Split block Bloom filters come from Putze, Sanders and Singler, *Cache-, Hash- and
  Space-Efficient Bloom Filters*, in the ACM Journal of Experimental Algorithmics.
- xxHash64 is specified in the
  [xxHash repository](https://github.com/Cyan4973/xxHash/blob/dev/doc/xxhash_spec.md).
- [ch10](#how-readers-read) turns these plans into requests against an object store.
