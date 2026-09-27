# The book's reader queries the table: what it decided about each file, and every request.
import sys
from pathlib import Path
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab.object_store import MemoryStore, NetworkModel
from parquet_lab.table import Discovery, query

store = MemoryStore()  # every file of the table, under its key in a simulated object store
for path in Path("fixtures/table").rglob("*"):
    if path.is_file():
        store.put(path.relative_to("fixtures").as_posix(), path.read_bytes())

sql = "SELECT count(*) FROM orders WHERE country = 'UK' AND order_id < 200"
# Try Discovery.LIST_AND_PRUNE, then Discovery.LIST; then 1 or 8 connections.
result = query(store, "table/", sql, Discovery.LOG, 4, NetworkModel())

for f in result.files:
    print(f"{f.key}: {f.why}")
for r in result.requests:
    when = f"{r.start_us // 1000:>3}-{r.end_us // 1000:>3} ms"
    print(f"{when} on {r.connection + 1}: {r.method} {r.key}, {r.bytes_returned} bytes")
print(*result.answer.columns)
for row in result.answer.rows:
    print(*row)
