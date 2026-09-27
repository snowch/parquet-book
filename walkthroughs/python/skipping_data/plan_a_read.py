# Plan SELECT * WHERE order_id = 431 with the reader, one mechanism at a time.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, prune, schema

path = "fixtures/pruning-sorted.parquet"  # try pruning-shuffled.parquet
data = open(path, "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
leaves = schema.leaves(schema.build(md.schema))
leaf = leaves[0]  # order_id; try 1, customer_id, with "424242"
converted = md.schema[leaf.element].converted_type
p = prune.Predicate.new(leaf, converted, prune.Op.EQ, "431")
use = prune.Mechanisms(statistics=True, bloom=True, page_index=True)  # turn each off
every = [x.column for x in leaves]  # SELECT *

plan = prune.plan(data, md, leaf, p, every, use)
for g in plan.row_groups:
    print(f"row group {g.index}: {'skip' if g.skipped else f'read rows {g.rows}'}")
    for mechanism, decision in g.steps:
        print(f"  {mechanism}: {'skip' if decision.skip else 'read'}, {decision.why}")
print(f"{plan.bytes_read()} bytes of column chunks, {plan.index_bytes()} to decide")
