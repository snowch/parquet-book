# The same bytes, read two ways: as the physical type stores them, then as the logical type says.
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import metadata

data = open("fixtures/types.parquet", "rb").read()
length = int.from_bytes(data[-8:-4], "little")
base = len(data) - 8 - length
md = metadata.decode_file_metadata(data[base:-8], base)
least = {c.dotted_path(): c.statistics.min_value for c in md.row_groups[0].columns}

raw = least["order_date"]  # INT32, DATE: days since 1970-01-01
days = int.from_bytes(raw, "little", signed=True)
print("order_date", raw.hex(" "), "->", days, "->", date(1970, 1, 1) + timedelta(days=days))
raw = least["paid_at"]  # INT64, TIMESTAMP(MICROS, UTC): microseconds since 1970-01-01, UTC
micros = int.from_bytes(raw, "little", signed=True)
epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
print("paid_at", raw.hex(" "), "->", micros, "->", epoch + timedelta(microseconds=micros))
raw = least["amount"]  # FIXED_LEN_BYTE_ARRAY(4), DECIMAL(9, 2): an integer of hundredths
cents = int.from_bytes(raw, "big", signed=True)  # most significant byte first
print("amount", raw.hex(" "), "->", cents, "->", Decimal(cents).scaleb(-2))
