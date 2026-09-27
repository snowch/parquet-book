//! The same facts from the `parquet` crate: each column chunk's encodings, and the pages of a
//! dictionary-encoded column, the dictionary page first.

use parquet::file::reader::{FileReader, SerializedFileReader};

fn open(path: &str) -> SerializedFileReader<std::fs::File> {
    let file = std::fs::File::open(path).expect("run this from the repository's root");
    SerializedFileReader::new(file).expect("a Parquet file")
}

fn main() {
    let reader = open("fixtures/encodings.parquet");
    for chunk in reader.metadata().row_group(0).columns() {
        let encodings: Vec<_> = chunk.encodings().collect();
        println!("{} {encodings:?}", chunk.column_path().string());
    }
    let reader = open("fixtures/dictionary.parquet");
    let row_group = reader.get_row_group(0).expect("a row group");
    let country = row_group.metadata().column(1);
    let offset = country.dictionary_page_offset();
    println!(
        "{}: dictionary page at {offset:?}",
        country.column_path().string()
    );
    for page in row_group
        .get_column_page_reader(1)
        .expect("country's pages")
    {
        let page = page.expect("a page");
        println!(
            "{} {} {}",
            page.page_type(),
            page.encoding(),
            page.num_values()
        );
    }
}
