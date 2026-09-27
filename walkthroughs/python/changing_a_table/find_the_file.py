# Which files a lookup of one order must open: the data files whose order_id range
# holds it, and the delete files that name those.
import json

snapshots = json.load(open("fixtures/changes/_snapshots.json"))["snapshots"]
snapshot = next(s for s in snapshots if s["id"] == "after-a-day")
key = 300

data = [f["path"] for f in snapshot["data_files"]
        if f["order_id"][0] <= key <= f["order_id"][1]]
for path in data:
    print("order", key, "can only be in", path)
deletes = [d["path"] for d in snapshot["delete_files"] if d["data_file"] in data]
print("and these delete files may remove it:", ", ".join(deletes))
