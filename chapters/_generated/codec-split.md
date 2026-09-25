| Column | Encoding | Before ZSTD | After ZSTD |
|---|---|--:|--:|
| `weight_kg` | `PLAIN` | 2,114 | 1,011 |
| `weight_kg` | `BYTE_STREAM_SPLIT` | 2,114 | 1,569 |
| `distance_km` | `PLAIN` | 2,114 | 1,674 |
| `distance_km` | `BYTE_STREAM_SPLIT` | 2,114 | 1,416 |

*Computed by the reader from the footers of `fixtures/codec-zstd.parquet` and `fixtures/codec-zstd-split.parquet`, which differ only in these two columns' encoding.*
