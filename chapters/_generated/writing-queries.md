| File | `country = 'FR'` | `status = 'refunded'` | `amount_cents > 9900` |
|---|--:|--:|--:|
| the baseline | 23,610 in 6 | 23,297 in 18 | 15,274 in 34 |
| one row group | 23,361 in 3 | 22,966 in 15 | 18,984 in 25 |
| row groups of 40 rows | 27,428 in 22 | 24,939 in 24 | 8,296 in 12 |
| sorted by country | 5,289 in 9 | 22,380 in 30 | 15,377 in 34 |
| shuffled | 23,588 in 6 | 22,318 in 30 | 15,248 in 34 |
| no dictionary | 24,011 in 6 | 22,031 in 18 | 8,111 in 22 |
| no page index | 26,608 in 1 | 26,608 in 1 | 19,958 in 2 |

*`SELECT *` with each condition, run by the reader against each file with the second step's strategy. Each cell is bytes and requests after the footer, which every query reads first.*
