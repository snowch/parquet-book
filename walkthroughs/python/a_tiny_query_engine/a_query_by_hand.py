# Answer SELECT country, count(*) WHERE order_id < 300 GROUP BY country, by hand.
import sys, collections
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import column, report, schema

data = open("fixtures/writing-baseline.parquet", "rb").read()
md = report.open_bytes(data)  # the footer, found and decoded as in ch02
order_id, _, _, country, *_ = schema.leaves(schema.build(md.schema))
limit = 300  # WHERE order_id < 300; try 450, then 1
counts = collections.Counter()

for g, row_group in enumerate(md.row_groups):
    s = row_group.columns[order_id.column].statistics  # an INT64, least byte first
    low = int.from_bytes(s.min_value, "little", signed=True)
    if low >= limit:  # no row here can pass: read none of its pages
        print(f"row group {g} skipped: min order_id {low}")
        continue
    ids = column.read_column(data, row_group.columns[order_id.column], order_id).triples
    names = column.read_column(data, row_group.columns[country.column], country).triples
    kept = [n.value.decode() for i, n in zip(ids, names) if i.value < limit]  # the filter
    print(f"row group {g} read: {len(ids)} rows, {len(kept)} pass")
    counts.update(kept)  # the aggregate: one count per country

for name, n in sorted(counts.items()):
    print(name, n)
