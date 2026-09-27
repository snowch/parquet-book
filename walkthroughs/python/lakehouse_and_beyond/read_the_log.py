# The table's log, read by hand: one action a line, and the statistics each add records.
import json

log = open("fixtures/table/_delta_log/00000000000000000000.json")
for n, line in enumerate(log, 1):
    action = json.loads(line)
    kind = next(iter(action))  # protocol, metaData, add or remove
    if kind != "add":
        print(f"line {n}: {kind}")
        continue
    add = action["add"]
    stats = json.loads(add["stats"])  # JSON inside a JSON string: parse it a second time
    low, high = stats["minValues"]["order_id"], stats["maxValues"]["order_id"]
    rows = stats["numRecords"]
    print(f"line {n}: add {add['path']}, {rows} rows, order_id {low} to {high}")
