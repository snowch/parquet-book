//! The table's log, read by hand: one action a line, and the statistics each add records.

use parquet_lab::json::Json;

fn main() {
    let log = std::fs::read_to_string("fixtures/table/_delta_log/00000000000000000000.json")
        .expect("run this from the repository's root");
    for (n, line) in (1..).zip(log.lines()) {
        let action = Json::parse(line).expect("one JSON object a line");
        let Json::Obj(fields) = &action else { continue };
        let kind = &fields[0].0; // protocol, metaData, add or remove
        if kind != "add" {
            println!("line {n}: {kind}");
            continue;
        }
        let add = &fields[0].1;
        // The statistics are JSON inside a JSON string: parse them a second time.
        let text = add.get("stats").and_then(Json::as_str).expect("statistics");
        let stats = Json::parse(text).expect("JSON");
        let order_id = |k: &str| stats.get(k).and_then(|m| m.get("order_id")).unwrap();
        let (low, high) = (
            order_id("minValues").to_json(),
            order_id("maxValues").to_json(),
        );
        let path = add.get("path").and_then(Json::as_str).unwrap();
        let rows = stats.get("numRecords").unwrap().to_json();
        println!("line {n}: add {path}, {rows} rows, order_id {low} to {high}");
    }
}
