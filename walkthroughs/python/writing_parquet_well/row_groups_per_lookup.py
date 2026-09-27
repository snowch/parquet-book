# Read each file's footer: how many of its row groups could hold order 431?
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata

files = "baseline one-group small-groups by-country shuffled plain no-index".split()
column, wanted = 0, 431  # order_id = 431; try 2, customer_id, and 500000

for name in files:
    data = open(f"fixtures/writing-{name}.parquet", "rb").read()
    length = int.from_bytes(data[-8:-4], "little")
    base = len(data) - 8 - length
    md = metadata.decode_file_metadata(data[base:-8], base)
    hits = 0
    for row_group in md.row_groups:
        s = row_group.columns[column].statistics  # an INT64: eight bytes, least first
        low = int.from_bytes(s.min_value, "little", signed=True)
        high = int.from_bytes(s.max_value, "little", signed=True)
        hits += low <= wanted <= high
    groups = len(md.row_groups)
    print(f"writing-{name}: footer {length} bytes, {hits} of {groups} row groups may hold it")
