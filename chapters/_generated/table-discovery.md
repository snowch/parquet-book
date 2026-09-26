| Query | Files found by | Files read | Requests | Bytes fetched | Time | Same as pyarrow |
|---|---|--:|--:|--:|--:|---|
| `SELECT count(*) FROM orders` | listing | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT count(*) FROM orders` | listing, pruned by path | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT count(*) FROM orders` | the log | 9 of 9 | 10 | 40,498 | 80 ms | yes |
| `SELECT count(*), sum(amount_cents) FROM orders WHERE country = 'UK'` | listing | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT count(*), sum(amount_cents) FROM orders WHERE country = 'UK'` | listing, pruned by path | 3 of 9 | 4 | 12,188 | 40 ms | yes |
| `SELECT count(*), sum(amount_cents) FROM orders WHERE country = 'UK'` | the log | 3 of 9 | 4 | 18,520 | 40 ms | yes |
| `SELECT order_id, country, amount_cents FROM orders WHERE order_id >= 431 AND order_id < 436 ORDER BY order_id` | listing | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT order_id, country, amount_cents FROM orders WHERE order_id >= 431 AND order_id < 436 ORDER BY order_id` | listing, pruned by path | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT order_id, country, amount_cents FROM orders WHERE order_id >= 431 AND order_id < 436 ORDER BY order_id` | the log | 6 of 9 | 7 | 30,698 | 60 ms | yes |
| `SELECT country, count(*) FROM orders WHERE status = 'refunded' GROUP BY country ORDER BY country` | listing | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT country, count(*) FROM orders WHERE status = 'refunded' GROUP BY country ORDER BY country` | listing, pruned by path | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT country, count(*) FROM orders WHERE status = 'refunded' GROUP BY country ORDER BY country` | the log | 8 of 9 | 9 | 38,824 | 60 ms | yes |
| `SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200` | listing | 9 of 9 | 10 | 34,166 | 80 ms | yes |
| `SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200` | listing, pruned by path | 3 of 9 | 4 | 12,188 | 40 ms | yes |
| `SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200` | the log | 1 of 9 | 2 | 10,406 | 40 ms | yes |

*Computed by the reader over the 9 data files of `fixtures/table/`, fetching through the simulated store with four connections, 20 ms before each request's first byte and 100 MB/s after it. The answers are compared with pyarrow's, from `fixtures/queries.json`.*
