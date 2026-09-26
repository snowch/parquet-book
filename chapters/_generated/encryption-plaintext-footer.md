| A reader without keys | What | Detail |
|---|---|---|
| can see | The encryption algorithm | AES_GCM_V1 |
| can see | The footer's signature, which only the footer key can check | 28 bytes |
| can see | The schema | order_id, country, email, amount_cents |
| can see | The number of rows | 12 |
| can see | The values of order_id | 1, 2, 3, 4, … |
| can see | The statistics of order_id | 1 to 12 |
| can see | The values of country | "UK", "SE", "UK", "PL", … |
| can see | The statistics of country | "PL" to "US" |
| can see | Which key protects email | pii |
| can see | Which key protects amount_cents | finance |
| cannot see | The values of email | column email is encrypted with its own key, and this reader has no keys |
| cannot see | The statistics of email | withheld from the plaintext footer |
| cannot see | The values of amount_cents | column amount_cents is encrypted with its own key, and this reader has no keys |
| cannot see | The statistics of amount_cents | withheld from the plaintext footer |

*Computed by the reader from `fixtures/plaintext-footer.parquet` (2192 bytes).*
