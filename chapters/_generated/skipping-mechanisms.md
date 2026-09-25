| File | Condition | Mechanisms | Row groups skipped | Bytes read | Bytes fetched to decide |
|---|---|---|--:|--:|--:|
| `pruning-sorted.parquet` | `order_id = 431` | none | 0 of 4 | 21,456 | 0 |
| `pruning-sorted.parquet` | `order_id = 431` | statistics | 3 of 4 | 5,365 | 0 |
| `pruning-sorted.parquet` | `order_id = 431` | statistics, page index | 3 of 4 | 1,113 | 342 |
| `pruning-shuffled.parquet` | `customer_id = 424242` | none | 0 of 4 | 21,426 | 0 |
| `pruning-shuffled.parquet` | `customer_id = 424242` | statistics | 0 of 4 | 21,426 | 0 |
| `pruning-shuffled.parquet` | `customer_id = 424242` | statistics, Bloom filters | 4 of 4 | 0 | 1,088 |

*Computed by the reader from the pruning fixtures, with each set of mechanisms allowed in turn.*
