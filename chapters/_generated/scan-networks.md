| Network | Latency | Bandwidth | Pages the plan needs | The whole file |
|---|--:|--:|--:|--:|
| same data centre | 1 ms | 1000 MB/s | 6.0 ms in 6 requests | **1.0 ms** |
| object store | 20 ms | 100 MB/s | 120 ms in 6 requests | **20 ms** |
| slow link | 1 ms | 1 MB/s | **15 ms in 6 requests** | 28 ms |
| far and slow | 100 ms | 1 MB/s | 609 ms in 6 requests | **127 ms** |

*`SELECT * WHERE order_id = 431` against `fixtures/pruning-sorted.parquet`, by the reader, under four simulated networks. The faster strategy on each is in bold.*
