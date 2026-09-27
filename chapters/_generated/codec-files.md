| Codec in the footer | File bytes | Column chunk bytes | Share of uncompressed |
|---|--:|--:|--:|
| `UNCOMPRESSED` | 15,953 | 15,135 | 100% |
| `SNAPPY` | 6,977 | 6,163 | 41% |
| `LZ4_RAW` | 6,641 | 5,827 | 39% |
| `GZIP` | 5,052 | 4,238 | 28% |
| `ZSTD` | 5,060 | 4,246 | 28% |
| `BROTLI` | 4,513 | 3,700 | 24% |

*Computed by the reader from the footers of `fixtures/codec-none.parquet`, `codec-snappy.parquet`, `codec-lz4.parquet`, `codec-gzip.parquet`, `codec-zstd.parquet` and `codec-brotli.parquet`: 256 orders, PLAIN-encoded, one row group, one data page per column chunk. Column chunk bytes include page headers.*
