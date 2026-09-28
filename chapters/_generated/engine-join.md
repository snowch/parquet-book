| Build side | Its keys | Row groups skipped: sorted probe | Shuffled probe |
|---|---|--:|--:|
| `table/country=UK/part-1.parquet` | 100, 274 to 533 | 2 of 4 | 0 of 4 |
| `table/country=DE/part-0.parquet` | 100, 1 to 796 | 0 of 4 | 0 of 4 |
| `changes/appends/append-00.parquet` | 10, 801 to 810 | 4 of 4 | 4 of 4 |

*Each build side's `order_id` range, found by the book's engine, run as a condition on the probe side's scan: `fixtures/writing-baseline.parquet` (sorted by `order_id`) and `fixtures/writing-shuffled.parquet` (the same orders shuffled). The engine has no joins; this is the scan a join's probe side would run.*
