---
title: "Part II: The values"
---

(part-the-values)=
# Part II: The values

> How do values become bytes, and back?

This part turns stored column bytes back into values. [ch05](#encodings) builds a
decoder for each encoding, [ch06](#pages) walks the pages of a column chunk, and
[ch07](#compression) adds decompression to the read path.

To prepare, follow [the footer’s column-chunk map](read-the-footer-map.html) and
[the stored level streams](stored-levels.html). They locate the bytes and explain the
integer-run format that also carries dictionary indices.
