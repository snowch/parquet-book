//! The same facts from the `parquet` crate: a column chunk's pages, one at a time, and a
//! damaged page refused. The crate checks checksums when built with its `crc` feature.

use bytes::Bytes;
use parquet::column::page::Page;
use parquet::file::reader::{FileReader, SerializedFileReader};

fn open(data: &[u8]) -> SerializedFileReader<Bytes> {
    SerializedFileReader::new(Bytes::copy_from_slice(data)).expect("a Parquet file")
}

fn print_pages(reader: &SerializedFileReader<Bytes>) {
    let row_group = reader.get_row_group(0).expect("a row group");
    for page in row_group.get_column_page_reader(1).expect("pages") {
        match page {
            Ok(Page::DataPageV2 {
                num_rows: rows,
                num_nulls: nulls,
                def_levels_byte_len: def,
                ..
            }) => {
                println!("DATA_PAGE_V2: {rows} rows, {nulls} nulls, {def} level bytes")
            }
            Ok(page) => println!("{}: {} values", page.page_type(), page.num_values()),
            Err(e) => println!("refused: {e}"),
        }
    }
}

fn main() {
    let path = "fixtures/pages-v2.parquet";
    let mut data = std::fs::read(path).expect("run this from the repository's root");
    let reader = open(&data);
    let country = reader.metadata().row_group(0).column(1);
    let (name, (start, size)) = (country.column_path().string(), country.byte_range());
    let end = start + size;
    println!("{name}: bytes {start} to {end}");
    print_pages(&reader);
    data[end as usize - 2] ^= 1; // the bit damage_a_page flipped
    println!("one bit flipped:");
    print_pages(&open(&data));
}
