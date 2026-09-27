# Undo Snappy by hand: a length, then tags that say "literal" or "copy".
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, pages

data = open("fixtures/codec-snappy.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
chunk = md.row_groups[0].columns[1].byte_range()  # country; try 5, distance_km
[page] = pages.walk_pages(data[chunk.start:chunk.end], chunk.start)
body = data[page.body_span.start:page.body_span.end]

size, shift, i = 0, 0, 0
while body[i] & 0x80:  # a varint: seven bits a byte, lowest first; a top bit means more
    size, shift, i = size | (body[i] & 0x7F) << shift, shift + 7, i + 1
size, i = size | body[i] << shift, i + 1
print(f"{len(body)} bytes; the varint says {size} will come out")
out, tokens = bytearray(), []
while i < len(body):
    tag, kind = body[i], body[i] & 3  # the low two bits say what the element is
    if kind == 0:  # a literal: its length - 1 in the top six bits, or in 1..4 more bytes
        n, i = (tag >> 2) + 1, i + 1
        if n > 60:
            n, i = int.from_bytes(body[i:i + n - 60], "little") + 1, i + n - 60
        out += body[i:i + n]
        i += n
        tokens.append(f"literal {n} bytes")
        continue
    if kind == 1:  # a copy of 4..11 bytes, up to 2047 back
        n, back, i = 4 + (tag >> 2 & 7), (tag >> 5) << 8 | body[i + 1], i + 2
    else:  # a copy of 1..64 bytes, its distance in 2 or 4 more bytes
        width = 2 if kind == 2 else 4
        n, back = (tag >> 2) + 1, int.from_bytes(body[i + 1:i + 1 + width], "little")
        i += 1 + width
    for _ in range(n):  # byte by byte: a copy may overlap the bytes it writes
        out.append(out[-back])
    tokens.append(f"copy {n} from {back} back")
print(*tokens[:6], sep="\n")  # try tokens[-6:]
header = page.uncompressed_page_size
print(f"{len(tokens)} tokens wrote {len(out)} bytes; the page header says {header}")
