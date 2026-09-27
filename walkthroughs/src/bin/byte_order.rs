//! Sort four cities by their UTF-8 bytes, then by the same bytes read as signed numbers.

fn main() {
    let mut cities = ["Zürich", "Łódź", "Aarhus", "Århus"];
    for city in cities {
        println!("{city} {:02x?}", city.as_bytes());
    }
    cities.sort(); // a str sorts by its bytes, each unsigned
    println!("unsigned bytes: {cities:?}");
    // Each byte as Java's byte reads it: 0x80 and above are negative.
    cities.sort_by_key(|city| city.bytes().map(|b| b as i8).collect::<Vec<_>>());
    println!("signed bytes:   {cities:?}");
}
