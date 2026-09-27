# The same questions to pyarrow: which row groups a condition keeps, and what else it sees.
import pyarrow.dataset as ds, pyarrow.parquet as pq

for path, column, value in [("fixtures/pruning-sorted.parquet", "order_id", 431),
                            ("fixtures/pruning-shuffled.parquet", "customer_id", 424242)]:
    fragment = next(ds.dataset(path).get_fragments())  # one file, one fragment
    kept = fragment.subset(ds.field(column) == value).row_groups  # by statistics alone
    print(f"{column} = {value}: kept row groups {[rg.id for rg in kept]}")

chunk = pq.read_metadata(path).row_group(0).column(1)  # customer_id, in the shuffled file
print(f"a column index: {chunk.has_column_index}; an offset index: {chunk.has_offset_index}")
