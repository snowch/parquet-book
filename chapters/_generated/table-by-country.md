| Files found by | Files read | Requests | Bytes fetched |
|---|--:|--:|--:|
| listing | 9 of 9 | 10 | 34,166 |
| listing, pruned by path | 3 of 9 | 4 | 12,188 |
| the log | 3 of 9 | 4 | 18,520 |

*`SELECT count(*), sum(amount_cents) FROM orders WHERE country = 'UK'`, by the reader over the 9 data files of `fixtures/table/`, with four connections, 20 ms before each request's first byte and 100 MB/s after it. It took 80 ms, 40 ms and 40 ms, in the table's order, and each way gave pyarrow's answer.*
