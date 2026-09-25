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

### Twelve orders in three row groups

`statistics.parquet` holds twelve orders, four to a row group. Each column was chosen for a way
statistics are misread. [Appendix B](#the-fixtures) says how it was written.

```lab
experiment: statistics
fixture: statistics.parquet
fixtures: statistics.parquet, types.parquet, multiple-row-groups.parquet
column: 0
```

The top table is every column chunk's minimum and maximum, as the reader decided it may use
them. Pick a cell to see the chunk's statistics field by field, and its values in the column's
order. Try these:

1. **`order_id`, row group by row group.** The ranges do not overlap, because the rows were
   written in order, and the footer says so. A reader looking for one order reads one row group.
2. **`customer_id`, row group 0.** The maximum is a customer number above `2^31`, stored in
   four bytes as an `INT32`. Read those bytes as a signed integer and it is negative.
3. **`city`, row group 0.** The maximum is `Łódź`, whose first byte is above `0x7f`. Compare
   bytes as signed numbers, as Java does, and it becomes the minimum.
4. **`temp_c`, row groups 0 and 1.** One value is NaN, and the bounds leave it out. In row
   group 1 the minimum is written as `-0`.
5. **`coupon`, row group 1.** Every value is null. There is no minimum, and the null count says
   why.
6. **`note`.** The writer was told not to keep statistics for it. The reader has nothing to use.

### What the footer records

This is which fields of the `Statistics` structure the writer set for each column of the first row
group:

```{include} _generated/statistics-fields.md
```

- **`min_value` and `max_value`** are the bounds in the column's own sort order.
- **`min` and `max`** are older fields with the same purpose. They are deprecated, and pyarrow
  writes them only where their old order happens to be right, as the table shows.
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

The order of strings is the order of their bytes in UTF-8. It is not alphabetical order for a
person: `Århus` sorts after `Zürich`, because `Å` is written with a byte above every ASCII
letter's.

These are the ranges the reader accepts, for every row group:

```{include} _generated/statistics-grid.md
```

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
  byte arrays.
- Never use a bound that is NaN.

Some readers go further, and ignore statistics from particular releases of particular writers,
which they recognise by the footer's `created_by` string. This reader does not.

### Floating point

Floats have two traps. NaN is not less than, equal to or greater than anything, so a writer
leaves it out of the bounds, and a reader looking for NaN cannot use them. And `-0` equals `+0`,
though their bytes differ. The format asks writers to store a zero minimum as `-0` and a zero
maximum as `+0`, and asks readers to remember that a chunk with either may hold both. Row group 1
of `temp_c` shows the first rule.

### What else the footer says

Beyond statistics, each row group records its row count and size, and may list the columns its
rows are sorted by. `sorting_columns` is a claim: a reader may rely on it and cannot check it
without reading every value. Each column chunk may also carry **size statistics**: the number of
bytes its strings take once decoded, and a histogram of its definition and repetition levels,
from which a reader can count nulls and list elements without reading a page. Open the structure
view below the panel to see them.

All of it costs bytes, in a place every reader must fetch:

```{include} _generated/statistics-cost.md
```

In a small file the footer can outweigh the data. A table with hundreds of columns and many row
groups can have a footer of megabytes, and every query pays for reading and decoding it before it
reads anything else. [ch10](#how-readers-read) measures that.

## Building it

### The comparator for a column

The order comes from the physical type and the annotation together:

```{literalinclude} ../crates/parquet-lab/src/stats.rs
:language: rust
:start-at: pub fn for_leaf(
:end-before: pub fn order(&self)
```

### The rules

`bounds` applies the rules in the order the chapter gives them, and says why when it refuses:

```{literalinclude} ../crates/parquet-lab/src/stats.rs
:language: rust
:start-at: pub fn bounds(
:end-before: #[cfg(test)]
```

[ch03](#the-type-system)'s reader used `min` and `max` whenever `min_value` and `max_value` were
missing. That was the mistake this chapter describes, and the statistics decoder now keeps the
two pairs apart.

### Checking it

For every column chunk of every fixture, the reader decodes the values, finds their minimum and
maximum in its chosen order, and compares them with the bounds pyarrow wrote. They agree. The
statistics fixture also shows that each mistaken order gets at least one of its columns wrong:

```bash
cargo test -p parquet-lab --test fixtures
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

Three, in `exercises/src/metadata_and_statistics.rs`. The first two have tests. The third has
none.

**8.1 Sort orders.** Compare two values of a column in its sort order, for six kinds of column.
The test finds each column chunk's minimum and maximum with your order and checks them against
the bounds pyarrow wrote.

```bash
cargo test -p exercises --test metadata_and_statistics problem_8_1 -- --ignored
```

**8.2 Which bounds.** Decide which bounds a reader may use. The test presents each chunk's
statistics as written, without `column_orders`, as an old writer would have set them, and with a
NaN.

```bash
cargo test -p exercises --test metadata_and_statistics problem_8_2 -- --ignored
```

**8.3 Your own footers.** No test: the files are yours. Run
`cargo run -p pqlab -- statistics FILE 0 COLUMN` on a file your systems write, for a few
columns. Record which columns have statistics, whether the reader accepts them, and what share of
the file the footer takes. Then find one column where the statistics could not help a query you
run, and say why: no statistics, a range as wide as the column's, or a comparison the order does
not support. A good answer says what the writer could change.

## Where to go next

- The `Statistics` and `ColumnOrder` structures, and the rules for floating point, are documented
  in [`parquet.thrift`](https://github.com/apache/parquet-format/blob/master/src/main/thrift/parquet.thrift).
- Each logical type's sort order is in
  [LogicalTypes.md](https://github.com/apache/parquet-format/blob/master/LogicalTypes.md).
- The history of the signed comparison of strings is in
  [PARQUET-686](https://issues.apache.org/jira/browse/PARQUET-686).
- [ch09](#skipping-data) uses these bounds, and the finer ones kept per page, to skip data.
