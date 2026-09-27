# The book's reader opens the file as you did, and the store it reads from logs every request.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab.object_store import MemoryStore, NetworkModel, TracingStore
from parquet_lab.reader import FooterOptions, Head, SuffixRange, read_footer

files = MemoryStore()
files.put("tiny.parquet", open("fixtures/tiny.parquet", "rb").read())
store = TracingStore(files, NetworkModel())

# Try SuffixRange() for Head(), then raise prefetch until the footer comes in the first read.
opened = read_footer(store, "tiny.parquet", FooterOptions(size=Head(), prefetch=8))

for r in store.requests:
    print(r.method, r.range or "·", f"-> {r.bytes_returned} bytes by {r.end_us // 1000} ms:", r.why)
print("footer length:", opened.trailer.footer_length, "rows:", opened.metadata.num_rows)
