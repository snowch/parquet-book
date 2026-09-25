| File | File bytes | Footer bytes | Statistics in the footer | Column chunks |
|---|--:|--:|--:|--:|
| `statistics.parquet` | 3,911 | 2,139 | 607 | 24 |
| `codec-none.parquet` | 15,953 | 806 | 240 | 7 |

*Computed by the reader from the fixtures' footers. Statistics bytes are the `Statistics` structures in the column chunks' metadata; page headers carry their own copies, which are not counted.*
