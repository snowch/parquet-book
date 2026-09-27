//! The same schema from the `parquet` crate, which rebuilds the tree. Without Arrow, it hands you
//! the statistics as bytes, and reading them through the logical type is yours to do.

use parquet::file::metadata::ParquetMetaDataReader;
use parquet::schema::printer::print_schema;

fn main() {
    let file =
        std::fs::File::open("fixtures/types.parquet").expect("run this from the repository's root");
    let md = ParquetMetaDataReader::new()
        .parse_and_finish(&file)
        .expect("a Parquet file");
    print_schema(&mut std::io::stdout(), md.file_metadata().schema());

    let leaves = md.file_metadata().schema_descr().columns();
    for (c, chunk) in leaves.iter().zip(md.row_group(0).columns()) {
        let levels = format!("max levels {} {}", c.max_def_level(), c.max_rep_level());
        let min = chunk
            .statistics()
            .and_then(|s| s.min_bytes_opt())
            .unwrap_or_default();
        let path = c.path().string();
        println!("{path}: {levels}, {}, min {min:02x?}", c.physical_type());
    }
}
