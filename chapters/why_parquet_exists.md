---
title: Why Parquet exists
---

(why-parquet-exists)=
# Why Parquet exists

## The question

Why store a table one column at a time, when every program thinks in rows?

An application writes a record, reads a record, updates a record. A CSV file, a JSON Lines file
and the pages of most transactional databases all keep each row's values together, because that
is the unit those programs work in. Analytical queries work differently. They read a few columns
of a great many rows, and a layout built for whole rows makes them read everything.

This chapter measures that on two files you could have written yourself: the same table of
orders as a CSV file and as a Parquet file. Then it shows why the numbers come out as they do. It
is the one chapter with no code for you to write. From the next chapter on, each one reads the
bytes of a real file by hand, builds what it read into a reader, and checks the result against a
library you already use.

## The experiment

### Two columns from a CSV file

`fixtures/formats/` holds a table of orders twice, both written by pyarrow with its default
settings, as a pipeline's `write_csv` and `write_table` write them. A query wants two of its
columns, `country` and `amount_cents`: the total spent in each country. First the CSV file, read
the way programs read CSV, a row at a time, through a file that counts the bytes it hands over:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/why_parquet_exists/read_a_csv.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/read_a_csv.rs
:language: rust
```
:::
::::

It read every byte of the file. Each line holds all six columns, and there is no way to reach the
next line without reading past the fields you do not want, since nothing says where it starts.

### The same two columns from Parquet

Now the Parquet file, read with a library, through the same kind of counting file:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/why_parquet_exists/columns_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/columns_with_a_library.rs
:language: rust
```
:::
::::

The same answer, from a fraction of the file. In Python the first run loads pyarrow into the
page, which takes a while; in Rust the step needs the `parquet` crate, so it runs in a Codespace
or at a desk. The two libraries read different amounts. The Rust crate reads the file's last
bytes, then its footer, then the two columns and nothing else. pyarrow reads a large piece of the
file's end in its first request, which usually holds the footer and saves a round trip, at the
price of bytes the query did not need. [ch10](#how-readers-read) weighs that trade.

The least any Parquet reader can read, worked out by the book's reader from each file's footer,
beside what a CSV reader reads:

```{include} _generated/csv-or-parquet.md
```

For the larger table, a Parquet reader needs a small part of what a CSV reader reads. For the
eight orders it needs more than the whole CSV file, because the footer alone is bigger than the
data: Parquet pays a fixed cost for every file, and wins only when a file holds enough rows to
repay it. [ch15](#changing-a-table) comes back to that cost, when a table is made of many small
files.

### One table, two layouts

Why the difference? The panel stores the eight orders both ways in the plainest encoding there
is: an integer is eight bytes, a date is a four-byte day number, and a string is a four-byte
length followed by its bytes. The only difference is order. The row layout writes each order's
values together, as a CSV file does. The column layout writes all eight `order_id` values, then
all eight `customer_id` values, and so on, as a Parquet file does within each row group.

```lab
experiment: layouts
```

Try these:

1. **Keep the default query**, `country` and `amount_cents` for every row. In the row layout the
   lit bytes are scattered through the object, one run per order. In the column layout they form
   one block.
2. **Add columns one at a time.** The row layout needs a range per order until you pick every
   column. The column layout needs one range for each run of adjacent columns you pick.
3. **Switch to one order.** Now the row layout needs one range and the column layout needs one per
   column. Reading a row back out of columns is called *reconstructing* it, and its cost grows
   with the number of columns. This is the trade Parquet makes, and the reason it is not a
   database format.
4. **Raise the latency.** Fetching range by range gets expensive fast. Fetching the whole object
   costs one request, but moves bytes the query did not need.

The panel is computed by the book's reader, in its `layout` module
(`python/parquet_lab/layout.py`, or `crates/parquet-lab/src/layout.rs`). The book does not walk
through that module, because it is not Parquet. The rest of the reader is.

### Why analytical queries favour columns

An analytical query looks like this:

```sql
SELECT country, SUM(amount_cents)
FROM sales
WHERE order_date >= '2026-01-04'
GROUP BY country
```

It touches three columns out of five and every row. Real tables have hundreds of columns, and a
query typically touches a handful. Three things follow from a column layout, and this chapter has
measured the first:

- **Projection.** A reader fetches only the columns a query names.
- **Compression.** A column holds values of one type that often repeat or change slowly: the
  `country` column above repeats a few codes. Similar values side by side encode and compress far
  better than interleaved rows ([ch05](#encodings), [ch07](#compression)).
- **Vectorised processing.** A processor is fastest running one operation over a run of values of
  one type. A column is already that run.

The cost is the lookup of one order. Fetching one row means visiting every column, and changing
one value means rewriting encoded, compressed blocks. Parquet accepts that: it is a format for
data written once and read many times.

Parquet adds the rest of its structure around the column layout. It splits a table into row
groups, so that a writer never holds a whole table in memory. It keeps types, encodings and the
position of every column chunk in the footer, which is why both libraries read the footer before
anything else. [ch02](#anatomy-of-a-parquet-file) opens a file from its last byte and finds the
footer for itself: first by hand, in a few lines of Python or Rust, then with the book's reader,
then with pyarrow.

## What this cannot tell you

**How the files compress.** The Parquet file is smaller than the CSV file, as well as cheaper to
read from, because pyarrow encoded and compressed each column on its own. The panel uses no
compression, so its two layouts are the same size. [ch05](#encodings) and [ch07](#compression)
show what a column's encoding and compression do.

**Other CSV readers.** Some readers split a CSV file among workers, or skip the fields a query
does not name while they parse. Each still reads every byte, because only reading a line finds
where the next one begins.

**What your storage charges.** The counting files read from a local disk, and the panel's store
charges a fixed latency per request. A local disk, an object store and a memory cache have very
different request costs, and the best way to fetch changes with them. The shape of the result
does not: a column layout turns a scan into a few large reads.

## Key takeaways

:::{div}
:class: takeaways

- **A CSV reader reads every byte, whatever columns you want.** Each line holds every column, so
  reaching the next row means reading past the ones you do not need.
- **A Parquet reader reads the footer and the columns it wants.** On a table of any size that is
  a fraction of the file; on a tiny table the footer costs more than the data.
- **A layout decides which bytes are next to each other.** Row and column layouts can hold
  identical bytes in a different order.
- **A column scan is one range in a column layout and one range per row in a row layout.** That
  is the whole of projection's advantage, and it grows with the table.
- **A whole-row lookup is the reverse.** Columns must be visited one by one to reconstruct a row.
- **Parquet is built for analytical reads.** It trades cheap row access and in-place updates for
  cheap scans of a few columns.
:::

## Problems

Two, both for reasoning. No test grades them: there is no code to write until the next chapter.

**1.1 A wider table.** No test. Imagine the sales table with hundreds of columns and millions of
rows, and a query that reads three of its columns for every row. For each layout, say how many
separate ranges the query needs, and how the bytes it moves compare with the size of the table,
both when it fetches range by range and when it fetches the whole object. Check the shape of
your answer against the panel by picking columns. A good answer says that the row layout needs a
range per row, or else the whole object, while the column layout needs at most one range per
column. It also says that the column layout moves about three columns' worth of bytes, however
many rows there are.

**1.2 Your own queries.** No test: the workload is yours. Take a table you query often and list the
five most frequent queries against it. For each, write down how many of the table's columns it
reads and what fraction of the rows. A good answer sorts the queries into scans and lookups and
says which layout suits the mix. If most of them are lookups of whole rows, a columnar format is
the wrong tool for that table, and the answer should say so.

## Where to go next

- The column-store idea predates Parquet by decades. Stonebraker and others' 2005 paper
  [C-Store: A Column-oriented DBMS](https://www.vldb.org/archives/website/2005/program/paper/thu/p553-stonebraker.pdf)
  is a clear statement of the case.
- Parquet's handling of nested data comes from Google's
  [Dremel paper](https://research.google/pubs/dremel-interactive-analysis-of-web-scale-datasets-2/),
  which [ch04](#nested-data) builds from.
- [ch02](#anatomy-of-a-parquet-file) opens a real Parquet file.
