| File | Codec in the footer | File bytes | Column chunk bytes | Share of uncompressed |
|---|---|--:|--:|--:|
| `codec-none.parquet` | `UNCOMPRESSED` | 15,953 | 15,135 | 100% |
| `codec-snappy.parquet` | `SNAPPY` | 6,977 | 6,163 | 41% |
| `codec-lz4.parquet` | `LZ4_RAW` | 6,641 | 5,827 | 39% |
| `codec-gzip.parquet` | `GZIP` | 5,052 | 4,238 | 28% |
| `codec-zstd.parquet` | `ZSTD` | 5,060 | 4,246 | 28% |
| `codec-brotli.parquet` | `BROTLI` | 4,513 | 3,700 | 24% |

*Computed by the reader from the footers of the `fixtures/codec-*.parquet` files: 256 orders, PLAIN-encoded, one row group, one data page per column chunk. Column chunk bytes include page headers.*
