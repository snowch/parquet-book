# pyarrow reads Parquet files, not tables: the deletes are yours to apply.
from pathlib import Path
import pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq

path = "data/part-1.parquet"
rows = pq.read_table(f"fixtures/changes/{path}")
gone = []
for d in sorted(Path("fixtures/changes/deletes").glob("*.parquet")):
    named = pq.read_table(d).to_pylist()
    gone += [r["pos"] for r in named if r["file_path"] == path]

positions = pa.array(range(len(rows)))
live = rows.filter(pc.invert(pc.is_in(positions, value_set=pa.array(gone, pa.int64()))))
print(f"{path} holds {len(rows)} rows; {len(gone)} are deleted; {len(live)} are live")
print("their amounts sum to", pc.sum(live["amount_cents"]).as_py())
