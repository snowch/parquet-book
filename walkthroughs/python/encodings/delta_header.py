# DELTA_BINARY_PACKED by hand: a header of varints, then a block of bit-packed deltas.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, pages

data = open("fixtures/encodings.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
column = 1  # ordered_at; try 0, which is order_id
chunk = md.row_groups[0].columns[column].byte_range()
page = pages.walk_pages(data[chunk.start:chunk.end], chunk.start)[0]  # its one page
body = data[page.body_span.start:page.body_span.end]  # values only: no levels

def uleb128(at):  # seven bits a byte, lowest first, until a byte without its top bit
    n = shift = 0
    while body[at] & 0x80:
        n, at, shift = n | (body[at] & 0x7F) << shift, at + 1, shift + 7
    return n | body[at] << shift, at + 1

def zigzag(at):  # 0, 1, 2, 3, 4 stand for 0, -1, 1, -2, 2: small either side of zero
    n, at = uleb128(at)
    return n >> 1 ^ -(n & 1), at

block, at = uleb128(0)
miniblocks, at = uleb128(at)
count, at = uleb128(at)
first, at = zigzag(at)
print(f"{len(body)} bytes; header {body[:at].hex(' ')}")
print(f"blocks of {block}, {miniblocks} miniblocks, {count} values, first {first}")
smallest, at = zigzag(at)
widths = list(body[at:at + miniblocks])
print(f"min delta {smallest}; widths {widths}")
at += miniblocks  # the first miniblock: each delta less the smallest, in widths[0] bits
width = widths[0]
bits = int.from_bytes(body[at:at + width], "little")  # eight deltas take width bytes
deltas = [smallest + (bits >> i * width & (1 << width) - 1) for i in range(8)]
print("first deltas:", deltas)
