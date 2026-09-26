# Where the footer starts: it ends where the last eight bytes begin, and is as long as they say.
data = open("fixtures/tiny.parquet", "rb").read()
footer_length = int.from_bytes(data[-8:-4], "little")

footer_start = len(data) - 8 - footer_length
footer = data[footer_start : len(data) - 8]
print("the footer starts at byte", footer_start, "and is", len(footer), "bytes long")
print("its first eight bytes:", footer[:8].hex(" "))
