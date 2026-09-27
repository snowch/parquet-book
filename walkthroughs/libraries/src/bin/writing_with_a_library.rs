//! The `parquet` crate reads each file's footer and finds the writer's choices in it.

use parquet::file::metadata::ParquetMetaDataReader;

fn main() {
    let files = "baseline one-group small-groups by-country shuffled plain no-index";
    for name in files.split_whitespace() {
        let path = format!("fixtures/writing-{name}.parquet");
        let file = std::fs::File::open(path).expect("run this from the repository's root");
        let md = ParquetMetaDataReader::new()
            .parse_and_finish(&file)
            .expect("a Parquet file");
        let group = md.row_group(0);
        let chunk = group.column(0); // order_id in the first row group
        let (groups, codec) = (md.num_row_groups(), chunk.compression());
        println!("writing-{name}: {groups} row groups, {codec}");
        let dictionary = chunk.dictionary_page_offset().is_some();
        let index = chunk.column_index_offset().is_some();
        let sorted = group.sorting_columns();
        println!("  dictionary {dictionary}, column index {index}, sorted by {sorted:?}");
    }
}
