| Files found by | Files read | Requests | Bytes fetched |
|---|--:|--:|--:|
| listing | 9 of 9 | 10 | 34,166 |
| listing, pruned by path | 9 of 9 | 10 | 34,166 |
| the log | 9 of 9 | 10 | 40,498 |

*`SELECT count(*) FROM orders`, by the reader over the 9 data files of `fixtures/table/`, with four connections, 20 ms before each request's first byte and 100 MB/s after it. It took 80 ms, 80 ms and 80 ms, in the table's order, and each way gave pyarrow's answer.*
