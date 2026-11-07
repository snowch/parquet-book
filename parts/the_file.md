---
title: "Part I: The file"
---

(part-the-file)=
# Part I: The file

> What is a Parquet file, byte by byte?

This part takes a Parquet file apart. [ch01](#why-parquet-exists) shows why a table is stored by
column at all. [ch02](#anatomy-of-a-parquet-file) recognises a file and finds the description of its contents.
[ch03](#the-type-system) follows that description to identify field types and nesting.
[ch04](#nested-data) shows how records with lists and missing values fit into flat columns.

At the end of the part you can explain how a reader finds a table’s layout before turning its
stored bytes back into values. Each lesson states which file variants the teaching reader supports.
