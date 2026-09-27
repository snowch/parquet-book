# The book's reader runs SELECT * WHERE order_id = 431, and the store logs each request.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab.object_store import NetworkModel
from parquet_lab.prune import Op
from parquet_lab.reader import FooterOptions, Head, SuffixRange
from parquet_lab.scan import Query, Strategy, scan

data = open("fixtures/pruning-sorted.parquet", "rb").read()
query = Query([0, 1, 2, 3], (0, Op.EQ, "431"))  # every column, where order_id = 431

# Try SuffixRange() and prefetch=8192; then coalesce_gap=4096; then connections=4.
footer = FooterOptions(Head(), prefetch=8)
strategy = Strategy(footer=footer, connections=1, coalesce_gap=None)
result = scan(data, "orders.parquet", query, strategy, NetworkModel())

for r in result.requests:
    when = f"{r.start_us // 1000:>3}-{r.end_us // 1000:>3} ms"
    print(f"{when} on {r.connection + 1}: {r.method} {r.range or ''} {r.why}")
fetched, ms = result.bytes_fetched, result.elapsed_us // 1000
print(f"{len(result.requests)} requests, {fetched} bytes, {ms} ms")
print("rows matching:", result.matches)
