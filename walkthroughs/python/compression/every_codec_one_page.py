# Decompress one page under three codecs, and compare it with the uncompressed file's.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import compress, metadata, pages

def first_page(name, column):
    data = open(f"fixtures/codec-{name}.parquet", "rb").read()
    length = int.from_bytes(data[-8:-4], "little")
    base = len(data) - 8 - length
    md = metadata.decode_file_metadata(data[base:-8], base)
    chunk = md.row_groups[0].columns[column]
    span = chunk.byte_range()
    [page] = pages.walk_pages(data[span.start:span.end], span.start)
    return chunk.codec, page, data[page.body_span.start:page.body_span.end]

column = 1  # country; try 5, which is distance_km
_, _, plain = first_page("none", column)
for name in ["snappy", "lz4", "gzip"]:  # try adding "zstd"
    codec, page, body = first_page(name, column)
    size = page.uncompressed_page_size
    out = compress.decompress(codec, body, page.body_span.start, size)
    tokens, same = len(out.tokens), out.data == plain
    print(f"{codec}: {len(body)} bytes become {size} in {tokens} tokens, the same: {same}")
