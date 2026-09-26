| A reader without keys | What | Detail |
|---|---|---|
| can see | That it is Parquet, with an encrypted footer | PARE |
| can see | The encryption algorithm | AES_GCM_V1 |
| can see | The footer key's name | footer |
| can see | The encrypted footer's size | 954 bytes |
| cannot see | The schema | inside the encrypted footer |
| cannot see | The number of rows | inside the encrypted footer |
| cannot see | Where any column is | inside the encrypted footer |
| cannot see | Any statistics | inside the encrypted footer |
| cannot see | Any values, even of columns not encrypted | inside the encrypted footer |

*Computed by the reader from `fixtures/encrypted-footer.parquet` (2123 bytes).*
