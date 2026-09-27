# Ask the reader which bounds it may use, column chunk by column chunk, and why not.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import encoding, logical, metadata, schema, stats

data = open("fixtures/statistics.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
old_writer = False  # try True: keep only the deprecated min and max, as old writers did

def show(leaf, v):  # through the logical type if it has one, else the physical type
    t, lt = leaf.physical_type, leaf.logical_type
    return (lt and logical.interpret(t, lt, v)) or encoding.plain_scalar(t, v)

for leaf in schema.leaves(schema.build(md.schema)):
    comparator = stats.Comparator.for_leaf(leaf, md.schema[leaf.element].converted_type)
    type_order = md.column_orders[leaf.column] == "TYPE_ORDER"
    print(f"{leaf.dotted_path()}, compared as {comparator.description}:")
    for g, row_group in enumerate(md.row_groups):
        s = row_group.columns[leaf.column].statistics
        if s is None:
            print(f"  row group {g}: no statistics")
            continue
        if old_writer:
            s.min_value = s.max_value = None
        try:
            b = stats.bounds(s, comparator, type_order)
            low, high = show(leaf, b.min), show(leaf, b.max)
            print(f"  row group {g}: {low} to {high}, from {b.source}")
        except stats.Unusable as refused:
            print(f"  row group {g}: refused, {refused}; null count {s.null_count}")
