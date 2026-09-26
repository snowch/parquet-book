//! # parquet-lab
//!
//! A Parquet reader small enough to read in full, built in the order the book teaches it.
//!
//! Each module is a layer, and each layer uses only the ones above it in this list:
//!
//! | Module | What it does | Chapter |
//! |---|---|---|
//! | [`layout`] | one table stored by rows and by columns | ch01 |
//! | [`bytes`] | little-endian integers, varints, zigzag, spans | ch02 |
//! | [`format`] | the magic bytes, the trailer, where the footer is | ch02 |
//! | [`thrift`] | Thrift's compact protocol, decoded without a schema | ch02 |
//! | [`parquet_thrift`] | the names `parquet.thrift` gives to field ids | ch03 |
//! | [`logical`] | logical types, and what they make of a value's bytes | ch03 |
//! | [`metadata`] | `FileMetaData` as Rust types | ch03, ch08 |
//! | [`stats`] | sort orders, and which statistics a reader may use | ch08 |
//! | [`schema`] | the schema tree, leaf paths, and maximum levels | ch03 |
//! | [`pages`] | walking a column chunk's page headers | ch06 |
//! | [`rle`] | the RLE / bit-packing hybrid, for levels and indices | ch04, ch05 |
//! | [`plain`] | PLAIN values, with the bytes of each | ch04, ch05 |
//! | [`decode`] | any encoding's values, with the steps and bytes of each | ch05 |
//! | [`delta`] | DELTA_BINARY_PACKED, the byte-array deltas, BYTE_STREAM_SPLIT | ch05 |
//! | [`compress`] | SNAPPY, LZ4_RAW and GZIP pages decompressed, token by token | ch07 |
//! | [`column`] | a column chunk read into (repetition, definition, value) triples | ch04 |
//! | [`nested`] | what the levels mean, and records rebuilt from them | ch04 |
//! | [`encoding`] | turning encoded bytes back into values | ch05 |
//! | [`object_store`] | a simulated S3: `HEAD`, `GET`, ranges, and a trace | ch02, ch10 |
//! | [`reader`] | opening a file in an object store | ch02, ch10 |
//! | [`prune`] | conditions judged against metadata: what a reader may skip | ch09 |
//! | [`scan`] | a query's requests: phases, merged ranges, connections | ch10 |
//! | [`engine`] | SQL over the reader: scan, filter, aggregate, sort, limit | ch12 |
//! | [`table`] | a table of many files: listing, partitions, a log | ch14 |
//! | [`changes`] | a changing table: lookups, delete files, compaction | ch15 |
//! | [`report`] | what the reader did, as JSON for the browser and the book | all |
//!
//! ## What it does not do yet
//!
//! The book grows this crate chapter by chapter, and `PLAN.md` lists what each chapter adds.
//! Today it finds and decodes the footer, walks pages, decompresses SNAPPY, LZ4_RAW and GZIP
//! pages, decodes every encoding writers use, and checks statistics against their types' sort
//! orders. It does not decompress ZSTD or BROTLI, evaluate
//! predicates, or decrypt. A file that needs any of those still
//! opens, and the missing step is reported as missing rather than guessed at.
//!
//! The crate has no dependencies. It is compiled natively for the tests and the command line,
//! and to WebAssembly for the browser, from the same source.

pub mod bloom;
pub mod bytes;
pub mod changes;
pub mod column;
pub mod compress;
pub mod crypto;
pub mod decode;
pub mod delta;
pub mod encoding;
pub mod engine;
pub mod format;
pub mod json;
pub mod layout;
pub mod logical;
pub mod metadata;
pub mod nested;
pub mod object_store;
pub mod page_index;
pub mod pages;
pub mod parquet_thrift;
pub mod plain;
pub mod prune;
pub mod reader;
pub mod report;
pub mod rle;
pub mod scan;
pub mod schema;
pub mod stats;
pub mod table;
pub mod thrift;
