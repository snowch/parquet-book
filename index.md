---
title: Preface
---

(preface)=
# Preface

## What this book is

This book is for data engineers who write Parquet every day and want to know what is in the
files. You can learn from the explanations and worked results, then explore the code if you want
to. Each chapter asks one question about the
format and answers it on the bytes of a real Parquet file, in three steps:

1. **By hand.** A few lines of Python or Rust that open the file and print the structure the
   chapter is about: the magic number, the footer, a page header, a column's statistics.
2. **In the reader.** Those lines grow into a piece of a working Parquet reader, which the book
   builds as it goes. By the end it opens files in an object store, decodes their pages, skips
   data it can prove it does not need, and answers small SQL queries.
3. **With a library.** The same question asked of pyarrow and of the Rust `parquet` crate, the
   tools you use at work, with the answer checked against what you found by hand.

Every chapter that builds a piece of the reader takes all three steps. Three chapters explain
instead, and build nothing; *How a chapter works* says which.

The reader exists twice, in Python and in Rust, held to identical answers by tests. Every excerpt
of the reader has a tab for each; pick one and the whole book follows. The same code runs in the
tests, which check it against files written by pyarrow, a production implementation; on the
command line; and in this page, where Python runs under Pyodide in the steps you run and the
problems you solve, and Rust, compiled to WebAssembly, draws the pictures. When a page shows a
footer length, a byte range or a request, the reader computed it from the bytes of the file.

## How a chapter works

Every chapter has the same seven sections, so you always know where you are:

1. **The question** it answers, and why the previous chapter left it open.
2. **The experiment**: worked results you can read immediately, optional code you can run and
   change, the reader's view of the same bytes, and generated tables. Where a picture helps (a map of a file's bytes, a timeline
   of requests), a panel draws what the reader returned.
3. **Building it**, optional: the reader's code, quoted from the implementation, and then the same answer
   from a library.
4. **What this cannot tell you**: the limits of the experiment and of the code.
5. **Key takeaways**, followed by a question you can answer without code. Try explaining your
   answer before opening the explanation.
6. **Problems**, optional: functions for you to write, with tests that fail until they are right, and one
   question about your own tables.
7. **Where to go next**: primary sources.

Three chapters explain and build nothing, so they have no *Building it* and their problems are
questions to reason about. [ch01](#why-parquet-exists) sets up the question the book answers,
before there is a file to open. [ch12](#what-a-query-engine-does) describes what a query engine
does with a file. [ch16](#what-iceberg-adds), the last, maps what Apache Iceberg adds above
Parquet files to the chapters that show it.

## Choose how to read

**Read for understanding.** Follow the question, explanations, diagrams and worked results.
Every walkthrough shows its Python output before the code, and important comparisons show what
changes. You do not need to install anything or press Run. Skip *Building it* if you wish, but
keep *What this cannot tell you*: its limits are part of the lesson. Finish with the takeaways
and the understanding check. An occasional byte sequence or SQL expression is worth reading;
writing a program is optional.

**Explore the examples.** Open **Read or run the code** beside a worked result. Pick Python or
Rust, read the source, or change an input and predict the result before running it. Python can
run in the page; Rust runs in a Codespace or at a desk. The saved result stays beside your run
so you can compare them. The displayed output uses Python's notation; the Rust examples are
checked against the same facts but may format them differently.

**Build the reader.** Add *Building it* and the coding problems to that reading path. Open the
implementation excerpts, run the checks, and extend the reader yourself. The explanations and
worked results remain available whichever path you choose.

Worked results are produced by running the examples when the book is built and checked again
by its tests. Request times from the teaching object store use a fixed network model; they are
not timings measured on your computer. A library may choose different reads in another version
or environment. The chapter explains those limits.

## Two rules the book keeps

**No number is typed into the prose.** A byte count, an offset, a request total or a time appears
in a generated table, computed by the reader when the book was built, or in an experiment,
computed as you watch. If the reader changes, the build recomputes the numbers and fails if a
committed table is stale.

**No code is pasted into the prose.** Every block of Python and Rust is quoted from the working
tree, by text anchors, so the book cannot drift from the code it describes. The bar above each
block names the file.

## What you need

To read the book: a browser. Explanations, worked results, diagrams and answer reveals remain
available with JavaScript disabled. Running Python steps and problems in the page needs JavaScript.

To run the Rust, or everything at a desk: Python with pyarrow, and a Rust toolchain, or a
Codespace, which has both. [Appendix A](#running-the-lab) has the commands. From a fresh clone,
`make` builds everything and `make serve` serves this book locally.

To explore or build, you should be comfortable reading code in one of the two languages. The code
is deliberately plain, and every chapter says what each quoted block does.

## Where this starts

[ch01](#why-parquet-exists) stores one table two ways and counts the bytes a query touches.
[ch02](#anatomy-of-a-parquet-file) opens a real Parquet file from its last byte, by hand, then in
the reader, then with pyarrow, and is where the reader begins.
