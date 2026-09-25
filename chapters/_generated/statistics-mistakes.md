| Column | Row group | The footer, in the column's order | The mistaken order | What it gives |
|---|--:|---|---|---|
| `customer_id` | 0 | 7 … 3000000000 | signed integers | 2147483648 … 42 |
| `delta` | 0 | -120 … 7 | unsigned integers | 3 … -5 |
| `city` | 0 | "Aarhus" … "Łódź" | signed bytes | "Łódź" … "Zürich" |
| `temp_c` | 0 | -3 … 12.5 | the bits as signed integers | -3 … NaN |
| `amount` | 0 | -5.00 … 42.10 | unsigned bytes | 19.99 … -0.50 |

*Computed by the reader from the values it decoded from `fixtures/statistics.parquet`. The footer's minimum and maximum equal the first column in every row.*
