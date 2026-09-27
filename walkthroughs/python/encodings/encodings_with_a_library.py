# The same facts from pyarrow: every column chunk's encodings, and a dictionary as read.
import pyarrow.parquet as pq

md = pq.read_metadata("fixtures/encodings.parquet").row_group(0)
for i in range(md.num_columns):
    print(md.column(i).path_in_schema, md.column(i).encodings)
path = "fixtures/dictionary.parquet"
table = pq.read_table(path, columns=["country"], read_dictionary=["country"])
country = table.column("country").chunk(0)  # an Arrow DictionaryArray
print("dictionary:", country.dictionary.to_pylist())
print("indices:", country.indices.to_pylist())
