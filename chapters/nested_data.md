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
list inside a list.

```lab
experiment: levels
fixture: nested.parquet
column: 2
```

The panel reads one column at a time, from its page bytes, and shows three things: the fields on
the column's path with the levels at which each appears, the levels as the page stores them, and
one row per value slot. Try these:

1. **Start with `tags[]`.** Read the triples top to bottom beside the records they rebuild. Each
   row's meaning is the reader's own reading of its two levels.
2. **Switch to `email`.** Its path has one optional field, so its maximum definition level is 1
   and it has no repetition levels at all. A null is a `d` of 0 and no value.
3. **Switch to `order_id`.** Required all the way down: no levels are stored, and the page body
   is values only.
4. **Switch to `items[].discounts[]`.** Two lists deep. Find the triple with `r` of 2: a new
   discount in the same item. Find the one with `r` of 1: a new item.
5. **Click a run's header** in the levels panel. The byte view marks one byte, and the inspector
   shows its low bit: 1 for a bit-packed run, 0 for a run of repeats.

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
whose definition level is `d + 1`. For `tags[]`:

- `d = 0`: `tags` itself is absent. The list is null.
- `d = 1`: `tags` is present, but its repeated `list` group has no entries. The list is empty.
- `d = 2`: an entry exists, but its `element` is absent. The element is null.
- `d = 3`: the value is present.

**The repetition level** `r` says where the slot sits in the nesting. Zero starts a new record.
Any other value names the repeated field that gains a new element: here, `r = 1` adds an element
to `tags`.

These are the four orders' `tags`, read from the page:

```{include} _generated/nested-levels-tags.md
```

A null list and an empty list store no value, but each still takes a slot. Without it, the
reader would not know those records existed.

### Two lists deep

Every item has its own list of discounts, so `items[].discounts[]` has two repeated fields on its
path and a maximum repetition level of 2. Now `r` has three meanings: 0 is a new record, 1 is a
new item, and 2 is another discount in the same item:

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

The discount column's levels are short and varied, so the writer bit-packed both streams:

```{include} _generated/nested-runs-discounts.md
```

The header `03` is binary `11`: bit-packed, one group of eight. The repetition levels need two
bits each, so eight of them take two bytes; the definition levels need three bits each and take
three. The last two values in each group are padding, because the page has six slots.

## Building it

### Decoding the hybrid

The decoder reads a header, decides the run's kind from its low bit, and takes the run's bytes.
Every run keeps the span of its header and its body, which is how the panel highlights them:

```{literalinclude} ../crates/parquet-lab/src/rle.rs
:language: rust
:start-at: pub fn decode(
:end-before: /// The `i`th value
```

Bit-packed values are read one bit at a time, least significant first, which makes the packing
order explicit:

```{literalinclude} ../crates/parquet-lab/src/rle.rs
:language: rust
:start-at: fn unpack(raw: &[u8], i: usize, bit_width: u32)
:end-before: /// All the values of a sequence of runs
```

### Splitting a page into levels and values

A data page body holds the repetition levels, then the definition levels, then the values. Each
level stream starts with a four-byte length, and is present only when the column's maximum for
it is above zero:

```{literalinclude} ../crates/parquet-lab/src/column.rs
:language: rust
:start-at: let rep_levels = if leaf.max_repetition_level > 0 {
:end-before: let present = defs
```

Only slots whose definition level is the maximum have a value, so the reader counts those, and
decodes that many PLAIN values after the levels (`crates/parquet-lab/src/plain.rs`).

### Rebuilding records

The reader turns triples back into records by splitting them. Records split where `r` is 0.
Within a record, a repeated field's triples split into elements wherever `r` is at most that
field's repetition level, and a field whose first triple has too low a `d` is null or, for a
repeated field, empty:

```{literalinclude} ../crates/parquet-lab/src/nested.rs
:language: rust
:start-at: fn field_value(&self, i: usize, triples: &[Triple])
:end-before: /// One present instance
```

### Checking it

The fixture tests read every column of every fixture from its page bytes, rebuild the records,
and compare them with the rows pyarrow reported when it wrote the file, reduced to that one
column:

```bash
cargo test -p parquet-lab --test fixtures records_rebuilt
```

## What this cannot tell you

**How several columns become one record.** The reader rebuilds each column's view of a record on
its own. A query engine that wants whole records runs the same splitting over several columns at
once, in step. [ch12](#a-tiny-query-engine) does that for the columns a query needs.

**How pages divide a record.** Each fixture column is one page. When a column spans pages, a
record can begin in one and continue in the next under data page version 1. A version-2 data page always
starts a new record, which [ch06](#pages) shows.

**How other formats keep the shape.** Apache Arrow, in memory, stores offsets and validity bitmaps
per nesting level instead of levels. Converting between the two is much of a Parquet reader's
work in practice; this reader produces JSON instead.

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
:::

## Problems

Three, in `exercises/src/nested_data.rs`. The first two have tests. The third has none.

**4.1 The hybrid.** Decode an RLE / bit-packing hybrid stream. The test uses every level stream in
the fixture and a thousand generated streams.

```bash
cargo test -p exercises --test nested_data problem_4_1 -- --ignored
```

**4.2 A list from its levels.** Rebuild a list of optional strings from its levels and values. The
test compares with pyarrow on the fixture and with the reader on generated levels.

```bash
cargo test -p exercises --test nested_data problem_4_2 -- --ignored
```

**4.3 Your own nested data.** No test: the data is yours. Take a nested column from your own
Parquet files and run `cargo run -p pqlab -- levels FILE COLUMN`, where `COLUMN` is its position
among the leaves. Pick three records and write down, before looking, the levels you expect for
each value slot. Then compare. A good answer explains every disagreement. If your records never
reach the column's maximum repetition level, say what the schema allows that the data never uses.

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
