# What a snapshot says the table is: its data files and delete files, from the table's metadata.
import json

snapshots = json.load(open("fixtures/changes/_snapshots.json"))["snapshots"]
snapshot = next(s for s in snapshots if s["id"] == "after-a-day")

for f in snapshot["data_files"]:
    per_row = f["file_size"] // f["record_count"]
    print(f"{f['path']}: {f['record_count']} rows in {f['file_size']} bytes, {per_row} bytes a row")
print(len(snapshot["data_files"]), "data files and", len(snapshot["delete_files"]), "delete files")
