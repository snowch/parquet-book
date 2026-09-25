| File | Row group | Filter bytes | Values in the chunk | Absent values tested | Passed anyway |
|---|--:|--:|--:|--:|--:|
| `pruning-shuffled.parquet` | 0 | 272 | 200 | 9,278 | 87 |
| `pruning-shuffled.parquet` | 1 | 272 | 200 | 9,274 | 97 |
| `pruning-shuffled.parquet` | 2 | 272 | 200 | 9,278 | 70 |
| `pruning-shuffled.parquet` | 3 | 272 | 200 | 9,277 | 126 |

*Computed by the reader: every customer number from 100,000 in steps of 97 that the row group does not hold, probed against its `customer_id` Bloom filter. 380 of 37,107 passed, 1.0%. The writer was asked for a false positive rate of 5% at 200 distinct values.*
