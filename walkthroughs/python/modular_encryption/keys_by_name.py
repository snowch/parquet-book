# Key metadata names a key without holding it: pyarrow writes it as JSON.
import json, re
for name in ["plaintext-footer", "encrypted-footer"]:
    data = open(f"fixtures/{name}.parquet", "rb").read()
    found = re.findall(rb'\{"keyMaterialType".*?\}', data)
    print(f"{name}.parquet, keys named in the clear: {len(found)}")
    for text in found:
        key = json.loads(text)  # try printing all of it
        kind = "footer" if key["isFooterKey"] else "column"
        master, wrapped = key["masterKeyID"], key["wrappedDEK"]
        print(f"  {kind} key {master!r}, wrapped data key {wrapped}")
