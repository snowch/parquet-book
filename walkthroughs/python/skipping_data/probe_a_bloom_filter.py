# Probe each row group's Bloom filter on customer_id for one customer number.
import struct, sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import bloom, metadata

path = "fixtures/pruning-shuffled.parquet"  # try pruning-sorted.parquet
data = open(path, "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
value = struct.pack("<q", 424242)  # an INT64's PLAIN bytes; try another customer
print(f"xxHash64 of {value.hex(' ')}: {bloom.xxh64(value):016x}")

for g, row_group in enumerate(md.row_groups):
    f = bloom.read(data, row_group.columns[1])  # customer_id's filter
    # The hash's high half picks a block, its low half a bit in each of its words.
    p = f.probe(value)
    print(f"row group {g}: block {p.block} of {f.num_blocks()}, bits {p.bits}")
    print(f"  may contain it: {p.may_contain}")
