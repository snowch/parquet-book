# The same two columns from the Parquet file of the same table, read with pyarrow.
import io, os
import pyarrow.compute as pc, pyarrow.parquet as pq

class Counted(io.FileIO):
    """A file that counts the bytes read from it, however the library asks for them."""
    bytes_read = 0
    def readinto(self, buffer):
        n = super().readinto(buffer)
        self.bytes_read += n
        return n
    def read(self, size=-1):
        data = super().read(size)
        self.bytes_read += len(data)
        return data

path = "fixtures/formats/orders.parquet"
file = Counted(path)
table = pq.read_table(file, columns=["country", "amount_cents"])
uk = table.filter(pc.equal(table["country"], "UK"))

print(f"read {file.bytes_read} of {os.path.getsize(path)} bytes")
print("amount_cents in the UK:", pc.sum(uk["amount_cents"]).as_py())
