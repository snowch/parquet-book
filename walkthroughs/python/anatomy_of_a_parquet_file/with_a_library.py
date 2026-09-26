# The same facts from pyarrow, which reads the trailer and parses the footer for you.
import pyarrow.parquet as pq

metadata = pq.read_metadata("fixtures/tiny.parquet")
print("footer length:", metadata.serialized_size)
print("rows:", metadata.num_rows, "in", metadata.num_row_groups, "row group")
for i in range(metadata.num_columns):
    chunk = metadata.row_group(0).column(i)
    # A chunk starts with its dictionary page when it has one, and its first data page otherwise.
    start = chunk.dictionary_page_offset or chunk.data_page_offset
    print(f"column chunk {chunk.path_in_schema}: bytes {start} to {start + chunk.total_compressed_size}")
