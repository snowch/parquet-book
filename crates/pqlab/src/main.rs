//! `pqlab`: the book's Parquet reader on the command line.
//!
//! ```text
//! pqlab inspect FILE                 the structure of a file, as an indented tree
//! pqlab footer FILE [options]        open FILE through the simulated object store
//! pqlab structure FILE               the structure, as JSON
//! pqlab pages FILE COLUMN           every page of one column chunk
//! pqlab table LISTING SQL [--discovery list|prune|log] [--connections N]
//!                                    SQL over a table of files; LISTING is fixtures/table.json
//! pqlab encryption FILE             what a reader without keys can see
//! pqlab query FILE SQL             SQL answered from the file, stage by stage
//! pqlab scan FILE [--where COLUMN OP VALUE] [--columns 0,2] [--size head|suffix] [--prefetch N]
//!            [--connections N] [--gap BYTES] [--chunks] [--use ...] [--latency-us N] [--bandwidth N]
//!                                    a query through the simulated object store
//! pqlab skipping FILE COLUMN OP [VALUE] [--use statistics,bloom,page-index]
//!                                    what a condition lets the reader skip
//! pqlab statistics FILE ROW_GROUP COLUMN
//!                                    every chunk's statistics, and one in detail
//! pqlab compression FILE COLUMN [PAGE]
//!                                    the codec's effect, and one page decompressed
//! pqlab encodings FILE COLUMN       how one column's values are encoded, step by step
//! pqlab levels FILE COLUMN          one column's levels, values and rebuilt records
//! pqlab schema FILE                  the schema: flat, rebuilt, and read through logical types
//! pqlab interpret FILE OFFSET        every reading of the bytes at OFFSET, as JSON
//! pqlab layouts --columns 2,3 [--row N]
//!                                    ch01's row and column layouts, queried, as JSON
//! pqlab figures [--out DIR] [--check]
//!                                    write the book's generated fragments, or check them
//! ```
//!
//! `footer` takes `--size head|known|suffix`, `--prefetch BYTES`, `--latency-us N`,
//! `--bandwidth BYTES_PER_SEC` and `--json`.
//!
//! Every subcommand prints what `parquet_lab::report` returns: the same JSON the browser gets
//! from the WebAssembly build.

mod figures;

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use pqlab::cli::{self, USAGE};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("figures") {
        let flag = |name: &str| {
            args.iter()
                .position(|a| a == name)
                .and_then(|i| args.get(i + 1))
        };
        let out = PathBuf::from(flag("--out").map_or("chapters/_generated", String::as_str));
        let check = args.iter().any(|a| a == "--check");
        return figures::run(Path::new("."), &out, check).unwrap_or_else(|message| {
            eprintln!("pqlab: {message}");
            ExitCode::from(2)
        });
    }
    let mut out = String::new();
    let result = cli::run(&args, &read, &mut out);
    // A closed pipe (`pqlab inspect FILE | head`) is not an error, so a failed write is ignored.
    let _ = std::io::stdout().write_all(out.as_bytes());
    match result {
        Ok(code) => ExitCode::from(code),
        Err(message) => {
            eprintln!("pqlab: {message}");
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
    }
}

fn read(path: &str) -> Result<Vec<u8>, String> {
    std::fs::read(path).map_err(|e| format!("cannot read {path}: {e}"))
}
