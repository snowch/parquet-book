# The table's files, found by walking its directories: each one's partition and size.
from pathlib import Path

table = Path("fixtures/table")
for path in sorted(table.rglob("*.parquet")):
    key = path.relative_to(table).as_posix()  # country=UK/part-0.parquet
    directory = key.split("/")[0]  # a name, an equals sign and a value
    name, _, value = directory.partition("=")
    print(f"{key}: {name} is {value}, {path.stat().st_size} bytes")
