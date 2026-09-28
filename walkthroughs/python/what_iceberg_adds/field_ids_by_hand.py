# Iceberg names a column by its field id, a number each data file's footer records.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import engine, metadata

data = open("fixtures/changes/data/part-0.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length  # where the footer starts, as in ch02
md = metadata.decode_file_metadata(data[base:-8], base)
by_id = {e.field_id: e.name for e in md.schema if e.field_id is not None}
for field_id, name in by_id.items():
    print(f"field id {field_id}: {name}")

# The table's schema now, by id: order_id has been renamed, and channel added since.
table = {1: "order_number", 4: "country", 6: "amount_cents", 7: "channel"}
names = [by_id[i] for i in table if i in by_id]  # this file's names for them
answer = engine.run(data, f"SELECT {', '.join(names)} FROM orders")
first = dict(zip(answer.columns, answer.rows[0]))
for field_id, name in table.items():
    column = by_id.get(field_id, "no column")  # the file predates the column
    print(f"{name} (id {field_id}) <- {column}: {first.get(column)}")
print("by name, the file has no", ", ".join(n for n in table.values() if n not in first))
