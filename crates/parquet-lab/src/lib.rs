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
//! | [`schema`] | the schema tree, leaf paths, and maximum levels | ch03 |
//! | [`pages`] | walking a column chunk's page headers | ch06 |
//! | [`encoding`] | turning encoded bytes back into values | ch05 |
//! | [`object_store`] | a simulated S3: `HEAD`, `GET`, ranges, and a trace | ch02, ch10 |
//! | [`reader`] | opening a file in an object store | ch02, ch10 |
//! | [`report`] | what the reader did, as JSON for the browser and the book | all |
//!
//! ## What it does not do yet
//!
//! The book grows this crate chapter by chapter, and `PLAN.md` lists what each chapter adds.
//! Today it finds and decodes the footer and walks page headers. It does not decode page
//! values, decompress, evaluate predicates, or decrypt. A file that needs any of those still
//! opens, and the missing step is reported as missing rather than guessed at.
//!
//! The crate has no dependencies. It is compiled natively for the tests and the command line,
//! and to WebAssembly for the browser, from the same source.

pub mod bytes;
pub mod encoding;
pub mod format;
pub mod json;
pub mod layout;
pub mod logical;
pub mod metadata;
pub mod object_store;
pub mod pages;
pub mod parquet_thrift;
pub mod reader;
pub mod report;
pub mod schema;
pub mod thrift;
