# Unpack a page's levels by hand: a length, a run header, then levels, lowest bits first.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, pages, schema

data = open("fixtures/nested.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
column = 4  # items[].discounts[]; try 2, which is tags[], or 1, which is email
leaf = schema.leaves(schema.build(md.schema))[column]
chunk = md.row_groups[0].columns[column].byte_range()
page = pages.walk_pages(data[chunk.start:chunk.end], chunk.start)[0]  # its one page
body, slots = data[page.body_span.start:page.body_span.end], page.num_values

at = 0  # repetition levels come first, then definition levels, then values
for name, most in (("rep", leaf.max_repetition_level), ("def", leaf.max_definition_level)):
    if most == 0:
        print(f"{name}: none stored, since the maximum is 0")
        continue
    size = int.from_bytes(body[at:at + 4], "little")  # a version-1 page's length prefix
    header, width = body[at + 4], most.bit_length()  # a ULEB128 header, one byte here
    bits = int.from_bytes(body[at + 5:at + 4 + size], "little")
    kind = f"{name}: {size} bytes, header {header:02x},"
    if header & 1:  # bit-packed: header >> 1 groups of eight levels, width bits each
        groups = header >> 1
        levels = [bits >> (i * width) & (1 << width) - 1 for i in range(slots)]
        padding = f"(+{8 * groups - slots} padding)"
        print(kind, f"bit-packed, {groups} group:", *levels, padding)
    else:  # RLE: header >> 1 copies of the one level that follows
        print(kind, f"RLE, {header >> 1} copies of", bits)
    at += 4 + size
