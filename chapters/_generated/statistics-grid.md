| Column | Order | Row group 0 | Row group 1 | Row group 2 |
|---|---|---|---|---|
| `order_id` | signed | 1 … 4 | 5 … 8 | 9 … 12 |
| `customer_id` | unsigned | 7 … 3000000000 | 8 … 4000000000 | 1 … 2500000000 |
| `delta` | signed | -120 … 7 | -1 … 100 | -3 … 12 |
| `city` | unsigned | "Aarhus" … "Łódź" | "Bergen" … "Écija" | "Cork" … "Ängelholm" |
| `temp_c` | signed | -3 … 12.5 | -0 … 20 | 1 … 7.5 |
| `amount` | signed | -5.00 … 42.10 | -19.99 … 7.25 | -100.00 … 12.00 |
| `coupon` | unsigned | "SPRING" … "WELCOME" | all null | "SUMMER" … "SUMMER" |
| `note` | unsigned | none | none | none |

*Computed by the reader from `fixtures/statistics.parquet` (3911 bytes).*
