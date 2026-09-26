# Damage the footer length, and see where the arithmetic now puts the footer.
data = bytearray(open("fixtures/tiny.parquet", "rb").read())
data[-7] = 0xFF  # the second of the four length bytes

footer_length = int.from_bytes(data[-8:-4], "little")
print("the footer length now reads", footer_length)
print("so the footer would start at byte", len(data) - 8 - footer_length)
