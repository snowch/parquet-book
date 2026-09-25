| Column | Order | `min_value`, `max_value` | `min`, `max` (deprecated) | `null_count` | exact flags |
|---|---|---|---|--:|---|
| `order_id` | signed | yes | yes | 0 | yes |
| `customer_id` | unsigned | yes | · | 0 | yes |
| `delta` | signed | yes | yes | 0 | yes |
| `city` | unsigned | yes | · | 0 | yes |
| `temp_c` | signed | yes | yes | 0 | yes |
| `amount` | signed | yes | yes | 0 | yes |
| `coupon` | unsigned | yes | · | 1 | yes |
| `note` | unsigned | · | · | · | · |

*Row group 0 of `fixtures/statistics.parquet`, as its footer records it. `·` means the field is absent.*
