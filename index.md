---
title: Preface
---

(preface)=
# Preface

## What this book is

This book is for data engineers who write Parquet every day and want to know what is in the
files. You learn the format by reading it in code. Each chapter asks one question about the
format and answers it on the bytes of a real Parquet file, in three steps:

1. **By hand.** A few lines of Python or Rust that open the file and print the structure the
   chapter is about: the magic number, the footer, a page header, a column's statistics.
2. **In the reader.** Those lines grow into a piece of a working Parquet reader, which the book
   builds as it goes. By the end it opens files in an object store, decodes their pages, skips
   data it can prove it does not need, and answers small SQL queries.
3. **With a library.** The same question asked of pyarrow and of the Rust `parquet` crate, the
   tools you use at work, with the answer checked against what you found by hand.

[ch02](#anatomy-of-a-parquet-file) takes all three steps. The chapters after it build the reader
and are gaining the first and third steps as the book is revised.

The reader exists twice, in Python and in Rust, held to identical answers by tests. Every
excerpt of the reader has a tab for each; pick one and the whole book follows. The same code runs
in the tests, which check it against files written by pyarrow, a production implementation; on
the command line; and in this page, where Python runs under Pyodide and Rust runs compiled to
WebAssembly. When a page shows a footer length, a byte range or a request, the reader computed it
from the bytes of the file.

## How a chapter works

Every chapter has the same seven sections, so you always know where you are:

1. **The question** it answers, and why the previous chapter left it open.
2. **The experiment**: code you run and change to read the file by hand, the reader's view of the
   same bytes, and generated tables. Where a picture helps (a map of a file's bytes, a timeline
   of requests), a panel draws what the reader returned.
3. **Building it**: the reader's code, quoted from the implementation, and then the same answer
   from a library.
4. **What this cannot tell you**: the limits of the experiment and of the code.
5. **Key takeaways**.
6. **Problems**: functions for you to write, with tests that fail until they are right, and one
   question about your own tables.
7. **Where to go next**: primary sources.

[ch01](#why-parquet-exists) is the exception. It sets up the question the book answers, before
there is a file to open, so it builds nothing and has no code for you to write.

## Two rules the book keeps

**No number is typed into the prose.** A byte count, an offset, a request total or a time appears
in a generated table, computed by the reader when the book was built, or in an experiment,
computed as you watch. If the reader changes, the build recomputes the numbers and fails if a
committed table is stale.

**No code is pasted into the prose.** Every block of Python and Rust is quoted from the working
tree, by text anchors, so the book cannot drift from the code it describes. The bar above each
block names the file.

## What you need

To read the book and run its Python: a browser. Python steps and problems run in the page.

To run the Rust, or everything at a desk: Python with pyarrow, and a Rust toolchain, or a
Codespace, which has both. [Appendix A](#running-the-lab) has the commands. From a fresh clone,
`make` builds everything and `make serve` serves this book locally.

You should be comfortable reading code in one of the two languages. The code is deliberately
plain, and every chapter says what each quoted block does.

## Where this starts

[ch01](#why-parquet-exists) stores one table two ways and counts the bytes a query touches.
[ch02](#anatomy-of-a-parquet-file) opens a real Parquet file from its last byte, by hand, then in
the reader, then with pyarrow, and is where the reader begins.
