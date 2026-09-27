| File | File bytes | `country` bytes | `order_id` bytes |
|---|--:|--:|--:|
| the baseline | 28,779 | 913 | 4,468 |
| one row group | 26,339 | 768 | 4,540 |
| row groups of 40 rows | 44,190 | 1,689 | 4,817 |
| sorted by country | 28,430 | 568 | 4,470 |
| shuffled | 28,740 | 913 | 4,486 |
| no dictionary | 28,910 | 2,433 | 3,857 |
| no page index | 29,253 | 1,193 | 5,388 |

*Computed by the reader from the `fixtures/writing-*.parquet` files: the same 800 orders, Snappy-compressed. Every file has 120 data pages. Column bytes are summed over row groups and include page headers.*
