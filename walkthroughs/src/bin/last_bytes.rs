//! The last four bytes, and whether they match the first four.

fn main() {
    let data = std::fs::read("fixtures/tiny.parquet").expect("run this from the repository's root");
    let last = &data[data.len() - 4..];

    println!("the last four: {:?}", String::from_utf8_lossy(last));
    println!("the same as the first four: {}", last == &data[..4]);
}
