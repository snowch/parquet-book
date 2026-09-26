//! Two columns from a CSV file, read the way programs read CSV: a row at a time.

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader, Read};

/// A file that counts the bytes read from it.
struct Counted {
    file: File,
    bytes_read: u64,
}

impl Read for Counted {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let n = self.file.read(buf)?;
        self.bytes_read += n as u64;
        Ok(n)
    }
}

fn main() {
    let path = "fixtures/formats/orders.csv";
    let file = File::open(path).expect("run this from the repository's root");
    let size = file.metadata().unwrap().len();
    let mut lines = BufReader::new(Counted {
        file,
        bytes_read: 0,
    });

    let mut line = String::new();
    lines.read_line(&mut line).unwrap();
    let header: Vec<String> = line.trim_end().split(',').map(unquote).collect();
    let at = |name: &str| header.iter().position(|h| h == name).unwrap();
    let (country, amount) = (at("country"), at("amount_cents"));

    let mut totals: HashMap<String, i64> = HashMap::new();
    loop {
        line.clear();
        if lines.read_line(&mut line).unwrap() == 0 {
            break;
        }
        // The query wants country and amount_cents; every other field is read and dropped.
        let fields: Vec<String> = line.trim_end().split(',').map(unquote).collect();
        *totals.entry(fields[country].clone()).or_default() +=
            fields[amount].parse::<i64>().unwrap();
    }

    println!("read {} of {size} bytes", lines.get_ref().bytes_read);
    println!("amount_cents in the UK: {}", totals["UK"]);
}

/// A field without the quotes a CSV writer puts around text.
fn unquote(field: &str) -> String {
    field.trim_matches('"').to_string()
}
