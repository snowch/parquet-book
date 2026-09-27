# One encrypted module, read from its length prefix: the first of email's column chunk.
import sys
sys.path.insert(0, "python")  # the book's reader, from the repository's python/ directory
from parquet_lab import report

data = open("fixtures/plaintext-footer.parquet", "rb").read()
md = report.open_bytes(data)  # a plaintext footer: found and decoded as in ch02
chunk = md.row_groups[0].columns[2]  # email; try 3, amount_cents
path, start, size = chunk.dotted_path(), chunk.data_page_offset, chunk.total_compressed_size
print(f"{path}: bytes {start} to {start + size}, statistics {chunk.statistics}")
at = start  # try the byte where the next module starts
n = int.from_bytes(data[at:at + 4], "little")  # the length: the bytes that follow it
print(f"a module at byte {at}: length {n}")
print("  nonce:", data[at + 4:at + 16].hex(" "))
print(f"  ciphertext: {n - 12 - 16} bytes")
print("  tag:", data[at + 4 + n - 16:at + 4 + n].hex(" "))
print(f"the next module starts at byte {at + 4 + n}")
