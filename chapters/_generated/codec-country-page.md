| Codec | Compressed bytes | Tokens | Bytes written as literals | Bytes copied from earlier | Longest copy |
|---|--:|--:|--:|--:|--:|
| SNAPPY | 102 | 35 | 13 | 1,523 | 64 |
| LZ4_RAW | 43 | 13 | 18 | 1,518 | 1,497 |
| GZIP | 54 | 18 | 15 | 1,521 | 258 |

*The `country` column's data page, 1,536 bytes before compression, decompressed by the reader from `fixtures/codec-snappy.parquet`, `codec-lz4.parquet` and `codec-gzip.parquet`. Tokens include headers and trailers.*
