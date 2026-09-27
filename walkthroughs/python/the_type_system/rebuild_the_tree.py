# Rebuild the tree from the flat list: each group's count of children is all it takes.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata, schema

data = bytearray(open("fixtures/types.parquet", "rb").read())
data[674] = 0x14  # the root's count of children, 10, as a zigzag varint; try 0x12, which is 9
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(bytes(data[base:-8]), base)

def walk(elements, depth=0, definition=0, repetition=0):
    e = next(elements)
    if depth:  # every optional or repeated field on the way down adds a level
        definition += e.repetition != "REQUIRED"
        repetition += e.repetition == "REPEATED"
    levels = f"  max levels: definition {definition}, repetition {repetition}"
    print("  " * depth + e.name + ("" if e.num_children else levels))
    for _ in range(e.num_children or 0):
        walk(elements, depth + 1, definition, repetition)

walk(iter(md.schema))
try:
    print("the reader's build finds", len(schema.leaves(schema.build(md.schema))), "columns")
except schema.SchemaError as refused:
    print("the reader refuses:", refused)
