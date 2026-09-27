| Files found by | Files read | Requests | Bytes fetched |
|---|--:|--:|--:|
| listing | 9 of 9 | 10 | 34,166 |
| listing, pruned by path | 9 of 9 | 10 | 34,166 |
| the log | 6 of 9 | 7 | 30,698 |

*`SELECT order_id, country, amount_cents FROM orders WHERE order_id >= 431 AND order_id < 436 ORDER BY order_id`, by the reader over the 9 data files of `fixtures/table/`, with four connections, 20 ms before each request's first byte and 100 MB/s after it. It took 80 ms, 80 ms and 60 ms, in the table's order, and each way gave pyarrow's answer.*
