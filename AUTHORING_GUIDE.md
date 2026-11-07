# Authoring Guide

How to write a chapter of *Parquet, byte by byte* without breaking the three things that make it
worth reading: experiments that are views of the real reader, numbers the build computes, and
problems that cannot lie about whether you solved them.

## Quick start

```bash
make install     # wasm target, Python packages, pinned MyST
make             # build everything into _build/html
make serve       # read it at http://localhost:8000
make check       # exactly what CI runs
```

`make` rebuilds the site in a few seconds. There is no live preview: re-run `make site` after an
edit and reload the page.

## The order to write in

Not the order the chapter is read in.

1. **The reader code.** Add the piece of `crates/parquet-lab` the chapter builds, with unit tests
   and, where a fixture can check it, a test against the pyarrow manifest in
   `crates/parquet-lab/tests/fixtures.rs`. If the chapter needs a new fixture, write it first
   (`fixtures/generate.py`), and say in its `why` what it exists to show. For a chapter the
   Python reader covers, write the same piece in `python/parquet_lab`, with the same JSON, and add
   its calls to `tests/test_python.py`: the two readers must agree before either is quoted.
2. **The problems and their tests.** Stubs in `exercises/src/<slug>.rs`, tests in
   `exercises/tests/<slug>.rs`. Make each fail, and read the failure: it is the first thing a
   reader sees, and it should say where to look. Then solve each one *outside the repository* and
   check it passes. Never commit the solution. Every chapter has the same problems in
   `exercises/python/`, marked `@pytest.mark.problem`, graded the same way.
3. **The experiment.** The walkthrough steps (below), and a panel only where a picture beats
   printed output: a report function that runs the reader, a WASM export, and a mount function in
   `web/lab/`. A panel is a picture and nothing else: the Rust reader, compiled to WebAssembly,
   draws it, and it offers no choice of engine and no editor. The Python reader runs in the page
   in the steps, the Run buttons and the workbench. See CLAUDE.md, *Adding things*.
4. **The figures.** Every number the prose will need, as a fragment from `pqlab figures`.
5. **The prose**, last, to serve all of the above.

Writing the prose first produces a chapter that explains what you meant to build.

## The seven sections

`tools/outline.CHAPTER_SHAPE`, and not negotiable; `tests/test_book.py` fails a chapter that adds or
loses one. A section the chapter needs and the shape lacks is a `###` inside one of them.

A chapter that explains and builds nothing (`tools/outline.EXPLAINERS`: ch01, ch12 and ch16)
drops *Building it*. ch01 comes before there is a file to open; ch12 describes what a query engine
does with a file, and how an engine works inside would take a book of its own; ch16 maps what
Apache Iceberg adds above Parquet files to the chapters that show it, and Iceberg in depth would
take another. Such a chapter quotes
no reader code: its code is walkthrough steps, which may call the reader. Its problems are
questions with no tests, each saying what a good answer contains, and it has no workbench. Keep
it light. Do not make a chapter an explainer to dodge building something.

**The question** is one question in one sentence, then a paragraph on why the previous chapter
leaves it open. The outline holds the question; the page expands it.

**The experiment** opens with a walkthrough (below): the reader reads the chapter's structure out
of a fixture by hand, in a few lines of code they run and change. The audience is data engineers,
and the worked result is their entry point. The renderer shows the saved Python output before
the optional source code. Then show the reader's view of the same bytes:
generated tables, and a `lab` block where a picture beats printed output (a byte map, a request
timeline, row groups lit by a predicate), with a numbered list of things to try, each saying what
to click and what to look for. Write it so a reader who does each step in order discovers the
chapter's point before being told it. Finish with short sections that name what was seen.

**Building it** quotes the code the experiment ran, in the order it ran. Mark the section as optional and link to the limitations for readers following the conceptual
path. Each quote gets a paragraph before it saying what to look for and, where useful, one after it saying what follows.
End with the command that tests the code against the fixtures, and then `### Ask a library`: a
walkthrough step that gets the same facts from pyarrow and from the `parquet` crate, so the
reader leaves knowing the call that does this at work. ch02 is the model.

**What this cannot tell you** is the easiest section to skip and the one that makes the others
believable. Name what the simulation leaves out, what the fixtures do not contain, and what the
code does not handle yet, with the chapter that handles it.

**Key takeaways** sits in a `:::{div}` with `:class: takeaways`. Each item opens with its claim in
bold and gives its reason. Nothing in it is new.

**Problems**: see below.

**Where to go next**: primary sources (the Parquet specification, `parquet.thrift`, RFCs, papers)
and the next chapter.

## Rules with a check behind them

### Never type a number into prose

Byte counts, offsets, lengths, request counts, times and ratios come from the reader. Add a
`Figure` to `crates/pqlab/src/figures.rs`, run `make figures`, and include it:

````markdown
```{include} _generated/tiny-trailer.md
```
````

Every fragment ends with the conditions it was computed under: which fixture, which simulated
network. `scripts/verify-numbers.py` fails on a number with a unit, or any number of two or more
digits, in prose. Format constants written as words ("the last eight bytes") pass; they are fixed
by the specification. A definition that must be typed as digits takes
`% number-ok: <reason>` on the line before its paragraph.

Static explanatory diagrams live in `crates/pqlab/src/figures/diagrams.rs`. `make figures`
generates an SVG and a Markdown figure fragment together; include the fragment beside the
explanation it supports. Both files are covered by `pqlab figures --check`. Read measurements
from the reader, label conceptual examples as schematics, and state what each chart counts.
Give every diagram a descriptive alternative text and a caption that states its takeaway.
Use labels as well as colour. The renderer keeps labels legible in a horizontally scrollable
region on narrow screens and provides a link to the full-size SVG without requiring JavaScript.

### Never paste code into prose

A chapter the Python reader covers quotes each step in both languages, Python first, in a tab set
whose items are synced `python` and `rust`, so every excerpt on every page follows the reader's
choice:

````markdown
::::{tab-set}
:::{tab-item} Python
:sync: python
```{literalinclude} ../python/parquet_lab/format.py
:language: python
:start-at: def footer_span(
:end-before: def check_header(
```
:::
:::{tab-item} Rust
:sync: rust
```{literalinclude} ../crates/parquet-lab/src/format.rs
:language: rust
:start-at: pub fn footer_span(
:end-before: /// Check the opening magic
```
:::
::::
````

Anchor on text that will survive `cargo fmt` and `ruff format`: a signature's opening, a doc
comment's first words. Never `:lines:`. The MyST parse fails if an anchor stops matching. Write
the prose around a tab set about the format, not the language: a remark that holds for one
language only belongs in a sentence that names it.

### Never fake the experiment

A panel draws JSON from `parquet_lab::report`. It never computes a Parquet quantity in JavaScript,
never shows a request the store did not log, and never shows a decoded value the reader did not
decode. If a panel needs a number, the report must return it. `tests/test_wasm.py` holds every
browser call to the native reader's answer, and `tests/browser/smoke.mjs` checks the drawn page
against the native reader.

## Walkthroughs

A chapter can open its experiment by having you do the reader's job by hand, a few lines at a
time, before the lab shows the reader doing it and *Building it* turns the lines into the reader.
ch02's "Read the bytes yourself" reads the magic at both ends, the footer length and where the
footer starts, then breaks the length to show why a reader must check what it reads.

- Each step is a file: `walkthroughs/python/<slug>/<step>.py` and its Rust twin
  `walkthroughs/src/bin/<step>.rs`, self-contained, run from the repository's root. Name steps by
  what they do; no numbers in names. Quote both in a tab set, whole, like the reader's code.
- Keep them short enough to read in one glance, and idiomatic: they are for changing, not for
  reuse. Keep them compact on a phone's screen: imports on one line, single blank lines,
  a small helper class without blank lines inside it. `walkthroughs/` is outside ruff's paths for
  this reason. Print facts in both languages' own idiom; do not bend them to print identical text.
- Add what each step must print to `tests/test_walkthroughs.py`, derived from the fixture and its
  manifest. The prose that follows a step describes what it printed without typing a number.
- End with an invitation to change something, and say what to try. Explain the outcome without
  requiring a run; show an important contrast in a generated table or saved comparison.

**Ask a library** is a walkthrough step too, named `<what>_with_a_library` (`footer_with_a_library`,
`deletes_with_a_library`), since each step's name is a binary and must be unique:
`walkthroughs/python/<slug>/<step>.py` using pyarrow, and its Rust twin in
`walkthroughs/libraries/src/bin/<step>.rs` using the `parquet` crate. That crate is a
workspace of its own, the repository's only dependency, kept out of the root workspace so the
reader stays dependency-free; `scripts/ci-check.sh` formats and lints it. Print the same facts the
hand-written steps and the reader found, and add them to `tests/test_walkthroughs.py` from the
manifest. Use the library's metadata API, not a whole-table read, unless the chapter is about
values. In the page, the first Python run loads pyarrow under Pyodide, which is a large download;
say so in the prose. The Rust step opens in a Codespace.

## Reading without code

Every chapter states a learning goal in a `reading-guide` div before *The experiment*. Its
explanations, diagrams, worked results and limitations must teach that goal without opening code.
The renderer places walkthroughs and implementation excerpts in native disclosures, closed by
default. Do not put an essential explanation only inside one of those disclosures.

`make figures` also runs `python -m tools.walkthrough_results`. It executes every Python
walkthrough and the explicit variations in `tools/walkthrough_results.py`, and writes
`walkthroughs/_generated/results.json`. Never edit the saved output. `make check` reruns the
examples and fails on stale results. The renderer checks the source digest and shows the output
outside the language tabs, labelled as Python output. Keep output concise and meaningful; explain
what to notice in the surrounding prose. Simulated request times are not wall-clock timings.

End *Key takeaways* with one `checkpoint` fence, with a `question:` and an `answer:` on separate
lines. The question asks readers to apply the chapter's idea to a case or explain a consequence.
The answer explains why, including the relevant limitation or misconception. It appears under
an accessible native disclosure so readers can think first, without JavaScript or code execution.

## Problems

A problem is a stub and a test that passes only when the stub is right.

- The stub's doc comment is the problem statement. Say what to return, what to refuse, and what
  not to use when using it would skip the lesson (`u32::from_le_bytes` in problem 2.1).
- Mark each graded test `#[ignore = "problem N.M: fails until you solve it"]` and name it
  `problem_N_M_…` so the chapter's command can select it.
- Derive the expected answer at test time: from the reader, from a pyarrow manifest, or from an
  independent computation. Never store it.
- Test many cases, including the edges, so a hard-coded answer fails. Hand inputs over in an order
  that catches a lazy solution (reversed, unsorted).
- Make failure messages teach: "if you got X, you read the bytes most significant first".
- Add an unmarked scaffolding test beside the problems proving they are answerable and not
  trivially so. CI runs it.
- The section opens, after a sentence saying how many problems there are, with the chapter's
  workbench: a fenced block in the language `problems` holding `chapter: <slug>`. It lets a reader
  edit the Python stub and run its tests in the page, under Pyodide, with the same graders, so it
  sits where a reader on a phone meets it first. Keep the Python graders to a few seconds: the
  page runs them more slowly than a desk.
- Each problem is its number, title and statement, with no command beneath it: the workbench runs
  them all and says which fail. The section ends with one tab set of two `bash` blocks that run the
  chapter's problems at a desk or in a Codespace, and in Rust:
  `python3 -m pytest exercises/python/tests/test_<slug>.py --problems` and
  `cargo test -p exercises --test <slug> -- --ignored`, with a sentence saying how to run one
  (`-k problem_N_M`; `problem_N_M` before the `--`). `tests/test_book.py` checks it.
- Commands get buttons in the page (`web/lab/commands.js`). Run: `python3 -m pytest` on
  `python/tests` or `exercises/python`, `PYTHONPATH=python python3 -m parquet_lab`, and
  `cargo run -p pqlab --`. Open in Codespaces: any other `cargo`, `make` or `python3` command.
  Keep a block to one kind, so it gets the button it should; a mixed block gets Codespaces.
- The last problem has no test. It is about the reader's own files or systems, says what a good
  answer contains, and says what a surprising result would mean.

## What no check catches

Read the finished page as somebody who has read every chapter before it and none after, and stop at:

- a sentence that states a fact about the repository ("the reader handles X"). Is it true today?
  Will it be true after the next phase?
- a word used technically (*range*, *span*, *chunk*, *page*, *request*) in two senses on one page;
- *the* in front of something the page has not introduced;
- a table nobody chose the rows of;
- the same argument made twice, far apart.

Then run STYLE.md's two passes.

## Definition of done

- [ ] Reader code merged, tested, and quoted by text anchor
- [ ] Problems written, failing for the right reason, solved outside the repository, scaffolded
- [ ] Experiment built as a view of `report`, with its calls in `tests/test_wasm.py` and a check in
      `tests/browser/smoke.mjs`
- [ ] Every number from a generated fragment
- [ ] *What this cannot tell you* names the simulation's and the code's limits
- [ ] Edited against STYLE.md, both passes
- [ ] The `[To write` markers gone, and `make check` clean


### Concept practice before code

Chapter two uses a `learning` fence naming `byte`, `length`, `start`, `chunk` or `requests`.
`tools/learning.py` derives answers from the fixture and the Python reader; request choices are
actual traces from that reader, not JavaScript estimates. The page enhances the static questions
and revealable explanations with answer checks. Keep the essential evidence available without
JavaScript and keep implementation listings in the existing Python/Rust disclosures.

### Modules and short lessons

Every chapter is a module of independently named lessons. The canonical chapter Markdown keeps
its seven sections for authoring and validation; it is not published as a combined reading page.
The chapter URL publishes a compact module index. Existing subsection links route to the lesson
that owns the content, and the two original pilot landing URLs redirect to their module indexes.

`tools/lessons.py` defines each lesson’s observable outcome and preparation. A `lesson` fence
marks its start; the next marker ends it. The optional build has its own marker, and `reference`
contains supporting material. The renderer publishes limitations/takeaways/sources as module
notes, appends coding problems to the build lab, and gives explainer questions their own further
practice page. Large feature/query comparisons have separate optional destinations. Never copy
prose or source code into a second lesson file.

Each core lesson ends with a fresh application: a `practice` fence with `question:` and `answer:`,
or a `transfer` case from `tools/lesson_practice.py`. Use specific reasoning, not a completion
score. Worked miniatures are explicitly labelled and bridge to the real format or fixture.
Native answer disclosures work without JavaScript. Keep essential qualifications beside the
mechanism, not solely in optional notes. The build refuses missing/reordered/empty boundaries;
checks verify exact ownership of literal and generated includes.

Core lessons have their own URLs, navigation and resumable reading positions. The sidebar lists
all modules and expands the current one. Optional labs do not interrupt Next. Preserve old
heading anchors in the canonical source; the ownership map sends old links to the proper page.
Returning readers whose saved chapter offset exceeds a module index start at its lesson choices.

`make check` also creates component integration harnesses in `_build/integration`, outside the
published site. These let existing stateful worker/lab tests run against full sets of actual
components. They are never deployed or offline-cached. Separate browser checks visit every real
core lesson and module index, exercise real lesson runtimes, native feedback, deep links and
resume. Do not describe a component-harness pass as testing a public combined page.

See `notes/course-learning-design.md` for the course brief and review evidence. Agent reviews,
checks and prototypes are not a novice learning study.
