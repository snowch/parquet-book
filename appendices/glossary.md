---
title: Glossary
---

(glossary)=
# Glossary

Terms the book uses, with the chapter that introduces each.

**Column chunk.** One column's data within one row group. Contiguous in the file.
[ch02](#anatomy-of-a-parquet-file)

**Column layout.** Storing all of a column's values together, then the next column's.
[ch01](#why-parquet-exists)

**Footer.** The `FileMetaData` structure near the end of a file: schema, row counts, and the
position and description of every column chunk. [ch02](#anatomy-of-a-parquet-file)

**Footer length.** The four-byte little-endian integer immediately before the closing magic.
[ch02](#anatomy-of-a-parquet-file)

**Little-endian.** Storing a multi-byte integer with its least significant byte first.
[ch02](#anatomy-of-a-parquet-file)

**Magic.** The four ASCII bytes `PAR1` at the start and end of every unencrypted Parquet file.
[ch02](#anatomy-of-a-parquet-file)

**Object store.** Storage addressed by key that serves whole objects and byte ranges over HTTP,
such as S3. [ch02](#anatomy-of-a-parquet-file)

**Page.** The unit a column chunk is divided into for encoding and compression, with a header of
its own. [ch02](#anatomy-of-a-parquet-file)

**Prefetch.** Reading more of a file's tail than the trailer, so that the footer arrives in the
same request. [ch02](#anatomy-of-a-parquet-file)

**Projection.** Reading only the columns a query names. [ch01](#why-parquet-exists)

**Range request.** An HTTP request for part of an object, `Range: bytes=a-b`, inclusive at both
ends. [ch02](#anatomy-of-a-parquet-file)

**Row group.** A horizontal slice of a table: some rows, all columns.
[ch02](#anatomy-of-a-parquet-file)

**Row layout.** Storing each row's values together. [ch01](#why-parquet-exists)

**Suffix range.** A range request for the last `n` bytes of an object, `Range: bytes=-n`. The
response reports the object's size. [ch02](#anatomy-of-a-parquet-file)

**Thrift compact protocol.** The binary serialisation Parquet uses for its footer and page
headers. [ch02](#anatomy-of-a-parquet-file)

**Trailer.** The last eight bytes of a file: the footer length and the closing magic.
[ch02](#anatomy-of-a-parquet-file)
