//! The first and last four bytes of two encrypted files: the magic names the footer mode.

fn main() {
    // Try adding "tiny".
    for name in ["plaintext-footer", "encrypted-footer"] {
        let path = format!("fixtures/{name}.parquet");
        let data = std::fs::read(path).expect("run this from the repository's root");
        let text = |b: &[u8]| String::from_utf8_lossy(b).into_owned();
        let (first, last) = (text(&data[..4]), text(&data[data.len() - 4..]));
        println!("{name}.parquet starts {first:?} and ends {last:?}");
    }
}
