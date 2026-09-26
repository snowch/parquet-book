---
title: "Part V: Beyond one file"
---

(part-beyond-one-file)=
# Part V: Beyond one file

> What changes when files are protected, or many?

[ch13](#modular-encryption) reads encrypted files and asks what stays visible.
[ch14](#lakehouse-and-beyond) puts many files behind one table, and shows file pruning working
above the row-group pruning of Part III. [ch15](#changing-a-table) changes that table, and
measures where Parquet works badly: finding one row, deleting one, and the small files and delete
files that changes leave behind until compaction.
