| Row group | Absent values tested | Passed anyway |
|--:|--:|--:|
| 0 | 9,278 | 87 |
| 1 | 9,274 | 97 |
| 2 | 9,278 | 70 |
| 3 | 9,277 | 126 |

*Computed by the reader from `fixtures/pruning-shuffled.parquet`: every customer number from 100,000 in steps of 97 that the row group does not hold, probed against its `customer_id` Bloom filter, of 272 bytes for 200 values. 380 of 37,107 passed, 1.0%. The writer was asked for a false positive rate of 5% at 200 distinct values.*
