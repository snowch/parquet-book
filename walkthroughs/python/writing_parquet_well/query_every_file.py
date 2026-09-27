# The book's reader runs one query on every file: what does it read after the footer?
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab.object_store import NetworkModel
from parquet_lab.prune import Op
from parquet_lab.reader import FooterOptions, Head
from parquet_lab.scan import Query, Strategy, scan

files = "baseline one-group small-groups by-country shuffled plain no-index".split()
# Every column, where order_id = 431; try (3, Op.EQ, "FR"), then (4, Op.EQ, "refunded").
query = Query([0, 1, 2, 3, 4, 5], (0, Op.EQ, "431"))
# The footer found exactly, every skipping mechanism, and only ranges that touch merged.
strategy = Strategy(footer=FooterOptions(Head(), prefetch=8), coalesce_gap=0)
later = ("read the indexes", "read the pages")  # the requests after the footer

for name in files:
    data = open(f"fixtures/writing-{name}.parquet", "rb").read()
    result = scan(data, name, query, strategy, NetworkModel())
    after = [r for r in result.requests if r.why.startswith(later)]
    fetched, rows = sum(r.bytes_returned for r in after), len(result.matches)
    print(f"writing-{name}: {fetched} bytes in {len(after)} requests, {rows} rows matching")
