---
title: "Part II: The values"
---

(part-the-values)=
# Part II: The values

> How do values become bytes, and back?

Part I found where each column's bytes are. This part decodes them. [ch05](#encodings) builds a
decoder for each encoding, [ch06](#pages) walks the pages of a column chunk, and
[ch07](#compression) adds decompression to the read path.
