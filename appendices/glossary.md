---
title: Glossary
---

(glossary)=
# Glossary

Look up a term here, then follow its lesson link for the worked example. Definitions needed
for an example or question also appear in the lesson before you need them.

## AES-GCM

An encryption scheme that protects content and produces an authentication tag for checking it. Parquet also supplies context about the file and module to that check, so valid encrypted bytes cannot be moved freely between locations.

Learn it: [Modules](../chapters/modular_encryption.md#modules).

## Aggregate

A calculation that combines values from several rows, such as a count, sum or minimum. An aggregate can cover the whole input or each group separately.

Learn it: [Answers from the footer](../chapters/what_a_query_engine_does.md#answers-from-the-footer).

## Analytical query

A query that examines many records to calculate a summary or find a pattern. It often needs only some columns, which is why column storage can help.

Learn it: [Two columns from a CSV file](../chapters/why_parquet_exists.md#two-columns-from-a-csv-file).

## ASCII

A character encoding that assigns numbers to letters, digits and other characters. The bytes for the letters `PAR1` form Parquet’s familiar file signature.

Learn it: [Before reading the bytes](../chapters/anatomy_of_a_parquet_file.md#before-reading-the-bytes).

## Atomicity

Making a change visible as a whole, rather than exposing only some of its parts. A table commit must publish a complete valid metadata state so readers do not see half of the change.

Learn it: [Commits and catalogs](../chapters/what_iceberg_adds.md#commits-and-catalogs).

## Authentication

Checking that protected content and its associated context have not been altered, using the appropriate key. Reading a visible footer or recognising an encryption header does not perform that check.

Learn it: [What a plaintext footer shows](../chapters/modular_encryption.md#what-a-plaintext-footer-shows).

## Authentication tag

A value computed during authenticated encryption and checked during decryption to detect modification. The tag can be visible in a file; verifying it requires the appropriate key.

Learn it: [Modules](../chapters/modular_encryption.md#modules).

## Bandwidth

The rate at which bytes can be transferred. It affects the time to move a response after the initial wait for that response.

Learn it: [When bytes matter](../chapters/how_readers_read.md#when-bytes-matter).

## Big-endian

Storing a multi-byte integer with its most significant byte first. Some Parquet values use this order, including the byte representation of a DECIMAL, even though many other fields use little-endian order.

Learn it: [Stored values and their meaning](../chapters/the_type_system.md#stored-values-and-their-meaning).

## Bit

A binary digit, either zero or one. The pattern of bits can represent a number, a character or another value, depending on how it is interpreted.

Learn it: [Before reading the bytes](../chapters/anatomy_of_a_parquet_file.md#before-reading-the-bytes).

## Bit packing

Storing several small integers using only the number of bits needed for each one, instead of giving each a whole byte or machine word.

Learn it: [How the levels are stored](../chapters/nested_data.md#how-the-levels-are-stored).

## Bit width

The number of bits used to represent one value in a particular stream or field. A smaller width can represent fewer distinct bit patterns.

Learn it: [The levels as stored](../chapters/nested_data.md#the-levels-as-stored).

## Bitset

A collection of individual bits used as flags. A Bloom filter sets and checks selected positions in a bitset to test possible membership.

Learn it: [Bloom filters](../chapters/skipping_data.md#bloom-filters).

## Bloom filter

A compact membership test that can rule out a value or say it might be present. With compatible hashing and a correctly constructed filter, it has false positives but no false negatives; Parquet can store one per column chunk.

Learn it: [Bloom filters](../chapters/skipping_data.md#bloom-filters).

## Bounds

Limits enclosing a set of values under a stated comparison order. Lower and upper statistics bounds can rule out regions that cannot satisfy a query condition.

Learn it: [Read the statistics yourself](../chapters/metadata_and_statistics.md#read-the-statistics-yourself).

## Build side

The join input used to construct a lookup structure, such as a hash table. The other input probes that structure to find matches.

Learn it: [Joins](../chapters/what_a_query_engine_does.md#joins).

## Byte

A group of eight bits. A file is a sequence of bytes; decoding decides what those bytes mean.

Learn it: [Before reading the bytes](../chapters/anatomy_of_a_parquet_file.md#before-reading-the-bytes).

## Byte-stream split

An encoding that gathers the first byte of each fixed-width value into one stream, then the second bytes, and so on. It reorders the bytes without shrinking them; a following compression codec may then find better patterns.

Learn it: [Byte-stream split](../chapters/encodings.md#byte-stream-split).

## Caching

Keeping data already fetched so a later request can reuse it. A cached result may avoid a transfer entirely, unlike coalescing or prefetching, which change how a transfer is made.

Learn it: [How readers read limits](../chapters/how_readers_read.md#how-readers-read-limits).

## Cardinality

The number of distinct values in a set of values. A column with many repeated values has low cardinality relative to its row count, which can make dictionary encoding useful.

Learn it: [Dictionary encoding](../chapters/encodings.md#dictionary-encoding).

## Catalog

A service or other authority that resolves a table name to its current metadata. For Iceberg, it also coordinates publishing a new current metadata location according to the catalog’s commit protocol.

Learn it: [Commits and catalogs](../chapters/what_iceberg_adds.md#commits-and-catalogs).

## Checksum

A compact value computed from some bytes to detect accidental corruption. A matching checksum does not prove that the bytes are meaningful or protected against deliberate modification.

Learn it: [Checksums](../chapters/pages.md#checksums).

## Ciphertext

The bytes produced by encryption. Their protected meaning is recovered by decryption with the appropriate key.

Learn it: [Two files two footer modes](../chapters/modular_encryption.md#two-files-two-footer-modes).

## Coalescing

Merging nearby byte ranges into one read request. The reader fetches the gaps too, trading extra bytes for fewer requests.

Learn it: [One query request by request](../chapters/how_readers_read.md#one-query-request-by-request).

## Codec

A compression and decompression algorithm, such as Snappy, GZIP or ZSTD. A Parquet column chunk names its codec, but page rules determine which bytes are compressed; version-two level streams are not compressed.

Learn it: [One table six codecs](../chapters/compression.md#one-table-six-codecs).

## Column chunk

The pages for one leaf column in one row group, stored together. Its metadata locates the bytes; Parquet also allows a column chunk to be stored in another file, which this book’s reader does not support.

Learn it: [Use the footer as a map](../chapters/anatomy_of_a_parquet_file.md#use-the-footer-as-a-map).

## Column index

The page-index structure called `ColumnIndex`, which records page-level bounds and null information. It helps a reader decide which data pages cannot satisfy a condition.

Learn it: [The page index](../chapters/skipping_data.md#the-page-index).

## Column layout

Storing values from the same column together. Reading a few columns can then avoid the values in other columns, instead of passing through every complete row.

Learn it: [One table two layouts](../chapters/why_parquet_exists.md#one-table-two-layouts).

## Column order

Parquet footer metadata that declares how a column’s newer statistics bounds should be compared. Readers must check whether the declaration and the column’s type give those bounds a usable ordering.

Learn it: [What the footer records](../chapters/metadata_and_statistics.md#what-the-footer-records).

## Commit

Publishing a table change so readers can discover the new version. Writing a data file alone does not commit it to a table.

Learn it: [Commits and catalogs](../chapters/what_iceberg_adds.md#commits-and-catalogs).

## Compaction

Rewriting selected small files, or files with pending deletes, into a more suitable set of files. The rewrite costs work now and can reduce the work of later reads.

Learn it: [Compaction](../chapters/changing_a_table.md#compaction).

## Compression

Representing bytes in a form that takes less space by exploiting patterns. Parquet’s codecs are lossless: decompression restores the original encoded bytes.

Learn it: [Encoding before compression](../chapters/compression.md#encoding-before-compression).

## Compression level

A setting that changes how much work a compressor spends finding a smaller representation. Its effects depend on the codec and data; a higher setting does not promise a particular speed or size.

Learn it: [What each codec saved](../chapters/compression.md#what-each-codec-saved).

## Concurrency

Allowing several operations to be in progress at once. A reader can overlap independent requests, but it must still wait for information needed to construct a dependent request.

Learn it: [Phases](../chapters/how_readers_read.md#phases).

## Connection

A communication channel used to send requests and receive responses. The book’s model can use several connections to overlap independent reads.

Learn it: [One query request by request](../chapters/how_readers_read.md#one-query-request-by-request).

## Conservative bound

A limit that encloses every relevant value, even if the limit is not itself a stored value. A safely shortened string bound may support pruning without being the exact minimum or maximum.

Learn it: [What the footer records](../chapters/metadata_and_statistics.md#what-the-footer-records).

## Copy

In LZ77-style decompression, an instruction to reproduce bytes from earlier output using a distance and length. The copied region can overlap the new output as it grows.

Learn it: [Step through the tokens](../chapters/compression.md#step-through-the-tokens).

## Copy-on-write

Applying a change by writing replacement data files containing the new state. Readers use the replacements, while older snapshots may still refer to the original files.

Learn it: [Delete one order two ways](../chapters/changing_a_table.md#delete-one-order-two-ways).

## CRC

A cyclic redundancy check: a checksum designed to detect accidental changes to bytes. For the unencrypted pages studied here, Parquet’s optional page CRC covers the stored page body, not the page header.

Learn it: [Checksums](../chapters/pages.md#checksums).

## Data key

A key used to encrypt data. In envelope encryption, the data key is itself encrypted with another key so it can be stored or transported in protected form.

Learn it: [Keys by name](../chapters/modular_encryption.md#keys-by-name).

## Data page version 1

A Parquet data-page format whose body contains repetition levels, definition levels and encoded values. When compression is used, the codec applies to that whole body.

Learn it: [Data page version 1](../chapters/pages.md#data-page-version-1).

## Data page version 2

A Parquet data-page format that records the level-stream lengths in its header. The levels remain uncompressed, and the values portion may be compressed separately.

Learn it: [Data page version 2](../chapters/pages.md#data-page-version-2).

## Definition level

A number indicating how far a value’s path through optional and repeated fields is defined. A slot at the column’s maximum definition level has a stored value; lower levels distinguish missing fields or empty containers.

Learn it: [One nullable value](../chapters/nested_data.md#one-nullable-value).

## Delta encoding

Representing a first value followed by differences between successive values. Parquet’s integer delta encoding then groups and packs those differences; the first-value-and-differences idea alone is not its complete file format.

Learn it: [A first value then differences](../chapters/encodings.md#a-first-value-then-differences).

## Dependency phase

A group of requests a reader can plan from information it already has. In this book’s
lookup model, a phase finishes before the next begins. Requests within a phase can overlap,
but a connection limit can make them run in several waves, so a phase is not a network round trip.

Learn it: [Find one order](../chapters/changing_a_table.md#find-one-order).

## Dictionary encoding

Storing distinct values in a dictionary and representing occurrences by indices into it. A Parquet dictionary belongs to a column chunk; the same index can mean different values in different chunks.

Learn it: [Dictionary encoding](../chapters/encodings.md#dictionary-encoding).

## Dictionary index

An integer identifying an entry in a dictionary. Its meaning is local to that dictionary, so identical indices from different column chunks need not represent equal values.

Learn it: [Dictionary encoding](../chapters/encodings.md#dictionary-encoding).

## Dynamic filtering

Using values discovered while running one part of a query to restrict another part. A join can use keys found on its build side to rule out data on its probe side.

Learn it: [Joins](../chapters/what_a_query_engine_does.md#joins).

## Encoding

A defined way to represent values as bytes, such as PLAIN, dictionary indices or integer deltas. In a Parquet write path, encoding comes before general-purpose compression.

Learn it: [Read the encodings yourself](../chapters/encodings.md#read-the-encodings-yourself).

## Encryption

Transforming data so that recovering its protected contents requires the appropriate key. Encryption can leave some file structure or metadata visible, depending on what is protected.

Learn it: [Two files two footer modes](../chapters/modular_encryption.md#two-files-two-footer-modes).

## Encryption key

Secret material used by an encryption algorithm. A visible key name or wrapped key is not the same as having the usable secret key.

Learn it: [Keys by name](../chapters/modular_encryption.md#keys-by-name).

## Entropy coding

Representing frequent symbols with fewer bits than rare symbols. Huffman coding, used by DEFLATE, is one example.

Learn it: [Step through the tokens](../chapters/compression.md#step-through-the-tokens).

## Envelope encryption

Encrypting content with a data key, then encrypting that data key with another key. Access to the protected data key is controlled separately from storing the encrypted file.

Learn it: [Keys by name](../chapters/modular_encryption.md#keys-by-name).

## Exact bound

A lower or upper bound equal to the actual minimum or maximum of the relevant values. Exact bounds can support some metadata-only answers that conservative bounds cannot.

Learn it: [What the footer records](../chapters/metadata_and_statistics.md#what-the-footer-records).

## False negative

A test saying something is absent when it is present. A correctly constructed Bloom filter queried with compatible hashing must not give this result.

Learn it: [Bloom filters](../chapters/skipping_data.md#bloom-filters).

## False positive

A test saying something might be present when it is absent. Bloom filters permit this result, so a positive test does not prove that a matching row exists.

Learn it: [Bloom filters](../chapters/skipping_data.md#bloom-filters).

## Field id

A stable identifier assigned to a schema field. Iceberg preserves an id across a rename and does not reuse a dropped field’s id, so old files can be matched to the intended field.

Learn it: [Columns by id](../chapters/what_iceberg_adds.md#columns-by-id).

## Filter

An operation that retains rows satisfying a condition. Checking a value in each decoded row is different from using metadata to rule out an entire page or row group.

Learn it: [Filters](../chapters/what_a_query_engine_does.md#filters).

## Fixture

An example input kept with a project so examples and tests can be repeated. This book’s Parquet fixtures are written by pyarrow and checked against its descriptions of their contents.

Learn it: [The fixture files](#the-fixtures).

## Floating-point number

A numeric representation with sign, exponent and fraction fields. The exponent supplies a scale and the fraction supplies precision; special bit patterns represent infinities and NaNs.

Learn it: [Byte-stream split](../chapters/encodings.md#byte-stream-split).

## Footer

Metadata near the end of a Parquet file that describes its schema, row groups and column chunks. It contains the information a reader needs to locate and interpret data; an encrypted footer requires keys to read it.

Learn it: [Locate the footer](../chapters/anatomy_of_a_parquet_file.md#locate-the-footer).

## Footer length

The four-byte little-endian length field immediately before the closing magic. For an ordinary unencrypted file, it tells the reader how many bytes to step back to find the footer.

Learn it: [What the trailer says](../chapters/anatomy_of_a_parquet_file.md#what-the-trailer-says).

## Grouping

Collecting rows with the same grouping-key values so an aggregate can be calculated for each group. Dictionary indices can help, but their meanings must be reconciled across dictionaries.

Learn it: [Grouping](../chapters/what_a_query_engine_does.md#grouping).

## Half-open span

A range that includes its start and excludes its end, written `[start, end)`. Its length is `end - start`; the final included byte is at `end - 1`.

Learn it: [Locate the footer](../chapters/anatomy_of_a_parquet_file.md#locate-the-footer).

## Hash

A value computed from an input by a hash function, often used to choose a storage or lookup position. Equal inputs must give the same hash under the same rules; different inputs can share one.

Learn it: [Bloom filters](../chapters/skipping_data.md#bloom-filters).

## Hash collision

Two different inputs producing the same hash value. A hash-based test may therefore need another check before declaring the inputs equal.

Learn it: [Bloom filters](../chapters/skipping_data.md#bloom-filters).

## Hash join

A join that builds a hash table from one input and probes it with keys from the other. Matching hashes lead to candidate matches; the join still has to apply the key-equality rules.

Learn it: [Joins](../chapters/what_a_query_engine_does.md#joins).

## Hash table

A lookup structure that uses a hash to choose where to find a key and its associated values. It handles collisions so different keys remain distinguishable.

Learn it: [Joins](../chapters/what_a_query_engine_does.md#joins).

## Hexadecimal

Base-sixteen notation, using digits zero to nine and letters A to F. Two hexadecimal digits display one byte; changing the notation does not change the stored bits.

Learn it: [Before reading the bytes](../chapters/anatomy_of_a_parquet_file.md#before-reading-the-bytes).

## Hidden partitioning

Deriving partition values from data columns and recording that relationship in table metadata. Iceberg can translate a condition on the original column into a partition test without requiring the query to name a separate partition column.

Learn it: [Hidden partitioning](../chapters/what_iceberg_adds.md#hidden-partitioning).

## Histogram

Counts grouped into categories or ranges. Parquet size statistics can count definition or repetition levels, giving information about missing values and repeated containers.

Learn it: [What else the footer says](../chapters/metadata_and_statistics.md#what-else-the-footer-says).

## Hive-style partition

A directory convention such as `country=UK`, where the path supplies a partition value for the files beneath it. The book’s fixtures omit that column from their data files; the convention does not require every writer to do so.

Learn it: [Partitions are in the paths](../chapters/lakehouse_and_beyond.md#partitions-are-in-the-paths).

## Inner join

A join that returns only matching row combinations from its two inputs. Rows without a matching partner do not appear in its output.

Learn it: [Joins](../chapters/what_a_query_engine_does.md#joins).

## Join

Combining rows from separate inputs according to a matching condition. An equality join commonly matches rows with the same key value.

Learn it: [Joins](../chapters/what_a_query_engine_does.md#joins).

## Key management service

A service that controls access to encryption keys and operations on them. A reader may ask it to unwrap a protected key, subject to the service’s access rules.

Learn it: [Keys by name](../chapters/modular_encryption.md#keys-by-name).

## Key metadata

Information attached to protected content that helps a reader find or recover the appropriate key. Its representation depends on the implementation; it can include a key identifier and an encrypted data key, rather than a usable plaintext key.

Learn it: [Keys by name](../chapters/modular_encryption.md#keys-by-name).

## Key-encryption key

A key used to encrypt another key. In envelope encryption it protects a data key, rather than directly protecting all of the file’s values.

Learn it: [Keys by name](../chapters/modular_encryption.md#keys-by-name).

## Key-value store

A storage interface that retrieves a value by its key. Looking up one order is a similar access pattern, although a Parquet file does not itself provide a key-value index.

Learn it: [What one lookup costs](../chapters/changing_a_table.md#what-one-lookup-costs).

## Latency

The initial wait for a request’s response before its bytes start arriving. The book’s network model charges a fixed latency per request and adds the time needed to transfer the bytes.

Learn it: [Why the reader made the requests it did](../chapters/anatomy_of_a_parquet_file.md#why-the-reader-made-the-requests-it-did).

## Layout

The order and placement of stored values or bytes. A row layout and a column layout can contain the same values but place the values a query needs at different positions.

Learn it: [One table two layouts](../chapters/why_parquet_exists.md#one-table-two-layouts).

## Leaf

A schema field with no child fields, such as a nested integer or string. A Parquet column stores the values for a leaf path, together with the levels needed to reconstruct its nesting.

Learn it: [Rebuilt as a tree](../chapters/the_type_system.md#rebuilt-as-a-tree).

## Length prefix

A length stored before the content it describes. An encryption module can use a length prefix to tell a reader how many following bytes belong to that module.

Learn it: [Modules](../chapters/modular_encryption.md#modules).

## Literal

In a compression token stream, bytes stored directly for the decoder to copy into its output. A literal does not refer back to an earlier repeated sequence.

Learn it: [Step through the tokens](../chapters/compression.md#step-through-the-tokens).

## Little-endian

Storing a multi-byte integer with its least significant byte first. Parquet uses this order for its footer-length field and many other numeric fields.

Learn it: [What the trailer says](../chapters/anatomy_of_a_parquet_file.md#what-the-trailer-says).

## Logical type

An annotation describing how to interpret a physical value, such as a date, decimal or timestamp. The underlying bytes and the meaning assigned to them are separate choices.

Learn it: [Stored values and their meaning](../chapters/the_type_system.md#stored-values-and-their-meaning).

## LZ77

A compression approach that replaces repeated sequences with references to earlier output. Decoding a reference copies bytes from a stated distance back, possibly overlapping the bytes being written.

Learn it: [Step through the tokens](../chapters/compression.md#step-through-the-tokens).

## Magic

A fixed byte sequence used to recognise a file format, also called a file signature. Parquet uses `PAR1` for ordinary and plaintext-footer files, and `PARE` for encrypted-footer files; a matching signature alone does not validate the whole file.

Learn it: [Recognise the format](../chapters/anatomy_of_a_parquet_file.md#recognise-the-format).

## Manifest

In Iceberg, a metadata file listing data files or delete files and facts about each, such as partition values and column bounds. The reader consults manifests before opening the listed Parquet files.

Learn it: [The metadata tree](../chapters/what_iceberg_adds.md#the-metadata-tree).

## Manifest list

In Iceberg versions one to three, a snapshot’s list of manifests, with summary information about them. This is the metadata path taught by the book; it lets a planner rule out some manifests before reading their file entries.

Learn it: [The metadata tree](../chapters/what_iceberg_adds.md#the-metadata-tree).

## Merge-on-read

Recording changes separately and combining them with base data when reading. The book’s example uses position-delete files; other table formats can represent changes in other ways.

Learn it: [Delete one order two ways](../chapters/changing_a_table.md#delete-one-order-two-ways).

## Metadata

Information describing data or its organisation. A Parquet footer, for example, describes the table’s fields and where its column data is stored.

Learn it: [The same two columns from parquet](../chapters/why_parquet_exists.md#the-same-two-columns-from-parquet).

## Metadata file

In Iceberg versions one to three, the JSON file describing table properties, schemas and snapshots. Following its current snapshot leads to a manifest list and then manifests; newer format versions can use a different metadata path.

Learn it: [The metadata tree](../chapters/what_iceberg_adds.md#the-metadata-tree).

## Miniblock

A subdivision of an integer-delta block whose residual values share one bit width. Grouping widths this way lets Parquet pack small residuals more tightly.

Learn it: [A first value then differences](../chapters/encodings.md#a-first-value-then-differences).

## Module

In Parquet modular encryption, an individually protected part of a file, such as a page body or footer. Modules are encrypted or authenticated separately, so a reader can access selected parts with the appropriate keys.

Learn it: [Modules](../chapters/modular_encryption.md#modules).

## NaN

A floating-point value meaning “not a number”. NaN does not follow ordinary numeric ordering, so a reader must handle its effect on statistics separately.

Learn it: [Floating point](../chapters/metadata_and_statistics.md#floating-point).

## Nonce

A value that must be unique for each encryption operation using the same key in the AES-GCM scheme used here. It is stored with the encrypted content and is not the secret key.

Learn it: [Modules](../chapters/modular_encryption.md#modules).

## Null

An absent value. A null is distinct from a present empty string, a zero, or an empty list.

Learn it: [One nullable value](../chapters/nested_data.md#one-nullable-value).

## Object key

The name used to identify an object within an object store. A name such as `country=UK/part.parquet` can look like a directory path even when the store has no physical directories.

Learn it: [Partitions are in the paths](../chapters/lakehouse_and_beyond.md#partitions-are-in-the-paths).

## Object store

Storage that names objects by keys and serves their contents, often through HTTP. The book’s simulated store supports reading a whole object or selected byte ranges.

Learn it: [Why the reader made the requests it did](../chapters/anatomy_of_a_parquet_file.md#why-the-reader-made-the-requests-it-did).

## Offset

A position measured from a stated starting point. A file byte offset counts from zero at the start of the file; an offset within a page starts from that page instead.

Learn it: [Before reading the bytes](../chapters/anatomy_of_a_parquet_file.md#before-reading-the-bytes).

## Offset index

The page-index structure called `OffsetIndex`, which records where data pages are stored and the first row represented by each page. It connects page selection with byte ranges and row positions.

Learn it: [The page index](../chapters/skipping_data.md#the-page-index).

## Optimistic concurrency

Preparing a change on the assumption that it can commit, then checking whether conflicting work has changed the required starting state. A conflict may require validation, retry or rejection.

Learn it: [Commits and catalogs](../chapters/what_iceberg_adds.md#commits-and-catalogs).

## Page

A unit of a column chunk with a header describing the body that follows. Data pages hold encoded values and, where needed, nesting levels; a dictionary page holds dictionary values.

Learn it: [Use the footer as a map](../chapters/anatomy_of_a_parquet_file.md#use-the-footer-as-a-map).

## Page body

The bytes following a page header, up to the stored size the header declares. Their interpretation depends on the page kind, encoding, version and compression settings.

Learn it: [What a page header says](../chapters/pages.md#what-a-page-header-says).

## Page header

Metadata immediately before a page body that describes its kind, sizes and other page-specific fields. Reading the header tells the reader how to handle the body and where the next page can begin.

Learn it: [What a page header says](../chapters/pages.md#what-a-page-header-says).

## Page index

Optional metadata for locating data pages and ruling some out. Parquet separates page bounds and null information into `ColumnIndex`, and page locations and row positions into `OffsetIndex`.

Learn it: [The page index](../chapters/skipping_data.md#the-page-index).

## Partition

A group of rows assigned the same partition value, used to organise a table’s files. A query can rule out partitions when their values cannot satisfy its condition.

Learn it: [Partitions are in the paths](../chapters/lakehouse_and_beyond.md#partitions-are-in-the-paths).

## Partition spec

An Iceberg definition of how source columns are transformed into partition values. Old files retain their original spec when the table adopts a new one.

Learn it: [Hidden partitioning](../chapters/what_iceberg_adds.md#hidden-partitioning).

## Partition transform

The rule deriving a partition value from a source column, such as the day of a timestamp. Iceberg records the rule in a partition spec so a planner can interpret old and new files correctly.

Learn it: [Hidden partitioning](../chapters/what_iceberg_adds.md#hidden-partitioning).

## Percent-encoding

Representing a byte in a URL or path component with a percent sign followed by two hexadecimal digits. Decoding it recovers the original byte; decoding text can also require the appropriate character encoding.

Learn it: [Partition values from a path](../chapters/lakehouse_and_beyond.md#partition-values-from-a-path).

## Physical type

The basic representation of a stored value, such as an integer, floating-point number or byte array. A logical type can give that representation a more specific meaning.

Learn it: [Stored values and their meaning](../chapters/the_type_system.md#stored-values-and-their-meaning).

## PLAIN

Parquet’s direct encoding for a physical type, without dictionary or delta transformations. PLAIN is an encoding choice, not a statement that a page is uncompressed.

Learn it: [Read the encodings yourself](../chapters/encodings.md#read-the-encodings-yourself).

## Plaintext

Data in its readable, unencrypted representation. A plaintext Parquet footer can still describe columns whose values are encrypted.

Learn it: [Two files two footer modes](../chapters/modular_encryption.md#two-files-two-footer-modes).

## Point lookup

A query looking for a particular key, such as one order identifier. Parquet statistics can help narrow the search, but a column layout does not itself provide a key index.

Learn it: [What a query reads](../chapters/writing_parquet_well.md#what-a-query-reads).

## Position delete file

A file identifying rows to remove by data-file path and row position. A reader applies those deletions to the appropriate snapshot’s data files.

Learn it: [One snapshot one later delete](../chapters/changing_a_table.md#one-snapshot-one-later-delete).

## Precision

For a Parquet DECIMAL, the maximum number of decimal digits permitted in the value’s unscaled integer. Precision is a decimal-type constraint, not the byte width of its physical storage.

Learn it: [Read the schema yourself](../chapters/the_type_system.md#read-the-schema-yourself).

## Predicate

A condition a query tests, such as `order_id = 431`. Metadata may prove that a region cannot contain a row satisfying it; otherwise the reader must keep the region as a candidate.

Learn it: [When a range rules a condition out](../chapters/skipping_data.md#when-a-range-rules-a-condition-out).

## Predicate pushdown

Passing a query condition to the component that reads the data, so it can apply useful filtering work earlier. Metadata pruning is one possible optimisation; pushdown does not guarantee that data can be skipped.

Learn it: [Who does what](../chapters/what_a_query_engine_does.md#who-does-what).

## Prefetch

Reading bytes ahead of an immediate need in the hope of avoiding later requests. Reading a larger part of a file’s tail to obtain its footer early is one example; unused prefetched bytes add transfer cost.

Learn it: [Choose a tail strategy](../chapters/anatomy_of_a_parquet_file.md#choose-a-tail-strategy).

## Prefix

The beginning of a sequence. A string encoder can reuse a prefix from the previous byte string; an object-store listing can use a name prefix to find related keys.

Learn it: [The delta encodings for strings](../chapters/encodings.md#the-delta-encodings-for-strings).

## Probe side

The join input whose keys are used to look for matches in the build side’s lookup structure.

Learn it: [Joins](../chapters/what_a_query_engine_does.md#joins).

## Projection

Selecting the columns an operation needs. At a Parquet scan this can avoid fetching other columns’ data, but metadata and prefetching still affect the bytes transferred; conditions can require columns that do not appear in the final output.

Learn it: [The same two columns from parquet](../chapters/why_parquet_exists.md#the-same-two-columns-from-parquet).

## Pruning

Ruling out a file, row group or page because its metadata proves that it cannot contribute a matching row. Keeping a region means it might match, not that every row in it does.

Learn it: [When a range rules a condition out](../chapters/skipping_data.md#when-a-range-rules-a-condition-out).

## Query engine

Software that plans and executes a query, from reading inputs to producing an answer. It combines file reads with operations such as filtering, grouping, sorting and joining.

Learn it: [Who does what](../chapters/what_a_query_engine_does.md#who-does-what).

## Query plan

A description of the operations used to answer a query and how their inputs and results connect. A file reader performs the scan part; other operations can be performed above it.

Learn it: [Who does what](../chapters/what_a_query_engine_does.md#who-does-what).

## Range request

A request for part of an object. An HTTP `Range: bytes=a-b` request includes both endpoints, unlike the half-open spans used internally by the book’s reader.

Learn it: [Use the footer as a map](../chapters/anatomy_of_a_parquet_file.md#use-the-footer-as-a-map).

## Read amplification

Reading more data than the requested answer itself contains. For example, a point lookup may read page bodies and delete files to recover one surviving row.

Learn it: [What one lookup costs](../chapters/changing_a_table.md#what-one-lookup-costs).

## Reader

Software that interprets stored bytes to recover values and information about a file. Its read strategy determines which bytes it fetches and when.

Learn it: [How this book uses a reader](../index.md#what-this-book-is).

## Repetition level

A number describing which repeated part of a nested path continues from the preceding slot. A level of zero starts a new top-level record; deeper levels identify continuation inside repeated containers.

Learn it: [What the levels say](../chapters/nested_data.md#what-the-levels-say).

## Round trip

A request and the response needed before the next dependent step can proceed. Several independent requests can overlap; a chain of dependent requests cannot all start together.

Learn it: [Why the reader made the requests it did](../chapters/anatomy_of_a_parquet_file.md#why-the-reader-made-the-requests-it-did).

## Row group

A horizontal slice of a table containing a run of rows and a column chunk for each leaf column. It provides a boundary for organising writes, reads and statistics.

Learn it: [Use the footer as a map](../chapters/anatomy_of_a_parquet_file.md#use-the-footer-as-a-map).

## Row layout

Storing each row’s values together. Reading a complete record can then find its fields close together, while scanning one column passes through fields it does not need.

Learn it: [One table two layouts](../chapters/why_parquet_exists.md#one-table-two-layouts).

## Run-length encoding

Representing a run of equal values by the value and its repetition count. Parquet’s hybrid encoding combines such runs with bit-packed groups.

Learn it: [How the levels are stored](../chapters/nested_data.md#how-the-levels-are-stored).

## Scalar

One value rather than a container of child values. An integer or string is a scalar; a list or struct is a container.

Learn it: [One nullable value](../chapters/nested_data.md#one-nullable-value).

## Scale

For a Parquet DECIMAL, the number of decimal digits after the decimal point. The interpreted value is its stored unscaled integer divided by ten raised to the scale.

Learn it: [Read the schema yourself](../chapters/the_type_system.md#read-the-schema-yourself).

## Scan

The operation that reads a data source and produces rows or batches for a query. A scan can use projection and pruning, so it need not read every byte or return every row.

Learn it: [Who does what](../chapters/what_a_query_engine_does.md#who-does-what).

## Schema

A description of fields, their types and their nesting. A Parquet schema also records whether fields are required, optional or repeated.

Learn it: [Read the schema yourself](../chapters/the_type_system.md#read-the-schema-yourself).

## Schema evolution

Changing a table’s field description over time while existing files retain their original schemas. Stable field ids and compatible interpretation rules let a reader combine old and new files.

Learn it: [Columns by id](../chapters/what_iceberg_adds.md#columns-by-id).

## Schema group

A schema node containing child fields rather than directly storing scalar values. Following groups down to a leaf gives the path of a stored column.

Learn it: [Rebuilt as a tree](../chapters/the_type_system.md#rebuilt-as-a-tree).

## Schema path

The sequence of field names from the root of a nested schema to a particular field. A path to a leaf identifies the column whose values and nesting levels are stored.

Learn it: [Rebuilt as a tree](../chapters/the_type_system.md#rebuilt-as-a-tree).

## Selectivity

How much of an input satisfies a query condition. A condition matching very few rows is highly selective, but it saves reads only if the layout and metadata let the reader locate or rule out regions.

Learn it: [What a query reads](../chapters/writing_parquet_well.md#what-a-query-reads).

## Serialisation

Representing structured information as a sequence of bytes so it can be stored or transferred. Deserialisation reads those bytes back into the corresponding structures.

Learn it: [Reading the footer](../chapters/anatomy_of_a_parquet_file.md#reading-the-footer).

## Sign extension

Widening a signed two’s-complement integer by repeating its sign bit in the added high positions. This preserves the represented numeric value.

Learn it: [Reading a value through its logical type](../chapters/the_type_system.md#reading-a-value-through-its-logical-type).

## Signed integer

An integer representation that includes negative values as well as zero and positive values. The same stored bits can have a different value under an unsigned interpretation.

Learn it: [Stored values and their meaning](../chapters/the_type_system.md#stored-values-and-their-meaning).

## Slot

A position in a leaf column’s sequence of nesting information. A slot can mark a stored value, a missing value or an empty container, so slot count and stored-value count need not match.

Learn it: [One nullable value](../chapters/nested_data.md#one-nullable-value).

## Snapshot

One version of a table’s state. Table metadata identifies the data and applicable deletes for that version, allowing readers to use a consistent view while later changes are prepared.

Learn it: [One snapshot one later delete](../chapters/changing_a_table.md#one-snapshot-one-later-delete).

## Sort order

The comparison rule used to decide which of two values comes first. Parquet statistics need the order appropriate to the column’s type; an Iceberg table sort order instead specifies how writers should order rows by fields and directions.

Learn it: [Sort orders](../chapters/metadata_and_statistics.md#sort-orders).

## Statistics

Summary information about data, such as minimum and maximum values and null counts. Parquet may store these for column chunks and pages; missing or unusable bounds cannot safely rule out data.

Learn it: [Read the statistics yourself](../chapters/metadata_and_statistics.md#read-the-statistics-yourself).

## Stream

A sequence of items processed in order. A Parquet level stream is a sequence of small integers; a byte stream is a sequence of bytes.

Learn it: [The levels as stored](../chapters/nested_data.md#the-levels-as-stored).

## Suffix

The end of a sequence after a chosen starting point. In a delta-encoded string, the stored suffix follows the reused prefix; in a file request, a suffix is a range at the file’s end.

Learn it: [The delta encodings for strings](../chapters/encodings.md#the-delta-encodings-for-strings).

## Suffix range

A request for the last part of an object, such as HTTP `Range: bytes=-n` for its last `n` bytes. A successful partial response also reports the object’s total size.

Learn it: [Choose a tail strategy](../chapters/anatomy_of_a_parquet_file.md#choose-a-tail-strategy).

## Table format

Rules and metadata for managing a table across files and changes. A table format identifies the table’s current files and versions; Parquet describes the contents of individual files.

Learn it: [What the log adds beyond skipping](../chapters/lakehouse_and_beyond.md#what-the-log-adds-beyond-skipping).

## Table membership

The set of files that belong to a particular table version. A file can exist in storage without being part of that version; the table’s metadata determines membership.

Learn it: [What the log adds beyond skipping](../chapters/lakehouse_and_beyond.md#what-the-log-adds-beyond-skipping).

## Thrift compact protocol

A binary serialisation format used for Parquet metadata, including footer and page-header structures. It defines how fields, types and lengths are represented in bytes.

Learn it: [Reading the footer](../chapters/anatomy_of_a_parquet_file.md#reading-the-footer).

## Time travel

Reading a table as it was at an earlier recorded version. It requires the relevant metadata and data files to remain available; a snapshot name alone cannot recover deleted files.

Learn it: [Changing a table limits](../chapters/changing_a_table.md#changing-a-table-limits).

## Token

One instruction in a compressed stream, such as a literal or a reference to earlier output. The token tells the decoder which bytes to produce next.

Learn it: [Step through the tokens](../chapters/compression.md#step-through-the-tokens).

## Top-k

The first `k` results under a requested ordering, such as the highest amounts. Keeping only the current best candidates can reduce sorting work, but safe bounds or a known input order are needed to avoid examining other candidates.

Learn it: [Sorting with a limit](../chapters/what_a_query_engine_does.md#sorting-with-a-limit).

## Trailer

The final eight bytes of a Parquet file: a four-byte length followed by the closing four-byte magic. The trailer tells a reader where to begin finding the footer; it is a different region from the footer itself.

Learn it: [Locate the footer](../chapters/anatomy_of_a_parquet_file.md#locate-the-footer).

## Transaction log

An ordered record of committed table changes. Delta Lake uses log actions such as adding and removing data files; replaying the relevant history identifies which files belong to a table version.

Learn it: [Replay a small complete history](../chapters/lakehouse_and_beyond.md#replay-a-small-complete-history).

## Transform

A rule for deriving one value from another. An Iceberg partition transform can derive the day of a timestamp, for example, so the planner can relate a timestamp condition to partition values.

Learn it: [Hidden partitioning](../chapters/what_iceberg_adds.md#hidden-partitioning).

## Two’s complement

The signed-integer representation used for Parquet’s integer values. A leading zero bit denotes a non-negative value; negative values use patterns that let ordinary binary addition work for both signs.

Learn it: [Sort orders](../chapters/metadata_and_statistics.md#sort-orders).

## ULEB128

An unsigned variable-length integer representation. Each byte contributes seven value bits and uses its remaining bit to indicate whether another byte follows.

Learn it: [How the levels are stored](../chapters/nested_data.md#how-the-levels-are-stored).

## Unsigned integer

An integer representation containing zero and positive values, with no negative values. Comparing the same bits as signed integers can produce a different order.

Learn it: [Stored values and their meaning](../chapters/the_type_system.md#stored-values-and-their-meaning).

## UTC

Coordinated Universal Time, a common reference for timestamps representing instants. A Parquet timestamp marked as adjusted to UTC represents an instant; a local timestamp has different interpretation rules.

Learn it: [Stored values and their meaning](../chapters/the_type_system.md#stored-values-and-their-meaning).

## UTF-8

An encoding that represents Unicode text as bytes, using a variable number of bytes per character. A Parquet STRING annotation says that its byte-array values contain UTF-8 text.

Learn it: [Stored values and their meaning](../chapters/the_type_system.md#stored-values-and-their-meaning).

## Validity bitmap

A bitset marking which positions in an in-memory value array are present rather than null. Nested Parquet data uses definition and repetition levels to describe missing values and containers, rather than using one such bitmap for each list.

Learn it: [One nullable value](../chapters/nested_data.md#one-nullable-value).

## Varint

An integer representation whose byte length depends on the value. A continuation marker tells the decoder whether another byte is part of the same integer.

Learn it: [How the levels are stored](../chapters/nested_data.md#how-the-levels-are-stored).

## Vectorised processing

Applying an operation to batches of values instead of handling one complete row at a time. A column layout supplies same-typed values together, which can suit this processing style.

Learn it: [Why analytical queries favour columns](../chapters/why_parquet_exists.md#why-analytical-queries-favour-columns).

## Write amplification

Writing more data than the change itself contains. Replacing a whole file to update one value is an example.

Learn it: [Where the work is paid](../chapters/changing_a_table.md#where-the-work-is-paid).

## Zigzag

A mapping from signed integers to unsigned integers that keeps values near zero small in either direction. A variable-length integer representation can then store those small mapped values compactly.

Learn it: [Inspect a physical delta header](../chapters/encodings.md#inspect-a-physical-delta-header).
