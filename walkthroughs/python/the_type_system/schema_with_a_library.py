# The same schema from pyarrow, which rebuilds the tree and reads the statistics' values for you.
import pyarrow.parquet as pq

md = pq.read_metadata("fixtures/types.parquet")
print(str(md.schema).partition("\n")[2])  # the text form; its first line is the object's repr
for i in range(md.num_columns):
    c, stats = md.schema.column(i), md.row_group(0).column(i).statistics
    levels = f"max levels {c.max_definition_level} {c.max_repetition_level}"
    print(f"{c.path}: {levels}, {c.physical_type}, min {stats.min!r}")
