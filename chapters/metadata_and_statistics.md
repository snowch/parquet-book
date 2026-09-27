---
title: Metadata and statistics
---

(metadata-and-statistics)=
# Metadata and statistics

## The question

What does the footer know that lets a reader avoid reading the data?

Every chapter so far read data to answer a question. The footer can answer some questions
without it. Each column chunk's metadata carries a summary of the chunk's values: the smallest,
the largest, and how many are null. A reader looking for orders above a certain amount can
compare that amount with each chunk's maximum and skip the chunks that cannot hold a match.
[ch09](#skipping-data) does that.

First there is a narrower question. A minimum is stored as bytes, and bytes mean nothing without
an order. When is the footer's minimum the value a reader thinks it is?

## The experiment

### Read the statistics yourself

`statistics.parquet` holds twelve orders, four to a row group. Each column was chosen for a way
statistics are misread. [Appendix B](#the-fixtures) says how pyarrow wrote it.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name. Each step finds the footer as
[ch02](#anatomy-of-a-parquet-file) did, and decodes it with the reader's
`decode_file_metadata` from [ch03](#the-type-system).

**Four bytes, two numbers.** `customer_id` holds customer numbers, and some are above `2^31`. The
footer stores each row group's smallest and largest in four bytes, least significant first. Read
the bytes two ways:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/metadata_and_statistics/signed_or_unsigned.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/signed_or_unsigned.rs
:language: rust
```
:::
::::

The schema says `customer_id` is an `INT32` annotated as an unsigned integer. Read as unsigned,
every row group's maximum is a customer number above `2^31`. Read as signed, the same four bytes
are negative, and the maximum falls below the minimum. The minimums are small, so both readings
agree on them. Nothing in the bytes says which reading is right. Only the annotation does.

Change the column to 2, which is `delta`, a signed 8-bit integer stored in an `INT32`. Now the
signed reading is the right one, and the unsigned reading turns its negative minimums into
numbers above `2^31`.

**Bytes in order.** Strings are compared byte by byte, as UTF-8 writes them. Sort four of the
fixture's cities by their bytes, then by the same bytes read as signed numbers:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/metadata_and_statistics/byte_order.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/byte_order.rs
:language: rust
```
:::
::::

UTF-8 writes each ASCII letter as one byte below `0x80`, and every other letter as two or more
bytes of `0x80` and above. So `Århus` and `Łódź` sort after `Zürich` by their bytes. Read each
byte as signed, as Java does, and those bytes become negative: both names move in front of
`Aarhus`. Python's own sort of the strings agrees with the bytes, because UTF-8 keeps the order of
code points. Rust sorts a `str` by its bytes.

Add `"Écija"` or `"Ängelholm"`, two more of the fixture's cities, and see where each order puts
them.

**The reader decides.** The reader chooses an order for each column from its physical type and
its annotation, then asks its `bounds` function whether it may use each column chunk's minimum
and maximum:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/metadata_and_statistics/the_reader_decides.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/the_reader_decides.rs
:language: rust
```
:::
::::

Every column chunk with a minimum and maximum gives a range in its column's order.
`customer_id`'s maximums are the unsigned numbers, and `city`'s maximum in row group 0 is `Łódź`,
as the second step predicted. `order_id`'s ranges do not overlap, because the rows were
written in order: a reader looking for one order reads one row group. `temp_c` holds a NaN in
row group 0, and the bounds leave it out. Its minimum in row group 1 is `-0`.

Two kinds of chunk give nothing. `coupon` in row group 1 has no minimum and no maximum, and its
null count says why: every value is null. `note` has no statistics at all, because the writer was
told not to keep them.

Set `old_writer` to true (`True` in Python). The step then deletes `min_value` and `max_value`, and keeps only the
deprecated `min` and `max`, as a writer from before the newer fields would have. The reader still
accepts `order_id`, `delta` and `temp_c`. `customer_id` and the strings have nothing left, because
pyarrow wrote no deprecated fields for them. The reader refuses `amount`, although pyarrow wrote
both pairs for it, and the section on the deprecated fields below says why. Then set `old_writer`
back, and make `type_order` false, as if the footer had no `column_orders`: every chunk with
statistics is refused.

### What the footer records

This is which fields of the `Statistics` structure the writer set for each column of the first row
group:

```{include} _generated/statistics-fields.md
```

- **`min_value` and `max_value`** are the bounds in the column's own sort order.
- **`min` and `max`** are older fields with the same purpose. They are deprecated. pyarrow still
  writes them, as copies of `min_value` and `max_value`, for every column whose order is signed.
  Here that is every column but the unsigned integers and the strings, as the table shows.
- **`null_count`** counts the nulls. A chunk whose null count equals its value count holds no
  values at all.
- **`is_min_value_exact` and `is_max_value_exact`** say whether each bound is a value in the
  chunk. A writer may shorten a long string to keep the footer small, and the shortened bound is
  then only a bound.
- **`distinct_count`** is defined and rarely written. pyarrow does not write it.

### Sort orders

The same bytes sort differently depending on what they hold. The format fixes an order for every
type:

| Values | Order |
|---|---|
| `INT32`, `INT64`, and the dates, times and timestamps stored in them | signed |
| `INT32`, `INT64` annotated as unsigned integers | unsigned |
| `FLOAT`, `DOUBLE`, `FLOAT16` | by value, with NaN left out |
| `DECIMAL` stored in bytes | by value, as a big-endian two's complement integer |
| every other byte array: strings, UUIDs, binary | unsigned, byte by byte |
| `INT96`, `INTERVAL` | undefined |

The order of strings is the order of their bytes in UTF-8, as the second step showed. It is not
alphabetical order for a person: `Århus` sorts after `Zürich`.

### What a mistaken order gives

Each column in the fixture has a likely mistake. The reader decodes the values, finds the
smallest and largest in the column's order, and checks them against the footer. Then it finds
them again in the mistaken order:

```{include} _generated/statistics-mistakes.md
```

Every mistaken result is confidently wrong, and the damage comes when two orders meet: bounds
computed in one and compared in the other. A reader comparing strings correctly against the
mistaken `city` bounds finds `Aarhus` below their minimum, and skips the row group that holds it.
One comparing customer numbers correctly against the mistaken `customer_id` bounds skips the row
group holding the largest of them. Nothing in the bytes warns of it; only the column's type does.

### The deprecated fields

The first versions of the format defined `min` and `max` without saying in what order. The most
widely used writer of the time compared everything as signed values, including strings, whose
bytes Java treats as signed. Its string statistics were wrong for any value with a byte above
`0x7f`, and readers could not tell which files were affected.

The fix added `min_value` and `max_value`, and a `column_orders` list in the footer that says,
column by column, which order they use. `TYPE_ORDER` is the order in the table above, and the one
every fixture's footer names; this reader treats any other as unknown. A reader's rules follow
from that history:

- Use `min_value` and `max_value` when the footer has `column_orders`. Without it, their order is
  undefined.
- Use `min` and `max` only where signed comparison is the right order and the values are not
  byte arrays. That rules out `amount`, a decimal stored in bytes. pyarrow's copies for it are
  right, but a reader cannot tell pyarrow's from the old writer's, which compared every byte as
  signed. For a decimal's bytes after the first, that order is wrong.
- Never use a bound that is NaN.

Some readers go further, and ignore statistics from particular releases of particular writers,
which they recognise by the footer's `created_by` string. This reader does not.

### Floating point

Floats have two traps. NaN is not less than, equal to or greater than anything, so a writer
leaves it out of the bounds, and a reader looking for NaN cannot use them. And `-0` equals `+0`,
though their bytes differ. The format asks writers to store a zero minimum as `-0` and a zero
maximum as `+0`, and asks readers to remember that a chunk with either may hold both. The `-0`
the third step printed for `temp_c` in row group 1 is the first rule at work.

### What else the footer says

Beyond statistics, each row group records its row count and size, and may list the columns its
rows are sorted by. `sorting_columns` is a claim: a reader may rely on it and cannot check it
without reading every value. Each column chunk may also carry **size statistics**: the number of
bytes its strings take once decoded, and a histogram of its definition and repetition levels,
from which a reader can count nulls and list elements without reading a page. pyarrow's
metadata does not show them; the `parquet` crate's does, as `unencoded_byte_array_data_bytes`
and the level histograms.

All of it costs bytes, in a place every reader must fetch:

```{include} _generated/statistics-cost.md
```

In a small file the footer can outweigh the data. A table with hundreds of columns and many row
groups can have a footer of megabytes, and every query pays for reading and decoding it before it
reads anything else. [ch11](#writing-parquet-well) shows a footer growing with the number of row
groups.

## Building it

The steps read bounds out of the footer, compared bytes in two orders, and asked the reader which
bounds it may use. This section builds the two parts of the reader the last step called: the
comparator for a column, and the rules in `bounds`. The tabs switch every excerpt on the page
between the two languages.

### The comparator for a column

The order comes from the physical type and the annotation together:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/stats.py
:language: python
:start-at: def for_leaf(leaf: Leaf, converted: str | None)
:end-before: def order(self)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/stats.rs
:language: rust
:start-at: pub fn for_leaf(
:end-before: pub fn order(&self)
```
:::
::::

### The rules

`bounds` applies the rules in the order the chapter gives them, and says why when it refuses. It
refuses a type without an order first, then prefers `min_value` and `max_value`, which it uses
only when the footer names their order and neither is NaN:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/stats.py
:language: python
:start-at: def bounds(stats: Statistics
:end-before: if stats.min is not None and stats.max is not None:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/stats.rs
:language: rust
:start-at: pub fn bounds(
:end-before: if let (Some(min), Some(max)) = (&stats.min, &stats.max)
```
:::
::::

Without the newer fields, it falls back to the deprecated pair, but only for a column whose order
is signed and whose values are not byte arrays. This is the branch that refused `amount` when you
set `old_writer`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/stats.py
:language: python
:start-at: if stats.min is not None and stats.max is not None:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/stats.rs
:language: rust
:start-at: if let (Some(min), Some(max)) = (&stats.min, &stats.max)
:end-before: #[cfg(test)]
```
:::
::::

[ch03](#the-type-system)'s reader used `min` and `max` whenever `min_value` and `max_value` were
missing. That was the mistake this chapter describes, and the statistics decoder now keeps the
two pairs apart.

### Checking it

For every column chunk of every fixture, the reader decodes the values, finds their minimum and
maximum in its chosen order, and compares them with the bounds pyarrow wrote. They agree. The
statistics fixture also shows that each mistaken order gets at least one of its columns wrong:

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

pyarrow and the `parquet` crate both read the statistics for you. Ask each for row group 0:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/metadata_and_statistics/statistics_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/statistics_with_a_library.rs
:language: rust
```
:::
::::

pyarrow reads the bounds through the logical type. Its `min` and `max` give `customer_id`'s
maximum as the unsigned customer number, and `city`'s as a string. Its `min_raw` and `max_raw`
give the physical type's reading, where `customer_id`'s maximum is negative, as the first step's
signed reading was. It reports the footer's size, which is the footer bytes in the cost table,
and the row group's `sorting_columns`. It has no attribute for the exact flags, and none for the
column orders.

The crate reports each column's order from `column_orders`: `customer_id`'s is
`TYPE_DEFINED_ORDER(UNSIGNED)`. Yet its statistics for an `INT32` column hold an `i32`, and
`max_opt` returns `customer_id`'s maximum as a negative number. The crate hands you the first
step's mistake, and applying the column order is left to you. It also says every bound is exact,
and that none came from the deprecated fields, although pyarrow wrote those too: where both pairs
are present, the crate reads `min_value` and `max_value`.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin statistics_with_a_library
```

## What this cannot tell you

**Whether a query can skip a chunk.** The bounds say what a chunk may hold. Turning a query's
condition into a decision is [ch09](#skipping-data)'s subject, along with the finer statistics
kept for each page.

**What shortened bounds look like.** pyarrow wrote exact bounds for every value here. Writers
that shorten long strings mark the bound as inexact, and the reader reports the flag, but no
fixture exercises it.

**Which writers wrote wrong statistics.** The reader applies the format's rules. Files from old
writers can break those rules in ways only a list of writer versions can catch.

**How people sort text.** Byte order is not a collation. A query that compares strings the way a
language does cannot use these bounds directly.

## Key takeaways

:::{div}
:class: takeaways

- **Statistics are bytes, and an order makes them mean something.** The column's type sets the
  order: signed, unsigned, by value, or byte by byte.
- **A mistaken order is confidently wrong.** Unsigned integers, non-ASCII strings, negative
  decimals and floats each have one, and the fixture catches every one.
- **Use `min_value` and `max_value` when the footer gives their order.** Use the deprecated `min`
  and `max` only where signed comparison was right.
- **NaN never belongs in a bound, and `-0` equals `+0`.** A reader looking for NaN cannot use the
  bounds at all.
- **The footer is not free.** Every statistic is read by every query before any data.
:::

## Problems

Three, in `exercises/python/metadata_and_statistics.py`, or in Rust in
`exercises/src/metadata_and_statistics.rs`. The first two have tests. The third has
none.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: metadata_and_statistics
```

**8.1 Sort orders.** Compare two values of a column in its sort order, for six kinds of column.
The test finds each column chunk's minimum and maximum with your order and checks them against
the bounds pyarrow wrote.

**8.2 Which bounds.** Decide which bounds a reader may use. The test presents each chunk's
statistics as written, without `column_orders`, as an old writer would have set them, and with a
NaN.

**8.3 Your own footers.** No test: the files are yours. Run
`PYTHONPATH=python python3 -m parquet_lab statistics FILE 0 COLUMN` or
`cargo run -p pqlab -- statistics FILE 0 COLUMN` on a file your systems write, for a few
columns. Record which columns have statistics, whether the reader accepts them, and what share of
the file the footer takes. Then find one column where the statistics could not help a query you
run, and say why: no statistics, a range as wide as the column's, or a comparison the order does
not support. A good answer says what the writer could change.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_8_1` in Python, or `problem_8_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_metadata_and_statistics.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test metadata_and_statistics -- --ignored
```
:::
::::

## Where to go next

- The `Statistics` and `ColumnOrder` structures, and the rules for floating point, are documented
  in [`parquet.thrift`](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift).
- Each logical type's sort order is in
  [LogicalTypes.md](https://github.com/apache/parquet-format/blob/master/LogicalTypes.md).
- The history of the signed comparison of strings is in
  [PARQUET-686](https://issues.apache.org/jira/browse/PARQUET-686).
- [ch09](#skipping-data) uses these bounds, and the finer ones kept per page, to skip data.
