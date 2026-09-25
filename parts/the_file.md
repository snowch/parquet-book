---
title: "Part I: The file"
---

(part-the-file)=
# Part I: The file

> What is a Parquet file, byte by byte?

This part takes a Parquet file apart. [ch01](#why-parquet-exists) shows why a table is stored by
column at all. [ch02](#anatomy-of-a-parquet-file) opens a file from its last byte and finds every
structure in it. [ch03](#the-type-system) reads the schema out of the footer, and
[ch04](#nested-data) shows how nested and nullable records fit into flat columns.

At the end of the part the reader can open any unencrypted Parquet file and say what is in it,
without yet decoding a single value.
