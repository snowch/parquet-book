# The same query to pyarrow: the row groups its scan keeps, and the answer.
import pyarrow.dataset as ds

dataset = ds.dataset("fixtures/writing-baseline.parquet")
condition = ds.field("order_id") < 300  # try 450, then 1
fragment = next(dataset.get_fragments())  # one file, one fragment
print("row groups kept:", [rg.id for rg in fragment.subset(condition).row_groups])

table = dataset.to_table(columns=["country"], filter=condition)
answer = table.group_by("country").aggregate([([], "count_all")]).sort_by("country")
for country, n in zip(answer["country"].to_pylist(), answer["count_all"].to_pylist()):
    print(country, n)
