# The book's reader answers SQL: what each stage of the pipeline did, then the answer.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import engine

data = open("fixtures/writing-baseline.parquet", "rb").read()
# Try SELECT count(*) FROM orders, or any other query in the chapter's table.
sql = """SELECT country, count(*) FROM orders WHERE order_id < 300
         GROUP BY country ORDER BY country"""
answer = engine.run(data, sql)

for stage in answer.stages:
    print(f"{stage.name}: {stage.rows_in} rows in, {stage.rows_out} out")
    for part in stage.detail.split("; "):
        print(f"  {part}")
print(*answer.columns)
for row in answer.rows:
    print(*row)
