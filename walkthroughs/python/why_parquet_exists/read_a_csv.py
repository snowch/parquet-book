# Two columns from a CSV file, read the way programs read CSV: a row at a time.
import csv
import io
import os


class Counted(io.FileIO):
    """A file that counts the bytes read from it."""

    bytes_read = 0

    def readinto(self, buffer):
        n = super().readinto(buffer)
        self.bytes_read += n
        return n


path = "fixtures/formats/orders.csv"
file = Counted(path)
totals = {}
for row in csv.DictReader(io.TextIOWrapper(io.BufferedReader(file), newline="")):
    # The query wants country and amount_cents; every other field is read and dropped.
    totals[row["country"]] = totals.get(row["country"], 0) + int(row["amount_cents"])

print(f"read {file.bytes_read} of {os.path.getsize(path)} bytes")
print("amount_cents in the UK:", totals["UK"])
