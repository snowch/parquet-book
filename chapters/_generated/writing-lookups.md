| File | Row groups | `order_id`: row groups per lookup | `customer_id`: row groups per lookup |
|---|--:|--:|--:|
| the baseline | 4 | 1.00 | 3.96 |
| one row group | 1 | 1.00 | 1.00 |
| row groups of 40 rows | 20 | 1.00 | 18.99 |
| sorted by country | 4 | 3.65 | 3.97 |
| shuffled | 4 | 3.98 | 3.98 |
| no dictionary | 4 | 1.00 | 3.96 |
| no page index | 4 | 1.00 | 3.96 |

*For every value in the column, the row groups whose footer bounds include it, averaged. Computed by the reader from the `fixtures/writing-*.parquet` files.*
