//! The same facts from the `parquet` crate: each file's codec for country, and the chunk's two
//! sizes. `compression()` turns the codec into a writer's setting, with a level of its own.

use parquet::file::reader::{FileReader, SerializedFileReader};

fn main() {
    for name in ["snappy", "lz4", "gzip"] {
        let file = std::fs::File::open(format!("fixtures/codec-{name}.parquet"))
            .expect("run this from the repository's root");
        let reader = SerializedFileReader::new(file).expect("a Parquet file");
        let chunk = reader.metadata().row_group(0).column(1); // country
        let (before, after) = (chunk.uncompressed_size(), chunk.compressed_size());
        let (path, codec) = (chunk.column_path().string(), chunk.compression_codec());
        println!("{path}: {codec:?}, {after} of {before} bytes");
        println!("  as a writer's setting: {}", chunk.compression());
    }
}
