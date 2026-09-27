# Read the page index of order_id in one row group: each page's range and first row.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, page_index

path = "fixtures/pruning-sorted.parquet"  # try pruning-shuffled.parquet
data = open(path, "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
chunk = md.row_groups[2].columns[0]  # order_id in row group 2
ci = page_index.column_index(data, chunk)  # per page: a minimum, a maximum, a null count
oi = page_index.offset_index(data, chunk)  # per page: an offset, a size, a first row
print(f"{len(oi.pages)} pages, boundary order {ci.boundary_order}")
wanted = 431

for i, page in enumerate(oi.pages):
    low = int.from_bytes(ci.min_values[i], "little", signed=True)
    high = int.from_bytes(ci.max_values[i], "little", signed=True)
    verdict = "read" if low <= wanted <= high else "skip"
    end = page.offset + page.compressed_page_size
    print(f"page {i}: order_id {low} to {high}, {verdict}; "
          f"rows from {page.first_row_index}, bytes {page.offset} to {end}")
