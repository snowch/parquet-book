//! One table, two layouts: the same values in a different order, and the ones a query needs.

fn main() {
    let text = std::fs::read_to_string("fixtures/formats/eight-orders.csv")
        .expect("run this from the repository's root");
    let mut lines = text.lines().map(|l| {
        l.split(',')
            .map(|v| v.trim_matches('"'))
            .collect::<Vec<_>>()
    });
    let header = lines.next().unwrap();
    let rows: Vec<Vec<&str>> = lines.collect();
    let wanted = ["country", "amount_cents"]; // try ["order_id"], or every column

    // Each value with its column's name: by rows, an order's values together; by columns, a
    // column's values together.
    let by_rows: Vec<(&str, &str)> = rows
        .iter()
        .flat_map(|row| header.iter().copied().zip(row.iter().copied()))
        .collect();
    let by_columns: Vec<(&str, &str)> = header
        .iter()
        .enumerate()
        .flat_map(|(c, &name)| rows.iter().map(move |row| (name, row[c])))
        .collect();

    for (label, layout) in [("by rows", by_rows), ("by columns", by_columns)] {
        let picture: String = layout
            .iter()
            .map(|(name, _)| if wanted.contains(name) { '#' } else { '.' })
            .collect();
        let runs = picture.split('.').filter(|p| !p.is_empty()).count();
        println!(
            "{label:>10}: {picture}  {runs} run{}",
            if runs == 1 { "" } else { "s" }
        );
    }
}
