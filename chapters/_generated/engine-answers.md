| Query | File | Rows | Row groups read | Same as pyarrow |
|---|---|--:|--:|---|
| `SELECT count(*) FROM orders` | `writing-baseline.parquet` | 1 | 4 of 4 | yes |
| `SELECT count(*) FROM orders WHERE country = 'UK'` | `writing-baseline.parquet` | 1 | 4 of 4 | yes |
| `SELECT country, count(*) FROM orders GROUP BY country ORDER BY country` | `writing-baseline.parquet` | 6 | 4 of 4 | yes |
| `SELECT status, sum(amount_cents) FROM orders GROUP BY status ORDER BY status` | `writing-baseline.parquet` | 3 | 4 of 4 | yes |
| `SELECT min(amount_cents), max(amount_cents), avg(amount_cents) FROM orders WHERE country = 'SE'` | `writing-baseline.parquet` | 1 | 4 of 4 | yes |
| `SELECT order_id, amount_cents FROM orders WHERE amount_cents > 9800 ORDER BY amount_cents DESC, order_id LIMIT 5` | `writing-baseline.parquet` | 5 | 4 of 4 | yes |
| `SELECT order_id, customer_id FROM orders WHERE order_id >= 431 AND order_id < 436 ORDER BY order_id` | `writing-baseline.parquet` | 5 | 1 of 4 | yes |
| `SELECT country, max(order_id) FROM orders WHERE status = 'refunded' GROUP BY country ORDER BY country` | `writing-baseline.parquet` | 6 | 4 of 4 | yes |
| `SELECT count(*) FROM orders WHERE country = 'FR' AND amount_cents < 1000` | `writing-baseline.parquet` | 1 | 4 of 4 | yes |
| `SELECT count(*), count(coupon) FROM orders` | `statistics.parquet` | 1 | 3 of 3 | yes |
| `SELECT coupon, count(*) FROM orders WHERE coupon IS NOT NULL GROUP BY coupon ORDER BY coupon` | `statistics.parquet` | 3 | 2 of 3 | yes |
| `SELECT city, delta FROM orders WHERE delta < 0 ORDER BY delta` | `statistics.parquet` | 4 | 3 of 3 | yes |

*Every query in `fixtures/queries.json`, answered by the engine from the file's bytes and compared with the answer pyarrow computed when the fixtures were written.*
