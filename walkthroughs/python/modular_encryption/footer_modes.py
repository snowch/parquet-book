# The first and last four bytes of two encrypted files: the magic names the footer mode.
for name in ["plaintext-footer", "encrypted-footer"]:  # try adding "tiny"
    data = open(f"fixtures/{name}.parquet", "rb").read()
    print(f"{name}.parquet starts {data[:4]} and ends {data[-4:]}")
