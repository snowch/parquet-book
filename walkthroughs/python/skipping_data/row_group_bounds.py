# Read each row group's range of order_id from the footer: can it hold order 431?
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata

path = "fixtures/pruning-sorted.parquet"  # try pruning-shuffled.parquet
data = open(path, "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
wanted = 431  # order_id = 431; try 200 and 201

for g, row_group in enumerate(md.row_groups):
    s = row_group.columns[0].statistics  # order_id, an INT64
    low = int.from_bytes(s.min_value, "little", signed=True)  # eight bytes, least first
    high = int.from_bytes(s.max_value, "little", signed=True)
    verdict = "read" if low <= wanted <= high else "skip"
    print(f"row group {g}: order_id {low} to {high}, {verdict}")
