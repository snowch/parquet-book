---
title: "Part IV: Writing and querying"
---

(part-writing-and-querying)=
# Part IV: Writing and querying

> What makes a file good to read, and what reads it?

[ch11](#writing-parquet-well) turns the reader's measurements back on the writer: which settings
make a file cheap to read. [ch12](#what-a-query-engine-does) describes what reads it: a query
engine, what it asks of a file, and what each kind of query costs.

Start with [the complete scan trace](trace-a-complete-scan.html) and
[read-strategy trade-offs](choose-a-read-strategy.html) if request costs are new to you.
The writer comparison changes the file layout; the query lessons then change the work
done with the selected data.
