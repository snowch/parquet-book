# The same facts from pyarrow: bounds read through the logical type, and raw.
import pyarrow.parquet as pq

md = pq.read_metadata("fixtures/statistics.parquet")
row_group = md.row_group(0)  # try 1
print(f"the footer: {md.serialized_size} bytes; sorted by {row_group.sorting_columns}")
for i in range(md.num_columns):
    c = row_group.column(i)
    s, name = c.statistics, c.path_in_schema
    if s is None:  # the writer kept none
        print(f"{name}: no statistics")
    elif not s.has_min_max:
        print(f"{name}: no minimum or maximum, null count {s.null_count}")
    else:
        print(f"{name}: {s.min!r} to {s.max!r}, null count {s.null_count}")
        if s.max_raw != s.max:  # as the physical type reads them, where that differs
            print(f"  raw, as {s.physical_type}: {s.min_raw!r} to {s.max_raw!r}")
