---
title: Running the lab
---

(running-the-lab)=
# Running the lab

Reading the book does not require these tools. Worked results and diagrams are visible without
running anything. Use this appendix when you want to explore code or build the reader.
For a first example, open [the footer-reader lab](build-footer-reader.html). Its
code follows the [worked footer calculations](locate-the-footer.html).

## In your browser

The page prepares the example files. Open **Read or run the code**, select **Python**, then
select **Run** for the code shown. The output appears below the code. To try a change, use
**Edit** and then **Run** again. **Show original** switches back to the book's code.
**Return to edit** reopens your draft.

On a build-lab page, open **Edit Python solutions and run tests** to work on the coding
problems. Edit the unfinished functions, select **Run the tests** and read the results
under the editor. A failed check describes an unmet expectation in your solution. If the test
runner cannot complete its work, read **Full test output** for the error. The page uses the
same tests as a local installation. Python commands elsewhere on the page also use the active
answers saved in the build lab.

The browser keeps your active drafts on this device when storage is available. Use **Download code**
in a build lab to keep a separate copy. If the browser cannot save a walkthrough edit, copy the
text before leaving the page.

The `cargo run -p pqlab` commands below have a Run button too. The page runs them on the Rust
reader compiled to WebAssembly, a program format browsers can execute. This is the reader
that draws the pictures, and its commands print what they print at a desk.

To compile Rust or run a changed Rust walkthrough, use a local Rust compiler or
**Open in Codespaces** in the Rust tab. [GitHub Codespaces](https://codespaces.new/snowch/parquet-book?quickstart=1)
opens the repository with an editor and terminal. Open the file named above the example,
make your change, then run the command shown or copied by the page in the Codespace terminal.
Use `make && make serve` there to view the book with diagrams drawn by your edited reader.

A Codespace runs on your own GitHub account, not the book's. Personal accounts get a free
allowance of use each month; past it, GitHub blocks further use unless you have set up billing,
and then charges you. [GitHub's billing page](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)
has the current terms. Stop or delete a Codespace when you are done with it: a stopped one still
counts against the storage allowance.

(two-pyarrows)=
## Two versions of pyarrow

The *Ask a library* steps use pyarrow. The browser runs the version bundled with Pyodide, the
browser's Python runtime. `requirements.txt` specifies a newer desktop version, which also
generates the book's example files and saved outputs.

For almost every step the two give the same output, and the tests check the steps at a desk. Where
they differ, the chapter says so beside the step: a field the older version does not report
([ch09](#skipping-data)), reads the WebAssembly build does not merge ([ch10](#how-readers-read)),
and a writer option it does not have ([ch11](#writing-parquet-well)). When a Pyodide release
ships a newer pyarrow, the book moves to it and those notes go.

## What you need

To run the Python reader locally, use Python 3.11 or later. Install pytest to run its tests.
To build the site or generate its results, install the following tools.

- A Rust toolchain, with the WebAssembly target: `rustup target add wasm32-unknown-unknown`.
- Python 3.11 or later, with the packages in `requirements.txt` for building the site and
  `requirements-dev.txt` for the tests.
- Node.js and the pinned MyST command-line tool, which parses the pages:
  `npm install -g mystmd@1.10.1`.

After installing the toolchains, the book's own readers can run offline. The first Python run
in a browser downloads Pyodide. The first example that uses pyarrow downloads that library too.

## Building and serving the book

```bash
git clone https://github.com/snowch/parquet-book
cd parquet-book
make            # build the reader, the WebAssembly module, the figures and the site
make serve      # serve the book at http://localhost:8000
```

`make check` runs the repository’s automated checks. Continuous integration runs the same checks
when a change is pushed to the repository.

## Running the reader at a desk

The commands here inspect `tiny.parquet`, the file in
[the footer byte-map example](read-the-footer-map.html), and reproduce
[the footer request experiment](trace-footer-requests.html).
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

The [footer-reader lab](build-footer-reader.html#problems) lists the tasks. To solve them at a
desk, edit `exercises/python/anatomy_of_a_parquet_file.py` or
`exercises/src/anatomy_of_a_parquet_file.rs`. Then run the matching command below from the
repository root. These commands include the exercise tests, which a plain test run skips.

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

Use `make problems` to run the exercise tests for all build labs.
