# The book's reader decodes a column, and records each step: a label, bytes, what it read.
import sys, json
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import column, logical, metadata, schema

data = open("fixtures/encodings.parquet", "rb").read()  # or dictionary.parquet
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
name = "url"  # try "order_id", "sku" or "weight_kg"; or "country" in dictionary.parquet
leaves = schema.leaves(schema.build(md.schema))
leaf = next(leaf for leaf in leaves if leaf.path == [name])
read = column.read_column(data, md.row_groups[0].columns[leaf.column], leaf)

def show(v):
    return json.dumps(logical.value_json(leaf.physical_type, leaf.logical_type, v))

if read.dictionary:
    print("dictionary page:", *(show(v) for v, _ in read.dictionary.entries))
for page in read.pages:
    print(page.encoding, "page")
    for step in page.steps:
        raw = data[step.span.start:step.span.end]
        more = f" … ({len(raw)} bytes)" if len(raw) > 8 else ""
        print(f"  {step.label}: {raw[:8].hex(' ')}{more}\n    {step.detail}")
print("values:", *(show(t.value) for t in read.triples[:4]), "…")
