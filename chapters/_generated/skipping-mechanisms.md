| Mechanisms | Row groups skipped | Bytes read | Bytes fetched to decide |
|---|--:|--:|--:|
| none | 0 of 4 | 21,456 | 0 |
| statistics | 3 of 4 | 5,365 | 0 |
| statistics, page index | 3 of 4 | 1,113 | 342 |

*`order_id = 431`, planned on `fixtures/pruning-sorted.parquet`.*

| Mechanisms | Row groups skipped | Bytes read | Bytes fetched to decide |
|---|--:|--:|--:|
| none | 0 of 4 | 21,426 | 0 |
| statistics | 0 of 4 | 21,426 | 0 |
| statistics, Bloom filters | 4 of 4 | 0 | 1,088 |

*`customer_id = 424242`, planned on `fixtures/pruning-shuffled.parquet`.*

*Computed by the reader from the pruning fixtures, with each set of mechanisms allowed in turn.*
