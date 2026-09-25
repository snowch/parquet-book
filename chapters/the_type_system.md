---
title: The type system
---

(the-type-system)=
# The type system

## The question

How do a handful of storage types carry strings, dates, decimals and timestamps?

[ch02](#anatomy-of-a-parquet-file) found the footer and decoded it into numbered fields. One of
those fields is the schema: the names and types of the columns. This chapter reads it. It
answers two questions a reader must settle before it can decode a single value: which columns
the file has, and what the bytes of each column mean.

The answer to the second is in two layers. A small set of **physical types** says how many bytes
a value takes and in what order. A **logical type**, written beside the physical type in the
schema, says what those bytes mean to a person. The same four bytes can be a count, a day, or an
unsigned number, and only the schema says which.

## The experiment

### The schema, stored and rebuilt

The panel runs the reader on `types.parquet`: three orders, with a column for each physical type
and the common logical types on top of them. [Appendix B](#the-fixtures) lists how pyarrow wrote
it.

```lab
experiment: schema
fixture: types.parquet
fixtures: types.parquet, tiny.parquet, multiple-row-groups.parquet
```

Try these:

1. **Click `shipping` in the flat list.** Its bytes light up in the footer. It has a number of
   children and no type: it is a group. The elements after it in the list are its children.
2. **Compare the two views.** The flat list is the order the footer stores the schema in. The
   tree is what the reader rebuilt from it, using nothing but each element's count of children.
3. **Read the levels beside each leaf.** `country` is optional, and `shipping.city` is optional
   inside an optional group. The reader counts those optional fields on the way down, and
   [ch04](#nested-data) needs the counts to decode the values.
4. **Click `order_date`'s minimum bytes** in the lower table. The inspector reads them as a
   little-endian integer, a count of days. The table shows the date that count means. Do the same
   for `amount`, and read its bytes the other way round.
5. **Damage the schema.** In the structure view, open `FileMetaData › schema › [0]` and select
   its `num_children` value byte. Change it to `12`, which is the zigzag varint for one child
   fewer. The reader refuses the file: some elements now belong to no group.

### Stored flat

The footer does not store a tree. It stores this list, in depth-first order:

```{include} _generated/types-schema-flat.md
```

The first element is the root. It names the whole record and says how many top-level fields
follow. A group, such as `shipping`, gives its own count of children, and they follow it
immediately. A leaf has no children and a physical type. Every leaf is one column of the file, in
this order, and the column chunks in every row group follow the same order.

### Rebuilt as a tree

Rebuilt, the same list is the schema in the textual notation that Parquet tools print, which
comes from the Dremel paper:

```{include} _generated/types-schema-text.md
```

Each line has three parts: a repetition, a type, and a name. The logical type, when there is one,
follows in brackets.

**The repetition** says how many values the field has in each record:

- `required`: exactly one. It is never null.
- `optional`: zero or one. It may be null.
- `repeated`: zero or more. The field is a list.

**A leaf's path** is the names from the root's child down to it: `shipping.city`. A column chunk
records its path, and the path is how a query names a nested column.

### The same bytes, read two ways

A physical type is a storage format. There are eight:

| Physical type | How a value is stored |
|---|---|
| `BOOLEAN` | one bit |
| `INT32`, `INT64` | a signed integer, little-endian |
| `INT96` | twelve bytes, deprecated, used by old engines for timestamps |
| `FLOAT`, `DOUBLE` | an IEEE floating-point number, little-endian |
| `BYTE_ARRAY` | a length, then that many bytes |
| `FIXED_LEN_BYTE_ARRAY` | a fixed number of bytes, declared in the schema |

A logical type says what a stored value means. Here is the minimum of every column in
`types.parquet`, as the footer stores it, read by its physical type alone, and read through its
logical type:

```{include} _generated/types-values.md
```

Read down the last two columns. Where there is no logical type, the physical reading is the
value. Where there is one, the physical reading is a number nobody meant:

- **`order_date`** is an `INT32` with the logical type `DATE`: a count of days since
  1970-01-01.
- **`paid_at`** is an `INT64` with `TIMESTAMP`: a count of microseconds since the same moment. The
  logical type also records the unit, and whether the value is an instant (`UTC`) or a wall-clock
  reading with no zone (`local`). The two look identical in the bytes and differ in meaning.
- **`amount`** is a `DECIMAL`: an integer to be divided by a power of ten, here with two digits
  after the point. pyarrow stored it in a `FIXED_LEN_BYTE_ARRAY`, and there the integer is
  big-endian: the most significant byte first. It is the one place Parquet stores a number the
  other way round.
- **`quantity`** and **`store_id`** are both `INT32`. The logical type says one is an 8-bit
  signed integer and the other a 16-bit unsigned one. A reader that ignored it would read a large
  unsigned value as negative.
- **`country`** is a `BYTE_ARRAY` with `STRING`: the bytes are UTF-8 text. Without the annotation
  they are opaque bytes, and a reader should not assume otherwise.

Encoders and decoders only ever handle the eight physical types. Every logical type is an
interpretation applied after decoding. That keeps the part of a reader that touches bytes small,
and lets the format add logical types without changing how anything is stored.

### Older annotations, and field ids

Files written before logical types existed carry a `converted_type` instead, such as `UTF8` or
`TIMESTAMP_MILLIS`. Writers still set both for older readers. A reader should prefer the logical
type when both are present.

A schema element can also carry a `field_id`: a number that identifies a column across renames.
Table formats use it to match columns between files written years apart
([ch14](#lakehouse-and-beyond)). The fixtures do not set one.

## Building it

### Rebuilding the tree

The rebuild reads an element, and if it has children, reads that many subtrees after it, each
the same way. The recursion consumes the list from the front:

```{literalinclude} ../crates/parquet-lab/src/schema.rs
:language: rust
:start-at: pub fn build(elements: &[SchemaElement])
:end-before: /// The largest definition
```

Two checks make a damaged schema an error rather than a wrong tree. A group that claims more
children than the list has left is refused. So is a list with elements left over after the root's
subtree ends, which is what the experiment's damaged byte produced.

### Maximum levels

A leaf's maximum definition level counts the fields on its path that may be absent. Its maximum
repetition level counts the fields that repeat:

```{literalinclude} ../crates/parquet-lab/src/schema.rs
:language: rust
:start-at: pub fn max_levels(path: &[Repetition])
:end-before: /// Every leaf of the tree
```

When both are zero, as for every column of `tiny.parquet`, the column stores no levels at all:
its pages hold values and nothing else. [ch04](#nested-data) shows what the levels are when they
are not zero.

### Reading a value through its logical type

The logical type arrives from the footer as a Thrift union: a struct with exactly one field set,
whose id names the type. `crates/parquet-lab/src/logical.rs` decodes it into an enum. Applying it
is a match on the pair of physical and logical type:

```{literalinclude} ../crates/parquet-lab/src/logical.rs
:language: rust
:start-at: pub fn interpret(physical: PhysicalType
:end-before: /// An `INT96` value
```

The decimal case is the one that reads bytes most significant first. Its helper sign-extends from
the top bit of the first byte:

```{literalinclude} ../crates/parquet-lab/src/logical.rs
:language: rust
:start-at: pub fn be_twos_complement(bytes: &[u8])
:end-before: /// A half-precision
```

### Checking it

The fixture tests compare the rebuilt schema with pyarrow's own reading of it: every leaf's path,
physical type and maximum levels. They also apply each column's logical type to its statistics and
compare with the values pyarrow reports:

```bash
cargo test -p parquet-lab --test fixtures
```

## What this cannot tell you

**How nested values are stored.** The levels tell a reader how deep a value is defined and where
lists begin. This chapter computes their maximums; [ch04](#nested-data) decodes them.

**Every logical type.** The fixture covers the common ones. `UUID`, `FLOAT16`, `TIME`, `JSON`,
`ENUM` and the newer `VARIANT` and geospatial types are decoded by name; the reader interprets
some of them and reports the rest as unrecognised rather than guessing.

**What a legacy writer meant.** `INT96` timestamps and files with only a `converted_type` follow
conventions that lived outside the specification for years. The reader can decode an `INT96` as
nanoseconds within a day and a Julian day number. Whether that moment was UTC is something the
file does not say.

**Whether a writer chose well.** Storing a date as a string, or a decimal as a double, is legal and
loses information. [ch11](#writing-parquet-well) looks at those choices from the writer's side.

## Key takeaways

:::{div}
:class: takeaways

- **A physical type says how a value is stored; a logical type says what it means.** Eight
  physical types carry every logical type.
- **The same bytes are different values under different logical types.** A day count, an unsigned
  integer and a decimal can share a physical type.
- **The schema is a tree stored as a depth-first list.** Each group gives its count of children,
  and nothing else is needed to rebuild it.
- **Every leaf is a column.** Its path names it, and its position among the leaves is its position
  among each row group's column chunks.
- **Optional and repeated fields set a leaf's maximum levels.** A column whose path is all
  required stores no levels at all.
:::

## Problems

Four, in `exercises/src/the_type_system.rs`. The first three have tests that fail until you solve
them. The fourth has no test.

**3.1 Rebuild the tree.** Given each element's name and number of children, in depth-first order,
return every leaf's path. The test uses the fixtures and hundreds of generated schemas.

```bash
cargo test -p exercises --test the_type_system problem_3_1 -- --ignored
```

**3.2 Maximum levels.** Given the repetitions along a path, return the maximum definition and
repetition levels. The test checks every path up to five fields deep, and the fixtures against
pyarrow.

```bash
cargo test -p exercises --test the_type_system problem_3_2 -- --ignored
```

**3.3 A decimal from bytes.** Read a big-endian two's-complement integer and place the decimal
point. The test compares with pyarrow on the fixture and with the reader on generated values,
negative ones included.

```bash
cargo test -p exercises --test the_type_system problem_3_3 -- --ignored
```

**3.4 Your own schema.** No test: the tables are yours. Print the schema of a Parquet file your
systems write (`cargo run -p pqlab -- schema FILE`, or any Parquet tool). List every column whose
logical type is missing where you would expect one: text stored without `STRING`, dates stored as
strings or integers, money stored as `DOUBLE`, timestamps stored as `INT96`. For each timestamp,
say whether it is `UTC` or `local`, and whether that matches what the data means. A good answer
names each column, what it should be, and what a reader would get wrong because of the gap.

## Where to go next

- The physical and logical types are specified in the Parquet format repository's
  [LogicalTypes.md](https://github.com/apache/parquet-format/blob/master/LogicalTypes.md).
- The textual schema notation and the repetition model come from the
  [Dremel paper](https://research.google/pubs/dremel-interactive-analysis-of-web-scale-datasets-2/).
- [ch04](#nested-data) decodes the definition and repetition levels whose maximums you computed
  here.
