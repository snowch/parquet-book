| Condition | Matching rows | Sorted: bytes read | Shuffled: bytes read |
|---|--:|--:|--:|
| `order_id = 431` | 1 | 1,113 | 21,426 |
| `order_id < 100` | 99 | 3,239 | 20,368 |
| `amount_cents > 9800` | 14 | 9,767 | 10,811 |
| `customer_id = 843807` | 1 | 5,365 | 5,362 |
| `customer_id = 424242` | 0 | 5,363 | 0 |
| `country is null` | 73 | 21,456 | 21,426 |

*Computed by the reader from `fixtures/pruning-sorted.parquet` and `fixtures/pruning-shuffled.parquet`, using row group statistics, Bloom filters and the page index. A full scan decodes 800 rows and reads 21,456 bytes of column chunks from the sorted file, 21,426 from the shuffled one. Bytes read do not include the indexes and filters fetched to decide.*
