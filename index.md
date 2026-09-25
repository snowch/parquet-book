---
title: Preface
---

(preface)=
# Preface

## What this book is

This book explains how Apache Parquet works by having you build a Parquet reader. Each chapter
asks one question about the format, answers it with an experiment on the bytes of a real Parquet
file, and then builds the piece of the reader the experiment needed. By the end the reader opens
files in an object store, decodes their pages, skips data it can prove it does not need, and
answers small SQL queries.

The reader is written in Rust. The same code runs in three places:

- in the **tests**, which check it against files written by pyarrow, a production implementation;
- on the **command line**, as `pqlab`; and
- in **this page**, compiled to WebAssembly, behind every experiment.

There is no second implementation for the browser. When an experiment shows a footer length, a
byte range or a request, the Rust reader computed it from the bytes on screen.

## How a chapter works

Every chapter has the same seven sections, so you always know where you are:

1. **The question** it answers, and why the previous chapter left it open.
2. **The experiment**: an interactive panel over a real file, and generated tables.
3. **Building it**: the code the experiment ran, quoted from the implementation.
4. **What this cannot tell you**: the limits of the experiment and of the code.
5. **Key takeaways**.
6. **Problems**: functions for you to write, with tests that fail until they are right.
7. **Where to go next**: primary sources.

The experiments are the centre of each chapter. Read the question, then work through the panel
before the explanation. The explanation will make more sense once you have seen what it explains.

## Two rules the book keeps

**No number is typed into the prose.** A byte count, an offset, a request total or a time appears
in a generated table, computed by the reader when the book was built, or in an experiment,
computed as you watch. If the reader changes, the build recomputes the numbers and fails if a
committed table is stale.

**No code is pasted into the prose.** Every block of Rust is quoted from the working tree, by
text anchors, so the book cannot drift from the code it describes. The bar above each block names
the file.

## What you need

To read the book: a browser. The experiments run offline once a page has loaded.

To solve the problems and run the reader at a desk: a Rust toolchain.
[Appendix A](#running-the-lab) has the commands. From a fresh clone, `make` builds everything
and `make serve` serves this book locally.

You should be comfortable reading code. You do not need to know Rust well: the code is
deliberately plain, and every chapter says what each quoted block does.

## Where this starts

[ch01](#why-parquet-exists) stores one table two ways and counts the bytes a query touches.
[ch02](#anatomy-of-a-parquet-file) opens a real Parquet file from its last byte, and is where the
reader begins.
