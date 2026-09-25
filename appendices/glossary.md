---
title: Glossary
---

(glossary)=
# Glossary

Terms the book uses, with the chapter that introduces each.

**Codec.** The general-purpose compressor applied to every page of a column chunk after encoding,
named in the chunk's metadata: SNAPPY, GZIP, LZ4_RAW, ZSTD, BROTLI, or UNCOMPRESSED.
[ch07](#compression)

**Column chunk.** One column's data within one row group. Contiguous in the file.
[ch02](#anatomy-of-a-parquet-file)

**Column layout.** Storing all of a column's values together, then the next column's.
[ch01](#why-parquet-exists)

**Column order.** The footer's statement, column by column, of which sort order `min_value` and
`max_value` use. Without it their order is undefined. [ch08](#metadata-and-statistics)

**Data page version 2.** A data page whose header records the level streams' lengths, its rows and
its nulls, and whose levels are never compressed. [ch06](#pages)

**Definition level.** For each value slot, how many of the optional and repeated fields on its path
are present. A slot whose level is the column's maximum holds a value. [ch04](#nested-data)

**Dictionary encoding.** Writing each distinct value once, in a dictionary page, and the data as
small indices into it. [ch05](#encodings)

**Encoding.** A type-aware way of writing a column's values as bytes, such as PLAIN, RLE_DICTIONARY
or DELTA_BINARY_PACKED. It happens before compression. [ch05](#encodings)

**Entropy coding.** Giving frequent symbols shorter codes than rare ones, as DEFLATE's Huffman codes
do. [ch07](#compression)

**Footer.** The `FileMetaData` structure near the end of a file: schema, row counts, and the
position and description of every column chunk. [ch02](#anatomy-of-a-parquet-file)

**Footer length.** The four-byte little-endian integer immediately before the closing magic.
[ch02](#anatomy-of-a-parquet-file)

**Little-endian.** Storing a multi-byte integer with its least significant byte first.
[ch02](#anatomy-of-a-parquet-file)

**Logical type.** What a physical type's bytes mean: a date, a decimal, a string, a timestamp.
[ch03](#the-type-system)

**LZ77.** Compressing by replacing bytes the output already holds with how far back they are and how
many. Every codec in [ch07](#compression) is built on it.

**Magic.** The four ASCII bytes `PAR1` at the start and end of every unencrypted Parquet file.
[ch02](#anatomy-of-a-parquet-file)

**Object store.** Storage addressed by key that serves whole objects and byte ranges over HTTP,
such as S3. [ch02](#anatomy-of-a-parquet-file)

**Page.** The unit a column chunk is divided into for encoding and compression, with a header of
its own. [ch02](#anatomy-of-a-parquet-file)

**Physical type.** How a value is stored: BOOLEAN, INT32, INT64, INT96, FLOAT, DOUBLE, BYTE_ARRAY or
FIXED_LEN_BYTE_ARRAY. [ch03](#the-type-system)

**Prefetch.** Reading more of a file's tail than the trailer, so that the footer arrives in the
same request. [ch02](#anatomy-of-a-parquet-file)

**Projection.** Reading only the columns a query names. [ch01](#why-parquet-exists)

**Range request.** An HTTP request for part of an object, `Range: bytes=a-b`, inclusive at both
ends. [ch02](#anatomy-of-a-parquet-file)

**Repetition level.** For each value slot, the depth of the repeated field at which a new element
starts; zero starts a new record. [ch04](#nested-data)

**Row group.** A horizontal slice of a table: some rows, all columns.
[ch02](#anatomy-of-a-parquet-file)

**Row layout.** Storing each row's values together. [ch01](#why-parquet-exists)

**Sort order.** The order a column's statistics use, fixed by its type: signed, unsigned, by value,
or byte by byte. [ch08](#metadata-and-statistics)

**Statistics.** A column chunk's or page's minimum, maximum and null count, kept in its metadata so
a reader can decide not to read it. [ch08](#metadata-and-statistics)

**Suffix range.** A range request for the last `n` bytes of an object, `Range: bytes=-n`. The
response reports the object's size. [ch02](#anatomy-of-a-parquet-file)

**Thrift compact protocol.** The binary serialisation Parquet uses for its footer and page
headers. [ch02](#anatomy-of-a-parquet-file)

**Trailer.** The last eight bytes of a file: the footer length and the closing magic.
[ch02](#anatomy-of-a-parquet-file)
