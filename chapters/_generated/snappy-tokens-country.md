| Compressed bytes | Token | Writes output | What it says |
|---|---|--:|---|
| `80 0c` | length | · | varint: the output is 1536 bytes |
| `14 02 00 00 00 55 4b` | literal | 0–5 | tag 14: a literal, the next 6 bytes |
| `01 06` | copy | 6–9 | tag 01: copy 4 bytes from 6 back |
| `04 50 4c` | literal | 10–11 | tag 04: a literal, the next 2 bytes |
| `01 06` | copy | 12–15 | tag 01: copy 4 bytes from 6 back |
| `04 44 45` | literal | 16–17 | tag 04: a literal, the next 2 bytes |
| `01 06` | copy | 18–21 | tag 01: copy 4 bytes from 6 back |
| `00 53` | literal | 22–22 | tag 00: a literal, the next 1 byte |
| `05 06` | copy | 23–27 | tag 05: copy 5 bytes from 6 back |

26 more tokens follow, 25 of them copies.

*Computed by the reader from `fixtures/codec-snappy.parquet` (6977 bytes).*
