---
title: Parquet, byte by byte
short_title: Cover
numbering: false
---

(cover)=
*What is in a Parquet file, read from its bytes, with a working reader to show for it.*

A book for data engineers who write Parquet every day and want to know what is in the files. You
learn the format by reading real files byte by byte, in Python and in Rust, and you build a
working Parquet reader as you go. Then you ask pyarrow and the Rust `parquet` crate the same
questions and check their answers against yours. Everything runs in the page: the code you read
by hand, the problems and their tests, and the pictures the reader draws.
[Start with the Preface](#preface) to see how a chapter works and what you need to run the code
at a desk.

![A Parquet file drawn as a strip of bytes from its first byte to its last: the PAR1 magic, two row groups each holding a column chunk per column, the footer, the footer's length, and the PAR1 magic again. An arrow from the length leads back to the start of the footer, and arrows from the footer lead to the start of every column chunk.](web/cover-hero.svg)

By Chris Snow, in collaboration with Claude (Anthropic)

% number-ok: the names of the two licences, which carry their version numbers
The prose and figures are under [CC BY-NC 4.0](https://github.com/snowch/parquet-book/blob/main/LICENSE); the code is under [Apache 2.0](https://github.com/snowch/parquet-book/blob/main/LICENSE-CODE).
