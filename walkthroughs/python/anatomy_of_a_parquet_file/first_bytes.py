# Read the whole file, and look at its first four bytes.
data = open("fixtures/tiny.parquet", "rb").read()

print(len(data), "bytes in the file")
print("the first four:", data[:4])
