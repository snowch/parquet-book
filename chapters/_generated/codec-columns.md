| Column | none | snappy | lz4 | gzip | zstd | brotli |
|---|--:|--:|--:|--:|--:|--:|
| `order_id` | 2,114 | 1,105 | 1,097 | 508 | 430 | 375 |
| `country` | 1,570 | 136 | 76 | 87 | 80 | 63 |
| `sku` | 3,118 | 351 | 246 | 188 | 313 | 120 |
| `amount_cents` | 2,114 | 1,141 | 1,134 | 804 | 640 | 679 |
| `weight_kg` | 2,114 | 1,316 | 1,309 | 949 | 1,011 | 905 |
| `distance_km` | 2,114 | 1,940 | 1,868 | 1,590 | 1,674 | 1,467 |
| `note` | 1,991 | 174 | 97 | 112 | 98 | 91 |

*Column chunk bytes, including page headers, from the footers of the `fixtures/codec-*.parquet` files.*
