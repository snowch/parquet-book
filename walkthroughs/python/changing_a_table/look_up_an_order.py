# The book's reader finds one order in a snapshot, and the store logs each request.
import sys
from itertools import groupby
from pathlib import Path
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab.changes import lookup
from parquet_lab.object_store import MemoryStore, NetworkModel

store = MemoryStore()  # every file of the table, under its key in a simulated store
for path in Path("fixtures/changes").rglob("*"):
    if path.is_file():
        store.put(path.relative_to("fixtures/changes").as_posix(), path.read_bytes())

# Try order 250; then the snapshot "written"; then prefetch 65536.
snapshot, key, prefetch = "after-a-day", 300, 0
result = lookup(store, "", snapshot, key, prefetch, connections=4, model=NetworkModel())

for trip, (_, requests) in enumerate(groupby(result.requests, lambda r: r.phase), 1):
    print(f"round trip {trip}:")
    for r in requests:
        print(f"  {r.end_us // 1000:>3} ms: {r.method} {r.key} {r.range or '·'} {r.why}")
if result.found is None:
    print(f"no file holds order {key}")
else:
    path, pos = result.found
    gone = f", but {result.deleted_by} deletes it" if result.deleted_by else ""
    print(f"order {key} is row {pos} of {path}{gone}")
    for column, value in result.row:
        print(f"  {column}: {value}")
n, fetched, ms = len(result.requests), result.bytes_fetched, result.elapsed_us // 1000
print(f"{n} requests, {fetched} bytes, {ms} ms")
