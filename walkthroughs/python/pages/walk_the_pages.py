# Walk a column chunk page by page: each header says how long its body is.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, pages
from parquet_lab.bytes import ByteReader

data = open("fixtures/pages.parquet", "rb").read()  # try pages-v2.parquet
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
chunk = md.row_groups[0].columns[1]  # country; try 2, which is amount_cents
start = chunk.dictionary_page_offset or chunk.data_page_offset  # the first page's header
end = start + chunk.total_compressed_size  # every page, headers included
print(f"{chunk.dotted_path()}: bytes {start} to {end}")

r = ByteReader(data[start:end], start)
while not r.is_at_end():
    page = pages.read_page(r)  # a Thrift header, then as many bytes of body as it says
    header = page.header_span.end - page.header_span.start
    line = f"{page.page_type} at {page.header_span.start}: {header}-byte header, "
    line += f"{page.compressed_page_size}-byte body, {page.num_values} values"
    if page.v2:  # a version 2 header also counts the page's rows and nulls
        line += f", {page.v2.num_rows} rows, {page.v2.num_nulls} nulls"
    print(line)
