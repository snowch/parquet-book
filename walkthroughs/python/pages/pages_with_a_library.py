# The same facts from pyarrow: where a column chunk's pages are, and damage refused.
import io
import pyarrow.parquet as pq

path = "fixtures/pages-v2.parquet"
chunk = pq.read_metadata(path).row_group(0).column(1)  # country; pyarrow has no page API
dictionary, first = chunk.dictionary_page_offset, chunk.data_page_offset
start = dictionary or first
print(f"{chunk.path_in_schema}: bytes {start} to {start + chunk.total_compressed_size}")
print(f"the dictionary page at {dictionary}, the first data page at {first}")

def country(source, **options):  # one thread: a refused read must not leave workers behind
    table = pq.read_table(source, columns=["country"], use_threads=False, **options)
    return table["country"].to_pylist()

data = bytearray(open(path, "rb").read())
data[start + chunk.total_compressed_size - 2] ^= 1  # the bit damage_a_page flipped
before, after = country(path), country(io.BytesIO(data))
for row in [row for row, (a, b) in enumerate(zip(before, after)) if a != b]:
    print(f"unchecked, row {row} reads {after[row]!r}, not {before[row]!r}")
try:
    country(io.BytesIO(data), page_checksum_verification=True)
except OSError as e:
    print("checked, it refuses:", e)
