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

This chapter stores one small table both ways and counts what a query costs against each, then
finds the same idea in a Parquet file that pyarrow wrote. It is the one chapter with no code for
you to write. From the next chapter on, each one reads the bytes of a real file by hand, builds
what it read into a reader, and checks the result against a library you already use.

## The experiment

### One table, two layouts

The table is eight orders with five columns. Both layouts use the same encoding for every value:
an integer is eight bytes, a date is a four-byte day number, and a string is a four-byte length
followed by its bytes. The only difference is order. The row layout writes each order's five
values together. The column layout writes all eight `order_id` values, then all eight
`customer_id` values, and so on.

The panel stores each layout as an object in the book's simulated object store, turns your query
into the exact byte ranges it needs, and fetches them.

```lab
experiment: layouts
```

Try these:

1. **Keep the default query**, `country` and `amount_cents` for every row. In the row layout the
   lit bytes are scattered through the object, one run per order. In the column layout they form
   one block.
2. **Add columns one at a time.** In the row layout every order contributes at least one run of its
   own, so the count of separate ranges never falls below the number of orders until you pick
   every column: then the whole object is one run. The column layout stays at one range for as long as the columns you
   pick are adjacent, and gains a range for each gap.
3. **Switch to one order.** Now the row layout needs one range and the column layout needs one per
   column. This is the trade Parquet makes, and the reason it is not a database format.
4. **Raise the latency.** Fetching range by range gets expensive fast. Fetching the whole object
   costs one request, but moves bytes the query did not need.

### What each query costs

The same experiment, run by the build for three queries:

```{include} _generated/layouts-costs.md
```

Two facts come out of the table, and the rest of the book depends on both.

**A scan of a few columns needs few ranges in a column layout.** However many rows there are, a
column is one contiguous run. The query reads exactly the bytes it needs in one request per
column, or fewer when the columns sit side by side. In the row layout the same bytes are spread
across every row. A reader must either issue one request per row or fetch the whole object and
discard most of it.

**A lookup of one whole row needs few ranges in a row layout.** The column layout has to visit
every column to reassemble one order. Reading a row back out of columns is called
*reconstructing* it, and its cost grows with the number of columns.

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
shown the first:

- **Projection.** A reader fetches only the columns a query names.
- **Compression.** A column holds values of one type that often repeat or change slowly: the
  `country` column above repeats a few codes. Similar values side by side encode and compress far
  better than interleaved rows ([ch05](#encodings), [ch07](#compression)).
- **Vectorised processing.** A processor is fastest running one operation over a run of values of
  one type. A column is already that run.

The cost is the third query in the table. Fetching one row means visiting every column, and
changing one value means rewriting encoded, compressed blocks. Parquet accepts that: it is a
format for data written once and read many times.

The panel and the table are computed by the book's reader, in its `layout` module
(`python/parquet_lab/layout.py`, or `crates/parquet-lab/src/layout.rs`). The book does not walk
through that module, because it is not Parquet. The rest of the reader is.

### The same table as a Parquet file

If you have written a Parquet file, you have written a column layout. The book's fixtures are
written by pyarrow, as the files of many pipelines are, and one of them holds these eight orders:

```{literalinclude} ../fixtures/generate.py
:language: python
:start-at: EIGHT_ORDERS = pa.table(
:end-before: EIGHT_ORDERS = EIGHT_ORDERS.cast(
```

`pyarrow.parquet.write_table` stores it with the options every fixture starts from: no
compression and no dictionary, which keep a file small enough to read byte by byte. The book's
reader finds these regions in the result:

```{include} _generated/eight-orders-regions.md
```

Each column is one contiguous chunk, in the schema's order: the column layout from the panel, with
a header before it and a footer after it. The two columns of the default query, `country` and
`amount_cents`, sit side by side, so one range covers both. Parquet adds the rest of its
structure around that layout. It splits a table into row groups, so that a writer never holds a
whole table in memory. It keeps types, encodings and the position of every chunk in the footer. It
compresses each column separately. In a file this small the footer is the largest region, and a
reader must read it before it can find anything else.

[ch02](#anatomy-of-a-parquet-file) opens this kind of file from its last byte and finds each
region for itself: first by hand, in a few lines of Python or Rust, then with the book's reader,
then with pyarrow.

## What this cannot tell you

**How real data compresses.** Both layouts here are the same size, because the experiment uses
the same fixed encoding for both. Real columnar files are usually much smaller than the row data
they came from, and [ch05](#encodings) and [ch07](#compression) show why. This chapter measures
only which bytes a query touches.

**What your storage charges.** The simulated store charges a fixed latency per request. A local
disk, an object store and a memory cache have very different request costs, and the best strategy
changes with them. The shape of the result does not: a column layout turns a scan into a few large
reads.

**How queries on real tables behave.** Eight orders make the layouts visible, not realistic. The
row layout's range count grows with the number of rows; the column layout's grows with the
number of columns. That difference is what the table shows, and it holds at any size.

## Key takeaways

:::{div}
:class: takeaways

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
