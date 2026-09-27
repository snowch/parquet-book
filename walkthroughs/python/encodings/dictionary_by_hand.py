# A dictionary page and the indices into it, by hand.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, pages

data = open("fixtures/dictionary.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
chunk = md.row_groups[0].columns[1].byte_range()  # country
dictionary, page = pages.walk_pages(data[chunk.start:chunk.end], chunk.start)

body = data[dictionary.body_span.start:dictionary.body_span.end]
entries, at = [], 0
while at < len(body):  # PLAIN strings: a four-byte length, then the bytes
    n = int.from_bytes(body[at:at + 4], "little")
    entries.append(body[at + 4:at + 4 + n].decode())
    at += 4 + n
print(dictionary.page_type, dictionary.encoding, entries)

body = data[page.body_span.start:page.body_span.end]
width, header = body[0], body[1]  # the indices' bit width, then a run's ULEB128 header
kind = f"{page.page_type} {page.encoding}: {len(body)} bytes"
print(f"{kind}, width {width}, header {header:02x}")
bits = int.from_bytes(body[2:], "little")  # bit-packed: header >> 1 groups of eight
slots = page.num_values  # try 8 * (header >> 1), to see the group's padding
indices = [bits >> i * width & (1 << width) - 1 for i in range(slots)]
print("indices:", indices)
print("values:", [entries[i] for i in indices])
