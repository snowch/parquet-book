# Parquet, byte by byte

An interactive technical book about Apache Parquet, in which you build a working Parquet reader
while you read.

Each chapter asks one question about the format, answers it with an experiment on the bytes of a
real Parquet file, and builds the piece of the reader that experiment needed. The reader is
written twice, in Python and in Rust, each with no dependencies, and tests hold the two to
identical answers. The pages show every step in both languages, and the experiments run either
reader in the browser: Rust compiled to WebAssembly, or Python through Pyodide. Nothing in the
browser is a scripted animation: every byte range, request and decoded value on screen was
computed by the reader.

Both readers cover every chapter.

## Build and read it

```bash
git clone https://github.com/snowch/parquet-book
cd parquet-book
make install    # one-off: wasm target, Python packages, pinned MyST
make            # reader, WebAssembly module, figures, site
make serve      # http://localhost:8000
```

You need a Rust toolchain, Python 3.11+, and Node.js 22. `make check` runs everything CI runs,
including a headless-browser test of the experiments if Playwright is installed.

## Use the reader

```bash
PYTHONPATH=python python3 -m parquet_lab footer fixtures/tiny.parquet   # the Python reader
python3 -m pytest python/tests tests/test_python.py                     # its tests, and parity with Rust
cargo run -p pqlab -- inspect fixtures/tiny.parquet     # the file's structure, as a tree
cargo run -p pqlab -- footer fixtures/tiny.parquet      # open it through the simulated store
cargo test --workspace                                  # the reader's tests
make problems                                           # the chapter exercises (fail until solved)
```

## What is here

| Path | |
|---|---|
| `crates/parquet-lab/` | the reader |
| `python/parquet_lab/` | the same reader in Python |
| `crates/parquet-lab-wasm/` | the reader for the browser, behind a small C ABI |
| `crates/pqlab/` | the reader on the command line, and the generator of every figure |
| `exercises/` | the problems: stubs, and the tests that grade them |
| `fixtures/` | small Parquet files written by pyarrow, with pyarrow's own description of each |
| `chapters/`, `parts/`, `appendices/` | the book, in MyST markdown |
| `web/` | the site stylesheet and the browser laboratory |
| `tools/`, `scripts/`, `tests/` | the renderer, the build, and the checks |

## Status

Every chapter is written, from ch01 (row and column layouts) to ch14 (lakehouse and beyond),
with working experiments and graded problems. See `PLAN.md` for the plan and `NEXT_STEPS.md` for
what could come next.

## Contributing

Read `CLAUDE.md` first: it holds the rules the build enforces. Then `AUTHORING_GUIDE.md` and
`STYLE.md`.

## Licence

The text is CC BY-NC 4.0. The code is Apache 2.0.
