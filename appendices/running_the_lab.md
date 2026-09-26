---
title: Running the lab
---

(running-the-lab)=
# Running the lab

## In your browser

Nothing to install. Every chapter ends its problems with a workbench, where you edit the Python
problems and run their tests: pytest runs in the page, under Pyodide, with the same tests a desk
runs. A Python command in these pages that runs the reader's tests, a problem's tests or the
reader's command line has a **Run** button, which runs it in the page and shows what it printed;
a problem's tests run on your answers from its chapter's workbench. On any lab, choose **Python**, then **Edit the code**, and you can change any file of the
Python reader and run the page's labs on your edit. Your edits stay in your browser until you
restore them.

Rust cannot compile inside a web page. For the Rust reader, open the repository in
[GitHub Codespaces](https://codespaces.new/snowch/parquet-book?quickstart=1): an editor, the
pinned toolchain and every dependency, in the browser, ready for every command below. The
configuration is in `.devcontainer/`, and works in any editor that supports dev containers.

## What you need

At a desk, to read and run the book's reader in Python, Python 3.11 or later is enough: the
Python reader and its tests use the standard library, and pytest. Everything below that builds
the site needs the rest.

- A Rust toolchain, with the WebAssembly target: `rustup target add wasm32-unknown-unknown`.
- Python 3.11 or later, with the packages in `requirements.txt` for building the site and
  `requirements-dev.txt` for the tests.
- Node.js and the pinned MyST command-line tool, which parses the pages:
  `npm install -g mystmd@1.10.1`.

Neither reader has dependencies outside the repository, so both build and run offline. The labs
can run the Python reader in the page too, through Pyodide, which the page fetches from a public
CDN the first time you choose Python.

## Building and serving the book

```bash
git clone https://github.com/snowch/parquet-book
cd parquet-book
make            # build the reader, the WebAssembly module, the figures and the site
make serve      # serve the book at http://localhost:8000
```

`make check` runs everything continuous integration runs.

## Running the reader at a desk

Each reader has a command line that prints what the browser shows, as the same JSON:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
PYTHONPATH=python python3 -m parquet_lab structure fixtures/tiny.parquet
PYTHONPATH=python python3 -m parquet_lab footer fixtures/tiny.parquet
PYTHONPATH=python python3 -m parquet_lab footer fixtures/tiny.parquet --size suffix --prefetch 65536
PYTHONPATH=python python3 -m parquet_lab interpret fixtures/tiny.parquet 629
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo run -p pqlab -- inspect fixtures/tiny.parquet
cargo run -p pqlab -- footer fixtures/tiny.parquet --json
cargo run -p pqlab -- footer fixtures/tiny.parquet --size suffix --prefetch 65536 --json
cargo run -p pqlab -- interpret fixtures/tiny.parquet 629
```
:::
::::

Both readers cover every chapter. The commands the chapters mention, such as `statistics`,
`skipping`, `scan`, `query`, `encryption` and `table`, are the same in each, and `--help` lists
them.

## Solving the problems

Each chapter's problems are stubs in Python, in `exercises/python/<chapter>.py`, and in Rust, in
`exercises/src/<chapter>.rs`. Their tests are
skipped by a plain test run, so the suite passes before you start. Run a chapter's problems with:

::::{tab-set}
:::{tab-item} Python
:sync: python
```bash
python3 -m pytest exercises/python/tests/test_anatomy_of_a_parquet_file.py --problems
```
:::
:::{tab-item} Rust
:sync: rust
```bash
cargo test -p exercises --test anatomy_of_a_parquet_file -- --ignored
```
:::
::::

and `make problems` runs them all. They fail until you solve them.
