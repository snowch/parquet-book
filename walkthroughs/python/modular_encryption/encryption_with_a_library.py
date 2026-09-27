# pyarrow without keys: a plaintext footer opens, an encrypted one does not.
import pyarrow.parquet as pq

path = "fixtures/plaintext-footer.parquet"
metadata = pq.read_metadata(path)
print(f"plaintext-footer.parquet: {metadata.num_rows} rows")
for i in [0, 1]:  # never 2 or 3: pyarrow stops Python on an encrypted column's metadata
    chunk = metadata.row_group(0).column(i)
    s = chunk.statistics
    print(f"  {chunk.path_in_schema}: statistics {s.min} to {s.max}")
for columns in [["order_id", "country"], ["email"]]:  # try ["amount_cents"]
    try:
        table = pq.read_table(path, columns=columns)
        print(f"  read {columns}: {table.num_rows} rows")
    except OSError as e:
        print(f"  read {columns}: {e}")
try:
    pq.read_metadata("fixtures/encrypted-footer.parquet")
except OSError as e:
    print(f"encrypted-footer.parquet: {e}")
