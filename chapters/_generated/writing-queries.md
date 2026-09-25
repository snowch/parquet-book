| File | `order_id = 431` | `country = 'FR'` | `status = 'refunded'` | `amount_cents > 9900` | everything |
|---|--:|--:|--:|--:|--:|
| the baseline | 4,764 in 8 | 23,610 in 6 | 23,297 in 18 | 15,274 in 34 | 22,126 in 1 |
| one row group | 17,373 in 14 | 23,361 in 3 | 22,966 in 15 | 18,984 in 25 | 21,852 in 1 |
| row groups of 40 rows | 1,388 in 3 | 27,428 in 22 | 24,939 in 24 | 8,296 in 12 | 25,486 in 1 |
| sorted by country | 21,078 in 41 | 5,289 in 9 | 22,380 in 30 | 15,377 in 34 | 21,795 in 1 |
| shuffled | 23,828 in 6 | 23,588 in 6 | 22,318 in 30 | 15,248 in 34 | 22,104 in 1 |
| no dictionary | 1,584 in 8 | 24,011 in 6 | 22,031 in 18 | 8,111 in 22 | 22,413 in 1 |
| no page index | 6,650 in 1 | 26,608 in 1 | 26,608 in 1 | 19,958 in 2 | 26,608 in 1 |

*`SELECT *` with each condition, run by the reader against each file. Each cell is bytes and requests after the footer, which every query reads first. The reader uses statistics, Bloom filters where written and the page index, and merges only ranges that touch.*
