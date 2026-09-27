---
title: Nested data
---

(nested-data)=
# Nested data

## The question

How can nested, nullable records live in flat columns without losing their shape?

[ch03](#the-type-system) rebuilt the schema tree and gave every leaf two numbers: a maximum
definition level and a maximum repetition level. Every column of `tiny.parquet` had zero for
both, and its pages held values and nothing else. This chapter reads a file whose columns do not.

A column stores a flat sequence of values. A record can hold a null, a list, an empty list, or a
list of structs that each hold a list. Store only the values and the shape is gone: nothing says
which record a value belongs to, where one list ends and the next begins, or whether a missing
value was null, in an empty list, or under a null parent. Parquet keeps the shape in two small
integers stored beside every value, a method it takes from Google's Dremel paper.

## The experiment

### Four orders, every way of being missing

`nested.parquet` holds four orders. Each has an optional `email`, an optional list of `tags`, and
an optional list of `items`, where each item has a `sku` and its own list of `discounts`. Between
them the orders contain a null string, a null list, an empty list, a list holding a null, and a
list inside a list. [Appendix B](#the-fixtures) says how pyarrow wrote it.

Each step below is a few lines of code. In Python, run them in the page, change them with
**Edit**, and run them again. In Rust, open them in a Codespace, or run one at a desk with
`cargo run -p walkthroughs --bin` and its name. Each step finds the footer as
[ch02](#anatomy-of-a-parquet-file) did and rebuilds the schema as [ch03](#the-type-system) did.

**The levels as stored.** A column chunk is a run of pages, each a header and a body.
[ch06](#pages) reads pages in full; here the reader's `walk_pages` finds the one page of
`items[].discounts[]`, the discounts of every item of every order. Unpack the start of its body
by hand:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/nested_data/unpack_the_levels.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/unpack_the_levels.rs
:language: rust
```
:::
::::

The body opens with two streams of small integers, one line each. The first holds the
*repetition levels*, the second the *definition levels*, and the values come after both. pyarrow
wrote a version-1 data page, so each stream starts with its length in four bytes. Then comes a
header byte, which says how the levels are packed, and the levels themselves. Each takes as few
bits as the column's maximum needs. The step takes the maximums from the schema, as
[ch03](#the-type-system) counted them: 2 for repetition and 6 for definition, so two bits and
three.

Count the levels in each stream: one per *slot*. There are more slots than orders, and more than
discounts. The levels say which slot starts a record, which holds a discount, and which holds
nothing.

Change `column` to 2, which is `tags[]`, and its levels need fewer bits. Change it to 1, which is
`email`: nothing on its path repeats, so the page stores no repetition levels at all.

**The levels, read by the reader.** The book's reader decodes the same streams, pairs each slot's
two levels with its value, and rebuilds the records from them. Ask it for `tags`:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/nested_data/levels_of_a_column.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/levels_of_a_column.rs
:language: rust
```
:::
::::

One row per slot: its repetition level `r`, its definition level `d`, and its value. The reader
calls each row a *triple*. Only a triple whose `d` is the column's maximum has a value.

The first two rows are the first order's two tags, and the `r` of 1 on the second says it
continues the same list. The next two rows have no value, and each is still a whole record: an
empty list and a null list. Without their slots, the reader would not know those records
existed. The last row is a null inside a list, one level below the maximum. The records at the
end are rebuilt from these rows alone.

Change `name` to `"email"`, `"order_id"` or `"items"`, and watch the maximum levels set what a
row can say. `items` has two columns, and each rebuilds its own view of the same records.

### What the levels say

The file's schema, as [ch03](#the-type-system) rebuilt it:

```{include} _generated/nested-schema-text.md
```

A list is three levels of schema, not one. An optional group annotated `LIST` can be null. Inside
it, a repeated group called `list` makes the repetition. Inside that, an optional `element` can be
null. That shape is what lets a file tell a null list from an empty list from a list holding a
null. The book writes these columns the way a reader of the data would, `tags[]` rather than
`tags.list.element`:

```{include} _generated/nested-columns.md
```

**The definition level** `d` counts how many optional or repeated fields on the path are present
for this slot. At the maximum, the value is there. Below it, the first missing field is the one
whose definition level is `d + 1`. For `tags[]`, as the second step printed:

- `d = 0`: `tags` itself is absent. The list is null.
- `d = 1`: `tags` is present, but its repeated `list` group has no entries. The list is empty.
- `d = 2`: an entry exists, but its `element` is absent. The element is null.
- `d = 3`: the value is present.

**The repetition level** `r` says where the slot sits in the nesting. Zero starts a new record.
Any other value names the repeated field that gains a new element: here, `r = 1` adds an element
to `tags`.

`email` is the simplest case. One optional field is on its path, so its maximum definition level
is 1: a `d` of 0 is a null and a `d` of 1 is a value. No field on the path is repeated, so the
page stores no repetition levels, as the first step found, and the reader takes every `r` as
zero.

### Two lists deep

Every item has its own list of discounts, so `items[].discounts[]` has two repeated fields on its
path and a maximum repetition level of 2. Now `r` has three meanings: 0 is a new record, 1 is a
new item, and 2 is another discount in the same item. These are the levels the first step
unpacked, with what the reader makes of each:

```{include} _generated/nested-levels-discounts.md
```

Read the third row. Its `r` of 1 says a new item has started. Its `d` of 4 says the item exists
and has a `discounts` list, but that list has no entries. That is item `B2`, whose discounts are
empty, and the reader can tell it from a record with no items at all, which is the next row.

### How the levels are stored

Levels are small integers with a known maximum, so a writer stores them in as few bits as that
maximum needs, using the RLE / bit-packing hybrid. The stream is a sequence of runs, and each
starts with a ULEB128 header whose lowest bit gives the run's kind:

- **Lowest bit 0: an RLE run.** The rest of the header is a count, and one value follows. A column
  with no nulls has definition levels that are all the maximum, and a whole page of them is one
  run of a couple of bytes.
- **Lowest bit 1: a bit-packed run.** The rest of the header is a number of groups of eight
  values, each packed into the bit width, least significant bit first.

The discount column's levels are short and varied, so the writer bit-packed both streams. The
header `03` that the first step printed is binary `11`: bit-packed, one group of eight. The
repetition levels need two bits each, so eight of them take two bytes; the definition levels need
three bits each and take three. With the header byte, those are the stream lengths the step
printed. The page has six slots, so the last two values in each group are padding.

## Building it

The steps called three parts of the book's reader: the decoder of the level streams, the split
of a page's body into levels and values, and the rebuild of records. This section builds them,
in both languages, and the tabs switch every excerpt on the page between them.

### Decoding the hybrid

The decoder reads a header and decides the run's kind from its low bit. Every run keeps the span
of its header and its body, so a caller can say which bytes held which levels. An RLE run is one
value, stored in as many whole bytes as the bit width needs:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/rle.py
:language: python
:start-at: def decode(data: bytes, base: int, width: int, count: int)
:end-before: else:
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/rle.rs
:language: rust
:start-at: pub fn decode(
:end-before: } else {
```
:::
::::

A bit-packed run is the header's count of groups, each eight values of the bit width. The last
group of a stream can run past the count of values, as it did in the first step, and the padding
is dropped:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/rle.py
:language: python
:start-at: # Bit-packed: groups of eight values
:end-before: def unpack(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/rle.rs
:language: rust
:start-at: // Bit-packed: groups of eight values
:end-before: /// The `i`th value
```
:::
::::

Bit-packed values are read one bit at a time, least significant first, which makes the packing
order explicit:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/rle.py
:language: python
:start-at: def unpack(raw: bytes, i: int, width: int)
:end-before: def values(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/rle.rs
:language: rust
:start-at: fn unpack(raw: &[u8], i: usize, bit_width: u32)
:end-before: /// All the values of a sequence of runs
```
:::
::::

### Splitting a page into levels and values

A data page body holds the repetition levels, then the definition levels, then the values. A
level stream is present only when the column's maximum for it is above zero. In a version-1 data
page each stream starts with a four-byte length. The second version of the data page, which
[ch06](#pages) reads, gives both lengths in its header instead, so its streams have no prefix:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/column.py
:language: python
:start-at: rep_levels = (
:end-before: present = sum(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: let rep_levels = if leaf.max_repetition_level > 0 {
:end-before: let present = defs
```
:::
::::

Only slots whose definition level is the maximum have a value, so the reader counts those, and
decodes that many PLAIN values after the levels (the `plain` module).

### Rebuilding records

The reader turns triples back into records by splitting them. Records split where `r` is 0.
Within a record, a repeated field's triples split into elements wherever `r` is at most that
field's repetition level, and a field whose first triple has too low a `d` is null or, for a
repeated field, empty:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/nested.py
:language: python
:start-at: def field_value(i: int, ts: list[Triple])
:end-before: def element_value(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/nested.rs
:language: rust
:start-at: fn field_value(&self, i: usize, triples: &[Triple])
:end-before: /// One present instance
```
:::
::::

### Checking it

The fixture tests read every column of every fixture from its page bytes, rebuild the records,
and compare them with the rows pyarrow reported when it wrote the file, reduced to that one
column:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest python/tests -k records_rebuilt
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p parquet-lab --test fixtures records_rebuilt
```
:::
::::

### Ask a library

pyarrow reads the levels and does not show them. It turns them into Arrow's shape for a list: an
array of *offsets*, where list `i` runs from `offsets[i]` to `offsets[i + 1]` in one array of
values, and a *validity bitmap* saying which lists are null. The `parquet` crate's column reader
works below Arrow, and hands you the levels as the page stores them:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/nested_data/levels_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/levels_with_a_library.rs
:language: rust
```
:::
::::

The two describe the same four records of `tags`. In pyarrow's offsets, the empty list and the
null list both have length zero, and only the validity bitmap tells them apart: the job a
definition level of 1 or 0 did in the file. A null element is a null in the values array, where
the file stored no value at all. The crate prints the repetition and definition levels the
reader decoded in the second step. Its values hold only the present strings, and it counts
records where the repetition level is zero.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin levels_with_a_library
```

## What this cannot tell you

**How several columns become one record.** The reader rebuilds each column's view of a record on
its own. A query engine that wants whole records runs the same splitting over several columns at
once, in step. [ch12](#a-tiny-query-engine) does that for the columns a query needs.

**How pages divide a record.** Each fixture column is one page. When a column spans pages, a
record can begin in one and continue in the next under data page version 1. A version-2 data page always
starts a new record, which [ch06](#pages) shows.

**How other formats keep the shape.** Apache Arrow, in memory, stores offsets and validity bitmaps
per nesting level instead of levels, as pyarrow showed for one list. Converting between the two
is much of a Parquet reader's work in practice; this reader produces JSON instead.

**Legacy list layouts.** Older writers produced two-level lists and other shapes. The
specification's backward-compatibility rules say how to read them; this reader follows the
standard three-level form only.

## Key takeaways

:::{div}
:class: takeaways

- **Two small integers keep the shape of nested data.** A definition level says how far down the
  path a value is defined; a repetition level says where it sits in the lists.
- **A null, an empty list and a null element are different definition levels.** Each takes a slot
  and stores no value.
- **A repetition level names the list that gains an element.** Zero starts a new record.
- **A required path stores no levels.** Flat, non-null columns pay nothing for Parquet's nesting.
- **Levels are stored in as few bits as their maximum needs,** as runs of repeats or bit-packed
  groups, so a column with no nulls pays a few bytes per page.
- **A library hides the levels or hands them over.** pyarrow turns them into Arrow's offsets and
  validity bitmaps; the `parquet` crate's column reader returns them as stored.
:::

## Problems

Three, in `exercises/python/nested_data.py`, or in Rust in
`exercises/src/nested_data.rs`. The first two have tests. The third has none.

**4.1 The hybrid.** Decode an RLE / bit-packing hybrid stream. The test uses every level stream in
the fixture and a thousand generated streams.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_nested_data.py --problems -k problem_4_1
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test nested_data problem_4_1 -- --ignored
```
:::
::::

**4.2 A list from its levels.** Rebuild a list of optional strings from its levels and values. The
test compares with pyarrow on the fixture and with the reader on generated levels.

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_nested_data.py --problems -k problem_4_2
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test nested_data problem_4_2 -- --ignored
```
:::
::::

**4.3 Your own nested data.** No test: the data is yours. Take a nested column from your own
Parquet files and run `PYTHONPATH=python python3 -m parquet_lab levels FILE COLUMN` or
`cargo run -p pqlab -- levels FILE COLUMN`, where `COLUMN` is its position
among the leaves. Pick three records and write down, before looking, the levels you expect for
each value slot. Then compare. A good answer explains every disagreement. If your records never
reach the column's maximum repetition level, say what the schema allows that the data never uses.

```problems
chapter: nested_data
```

## Where to go next

- The levels come from Melnik and others'
  [Dremel paper](https://research.google/pubs/dremel-interactive-analysis-of-web-scale-datasets-2/),
  section 4.
- The standard `LIST` and `MAP` layouts, and the backward-compatibility rules for older ones, are
  in the format repository's
  [LogicalTypes.md](https://github.com/apache/parquet-format/blob/master/LogicalTypes.md#nested-types).
- The hybrid encoding is specified in
  [Encodings.md](https://github.com/apache/parquet-format/blob/master/Encodings.md).
- [ch05](#encodings) uses the same hybrid for dictionary indices, and adds the encodings for values.
