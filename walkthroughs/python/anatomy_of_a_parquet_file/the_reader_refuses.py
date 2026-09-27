# The same damage as before, handed to the book's reader: it checks the length before trusting it.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab.object_store import MemoryStore, NetworkModel, TracingStore
from parquet_lab.reader import FooterOptions, read_footer

data = bytearray(open("fixtures/tiny.parquet", "rb").read())
data[-7] = 0xFF  # the second byte of the footer length
files = MemoryStore()
files.put("tiny.parquet", bytes(data))
store = TracingStore(files, NetworkModel())

try:
    read_footer(store, "tiny.parquet", FooterOptions())
except Exception as refused:
    print("the reader refuses:", refused)
print("after", len(store.requests), "requests:", ", ".join(r.why for r in store.requests))
