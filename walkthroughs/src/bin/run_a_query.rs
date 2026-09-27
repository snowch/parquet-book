//! The book's reader answers SQL: what each stage of the pipeline did, then the answer.

use parquet_lab::engine::{run, Value};

fn main() {
    let path = "fixtures/writing-baseline.parquet";
    let data = std::fs::read(path).expect("run this from the repository's root");
    // Try AND status = 'refunded' after the condition, avg(amount_cents), or LIMIT 3.
    let sql = "SELECT country, count(*) FROM orders WHERE order_id < 300 \
               GROUP BY country ORDER BY country";
    let answer = run(&data, sql).expect("a query the engine understands");

    for stage in &answer.stages {
        let (name, rows_in, rows_out) = (&stage.name, stage.rows_in, stage.rows_out);
        println!("{name}: {rows_in} rows in, {rows_out} out");
        for part in stage.detail.split("; ") {
            println!("  {part}");
        }
    }
    println!("{}", answer.columns.join(" "));
    for row in &answer.rows {
        let cells: Vec<String> = (row.iter())
            .map(|v| match v {
                Value::Str(s) => s.clone(),
                v => v.to_json().to_json(), // a number, or null
            })
            .collect();
        println!("{}", cells.join(" "));
    }
}
