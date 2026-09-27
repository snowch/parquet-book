# One table, two layouts: the same values in a different order, and the ones a query needs.
import csv

orders = list(csv.reader(open("fixtures/formats/eight-orders.csv")))
header, rows = orders[0], orders[1:]
wanted = {"country", "amount_cents"}  # try {"order_id"}, or every column

by_rows = [(name, v) for row in rows for name, v in zip(header, row)]
by_columns = [(name, row[c]) for c, name in enumerate(header) for row in rows]

for label, layout in (("by rows", by_rows), ("by columns", by_columns)):
    picture = "".join("#" if name in wanted else "." for name, _ in layout)
    runs = len([p for p in picture.split(".") if p])
    print(f"{label}, {runs} run{'s' * (runs != 1)}:")
    print(picture)
