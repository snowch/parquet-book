---
title: Parquet, byte by byte
short_title: Cover
numbering: false
---

(cover)=
*Understand Parquet from its bytes. Build a reader if you want to go further.*

A book for data engineers who write Parquet every day and want to know what is in the files. You
learn the format through explanations, diagrams and worked results from real files. Reading or
running code is optional: every example shows its answer before you open its Python and Rust.
If you want to go further, follow the implementation and build a working Parquet reader, then
ask pyarrow and the Rust `parquet` crate the same questions. Python examples run in the page;
Rust examples run in a Codespace or at a desk.
[Start with the Preface](#preface) to choose a reading path.

![A Parquet file drawn as a strip of bytes from its first byte to its last: the PAR1 magic, two row groups each holding a column chunk per column, the footer, the footer's length, and the PAR1 magic again. An arrow from the length leads back to the start of the footer, and arrows from the footer lead to the start of every column chunk.](web/cover-hero.svg)

By Chris Snow, in collaboration with Claude (Anthropic)

% number-ok: the names of the two licences, which carry their version numbers
The prose and figures are under [CC BY-NC 4.0](https://github.com/snowch/parquet-book/blob/main/LICENSE); the code is under [Apache 2.0](https://github.com/snowch/parquet-book/blob/main/LICENSE-CODE).
