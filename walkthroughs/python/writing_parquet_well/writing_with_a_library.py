# pyarrow writes the orders again, one setting changed at a time, and reads its footer back.
import io
import pyarrow.parquet as pq

table = pq.read_table("fixtures/writing-baseline.parquet")
# The fixtures' settings, in fixtures/generate.py, with no Arrow schema stored in the footer.
# A page ends at every size check, so a check every 40 rows makes pages of 40 rows: what
# max_rows_per_page=40 says in pyarrow 25, which the page's pyarrow predates.
baseline = dict(compression="snappy", use_dictionary=True, row_group_size=200,
                write_batch_size=40, data_page_size=1,
                write_page_index=True, store_schema=False)
changes = {
    "the baseline": {},
    "row groups of 40": {"row_group_size": 40},
    "no dictionary": {"use_dictionary": False},
    "no page index": {"write_page_index": False},
    "the sort declared": {"sorting_columns": [pq.SortingColumn(0)]},  # sorted by order_id
}
for change, options in changes.items():
    sink = io.BytesIO()
    pq.write_table(table, sink, **{**baseline, **options})
    md = pq.read_metadata(io.BytesIO(sink.getvalue()))
    size, footer, groups = len(sink.getvalue()), md.serialized_size, md.num_row_groups
    print(f"{change}: {size} bytes, footer {footer}, {groups} row groups")
    group = md.row_group(0)
    c = group.column(0)  # order_id in the first row group
    print(f"  dictionary {c.has_dictionary_page}, column index {c.has_column_index}, "
          f"sorted by {group.sorting_columns}")
