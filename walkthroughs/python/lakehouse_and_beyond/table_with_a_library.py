# The same table to pyarrow: a dataset of the directory, with its partition read from the paths.
import pyarrow.dataset as ds

dataset = ds.dataset("fixtures/table", format="parquet", partitioning="hive")
print(dataset.schema.field("country"))  # from the paths: no file holds it
uk = ds.field("country") == "UK"
condition = uk & (ds.field("order_id") < 200)  # try 300

for fragment in dataset.get_fragments(filter=uk):  # the paths rule out the others
    s = fragment.row_groups[0].statistics["order_id"]  # from the file's footer
    kept = [rg.id for rg in fragment.subset(condition, schema=dataset.schema).row_groups]
    print(f"{fragment.path}: order_id {s['min']} to {s['max']}, row groups kept {kept}")
print("rows:", dataset.count_rows(filter=condition))
