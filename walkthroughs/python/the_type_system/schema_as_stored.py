# The schema as the footer stores it: a flat list, one element per field, groups included.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata

data = open("fixtures/types.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length  # where the footer starts, as in ch02
md = metadata.decode_file_metadata(data[base:-8], base)

for e in md.schema:
    if e.num_children:
        print(e.name, e.num_children, "children", e.repetition)
    else:
        print(e.name, e.repetition, e.physical_type.name, e.logical_type or "")
