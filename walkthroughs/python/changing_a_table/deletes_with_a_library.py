# The same deletes applied with pyarrow, which reads Parquet files but not tables: you apply them.
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

path = "data/part-1.parquet"
rows = pq.read_table(f"fixtures/changes/{path}")
gone = []
for d in sorted(Path("fixtures/changes/deletes").glob("*.parquet")):
    named = pq.read_table(d).to_pylist()
    gone += [r["pos"] for r in named if r["file_path"] == path]

keep = pc.invert(pc.is_in(pa.array(range(rows.num_rows)), value_set=pa.array(gone, pa.int64())))
live = rows.filter(keep)
print(f"{path} holds {rows.num_rows} rows; {len(gone)} are deleted; {live.num_rows} are live")
print("their amounts sum to", pc.sum(live["amount_cents"]).as_py())
