# The book's reader: every slot of a column as its two levels and a value, then the records.
import sys, json
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import column, logical, metadata, nested, schema

data = open("fixtures/nested.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
root = schema.build(md.schema)
name = "tags"  # try "email", "order_id", or "items", which has two columns

for leaf in (leaf for leaf in schema.leaves(root) if leaf.path[0] == name):
    fields = nested.path_fields(root, leaf)  # each field on the path, with its levels
    triples = column.read_column(data, md.row_groups[0].columns[leaf.column], leaf).triples
    most = f"definition {leaf.max_definition_level}, repetition {leaf.max_repetition_level}"
    print(f"{fields[-1].label}  max levels: {most}\nr d value")
    for t in triples:
        v = t.value
        v = None if v is None else logical.value_json(leaf.physical_type, leaf.logical_type, v)
        print(t.rep, t.definition, json.dumps(v))
    for record in nested.assemble(fields, leaf, triples):
        print(json.dumps(record))
