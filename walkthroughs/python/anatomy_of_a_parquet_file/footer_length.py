# The four bytes before the closing magic, read as a little-endian number.
data = open("fixtures/tiny.parquet", "rb").read()

length_bytes = data[-8:-4]
print("the four before them:", length_bytes.hex(" "))
print("read little-endian:", int.from_bytes(length_bytes, "little"))
