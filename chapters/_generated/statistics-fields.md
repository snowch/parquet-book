| Column | `min_value`, `max_value` | `min`, `max` (deprecated) | `null_count` |
|---|---|---|--:|
| `order_id` | yes | yes | 0 |
| `customer_id` | yes | · | 0 |
| `delta` | yes | yes | 0 |
| `city` | yes | · | 0 |
| `temp_c` | yes | yes | 0 |
| `amount` | yes | yes | 0 |
| `coupon` | yes | · | 1 |
| `note` | · | · | · |

*Row group 0 of `fixtures/statistics.parquet`, as its footer records it. `·` means the field is absent. Every column with `min_value` and `max_value` also has `is_min_value_exact` and `is_max_value_exact`.*
