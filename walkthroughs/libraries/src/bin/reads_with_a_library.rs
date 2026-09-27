//! The `parquet` crate reads the same file's tail, and asks for more until it has enough.

use bytes::Bytes;
use parquet::errors::ParquetError;
use parquet::file::metadata::{PageIndexPolicy, ParquetMetaDataReader};

fn main() {
    let data = std::fs::read("fixtures/pruning-sorted.parquet")
        .expect("run this from the repository's root");
    let size = data.len() as u64;
    let policy = PageIndexPolicy::Required; // the footer, and the page index before it
    let mut reader = ParquetMetaDataReader::new().with_page_index_policy(policy);

    let mut tail = 8; // try 8192, or 65536
    loop {
        println!("read the last {tail} bytes");
        let bytes = Bytes::copy_from_slice(&data[data.len().saturating_sub(tail)..]);
        match reader.try_parse_sized(&bytes, size) {
            Ok(()) => break,
            Err(ParquetError::NeedMoreData(needed)) => {
                println!("  NeedMoreData({needed})");
                tail = needed;
            }
            Err(e) => panic!("{e}"),
        }
    }
    let md = reader.finish().expect("the footer and the page index");
    let (groups, index) = (md.num_row_groups(), md.page_index().is_some());
    println!("{groups} row groups; the page index read: {index}");
}
