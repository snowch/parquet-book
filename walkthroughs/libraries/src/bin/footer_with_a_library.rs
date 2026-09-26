//! The same facts from the `parquet` crate, which reads the trailer and parses the footer for you.

use parquet::file::metadata::{FooterTail, ParquetMetaDataReader};

fn main() {
    let file =
        std::fs::File::open("fixtures/tiny.parquet").expect("run this from the repository's root");
    let metadata = ParquetMetaDataReader::new()
        .parse_and_finish(&file)
        .expect("a Parquet file");

    // The crate checks the trailer as it parses; it also decodes one on its own, from eight bytes.
    let data = std::fs::read("fixtures/tiny.parquet").unwrap();
    let tail = FooterTail::try_from(&data[data.len() - 8..]).expect("a Parquet trailer");
    println!("footer length: {}", tail.metadata_length());
    println!(
        "rows: {} in {} row group",
        metadata.file_metadata().num_rows(),
        metadata.num_row_groups()
    );
    for chunk in metadata.row_group(0).columns() {
        // A chunk starts with its dictionary page when it has one, and its first data page otherwise.
        let (start, length) = chunk.byte_range();
        println!(
            "column chunk {}: bytes {start} to {}",
            chunk.column_path().string(),
            start + length
        );
    }
}
