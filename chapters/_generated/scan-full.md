| `SELECT *`, no condition | Requests | Bytes fetched | Time |
|---|--:|--:|--:|
| one request per column chunk | 19 | 23,356 | 380 ms |
| one request per column chunk, four connections | 19 | 23,356 | 140 ms |
| one request per column chunk, sixteen connections | 19 | 23,356 | 80 ms |
| chunks that touch merged into one request | 4 | 23,356 | 80 ms |

*Computed by the reader against `fixtures/pruning-sorted.parquet`, which has 16 column chunks, with the footer found by `HEAD` and an exact tail read first. 20 ms per request, 100 MB/s once data flows.*
