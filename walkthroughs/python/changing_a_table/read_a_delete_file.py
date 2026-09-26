# A position delete file is a Parquet file of (file_path, pos): read one with the book's reader.
import sys

sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import engine  # noqa: E402

deletes = open("fixtures/changes/deletes/delete-00.parquet", "rb").read()
for path, pos in engine.run(deletes, "SELECT file_path, pos FROM deletes").rows:
    data = open(f"fixtures/changes/{path}", "rb").read()
    order = engine.run(data, "SELECT order_id FROM orders").rows[pos][0]
    print(f"row {pos} of {path} is deleted: order {order}")
