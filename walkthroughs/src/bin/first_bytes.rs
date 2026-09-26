//! Read the whole file, and look at its first four bytes.

fn main() {
    let data = std::fs::read("fixtures/tiny.parquet").expect("run this from the repository's root");

    println!("{} bytes in the file", data.len());
    println!("the first four: {:?}", String::from_utf8_lossy(&data[..4]));
}
