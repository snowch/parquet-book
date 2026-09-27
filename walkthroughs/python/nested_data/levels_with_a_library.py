# The same column from pyarrow, which reads the levels into Arrow's own shape and hides them.
import pyarrow.parquet as pq

tags = pq.read_table("fixtures/nested.parquet", columns=["tags"]).column("tags")
tags = tags.combine_chunks()  # one Arrow ListArray: offsets, a validity bitmap, and values
print("offsets:", tags.offsets.to_pylist())  # list i is values[offsets[i]:offsets[i + 1]]
print("null lists:", tags.is_null().to_pylist())
print("values:", tags.values.to_pylist())
print("records:", tags.to_pylist())
