| Query | Bytes read | Row groups skipped | Values decoded |
|---|--:|--:|--:|
| `SELECT * FROM orders` | 22,126 | 0 of 4 | 4,800 |
| `SELECT country, amount_cents FROM orders` | 5,522 | 0 of 4 | 1,600 |
| `SELECT * FROM orders WHERE order_id < 300` | 11,071 | 2 of 4 | 2,400 |
| `SELECT * FROM orders WHERE status = 'refunded'` | 22,126 | 0 of 4 | 4,800 |
| `SELECT count(*) FROM orders` | 0 | 0 of 4 | 0 |
| `SELECT min(order_id), max(order_id) FROM orders` | 4,468 | 0 of 4 | 800 |
| `SELECT country, count(*) FROM orders GROUP BY country` | 913 | 0 of 4 | 800 |
| `SELECT order_id, amount_cents FROM orders ORDER BY amount_cents DESC LIMIT 5` | 9,077 | 0 of 4 | 1,600 |
| `SELECT order_id, amount_cents FROM orders ORDER BY order_id LIMIT 5` | 9,077 | 0 of 4 | 1,600 |

*Each query run by the book's engine on `fixtures/writing-baseline.parquet` (28,779 bytes: 800 rows of 6 columns in 4 row groups, sorted by `order_id`). Bytes read are the column chunks the scan read, after the footer every query reads first. Values decoded are the rows the scan decoded times the columns it read.*
