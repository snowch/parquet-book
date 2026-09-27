# What a snapshot says the table is: its data files and delete files, from its metadata.
import json

snapshots = json.load(open("fixtures/changes/_snapshots.json"))["snapshots"]
snapshot = next(s for s in snapshots if s["id"] == "after-a-day")

for f in snapshot["data_files"]:
    rows, size = f["record_count"], f["file_size"]
    print(f"{f['path']}: {rows} rows in {size} bytes, {size // rows} bytes a row")
data, deletes = snapshot["data_files"], snapshot["delete_files"]
print(len(data), "data files and", len(deletes), "delete files")
