# The same facts from pyarrow: each file's codec for country, and the chunk's two sizes.
import pyarrow.parquet as pq

for name in ["snappy", "lz4", "gzip"]:  # try "zstd", "brotli" or "none"
    chunk = pq.read_metadata(f"fixtures/codec-{name}.parquet").row_group(0).column(1)
    before, after = chunk.total_uncompressed_size, chunk.total_compressed_size
    print(f"{chunk.path_in_schema}: {chunk.compression}, {after} of {before} bytes")
