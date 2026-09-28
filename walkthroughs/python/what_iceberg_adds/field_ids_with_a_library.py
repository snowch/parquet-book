# pyarrow keeps each field's id in its metadata, under the key PARQUET:field_id.
import pyarrow.parquet as pq

path = "fixtures/changes/data/part-0.parquet"
by_id = {int(f.metadata[b"PARQUET:field_id"]): f.name for f in pq.read_schema(path)}
for field_id, name in by_id.items():
    print(f"field id {field_id}: {name}")

# pyarrow reads columns by name, so the id the table knows is turned into this file's name.
wanted = 1
column = pq.read_table(path, columns=[by_id[wanted]]).column(0)
print(f"id {wanted} <- {by_id[wanted]}: {column[0]}")
