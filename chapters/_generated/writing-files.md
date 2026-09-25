| File | Change | File bytes | Footer bytes | Row groups | Data pages | `country` bytes | `order_id` bytes |
|---|---|--:|--:|--:|--:|--:|--:|
| `writing-baseline.parquet` | the baseline | 28,779 | 2,935 | 4 | 120 | 913 | 4,468 |
| `writing-one-group.parquet` | one row group | 26,339 | 889 | 1 | 120 | 768 | 4,540 |
| `writing-small-groups.parquet` | row groups of 40 rows | 44,190 | 13,648 | 20 | 120 | 1,689 | 4,817 |
| `writing-by-country.parquet` | sorted by country | 28,430 | 2,935 | 4 | 120 | 568 | 4,470 |
| `writing-shuffled.parquet` | shuffled | 28,740 | 2,935 | 4 | 120 | 913 | 4,486 |
| `writing-plain.parquet` | no dictionary | 28,910 | 2,665 | 4 | 120 | 2,433 | 3,857 |
| `writing-no-index.parquet` | no page index | 29,253 | 2,633 | 4 | 120 | 1,193 | 5,388 |

*Computed by the reader from the `fixtures/writing-*.parquet` files: the same 800 orders, Snappy-compressed. Column bytes are summed over row groups and include page headers.*
