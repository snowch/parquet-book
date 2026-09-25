---
title: Running the lab
---

(running-the-lab)=
# Running the lab

## What you need

- A Rust toolchain, with the WebAssembly target: `rustup target add wasm32-unknown-unknown`.
- Python 3.11 or later, with the packages in `requirements.txt` for building the site and
  `requirements-dev.txt` for the tests.
- Node.js and the pinned MyST command-line tool, which parses the pages:
  `npm install -g mystmd@1.10.1`.

The reader itself has no dependencies outside the repository, so the Rust half builds offline.

## Building and serving the book

```bash
git clone https://github.com/snowch/parquet-book
cd parquet-book
make            # build the reader, the WebAssembly module, the figures and the site
make serve      # serve the book at http://localhost:8000
```

`make check` runs everything continuous integration runs.

## Running the reader at a desk

The command-line reader prints what the browser shows:

```bash
cargo run -p pqlab -- inspect fixtures/tiny.parquet
cargo run -p pqlab -- footer fixtures/tiny.parquet
cargo run -p pqlab -- footer fixtures/tiny.parquet --size suffix --prefetch 65536
cargo run -p pqlab -- interpret fixtures/tiny.parquet 629
```

## Solving the problems

Each chapter's problems are stubs in `exercises/src/<chapter>.rs`. Their tests are marked
`#[ignore]`, so `cargo test` passes before you start. Run a chapter's problems with:

```bash
cargo test -p exercises --test anatomy_of_a_parquet_file -- --ignored
```

and `make problems` runs them all. They fail until you solve them.
