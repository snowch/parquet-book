# Take a column's bounds from the footer, and read their bytes two ways.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata

data = open("fixtures/statistics.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
column = 1  # customer_id; try 2, which is delta
e = md.leaves()[column]
print(e.name, e.physical_type.name, e.logical_type)

for g, row_group in enumerate(md.row_groups):
    s = row_group.columns[column].statistics
    low, high = s.min_value, s.max_value  # four bytes each, least significant first
    unsigned = [int.from_bytes(b, "little") for b in (low, high)]
    signed = [int.from_bytes(b, "little", signed=True) for b in (low, high)]
    print(f"row group {g}: max {high.hex(' ')}; unsigned {unsigned}, signed {signed}")
