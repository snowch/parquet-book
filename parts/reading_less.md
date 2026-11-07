---
title: "Part III: Reading less"
---

(part-reading-less)=
# Part III: Reading less

> How does a reader avoid reading most of a file?

Reading every value can waste work when a query needs only a few. This part uses metadata to
rule out data: summaries of column values ([ch08](#metadata-and-statistics)), small structures
for ruling out pages or testing whether a value might be present ([ch09](#skipping-data)),
and the request strategies that put them together
([ch10](#how-readers-read)). Request costs come from a simulated object store.

To prepare, review [how stored types determine a value’s meaning](interpret-logical-types.html)
and [the footer request chain](trace-footer-requests.html). The first makes statistics
comparable; the second explains why saving bytes can still cost more requests.
