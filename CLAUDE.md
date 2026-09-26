# CLAUDE.md

Project instructions for anyone, human or AI, working on this book. They are binding.

## What this is

*Parquet, byte by byte*: an interactive technical book about Apache Parquet in which the reader
builds a working Parquet reader while reading. Each chapter asks a question, answers it with an
experiment on the bytes of a real Parquet file, and builds the piece of the reader the experiment
needed. The reader exists twice, in Python and in Rust, held to identical answers by tests; the
page shows both, and the labs run either in the browser (Rust through WebAssembly, Python through
Pyodide).

Read **PLAN.md** for the argument and the settled decisions, **AUTHORING_GUIDE.md** before
writing or editing a page, and **STYLE.md** while editing. **NEXT_STEPS.md** is the working list.

The architecture follows `snowch/sizing-and-tco`: MyST parses, the repository renders, every
number is generated, code is quoted rather than pasted, and problems are tests. What differs is the
implementation. The Rust reader is compiled natively for the tests, the command line and the
figures, and to WebAssembly for the browser. The Python reader mirrors it module for module, for
readers who know Python better, and runs natively for its tests and in the page under Pyodide.
Either way the page runs the code the tests run.

## Architecture

```
                         THE BOOK (chapters/*.md)
                                   │
                ┌──────────────────┴──────────────────┐
           explanation                           experiment
      {literalinclude} of Rust              ```lab block in a page
      {include} of generated tables                    │
                └──────────────────┬──────────────────┘
                                   │
        crates/parquet-lab  (the reader)  ══ tests/test_python.py ══  python/parquet_lab
                                   │                                    │  (the same reader,
                                   │                                    │   in Python; pytest,
                                   │                                    │   Pyodide in the page)
        ┌──────────────┬───────────┼─────────────┬─────────────────┐
        │              │           │             │                 │
   cargo tests    crates/pqlab   crates/        exercises/      fixtures/
   (vs pyarrow    (CLI, and      parquet-lab-   (reader's       (written by
    manifests)    `figures`)     wasm (C ABI)   problems)        pyarrow)
                       │           │
          chapters/_generated/   web/lab/*.js  ── the browser draws what Rust returned
```

| Path | What it is |
|---|---|
| `crates/parquet-lab/` | The reader. Zero dependencies. One module per layer (see its `lib.rs`). |
| `python/parquet_lab/` | The same reader in Python, standard library only, module for module. Tests in `python/tests/`. |
| `crates/parquet-lab-wasm/` | The reader behind a numbers-only C ABI, compiled to `wasm32-unknown-unknown`. |
| `crates/pqlab/` | The reader on the command line (its commands in `cli.rs`, a library the WASM crate runs too), and `pqlab figures`, which writes every generated fragment. |
| `exercises/` | Problem stubs (`src/<slug>.rs`) and the `#[ignore]`d tests that grade them (`tests/<slug>.rs`); in Python, `python/<slug>.py` and `python/tests/test_<slug>.py`, run with `--problems`. |
| `fixtures/` | Parquet files written by pyarrow, each with a manifest (`.json`) pyarrow wrote about it. |
| `chapters/`, `parts/`, `appendices/`, `index.md` | The book, in MyST markdown. |
| `chapters/_generated/` | Fragments written by `pqlab figures`. Never edited by hand. |
| `tools/` | Python: the outline (`outline.py`), the renderer (`render.py`), the highlighter. |
| `scripts/` | Build and check entry points. `ci-check.sh` is what CI runs. |
| `web/` | The site stylesheet, and `web/lab/`: the browser half of the laboratory, the problems workbench and the reader editor. |
| `.devcontainer/` | The repository as a Codespace: the pinned toolchains, for editing and running the Rust reader online. |
| `tests/` | Python tests of the book, the renderer, WASM/native parity; `tests/browser/` drives Chromium. |

## Build, run, test

```bash
make install     # rustup wasm target, Python packages, pinned MyST
make             # wasm + figures + site: _build/html
make serve       # http://localhost:8000
make test        # cargo test --workspace, then pytest
make problems    # the reader's exercises, Python and Rust; they fail until solved
make check       # ./scripts/ci-check.sh: exactly what CI runs
```

Always run `make check` before pushing. It runs, in order: ruff, `cargo fmt --check`, clippy with
`-D warnings`, `cargo test`, the fixture check, the figures check, the number check, the WASM
build, the MyST parse, the site render, the link check, pytest (the book's tests, the Python
reader's, and the Python-Rust parity test), and the headless browser test.

## How the pieces talk

**MyST parses; this repository renders.** `scripts/parse-book.sh` runs `myst build --site --strict`,
which writes the parse to `_build/site/content/*.json` and resolves every cross-reference. MyST
then tries to fetch a site theme; this book never uses it, and the script tolerates that one
failure only. `scripts/build-site.py` renders the parse through `tools/render.py`, which raises on
any node type it does not handle.

**The browser calls Rust through a C ABI.** `crates/parquet-lab-wasm/src/lib.rs` exports
`pl_alloc`, `pl_load`, `pl_out_ptr`, `pl_set_byte`, one `pl_<experiment>` per lab, and `pl_cli`,
which runs `pqlab`'s own command code (`pqlab::cli`) on the loaded files. Arguments are numbers; files cross as a pointer and a length;
results come back as JSON in a buffer inside the module. `web/lab/wasm.js` is the other half.
The module imports nothing, so it cannot reach the network, the clock or the page.

**Every result is `parquet_lab::report`'s JSON.** The CLI prints it, the browser draws it, the
figures render it. `tests/test_wasm.py` makes every browser call twice, through WASM under Node and
natively through `pqlab`, and requires identical JSON. That test has already caught one real bug:
64-bit integers above 2^53 being rounded by JavaScript (`json.rs` now writes them as strings).

**The Python reader gives the Rust reader's answers.** `python/parquet_lab/report.py` writes the
same JSON as `report.rs`, and `tests/test_python.py` makes every call the Python engine supports
through both, on every fixture and on damaged copies, requiring identical JSON, key order and
error messages included. `python/parquet_lab/browser.py` is the Python engine's equivalent of the
C ABI; `web/lab/python.js` loads it into Pyodide (pinned, from a CDN) behind the same methods as
`wasm.js`. Its `EXPERIMENTS` names the labs it can run, which is every lab; the page offers the
Python engine for those, and a test requires them to be exactly the chapters' experiments.

**Experiments are fenced blocks.** A page embeds one with:

````markdown
```lab
experiment: footer
fixture: tiny.parquet
fixtures: tiny.parquet, multiple-row-groups.parquet
```
````

`tools/render.py` validates the experiment name and the fixtures and emits a mount point;
`web/lab/lab.js` loads the WASM module and the fixtures, relative to its own URL, and mounts it.

**Code runs where the reader is.** Every chapter's Problems section ends with a ```` ```problems ````
block (`chapter: <slug>`): a workbench (`web/lab/workbench.js`) where the reader edits the Python
stub and runs its graders with pytest under Pyodide, in a worker (`python-worker.js`, shared
through `runner.js`), on the repository's own files laid out as a desk has them. A `bash` block
whose every command the page can run gets a Run button (`web/lab/commands.js`): `python3 -m
pytest` on `python/tests` or `exercises/python` and `PYTHONPATH=python python3 -m parquet_lab` run
in that worker, and `cargo run -p pqlab -- …` runs through `pl_cli` in the WebAssembly reader,
printing what the binary prints (`tests/test_wasm.py` holds it to the byte). A block of commands
that need a compiler (`cargo test`, `make`) gets Open in Codespaces instead, never Run. On the Python engine, **Edit the code**
(`web/lab/editor.js`) swaps the reader's edits into the Python reader and remounts every lab.
Edits live in the browser's storage, never on the server. Rust cannot compile in a page, so
`.devcontainer/` gives a Codespace with the pinned toolchain instead, and on the Rust engine
**Edit the code** says which `crates/parquet-lab/src/*.rs` file to edit there and how to see the
labs on the edit (`make && make serve`). The browser test runs a workbench, Run buttons in both
languages against the same commands at a desk, and an edit.

## The invariants

1. **The interactive UI is a view of the implementation, never a scripted animation.** If the page
   says `GET bytes=249-628`, that range was requested from the object-store abstraction by the
   reader. If it says a footer length, the reader decoded it from the bytes on screen. The browser
   test checks this against the native reader.
2. **No number typed into prose.** Byte counts, offsets, request counts, times and ratios come from
   `pqlab figures` fragments `{include}`d into the page, or from a live experiment.
   `scripts/verify-numbers.py` fails the build otherwise. A definition that must be typed takes
   `% number-ok: <reason>` before its paragraph.
3. **No code pasted into prose.** Rust is quoted with `{literalinclude}` and `:start-at:` /
   `:end-before:` text anchors, never `:lines:`. A pasted Rust block fails `tests/test_book.py`. If
   you rename a function a page quotes, the MyST parse fails with a missing-anchor warning.
4. **Fixtures are written by a production implementation.** pyarrow, pinned in
   `requirements.txt`. The reader is tested against files it did not write, and against the
   manifest pyarrow wrote, never against its own output.
5. **Problems are tests.** Stubs in `exercises/src/<slug>.rs` with `todo!()`; tests in
   `exercises/tests/<slug>.rs` marked `#[ignore = "problem …"]`, deriving the expected answer at
   test time from the reader or the pyarrow manifest; unmarked scaffolding tests beside them
   proving the problem is answerable. Never commit a solution. Every chapter also has one problem
   about the reader's own files, which has no test and says what a good answer contains.
6. **Deterministic.** The object store is simulated, with a fixed `NetworkModel`; nothing reads a
   clock or a network. The same commit builds the same book, byte for byte.
7. **Two readers, one answer.** The Python and Rust readers cover every chapter: a chapter quotes
   every step in both languages in a `{tab-set}` (Python first, synced `python` and `rust`), ships
   its problems in both, and offers its labs on both engines. A change
   to one reader is made to the other in the same commit; the parity test fails otherwise.

## Adding things

**A chapter.** Add it to `tools/outline.py` (order, slug, title, part, question, what it builds,
experiments, fixtures), regenerate `myst.yml`'s toc to match (the test says how it differs), and
run `make chapter` for the skeleton. Then follow AUTHORING_GUIDE.md: problems first, then the
reader code, then figures, then prose. A chapter's number is derived from its position; its
identity is its slug. Never put a number in a slug, label or file name.

**A chapter's Python half.** A new chapter is written in both readers. Write the Python twin of
every Rust module the chapter adds in `python/parquet_lab/`, same names and same JSON; add their reports to `browser.py` and its `EXPERIMENTS`, their calls to
`tests/test_python.py` and methods to `web/lab/python.js`; port the Rust unit and fixture tests to
`python/tests/`; write the problems in `exercises/python/`; and put every excerpt in the chapter
in a tab set beside its Rust twin. `tests/test_book.py` checks the chapter's side of this.

**A fixture.** Add a `Fixture` to `fixtures/generate.py` with a `why`, run `make fixtures`, and
commit the `.parquet`, the `.json` manifest and the regenerated `fixtures/README.md` together.
Keep it small enough to read byte by byte. The Rust fixture tests pick it up automatically.

**An experiment.** Add a report function in `crates/parquet-lab/src/report.rs` that runs the reader
and returns JSON, and its twin in `python/parquet_lab/report.py`; export it from
`crates/parquet-lab-wasm` and `python/parquet_lab/browser.py`; add a method to `web/lab/wasm.js`
and `web/lab/python.js`, a mount function in `web/lab/`, its name to `EXPERIMENTS` in
`web/lab/lab.js` and `tools/outline.py`, a matching subcommand in `pqlab` and in
`python -m parquet_lab`, and its calls to `tests/test_wasm.py` and `tests/test_python.py`. JavaScript draws; it never
computes anything Parquet-shaped.

**A figure.** Add a `Figure` to `crates/pqlab/src/figures.rs` that runs the reader and returns
markdown ending with its conditions line, run `make figures`, and `{include}` the fragment.

## Coding conventions

- **Rust:** zero dependencies in every crate. Readable before fast: this code is quoted in a book.
  Every read reports a `Span` of absolute file offsets. Errors are values with offsets, never
  panics on bad input. `cargo fmt`, clippy clean with `-D warnings`. Module docs say what the
  module teaches and which chapter uses it.
- **JavaScript:** plain ES modules, no framework, no build step. It moves bytes and draws JSON.
- **Python reader:** standard library only, Python 3.11 and whatever Pyodide pins, so it runs
  unchanged at a desk and in the page. Idiomatic Python, not transliterated Rust: dataclasses,
  exceptions, `match`. It mirrors the Rust reader's modules, names and JSON. Errors are exceptions
  whose messages are the Rust `Display` text, because the page shows them and the parity test
  compares them. Readable before fast: this code is quoted in a book.
- **Python tooling:** the renderer, the scripts and the tests. `python3 -m pytest`, ruff clean.
- **Comments** say why, in full sentences, as in the reference repository.

## Book-writing conventions

British English, direct, active voice, short sentences, the reader as *you*. No em dashes. No
"In this chapter". No *simply*, *just*, *obviously*, *basically*: `tests/test_book.py` enforces
the list. Every chapter has the seven headings in `tools/outline.CHAPTER_SHAPE`. STYLE.md is the
checklist; run both of its passes over a page before finishing it.

Product and implementation names are allowed where the book describes a specific implementation's
behaviour (pyarrow wrote the fixtures; a reader's prefetch default). They are never used as
shorthand for the format itself, and the book never recommends a vendor.

## Things that break the build

- Renaming or reformatting a line a `{literalinclude}` anchors on. Search `chapters/` for the text.
- Changing the reader so a generated number moves, without `make figures`.
- Upgrading pyarrow without regenerating fixtures (the check refuses to run under another version).
- A new MyST directive or node type without a branch in `tools/render.py`.
- A root-relative URL (`/lab/...`) anywhere in a page: the site is served under a base path.
