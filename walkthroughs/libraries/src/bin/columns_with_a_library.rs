//! The same two columns from the Parquet file of the same table, read with the `parquet` crate.

use std::fs::File;
use std::io::Read;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use bytes::Bytes;
use parquet::file::reader::{ChunkReader, FileReader, Length, SerializedFileReader};
use parquet::record::RowAccessor;
use parquet::schema::parser::parse_message_type;

/// A file that counts the bytes read from it, however the crate asks for them.
struct Counted {
    file: File,
    bytes_read: Arc<AtomicU64>,
}

impl Length for Counted {
    fn len(&self) -> u64 {
        self.file.len()
    }
}

impl ChunkReader for Counted {
    type T = CountedRead<<File as ChunkReader>::T>;

    fn get_read(&self, start: u64) -> parquet::errors::Result<Self::T> {
        Ok(CountedRead(
            self.file.get_read(start)?,
            self.bytes_read.clone(),
        ))
    }

    fn get_bytes(&self, start: u64, length: usize) -> parquet::errors::Result<Bytes> {
        self.bytes_read.fetch_add(length as u64, Ordering::Relaxed);
        self.file.get_bytes(start, length)
    }
}

struct CountedRead<R>(R, Arc<AtomicU64>);

impl<R: Read> Read for CountedRead<R> {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let n = self.0.read(buf)?;
        self.1.fetch_add(n as u64, Ordering::Relaxed);
        Ok(n)
    }
}

fn main() {
    let path = "fixtures/formats/orders.parquet";
    let file = File::open(path).expect("run this from the repository's root");
    let size = file.metadata().unwrap().len();
    let bytes_read = Arc::new(AtomicU64::new(0));
    let reader = SerializedFileReader::new(Counted {
        file,
        bytes_read: bytes_read.clone(),
    })
    .expect("a Parquet file");

    // Only these two columns, named as the file names them (pyarrow calls the root "schema"):
    // the crate reads their chunks and no others.
    let wanted = parse_message_type(
        "message schema { required binary country (STRING); required int64 amount_cents; }",
    )
    .unwrap();
    let mut uk = 0;
    for row in reader.get_row_iter(Some(wanted)).unwrap() {
        let row = row.unwrap();
        if row.get_string(0).unwrap() == "UK" {
            uk += row.get_long(1).unwrap();
        }
    }

    println!(
        "read {} of {size} bytes",
        bytes_read.load(Ordering::Relaxed)
    );
    println!("amount_cents in the UK: {uk}");
}
