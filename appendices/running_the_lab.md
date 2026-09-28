---
title: Running the lab
---

(running-the-lab)=
# Running the lab

## In your browser

Nothing to install. Every chapter from ch02 on opens its problems with a workbench, where you edit the Python
problems and run their tests: pytest runs in the page, under Pyodide, with the same tests a desk
runs. A Python command in these pages that runs the reader's tests, a problem's tests or the
reader's command line has a **Run** button, which runs it in the page and shows what it printed;
a problem's tests run on your answers from its chapter's workbench. Every walkthrough step has
**Edit** and **Run**: change the step and run your version in the page. Your answers and edits
stay in your browser.

The `cargo run -p pqlab` commands below have a Run button too. The page runs them on the Rust
reader compiled to WebAssembly, the one that draws the pictures, and they print what they print
at a desk.

Rust cannot compile inside a web page, so editing the Rust reader, and every other Rust command,
needs a compiler. Their blocks have an **Open in Codespaces** button, and so does every Rust
walkthrough step: [GitHub Codespaces](https://codespaces.new/snowch/parquet-book?quickstart=1)
opens the repository with an editor, the pinned toolchain and every dependency, in the browser.
Edit a file there and run the command in its terminal; `make && make serve` shows the book with
every picture drawn by your edited reader. The configuration is in `.devcontainer/`, and works
in any editor that supports dev containers.

A Codespace runs on your own GitHub account, not the book's. Personal accounts get a free
allowance of use each month; past it, GitHub blocks further use unless you have set up billing,
and then charges you. [GitHub's billing page](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)
has the current terms. Stop or delete a Codespace when you are done with it: a stopped one still
counts against the storage allowance.

(two-pyarrows)=
## Two versions of pyarrow

The *Ask a library* steps run pyarrow, and the pyarrow in the page is older than the one at a
desk. That is not a choice the book makes twice. At a desk, `requirements.txt` pins the pyarrow
that wrote every fixture, and the build refuses to run under any other, so the files and every
number measured from them come out the same on every machine. In the page, pyarrow is whatever
the book's pinned Pyodide release ships. pyarrow is compiled C++, not pure Python, so the page
cannot install another version the way it installs a pure-Python package; it takes the build
Pyodide made for WebAssembly, which trails the desk's.

For almost every step the two give the same output, and the tests check the steps at a desk. Where
they differ, the chapter says so beside the step: a field the older version does not report
([ch09](#skipping-data)), reads the WebAssembly build does not merge ([ch10](#how-readers-read)),
and a writer option it does not have ([ch11](#writing-parquet-well)). When a Pyodide release
ships a newer pyarrow, the book moves to it and those notes go.

## What you need

At a desk, to read and run the book's reader in Python, Python 3.11 or later is enough: the
Python reader and its tests use the standard library, and pytest. Everything below that builds
the site needs the rest.

- A Rust toolchain, with the WebAssembly target: `rustup target add wasm32-unknown-unknown`.
- Python 3.11 or later, with the packages in `requirements.txt` for building the site and
  `requirements-dev.txt` for the tests.
- Node.js and the pinned MyST command-line tool, which parses the pages:
  `npm install -g mystmd@1.10.1`.

Neither reader has dependencies outside the repository, so both build and run offline. The page
runs Python through Pyodide, which it fetches from a public CDN the first time you run Python in
the page.

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
