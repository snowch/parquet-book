# Check a page's checksum, then flip one bit of its body and check again.
import sys, zlib
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, pages

data = bytearray(open("fixtures/pages-v2.parquet", "rb").read())
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
chunk = md.row_groups[0].columns[1].byte_range()  # country
page = pages.walk_pages(data[chunk.start:chunk.end], chunk.start)[-1]  # its last page
start, end = page.body_span.start, page.body_span.end
stored = page.crc & 0xFFFF_FFFF  # the header stores it as a signed 32-bit integer
print(f"{page.page_type} at {page.header_span.start}: its header says {stored:08x}")

def check(label):
    crc = zlib.crc32(data[start:end])  # CRC-32 of the body, as zlib computes it
    print(f"{label}: {crc:08x}, matches the header: {crc == stored}")

check("the body as written")
data[end - 2] ^= 1  # one bit of the values; try another byte, or another bit
check("one bit flipped")
walked = pages.walk_pages(data[chunk.start:chunk.end], chunk.start)
print("the reader's walk:", [p.crc_ok for p in walked])
