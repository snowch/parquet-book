# The last four bytes, and whether they match the first four.
data = open("fixtures/tiny.parquet", "rb").read()

print("the last four:", data[-4:])
print("the same as the first four:", data[-4:] == data[:4])
