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

:::{div}
:class: reading-guide

**What you will learn:** Distinguish how a value is stored from what it means, and follow a leaf through the schema tree.

Read the explanations, worked results and diagrams; the code is optional.
:::

## The experiment

```lesson
follow-schema-paths
```

(read-the-schema-yourself)=
### Read the schema yourself

A **physical type** describes how a value is stored. A **logical type** gives those stored bytes
a meaning, such as a date or a decimal. The **schema** records the fields, their types and how
they nest. We first follow its structure; the next lesson interprets the values.

`types.parquet` holds three orders, with a column for each physical type and the common logical
types on top of them. [Appendix B](#the-fixtures) says how pyarrow wrote it. Each step shows its worked result before its optional code. You can read the results as they
stand, or open **Read or run the code** to explore them. Each step finds the footer as [ch02](#anatomy-of-a-parquet-file) did, and hands its
bytes to the book's reader. It decodes the footer's numbered fields; the optional build lab in
ch02 explains their binary representation.

**The schema as stored.** The footer's second field is the schema. Each printed element names
a field, its repetition and its types, or a group and its count of children.

**The repetition** says how many values the field has in each record:

- `REQUIRED`: exactly one. It is never null.
- `OPTIONAL`: zero or one. It may be **null**, meaning that no value is present.
- `REPEATED`: zero or more. The field is a list.

The type labels will matter in the next lesson. One has two parameters worth distinguishing:
`DECIMAL(precision, scale)`. **Precision** is the maximum number of decimal digits the value
may need; **scale** is how many of those digits come after the decimal point.

Print every element:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/the_type_system/schema_as_stored.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/schema_as_stored.rs
:language: rust
```
:::
::::

One line per element, in the footer's order. The first is the root, `schema`. It has children and
no type, and it names the whole record. Most of the others have a physical type and no children:
they are **leaves**, the fields at the ends of the tree. Each leaf is one column of the file. The leaves come in column order, and
the column chunks in every row group follow the same order.

`shipping` is neither a leaf nor the root. It has children and no type: it is a *group*, and the
elements after it are its children. Nothing in the list says where a group ends. Its count of
children is the only clue. Change the path to `fixtures/nested.parquet` and run the step again:
a list is a group too, with a `REPEATED` field inside it.

### Rebuilt as a tree

These fields form the schema tree. Parquet tools print it in a textual notation that comes from
the Dremel paper. `message schema` names the root; braces enclose its fields and the fields of
nested groups. Each field starts with a repetition, a type and a name. A logical type, when
there is one, follows in parentheses.

The repetition labels here are lowercase versions of the ones above. For example, `optional binary country (STRING)` names a field that may be missing. It stores
bytes (`binary`) interpreted as text (`STRING`). Read the other fields with the same pattern:

```{include} _generated/types-schema-text.md
```

**A leaf's path** is the names from the root's child down to it: `shipping.city`. A column chunk
records its path, and the path is how a query names a nested column.

```practice
question: A schema group contains another group with a leaf called city, while a separate top-level leaf is also called city. Are those the same column?
answer: No. A column is identified by its complete path, such as shipping.address.city versus city. A group describes structure and is not itself a physical leaf column.
```

```lesson
interpret-logical-types
```

(stored-values-and-their-meaning)=
### Stored values and their meaning

A **physical type** describes storage; a **logical type** tells you how to interpret those stored values.
The examples use `types.parquet`, whose [schema walkthrough](#read-the-schema-yourself) identifies
its columns. Here the date, timestamp and decimal columns show why storage alone is not enough.

**Statistics** summarise a column chunk, for example by recording its smallest value. We can
read such a stored value without fetching the column's data pages.

**The same bytes, read two ways.** Each column chunk's statistics hold its smallest value, as
bytes. Read three of them, first as the physical type stores them and then as the logical type
says:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/the_type_system/same_bytes_two_ways.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/same_bytes_two_ways.rs
:language: rust
```
:::
::::

`order_date`'s bytes are a little-endian `INT32`, and as a number they mean little. Its logical
type, `DATE`, says the number counts days since 1970-01-01, and then it is a date. `paid_at` is
the same idea at a finer grain: an `INT64` count of microseconds. `amount` is the odd one out. Its
integer is read most significant byte first, which is **big-endian**, and it counts hundredths.
Change `"big"` to `"little"` (`from_be_bytes` to `from_le_bytes` in Rust), and the same bytes are
a number nobody meant. Only the schema says which reading is right.

### Every column, read two ways

A **signed integer** can represent negative values as well as zero and positive values. An
**unsigned integer** represents only zero and positive values. A **floating-point number**
represents numbers using a sign, a scale and precision bits; some fractions must be rounded.

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
value. Where there is one, the physical reading is often a number nobody meant:

- **`order_date`** is an `INT32` with the logical type `DATE`: a count of days since
  1970-01-01.
- **`paid_at`** is an `INT64` with `TIMESTAMP`: a count of microseconds since the same moment. The
  logical type also records the unit, and whether the value is an instant (`UTC`, Coordinated
  Universal Time, the common time reference) or a wall-clock
  reading with no zone (`local`). The two look identical in the bytes and differ in meaning.
- **`amount`** is a `DECIMAL`: an integer to be divided by a power of ten, here with two digits
  after the point. pyarrow stored it in a `FIXED_LEN_BYTE_ARRAY`, and there the integer is
  big-endian. A decimal stored as bytes is big-endian in a `BYTE_ARRAY` too, and so is a `UUID`'s
  sixteen bytes. Every other number Parquet stores is little-endian.
- **`quantity`** and **`store_id`** are both `INT32`. The logical type says one is an 8-bit
  signed integer and the other a 16-bit unsigned one. Both ranges fit in a signed 32-bit integer,
  so here the two readings agree. They part for unsigned 32-bit and 64-bit integers, stored in
  `INT32` and `INT64`: a reader that ignored the logical type would read a large value as
  negative.
- **`country`** is a `BYTE_ARRAY` with `STRING`: the bytes are **UTF-8** text. UTF-8 represents
  text with bytes, using more than one byte for some characters. Without the annotation
  they are opaque bytes, and a reader should not assume otherwise.

Encoders and decoders only ever handle the eight physical types. Every logical type is an
interpretation applied after decoding. That keeps the part of a reader that touches bytes small,
and lets the format add logical types without changing how anything is stored.

INT96 is deprecated and its timezone interpretation is ambiguous. This reader displays it rather than guessing a conversion; unknown logical annotations need explicit handling.

```practice
question: Two UTC timestamp columns store the same non-zero integer, but one annotation says milliseconds and the other says microseconds. Do the bytes represent the same instant?
answer: No. The physical integer is the same; the logical unit changes its meaning. Also check whether a timestamp is a UTC instant or a local wall-clock value before interpreting it.
```

```lesson
count-schema-levels
```

(schema-level-walkthrough)=
### Count levels while rebuilding

A leaf’s **maximum definition level** counts the optional or repeated fields along its path.
Its **maximum repetition level** counts only the repeated fields. These are limits set by the
schema. The next module uses each record’s actual levels to describe missing values and list
boundaries. Here we count the limits from the tree.

The [schema walkthrough](#read-the-schema-yourself) reads `types.parquet` as a list of fields and
groups. This lesson rebuilds that list into paths, then counts each path's optional and repeated fields.

**The tree, rebuilt.** A count of children is enough to rebuild the tree. Take an element; if it
has children, take that many subtrees after it, each the same way:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/the_type_system/rebuild_the_tree.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/src/bin/rebuild_the_tree.rs
:language: rust
```
:::
::::

The walk consumes the list from the front, and the indentation is its depth. On the way down it
counts the fields that may be absent. `country` is optional, so each of its values needs a level
saying whether it is there. `shipping.city` is optional inside an optional group, so it needs a
level that can say which of the two is missing. These counts are each leaf's *maximum levels*,
and [ch04](#nested-data) needs them to decode the values. The book's reader then rebuilds the same
tree with `schema.build`, and finds the same columns.

### One path, counted completely

For `shipping.city`, the optional `shipping` group contributes one definition level and the
optional `city` leaf contributes another. A present city therefore reaches two; a missing
shipping group reaches zero, and a present group with a missing city reaches one. No field
on this path repeats, so its maximum repetition level is zero.

Each optional or repeated field on the path, including the leaf, raises the definition maximum.
Only a repeated field raises the repetition maximum. Required fields raise neither. The tree output shows these
schema maxima, not the actual level of every record.

Counting maxima prepares the next module. It does not yet reconstruct records from their actual level streams.

```practice
question: A required address group contains an optional street leaf, and nothing repeats. What are that leaf’s maximum levels? Does the maximum say that every record has a street?
answer: Maximum definition is one, maximum repetition is zero. The required parent contributes neither; the optional leaf contributes one definition level. A maximum describes what the schema permits, not what each record contains.
```

```lesson
build-schema-reader
```

## Building it

:::{div}
:class: optional-section

**Optional implementation.** Read this section to see how the reader is built.
For the conceptual path, continue to [What this cannot tell you](#the-type-system-limits),
then the takeaways and the understanding check.
:::

Build the schema reader used by the [field walkthrough](#read-the-schema-yourself),
[tree and level counts](#schema-level-walkthrough), and [stored-value interpretations](#stored-values-and-their-meaning).
Those examples use `types.parquet`. The implementation decodes fields, rebuilds paths and applies
logical types; the tabs select Python or Rust.

### Optional schema-damage investigation

**Zigzag encoding** maps signed integers to unsigned ones: zero stays zero, positive values
become even numbers, and negative values become odd numbers. A **varint** stores an integer in
a variable number of bytes, using fewer bytes for smaller unsigned values. Thrift combines them
to keep small signed numbers short.

Open the code for [the tree-rebuilding walkthrough](#schema-level-walkthrough) to damage
the list. That step writes the root's count of children back to the byte that holds it,
as the zigzag varint `0x14`. Change it to `0x12`, one child fewer, and run the step again. The
walk prints a shorter tree without complaint: it never looks at the elements after the root's
last child. `shipping` and its children now belong to no one, and the reader's `build` refuses the
file for that reason.

### Schema elements

`decode_file_metadata` gives the footer's Thrift fields their Parquet names. The
[footer-reader implementation](anatomy_of_a_parquet_file.md#building-it) explains how the binary fields are decoded.
Field 2 is the schema: a list of structs, each decoded into a `SchemaElement` by field id:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/metadata.py
:language: python
:start-at: def schema_element(node: Node)
:end-before: def row_group(node: Node)
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/metadata.rs
:language: rust
:start-at: fn schema_element(node: &Node)
:end-before: fn row_group(node: &Node)
```
:::
::::

Only the name is required. A group has `num_children` and no physical type; a leaf has a physical
type and no children. The logical type is a struct of its own, decoded below.

### Rebuilding the tree

The rebuild follows the [tree walkthrough](#schema-level-walkthrough), with checks. It starts at the root and requires the root's
subtree to use up the whole list:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/schema.py
:language: python
:start-at: def build(elements: list[SchemaElement])
:end-before: def _subtree(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/schema.rs
:language: rust
:start-at: pub fn build(elements: &[SchemaElement])
:end-before: fn subtree(elements
```
:::
::::

Each subtree reads an element, and if it has children, reads that many subtrees after it, each the
same way. The recursion consumes the list from the front:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/schema.py
:language: python
:start-at: def _subtree(
:end-before: def max_levels(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/schema.rs
:language: rust
:start-at: fn subtree(elements
:end-before: /// The largest definition
```
:::
::::

Two checks make a damaged schema an error rather than a wrong tree. A group that claims more
children than the list has left is refused. So is a list with elements left over after the root's
subtree ends, which is what the byte you changed in the walk produced.

### Maximum levels

A leaf's maximum definition level counts the fields on its path that may be absent. Its maximum
repetition level counts the fields that repeat:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/schema.py
:language: python
:start-at: def max_levels(path: list[str])
:end-before: def leaves(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/schema.rs
:language: rust
:start-at: pub fn max_levels(path: &[Repetition])
:end-before: /// Every leaf of the tree
```
:::
::::

When both are zero, as for every column of `tiny.parquet`, the column stores no levels at all:
its pages hold values and nothing else. [ch04](#nested-data) shows what the levels are when they
are not zero.

### Reading a value through its logical type

The logical type arrives from the footer as a Thrift union: a struct with exactly one field set,
whose id names the type. The `logical` module decodes it into a value naming the type and its
parameters. Applying it is a match on the pair of physical and logical type. Its first cases
include the date and timestamp from the [stored-value example](#stored-values-and-their-meaning):

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/logical.py
:language: python
:start-at: def interpret(physical: int
:end-before: if physical in (1, 2) and name == "TIME"
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/logical.rs
:language: rust
:start-at: pub fn interpret(physical: PhysicalType
:end-before: (1 | 2, LogicalType::Time
```
:::
::::

The rest follow the same pattern: `TIME`, then `DECIMAL`, then text, `FLOAT16` and `UUID`. A
decimal can be stored in an `INT32`, an `INT64` or bytes, and only the bytes are big-endian:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/logical.py
:language: python
:start-at: if physical in (1, 2) and name == "DECIMAL"
:end-before: if physical in (6, 7) and name in ("STRING"
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/logical.rs
:language: rust
:start-at: (1, LogicalType::Decimal { scale, .. })
:end-before: (6 | 7, LogicalType::String
```
:::
::::

These signed bytes use **two’s complement**. The highest bit marks a negative value; for
`n` stored bits, subtract `2**n` from the unsigned reading when that bit is set. **Sign extension**
keeps that value when widening it by repeating the sign bit into the new high bits. The helper
uses the top bit of the first byte:

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/logical.py
:language: python
:start-at: def be_twos_complement(data: bytes)
:end-before: def f16_to_float(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/logical.rs
:language: rust
:start-at: pub fn be_twos_complement(bytes: &[u8])
:end-before: /// A half-precision
```
:::
::::

### Checking it

The fixture tests compare the rebuilt schema with pyarrow's own reading of it: every leaf's path,
physical type and maximum levels. They also apply each column's logical type to its statistics and
compare with the values pyarrow reports:

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

pyarrow and the `parquet` crate both rebuild the tree when they open a file, and print it in the
Dremel notation. pyarrow's `schema.column(i)` and the crate's `SchemaDescriptor` give each leaf's
path, physical type and maximum levels for `types.parquet`, as in the
[tree walkthrough](#schema-level-walkthrough):

::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../walkthroughs/python/the_type_system/schema_with_a_library.py
:language: python
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../walkthroughs/libraries/src/bin/schema_with_a_library.rs
:language: rust
```
:::
::::

The two part over the statistics. pyarrow reads each minimum through its logical type and hands
you a `datetime.date` and a `Decimal`. The crate, without its Arrow feature, hands you stored bytes,
as in the [physical/logical comparison](#stored-values-and-their-meaning), and the logical reading is yours to do. The two also name the logical types
differently: pyarrow's `Int(bitWidth=8, isSigned=true)` is the crate's `INTEGER(8,true)`. pyarrow
prints `field_id=-1` for a field with no field id, which is every field of this fixture.

In Python, the first run loads pyarrow into the page, a much larger download than the other
steps. In Rust the step needs the `parquet` crate, in `walkthroughs/libraries`, so it runs in a
Codespace or at a desk:

```bash
cargo run -q --manifest-path walkthroughs/libraries/Cargo.toml --bin schema_with_a_library
```

```lesson
reference
```

These notes cover the schema and types of `types.parquet`. The [schema walkthrough](#read-the-schema-yourself)
shows its fields, the [value comparison](#stored-values-and-their-meaning) applies their annotations, and
[maximum-level counting](#schema-level-walkthrough) prepares for nested records.

### Older annotations, and field ids

Files written before logical types existed carry a `converted_type` instead, such as `UTF8` or
`TIMESTAMP_MILLIS`. Writers still set both for older readers. A reader should prefer the logical
type when both are present.

A schema element can also carry a `field_id`: a number that identifies a column across renames.
Table formats use it to match columns between files written years apart
([Iceberg's table metadata](#what-iceberg-adds)). `types.parquet` sets none; the
[table-change example](#changing-a-table) sets one on every column.

(the-type-system-limits)=
## What this cannot tell you

**How nested values are stored.** The levels tell a reader how deep a value is defined and where
lists begin. The [level-counting example](#schema-level-walkthrough) computes their maximums;
[nested-data lessons](#nested-data) decode their actual values.

**Every logical type.** `types.parquet` covers common physical and logical types. `UUID`, `FLOAT16`, `TIME`, `JSON`,
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
- **A library reads the same schema.** pyarrow and the `parquet` crate rebuild the tree and report
  each leaf's levels. Whether they read a value through its logical type depends on the library.
:::

```checkpoint
question: Two columns both store INT32 values. Can you decide how to display them from that physical type alone?
answer: No. The logical annotation may describe a date, an unsigned integer or another meaning. The physical type tells you how to decode the bytes; the logical type tells you how to interpret the result.
```

## Problems

The coding exercises are optional. You can also reason through the question about your own data
without writing a program.

Four, in `exercises/python/the_type_system.py`, or in Rust in
`exercises/src/the_type_system.rs`. The first three have tests that fail until you solve
them. The fourth has no test.

The editor below holds the Python stubs and keeps your edits in this browser. **Run the tests**
runs the graders in the page, the same tests that run at a desk.

```problems
chapter: the_type_system
```

**3.1 Rebuild the tree.** Given each element's name and number of children, in depth-first order,
return every leaf's path. The test uses the fixtures and hundreds of generated schemas.

**3.2 Maximum levels.** Given the repetitions along a path, return the maximum definition and
repetition levels. The test checks every path up to five fields deep, and the fixtures against
pyarrow.

**3.3 A decimal from bytes.** Read a big-endian two's-complement integer and place the decimal
point. The test compares with pyarrow on the fixture and with the reader on generated values,
negative ones included.

**3.4 Your own schema.** No test: the tables are yours. Print the schema of a Parquet file your
systems write (`PYTHONPATH=python python3 -m parquet_lab schema FILE`, `cargo run -p pqlab -- schema FILE`, or any
Parquet tool). List every column whose
logical type is missing where you would expect one: text stored without `STRING`, dates stored as
strings or integers, money stored as `DOUBLE`, timestamps stored as `INT96`. For each timestamp,
say whether it is `UTC` or `local`, and whether that matches what the data means. A good answer
names each column, what it should be, and what a reader would get wrong because of the gap.

For the Rust stubs, or to work at a desk, run the chapter's graders with these commands. Add
`-k problem_3_1` in Python, or `problem_3_1` before the `--` in Rust, to run one problem:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_the_type_system.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test the_type_system -- --ignored
```
:::
::::

## Where to go next

- The physical and logical types are specified in the Parquet format repository's
  [LogicalTypes.md](https://github.com/apache/parquet-format/blob/master/LogicalTypes.md).
- The textual schema notation and the repetition model come from the
  [Dremel paper](https://research.google/pubs/dremel-interactive-analysis-of-web-scale-datasets-2/).
- [Nested data](#nested-data) decodes the definition and repetition levels introduced by the
  [schema-level walkthrough](#schema-level-walkthrough).
