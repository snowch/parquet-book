# The book's reader plans a compaction: which files it would rewrite together.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab.changes import plan_compaction, read_snapshots

snapshots = read_snapshots(open("fixtures/changes/_snapshots.json").read())
snapshot = next(s for s in snapshots if s.id == "after-a-day")

# Try target_rows=100; then small_rows=10; then the snapshot "merge-on-read-8".
plan = plan_compaction(snapshot, target_rows=200, small_rows=100)

for n, group in enumerate(plan, 1):
    print(f"group {n}: {group.rows_in} rows in, {group.rows_out} out, "
          f"{group.bytes_in} bytes to read")
    for path in group.data_files + group.delete_files:
        print(f"  {path}")
print(f"{len(plan)} files to write, from {sum(g.bytes_in for g in plan)} bytes read")
