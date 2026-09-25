//! The reader's problems. One module per chapter, named for the chapter's slug.
//!
//! Each function below is a stub with its problem statement as its documentation. The tests in
//! `exercises/tests/<slug>.rs` say whether your version is right. They are marked `#[ignore]`, so
//! a plain `cargo test` skips them and stays green; run them with
//!
//! ```text
//! cargo test -p exercises --test <slug> -- --ignored
//! ```
//!
//! and they fail until you have solved the problem. That is the point.
//!
//! No test stores an answer. Each one computes what it expects at test time, from the book's own
//! reader (`parquet-lab`) or from what pyarrow reported when it wrote the fixture, and compares
//! your function against it across many cases.

pub mod anatomy_of_a_parquet_file;
pub mod compression;
pub mod encodings;
pub mod how_readers_read;
pub mod metadata_and_statistics;
pub mod nested_data;
pub mod pages;
pub mod skipping_data;
pub mod the_type_system;
pub mod why_parquet_exists;
