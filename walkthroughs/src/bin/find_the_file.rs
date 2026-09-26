//! Which files a lookup of one order must open: the data files whose order_id range holds it,
//! and the delete files that name those.

use parquet_lab::json::Json;

fn main() {
    let text = std::fs::read_to_string("fixtures/changes/_snapshots.json")
        .expect("run this from the repository's root");
    let all = Json::parse(&text).expect("JSON");
    let snapshot = all
        .get("snapshots")
        .and_then(Json::as_array)
        .and_then(|s| {
            s.iter()
                .find(|s| s.get("id").and_then(Json::as_str) == Some("after-a-day"))
        })
        .expect("a snapshot called after-a-day");
    let list = |k: &str| snapshot.get(k).and_then(Json::as_array).unwrap();
    let text = |j: &Json, k: &str| j.get(k).and_then(Json::as_str).unwrap().to_string();
    let key = 300;

    let data: Vec<String> = list("data_files")
        .iter()
        .filter(|f| {
            let range = f.get("order_id").and_then(Json::as_array).unwrap();
            range[0].as_i64().unwrap() <= key && key <= range[1].as_i64().unwrap()
        })
        .map(|f| text(f, "path"))
        .collect();
    for path in &data {
        println!("order {key} can only be in {path}");
    }
    let deletes: Vec<String> = list("delete_files")
        .iter()
        .filter(|d| data.contains(&text(d, "data_file")))
        .map(|d| text(d, "path"))
        .collect();
    println!(
        "and these delete files may remove it: {}",
        deletes.join(", ")
    );
}
