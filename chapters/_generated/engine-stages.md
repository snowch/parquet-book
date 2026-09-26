`SELECT country, count(*), avg(amount_cents) FROM orders WHERE order_id < 300 AND status = 'refunded' GROUP BY country ORDER BY country`

| Stage | What it did | Rows in | Rows out |
|---|---|--:|--:|
| Scan | read 2 of 4 row groups, 5396 bytes of column chunks; skipped row group 2: order_id < 300: the minimum is too large; row group 3: order_id < 300: the minimum is too large | 800 | 400 |
| Filter | order_id < 300 and status = refunded | 400 | 12 |
| Aggregate | by country | 12 | 5 |
| Sort | country | 5 | 5 |

*Computed by the reader from `fixtures/writing-baseline.parquet` (28779 bytes).*
