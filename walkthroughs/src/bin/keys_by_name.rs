//! Key metadata names a key without holding it: pyarrow writes it as JSON.

/// A string field of flat JSON: what follows `"name":"`, up to the next quote.
fn field<'a>(json: &'a str, name: &str) -> &'a str {
    let start = json.find(&format!("\"{name}\":\"")).expect("the field") + name.len() + 4;
    &json[start..start + json[start..].find('"').unwrap()]
}

fn main() {
    for name in ["plaintext-footer", "encrypted-footer"] {
        let path = format!("fixtures/{name}.parquet");
        let data = std::fs::read(path).expect("run this from the repository's root");
        let text = String::from_utf8_lossy(&data); // the ciphertext comes out as nonsense
        let found: Vec<&str> = text
            .match_indices("{\"keyMaterialType\"")
            .map(|(at, _)| &text[at..at + text[at..].find('}').unwrap() + 1])
            .collect();
        println!("{name}.parquet, keys named in the clear: {}", found.len());
        for json in found {
            // Try printing all of it.
            let footer = json.contains("\"isFooterKey\":true");
            let kind = if footer { "footer" } else { "column" };
            let master = field(json, "masterKeyID");
            let wrapped = field(json, "wrappedDEK");
            println!("  {kind} key {master:?}, wrapped data key {wrapped}");
        }
    }
}
