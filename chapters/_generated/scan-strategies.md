| Strategy | Requests | Bytes fetched | Time |
|---|--:|--:|--:|
| HEAD, trailer, footer; every column chunk | 19 | 23,356 | 380 ms |
| … skipping row groups by statistics | 7 | 7,265 | 140 ms |
| … and pages by the page index | 13 | 3,355 | 260 ms |
| … with an 8 KiB suffix read for the footer | 6 | 9,305 | 120 ms |
| … merging ranges within 4 KiB | 2 | 12,201 | 40 ms |
| … on four connections, without merging | 6 | 9,305 | 60 ms |
| One suffix read of 64 KiB: the whole file | 1 | 26,926 | 20 ms |

*`SELECT * WHERE order_id = 431`, run by the reader against `fixtures/pruning-sorted.parquet` (26,926 bytes) in the simulated object store: 20 ms per request, 100 MB/s once data flows. Every strategy returns the same one row.*
