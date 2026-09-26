| File | Partition | Bytes | Rows | `order_id` from | to |
|---|---|--:|--:|--:|--:|
| `country=DE/part-0.parquet` | `country=DE` | 4,071 | 100 | 1 | 796 |
| `country=FR/part-0.parquet` | `country=FR` | 4,051 | 99 | 10 | 800 |
| `country=PL/part-0.parquet` | `country=PL` | 4,064 | 100 | 16 | 795 |
| `country=SE/part-0.parquet` | `country=SE` | 4,069 | 100 | 5 | 790 |
| `country=UK/part-0.parquet` | `country=UK` | 4,074 | 100 | 3 | 271 |
| `country=UK/part-1.parquet` | `country=UK` | 4,062 | 100 | 274 | 533 |
| `country=UK/part-2.parquet` | `country=UK` | 4,052 | 99 | 536 | 797 |
| `country=US/part-0.parquet` | `country=US` | 4,049 | 100 | 4 | 779 |
| `country=US/part-1.parquet` | `country=US` | 1,674 | 2 | 785 | 798 |

*Every `add` action in `fixtures/table/_delta_log/00000000000000000000.json` (6332 bytes), as the reader's `table::read_log` reads it.*
