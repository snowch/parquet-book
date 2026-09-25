---
title: "Part III: Reading less"
---

(part-reading-less)=
# Part III: Reading less

> How does a reader avoid reading most of a file?

A reader that decodes everything is correct and slow. This part is about the metadata that lets
it skip: statistics in the footer ([ch08](#metadata-and-statistics)), page indexes and Bloom
filters ([ch09](#skipping-data)), and the request strategies that put them together
([ch10](#how-readers-read)). The object-store trace from [ch02](#anatomy-of-a-parquet-file) is
the measure throughout.
