//! Static, accessible companions to the walkthroughs. Measurements come from the reader;
//! conceptual drawings say that they are schematic. The normal figures check covers both
//! the SVG and its caption, so these cannot silently drift away from the fixtures.

use super::*;
use std::fmt::Write;

const BLUE: &str = "#dceaf5";
const GREEN: &str = "#dceee6";
const GOLD: &str = "#f8e7c9";
const GREY: &str = "#edf0f3";
const COLOURS: [&str; 4] = [BLUE, GREEN, GOLD, "#e8e0f2"];

fn xml(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

struct Drawing {
    body: String,
    height: usize,
    title: String,
    description: String,
}

impl Drawing {
    fn new(height: usize, title: &str, description: &str) -> Self {
        let mut s = Self {
            body: String::new(),
            height,
            title: title.into(),
            description: description.into(),
        };
        s.text(24, 36, title, "heading");
        s
    }

    fn text(&mut self, x: usize, y: usize, label: &str, class: &str) {
        writeln!(
            self.body,
            "<text x=\"{x}\" y=\"{y}\" class=\"{class}\">{}</text>",
            xml(label)
        )
        .unwrap();
    }

    fn rect(&mut self, x: usize, y: usize, w: usize, h: usize, colour: &str) {
        writeln!(self.body, "<rect x=\"{x}\" y=\"{y}\" width=\"{w}\" height=\"{h}\" rx=\"5\" fill=\"{colour}\" stroke=\"#71818c\"/>").unwrap();
    }

    fn card(&mut self, x: usize, y: usize, w: usize, lines: &[&str], colour: &str) {
        self.rect(x, y, w, lines.len() * 24 + 20, colour);
        for (i, line) in lines.iter().enumerate() {
            self.text(
                x + 12,
                y + 27 + i * 24,
                line,
                if i == 0 { "strong" } else { "small" },
            );
        }
    }

    fn arrow(&mut self, x: usize, y: usize, end_x: usize, end_y: usize) {
        writeln!(self.body, "<path d=\"M{x} {y} L{end_x} {end_y}\" fill=\"none\" stroke=\"#435764\" stroke-width=\"2\" marker-end=\"url(#arrow)\"/>").unwrap();
    }

    fn finish(self) -> String {
        format!(
            r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 {}" role="img" aria-labelledby="title description">
<title id="title">{}</title><desc id="description">{}</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="#435764"/></marker></defs>
<style>text{{font-family:system-ui,sans-serif;font-size:18px;fill:#233641}}.heading{{font-size:22px;font-weight:700}}.strong{{font-weight:600}}.small{{font-size:16px}}.mono{{font-family:ui-monospace,monospace;font-size:17px}}</style>
<rect width="680" height="{}" rx="8" fill="#ffffff"/>
{}</svg>
"##,
            self.height,
            xml(&self.title),
            xml(&self.description),
            self.height,
            self.body
        )
    }
}

struct Visual {
    name: &'static str,
    drawing: Drawing,
    caption: String,
    source: String,
}

pub(super) fn render(root: &Path) -> Result<Vec<(String, String)>, String> {
    let visuals = vec![
        layouts(root)?,
        footer(root)?,
        hierarchy(root)?,
        requests(root)?,
        missing(root)?,
        tags(root)?,
        discounts(root)?,
        split(root)?,
        page_layouts(),
        pruning(root)?,
        writing(root)?,
        engine(root)?,
        changes(),
        iceberg(),
    ];
    let mut out = Vec::new();
    for v in visuals {
        let markdown = format!(
            "{HEADER}```{{figure}} _generated/{}.svg\n:alt: {}\n\n{}\n```\n\n*{}*\n",
            v.name, v.drawing.description, v.caption, v.source
        );
        out.push((format!("{}.md", v.name), markdown));
        out.push((format!("{}.svg", v.name), v.drawing.finish()));
    }
    Ok(out)
}

fn source(file: &str) -> String {
    format!("Computed by the reader from `fixtures/{file}`. Diagram spacing is schematic.")
}

fn layouts(root: &Path) -> Result<Visual, String> {
    let bytes = fixture(root, "formats/eight-orders.csv")?;
    let csv = std::str::from_utf8(&bytes).map_err(|e| e.to_string())?;
    let mut lines = csv.lines();
    // This fixture has no embedded commas, as in the chapter's Rust walkthrough.
    let names: Vec<_> = lines
        .next()
        .ok_or("empty CSV")?
        .split(',')
        .map(|name| name.trim_matches('"'))
        .collect();
    let rows = lines.count();
    let selected: Vec<_> = names
        .iter()
        .map(|n| matches!(*n, "country" | "amount_cents"))
        .collect();
    if selected.iter().filter(|&&v| v).count() != 2 {
        return Err("layout fixture must contain country and amount_cents".into());
    }
    let mut d = Drawing::new(340, "The same values, stored in a different order", "The query needs country and amount_cents. In row order its values are scattered; in column order they form neighbouring runs. Filled cells marked with a dot are selected.");
    for (panel, label) in [
        "Row order: every order's fields together",
        "Column order: every column's values together",
    ]
    .iter()
    .enumerate()
    {
        let y = 80 + panel * 110;
        d.text(24, y, label, "strong");
        let count = rows * names.len();
        for i in 0..count {
            let c = if panel == 0 {
                i % names.len()
            } else {
                i / rows
            };
            let x = 24 + i * 630 / count;
            let w = 630 / count - 2;
            d.rect(x, y + 15, w, 32, if selected[c] { BLUE } else { GREY });
            if selected[c] {
                d.text(x + 1, y + 37, "•", "small");
            }
        }
    }
    d.text(
        24,
        290,
        "• selected value       unmarked cell: another column",
        "small",
    );
    d.text(
        24,
        318,
        "Logical values only; CSV parsing and Parquet metadata add work.",
        "small",
    );
    Ok(Visual { name: "visual-layouts", drawing: d, caption: "Storing a column together gathers the values this query needs into continuous runs.".into(), source: "Computed from the header and rows of `fixtures/formats/eight-orders.csv`, using the walkthrough's selected columns. Each cell represents one value, not one byte.".into() })
}

fn footer(root: &Path) -> Result<Visual, String> {
    let bytes = fixture(root, "tiny.parquet")?;
    let trailer = parse_trailer(
        bytes[bytes.len() - 8..]
            .try_into()
            .map_err(|_| "short trailer")?,
        bytes.len() as u64,
    )
    .map_err(|e| e.to_string())?;
    let span = footer_span(bytes.len() as u64, trailer.footer_length).map_err(|e| e.to_string())?;
    let mut d = Drawing::new(365, "Find the footer by reading backwards", "File order is opening PAR1, data, footer, footer length and closing PAR1. Read the last eight bytes, then subtract their length and the decoded footer length from the file size to locate the footer.");
    for (x, w, label, colour) in [
        (24, 70, "PAR1", GREY),
        (98, 190, "Data", BLUE),
        (292, 190, "Footer", GREEN),
        (486, 80, "Length", GOLD),
        (570, 86, "PAR1", GREY),
    ] {
        d.card(x, 72, w, &[label], colour);
    }
    d.text(24, 144, "File order →", "small");
    d.arrow(615, 166, 530, 166);
    d.text(282, 195, "Start at the trailer", "strong");
    let hex = parquet_lab::encoding::hex(&bytes[bytes.len() - 8..]);
    d.card(
        282,
        211,
        374,
        &[&hex, "footer length (little-endian) + PAR1"],
        GOLD,
    );
    d.arrow(530, 292, 292, 292);
    d.text(
        24,
        322,
        &format!(
            "Footer starts at {} − 8 − {} = {}",
            bytes.len(),
            span.len(),
            span.start
        ),
        "mono",
    );
    d.text(
        24,
        350,
        "Offsets are absolute; block widths are not byte counts.",
        "small",
    );
    Ok(Visual {
        name: "visual-footer",
        drawing: d,
        caption:
            "The trailer gives the footer's length; its position follows from the file's size."
                .into(),
        source: source("tiny.parquet"),
    })
}

fn hierarchy(root: &Path) -> Result<Visual, String> {
    let bytes = fixture(root, "multiple-row-groups.parquet")?;
    let md = metadata(&bytes)?;
    let rg = md.row_groups.first().ok_or("no row group")?;
    let c = rg.columns.first().ok_or("no column")?;
    let span = c.byte_range();
    let pages =
        parquet_lab::pages::walk_pages(&bytes[span.start as usize..span.end as usize], span.start)
            .map_err(|e| e.to_string())?;
    let height = 290 + md.row_groups.len() * 50;
    let mut d = Drawing::new(height, "From table rows to pages", "A logical table is divided horizontally into row groups. Each row group has one chunk per leaf column. A column chunk is a sequence of page headers and bodies in the physical file.");
    d.text(24, 75, "Logical table", "strong");
    d.text(340, 75, "Physical column chunks", "strong");
    for (i, g) in md.row_groups.iter().enumerate() {
        let y = 95 + i * 50;
        d.card(
            24,
            y,
            240,
            &[&format!("Group {i}: {} rows", g.num_rows)],
            COLOURS[i % 4],
        );
        d.arrow(274, y + 22, 326, y + 22);
        let w = 310 / g.columns.len();
        for (j, _) in g.columns.iter().enumerate() {
            d.card(
                340 + j * w,
                y,
                w - 6,
                &[&format!("col {j}")],
                COLOURS[j % 4],
            );
        }
    }
    let y = 115 + md.row_groups.len() * 50;
    d.text(
        24,
        y,
        &format!("Expand group 0, {}", c.dotted_path()),
        "strong",
    );
    let w = 630 / pages.len();
    for (i, p) in pages.iter().enumerate() {
        d.card(
            24 + i * w,
            y + 20,
            w - 8,
            &[
                &format!("Page {i}"),
                "header → body",
                &format!("{} bytes", p.span().len()),
            ],
            BLUE,
        );
    }
    d.text(
        24,
        height - 20,
        "The footer records each chunk's location and size.",
        "small",
    );
    Ok(Visual { name:"visual-hierarchy", drawing:d, caption:"Row groups divide the table by rows; column chunks divide each group by column; pages divide each chunk.".into(), source:source("multiple-row-groups.parquet") })
}

fn requests(root: &Path) -> Result<Visual, String> {
    let bytes = fixture(root, "tiny.parquet")?;
    let trace = trace_for(
        &bytes,
        "tiny.parquet",
        FooterOptions::default(),
        NetworkModel::default(),
    )?;
    let mut d=Drawing::new(400,"Each request learns what the next one needs","The default opening strategy asks for the size, then the trailer, then the footer. The size locates the trailer; the trailer locates the footer; the footer locates the columns.");
    for (i, r) in trace.requests.iter().enumerate() {
        let y = 68 + i * 105;
        let label = format!(
            "{} {}",
            r.method.name(),
            r.range.as_deref().unwrap_or("file size")
        );
        d.card(
            24,
            y,
            310,
            &[&label, &format!("{} bytes returned", r.bytes_returned)],
            COLOURS[i % 4],
        );
        let learned = [
            "Size locates the trailer",
            "Length locates the footer",
            "Metadata locates columns",
        ];
        d.text(
            350,
            y + 28,
            learned.get(i).unwrap_or(&"Next structure"),
            "small",
        );
        if i + 1 < trace.requests.len() {
            d.arrow(170, y + 72, 170, y + 99);
        }
    }
    Ok(Visual {name:"visual-footer-requests",drawing:d,caption:"The default strategy waits for each answer before issuing the next request. A suffix prefetch can combine these steps.".into(),source:source("tiny.parquet")})
}

fn missing(root: &Path) -> Result<Visual, String> {
    let (_, j) = nested_levels_json(root, "tags.list.element")?;
    let triples = arr(j.get("triples"));
    let mut d=Drawing::new(400,"How much of the list exists?","Four definition levels distinguish an absent tags list, an empty list, a null element inside a present list, and a present value. Each case is taken from the tags column's decoded slots.");
    let records = arr(j.get("records"));
    let labels = [
        "List absent",
        "List has no entries",
        "Null element",
        "Value present",
    ];
    for (level, label) in labels.iter().enumerate() {
        let slot = triples
            .iter()
            .position(|t| num(t, "def") == level as u64)
            .ok_or("missing tags definition level")?;
        let t = &triples[slot];
        let row = triples[..=slot]
            .iter()
            .filter(|t| num(t, "rep") == 0)
            .count()
            - 1;
        let record = records[row]
            .get("tags")
            .ok_or("missing tags record")?
            .to_json();
        let y = 65 + level * 78;
        d.text(24, y + 22, &format!("d = {}", num(t, "def")), "mono");
        d.rect(110, y, 240, 60, GREY);
        if level > 0 {
            d.rect(120, y + 8, 220, 44, BLUE);
        }
        if level > 1 {
            d.rect(136, y + 16, 90, 28, if level == 2 { GREY } else { GREEN });
        }
        if level > 1 {
            let value = match t.get("value") {
                Some(Json::Null) => "null".into(),
                other => text_of(other),
            };
            d.text(145, y + 36, &value, "mono");
        }
        if level == 0 {
            d.text(130, y + 37, "no list", "small");
        }
        if level == 1 {
            d.text(130, y + 37, "empty list", "small");
        }
        d.text(365, y + 22, &record, "mono");
        d.text(365, y + 47, label, "small");
    }
    Ok(Visual{name:"visual-nested-missing",drawing:d,caption:"A definition level says how far the path exists. An absent value still needs a level slot to preserve the record's shape.".into(),source:source("nested.parquet")})
}

fn tags(root: &Path) -> Result<Visual, String> {
    let (_, j) = nested_levels_json(root, "tags.list.element")?;
    let triples = arr(j.get("triples"));
    let records = arr(j.get("records"));
    let mut d=Drawing::new(180+triples.len()*54,"Keep each record beside its level slots","Each tags record is aligned with its repetition, definition and value slots. Repetition zero starts a record; repetition one continues its list. Empty and absent lists each have a slot without a value. The same records are reconstructed from these slots.");
    d.text(24, 75, "Record: tags", "strong");
    d.text(310, 75, "r", "strong");
    d.text(370, 75, "d", "strong");
    d.text(430, 75, "Stored value", "strong");
    let mut row = 0;
    let mut start = 0;
    for (i, t) in triples.iter().enumerate() {
        let y = 92 + i * 54;
        let rep = num(t, "rep");
        if rep == 0 {
            start = i;
            let record = records
                .get(row)
                .and_then(|r| r.get("tags"))
                .ok_or("missing tags record")?;
            d.card(24, y, 245, &[&record.to_json()], COLOURS[row % 4]);
            row += 1;
        } else {
            d.arrow(275, 114 + start * 54, 295, y + 22);
        }
        d.rect(300, y, 352, 44, COLOURS[(row - 1) % 4]);
        d.text(310, y + 28, &rep.to_string(), "mono");
        d.text(370, y + 28, &num(t, "def").to_string(), "mono");
        let value = if t.get("value") == Some(&Json::Null) {
            "∅ (no value)".into()
        } else {
            text_of(t.get("value"))
        };
        d.text(430, y + 28, &value, "mono");
    }
    let y = 110 + triples.len() * 54;
    d.text(
        24,
        y,
        "r = 0 starts a record; r = 1 adds an element to the same list.",
        "small",
    );
    d.text(
        24,
        y + 28,
        "Read the slots back → the same records, including empty and null.",
        "small",
    );
    Ok(Visual{name:"visual-nested-tags",drawing:d,caption:"Record boundaries come from repetition levels. Definition levels preserve missing containers and elements when there is no value to store.".into(),source:source("nested.parquet")})
}

fn discounts(root: &Path) -> Result<Visual, String> {
    let (_, j) = nested_levels_json(root, "items.list.element.discounts.list.element")?;
    let (_, skus) = nested_levels_json(root, "items.list.element.sku")?;
    let triples = arr(j.get("triples"));
    let records = arr(j.get("records"));
    let sku_records = arr(skus.get("records"));
    let mut d=Drawing::new(185+triples.len()*64,"A repetition level names the list that continues","Orders contain items, and items contain discounts. Every discount slot is aligned with its containing order and item. Repetition zero starts an order, one starts another item, and two adds a discount. B2 has an empty discounts list but still has a level slot.");
    d.text(24, 76, "Order → item → discounts", "strong");
    d.text(420, 76, "(r, d, value)", "strong");
    let (mut record, mut item) = (0usize, 0usize);
    for (i, t) in triples.iter().enumerate() {
        let rep = num(t, "rep");
        if i > 0 && rep == 0 {
            record += 1;
            item = 0;
        } else if rep == 1 {
            item += 1;
        }
        let y = 94 + i * 64;
        if rep == 0 {
            d.text(24, y + 27, &format!("Order {}", record + 1), "strong");
        }
        let items = arr(records[record].get("items"));
        let sku_items = arr(sku_records[record].get("items"));
        let label = if let Some(it) = items.get(item) {
            format!(
                "{}: {}",
                text_of(sku_items.get(item).and_then(|s| s.get("sku"))),
                it.get("discounts").ok_or("no discounts")?.to_json()
            )
        } else {
            format!(
                "items = {}",
                records[record].get("items").ok_or("no items")?.to_json()
            )
        };
        if rep != 2 {
            d.card(145, y, 245, &[&label], COLOURS[record % 4]);
        } else {
            d.arrow(380, y - 25, 405, y + 23);
        }
        let value = if t.get("value") == Some(&Json::Null) {
            "∅".into()
        } else {
            text_of(t.get("value"))
        };
        d.card(
            415,
            y,
            240,
            &[&format!("({}, {}, {})", rep, num(t, "def"), value)],
            COLOURS[record % 4],
        );
    }
    let y = 115 + triples.len() * 64;
    d.text(
        24,
        y,
        "r = 0: new order  ·  r = 1: new item  ·  r = 2: next discount",
        "small",
    );
    d.text(
        24,
        y + 28,
        "∅ means no stored value; d explains what is missing.",
        "small",
    );
    Ok(Visual{name:"visual-nested-discounts",drawing:d,caption:"The empty discounts list in item B2 starts an item, not an order. Its slot preserves both containers without storing a discount.".into(),source:source("nested.parquet")})
}

fn split(root: &Path) -> Result<Visual, String> {
    let (bytes, j) = encodings_json(root, "encodings.parquet", "weight_kg")?;
    let pages = arr(j.get("pages"));
    let steps = arr(pages.first().ok_or("no encoded page")?.get("steps"));
    let mut streams = Vec::new();
    for step in &steps {
        let span = arr(step.get("span"));
        let a = span[0].as_u64().ok_or("no stream start")? as usize;
        let b = span[1].as_u64().ok_or("no stream end")? as usize;
        streams.push(&bytes[a..b]);
    }
    let count = streams
        .iter()
        .map(|s| s.len())
        .min()
        .ok_or("no streams")?
        .min(4);
    let mut d=Drawing::new(405,"Group the same byte positions together","The first four weight values are shown as rows of bytes, then transposed into byte-position streams. Byte labels identify their original positions. The bytes are unchanged and the encoding alone saves no space.");
    d.text(24, 78, "Bytes grouped by value", "strong");
    d.text(370, 78, "Bytes grouped by position", "strong");
    for value in 0..count {
        for (pos, stream) in streams.iter().enumerate() {
            let label = format!("{:02x}", stream[value]);
            d.card(
                24 + pos * 65,
                100 + value * 52,
                58,
                &[&label],
                COLOURS[pos % 4],
            );
            d.card(
                370 + value * 65,
                100 + pos * 52,
                58,
                &[&label],
                COLOURS[pos % 4],
            );
        }
    }
    d.arrow(295, 195, 352, 195);
    for pos in 0..streams.len() {
        d.text(35 + pos * 65, 326, &format!("b{pos}"), "mono");
        d.text(640, 129 + pos * 52, &format!("b{pos}"), "small");
    }
    d.text(
        24,
        375,
        &format!(
            "{} bytes before → {} bytes after; compression comes next.",
            count * streams.len(),
            count * streams.len()
        ),
        "strong",
    );
    Ok(Visual{name:"visual-byte-stream-split",drawing:d,caption:"BYTE_STREAM_SPLIT keeps every byte, but brings similar byte positions together for the compressor.".into(),source:source("encodings.parquet")})
}

fn page_layouts() -> Visual {
    let mut d=Drawing::new(510,"Data pages: where the boundaries move","Version one stores level lengths in the body and compresses the whole body when a codec is used. Version two puts level lengths in the header, leaves levels uncompressed and may compress only values. A repetition or definition stream is omitted when its maximum level is zero.");
    for (x, version) in [(24, "Version 1"), (354, "Version 2")] {
        d.text(x, 79, version, "strong");
        d.card(
            x,
            96,
            300,
            if x == 24 {
                &["Page header", "value count; body sizes"]
            } else {
                &["Page header", "+ level lengths, rows, nulls"]
            },
            GREY,
        );
        d.arrow(x + 150, 169, x + 150, 190);
    }
    d.rect(24, 196, 300, 234, GOLD);
    d.text(36, 222, "Body: compressed together*", "strong");
    d.card(36, 240, 276, &["Length + repetition levels"], BLUE);
    d.card(36, 298, 276, &["Length + definition levels"], BLUE);
    d.card(36, 356, 276, &["Encoded values"], GREEN);
    d.rect(354, 196, 300, 234, GREY);
    d.card(
        366,
        210,
        276,
        &["Repetition levels", "Uncompressed; no prefix"],
        BLUE,
    );
    d.card(
        366,
        287,
        276,
        &["Definition levels", "Uncompressed; no prefix"],
        BLUE,
    );
    d.card(366, 364, 276, &["Values: may be compressed*"], GOLD);
    d.text(
        24,
        464,
        "* With a codec. Headers themselves are not compressed.",
        "small",
    );
    d.text(
        24,
        490,
        "A level stream is absent when its maximum level is zero.",
        "small",
    );
    Visual{name:"visual-page-layouts",drawing:d,caption:"Version two separates the level streams from the compression boundary, so a reader can inspect them without decompressing values.".into(),source:"Format schematic, not byte-scaled. The chapter's page tables give the layouts measured from its uncompressed fixtures.".into()}
}

fn pruning(root: &Path) -> Result<Visual, String> {
    let mut groups = Vec::new();
    for file in [SORTED, SHUFFLED] {
        let bytes = fixture(root, file)?;
        let md = metadata(&bytes)?;
        let report = parquet_lab::report::skipping(&bytes, 0, "=", "431", 1);
        let decisions = arr(report.get("row_groups"));
        let mut ranges = Vec::new();
        for (g, decision) in md.row_groups.iter().zip(decisions.iter()) {
            let stats = g.columns[0]
                .statistics
                .as_ref()
                .ok_or("missing statistics")?;
            let decode = |v: &Option<Vec<u8>>| -> Result<i64, String> {
                Ok(i64::from_le_bytes(
                    v.as_ref()
                        .ok_or("missing bound")?
                        .as_slice()
                        .try_into()
                        .map_err(|_| "non-int64 bound")?,
                ))
            };
            ranges.push((
                decode(&stats.min_value)?,
                decode(&stats.max_value)?,
                decision.get("skipped") == Some(&Json::Bool(true)),
            ));
        }
        groups.push(ranges);
    }
    let low = groups
        .iter()
        .flatten()
        .map(|r| r.0)
        .min()
        .ok_or("no bounds")?;
    let high = groups
        .iter()
        .flatten()
        .map(|r| r.1)
        .max()
        .ok_or("no bounds")?;
    let px =
        |v: i64| 130 + ((v - low) as f64 / (high - low).max(1) as f64 * 380.0).round() as usize;
    let mut d=Drawing::new(200+groups.iter().map(|g|g.len()*55+65).sum::<usize>(),"Sorting narrows the ranges a query must read","Sorted and shuffled row groups use the same value axis. The vertical line marks order_id 431. A group is kept only when its minimum-to-maximum interval crosses the line; all others are labelled skip. Statistics decide possible matches, not exact matching rows.");
    d.text(24, 73, "Predicate: order_id = 431", "strong");
    let mut y = 118;
    for (panel, ranges) in groups.iter().enumerate() {
        d.text(
            24,
            y,
            if panel == 0 {
                "Sorted by order_id"
            } else {
                "Shuffled"
            },
            "strong",
        );
        y += 20;
        for (i, (a, b, skip)) in ranges.iter().enumerate() {
            d.text(24, y + 23, &format!("Group {i}"), "small");
            d.rect(
                px(*a),
                y,
                px(*b) - px(*a) + 1,
                28,
                if *skip { GREY } else { BLUE },
            );
            d.text(535, y + 21, if *skip { "SKIP" } else { "KEEP" }, "strong");
            d.text(130, y + 47, &format!("{a} … {b}"), "small");
            y += 55;
        }
        writeln!(d.body,"<path d=\"M{} {} V{}\" stroke=\"#9a4c16\" stroke-width=\"2\" stroke-dasharray=\"5 4\"/>",px(431),y-ranges.len()*55,y).unwrap();
        y += 45;
    }
    d.text(
        130,
        y,
        &format!("Common value axis: {low} … {high}"),
        "small",
    );
    Ok(Visual{name:"visual-pruning",drawing:d,caption:"The same predicate intersects narrow bands in sorted data and nearly every band in shuffled data. KEEP means a match is possible.".into(),source:format!("Bounds and keep/skip decisions computed by the reader from `fixtures/{SORTED}` and `fixtures/{SHUFFLED}`, with row-group statistics only. The value axis is shared and linear.")})
}

fn writing(root: &Path) -> Result<Visual, String> {
    let mut values = Vec::new();
    for (file, label) in WRITING {
        let bytes = fixture(root, file)?;
        let q = Query {
            columns: parquet_lab::report::flat_columns(&bytes)?,
            condition: Some((0, Op::Eq, "431".into())),
        };
        let (bytes, requests) = after_footer(&bytes, &q)?;
        values.push((label, bytes, requests));
    }
    let max = values.iter().map(|v| v.1).max().ok_or("no writer cases")?;
    let mut d=Drawing::new(170+values.len()*75,"One order, different amounts of reading","A shared linear bar chart compares bytes fetched after the footer for order_id 431 across every writer configuration. Labels also give request counts, so fewer bytes are not mistaken for lower latency.");
    d.text(24, 76, "SELECT * WHERE order_id = 431", "mono");
    for (i, (label, bytes, requests)) in values.iter().enumerate() {
        let y = 105 + i * 75;
        d.text(24, y, label, "strong");
        d.rect(
            24,
            y + 12,
            (*bytes as f64 / max as f64 * 440.0).round().max(1.0) as usize,
            25,
            BLUE,
        );
        d.text(
            475,
            y + 32,
            &format!("{} B / {} req", thousands(*bytes), requests),
            "small",
        );
    }
    d.text(
        24,
        140 + values.len() * 75,
        &format!(
            "Bars start at zero; longest bar = {} bytes.",
            thousands(max)
        ),
        "small",
    );
    Ok(Visual{name:"visual-writing-costs",drawing:d,caption:"The layout changes the bytes needed for the same answer. Request counts show why the smallest read need not be the fastest.".into(),source:"Computed by the reader from `fixtures/writing-*.parquet`: all columns, row-group statistics, Bloom filters and page index enabled; only touching ranges merged. Bars count index and page bytes after footer discovery, not total file size or elapsed time.".into()})
}

fn engine(root: &Path) -> Result<Visual, String> {
    let bytes = fixture(root, "writing-baseline.parquet")?;
    let sql="SELECT country, count(*) FROM orders WHERE order_id < 300 GROUP BY country ORDER BY country";
    let j = parquet_lab::report::query(&bytes, sql);
    let stages = arr(j.get("stages"));
    if stages.is_empty() {
        return Err(format!("query has no stages: {}", j.to_json()));
    }
    let mut d=Drawing::new(220+stages.len()*90,"Only the scan reads the Parquet file","Planning chooses order_id and country and pushes the condition into the scan. The scan uses row-group bounds and decodes possible matches. Filter checks those rows, Aggregate counts countries, and Sort orders the results. Row counts come from the book's engine.");
    d.card(
        24,
        64,
        630,
        &[
            "Plan: select order_id and country",
            "Push order_id < 300 into the scan",
        ],
        GREY,
    );
    d.arrow(190, 137, 190, 157);
    for (i, s) in stages.iter().enumerate() {
        let y = 165 + i * 90;
        let label = text_of(s.get("name"));
        d.card(
            24,
            y,
            330,
            &[
                &label,
                &format!("{} rows → {} rows", num(s, "rows_in"), num(s, "rows_out")),
            ],
            if i == 0 { BLUE } else { GREEN },
        );
        let notes = match label.as_str() {
            "Scan" => ["Reads the file", "Skips impossible row groups"],
            "Filter" => ["Checks decoded rows", "Removes remaining non-matches"],
            "Aggregate" => ["Groups by country", "Counts rows in each group"],
            _ => ["Orders the result", "Works on decoded values"],
        };
        d.text(374, y + 25, notes[0], "strong");
        d.text(374, y + 52, notes[1], "small");
        if i + 1 < stages.len() {
            d.arrow(190, y + 70, 190, y + 84);
        }
    }
    d.text(
        24,
        195 + stages.len() * 90,
        "Metadata pruning saves reads; row filtering still checks the condition.",
        "small",
    );
    Ok(Visual{name:"visual-query-stages",drawing:d,caption:"The scan prunes and decodes. Later stages work on its output, and only the filter establishes which individual rows match.".into(),source:format!("Computed by the book's engine from `fixtures/writing-baseline.parquet` for `{sql}`. Planning is schematic; stage counts are the reader's actual results.")})
}

fn changes() -> Visual {
    let mut d=Drawing::new(520,"Delete a row: choose where the work happens","Both approaches keep the original immutable data file available to old snapshots. Copy-on-write creates a replacement without the deleted row. Merge-on-read retains the data file and adds a position delete file; readers combine them. Compaction later creates replacement files with deletes applied.");
    d.card(195, 65, 290, &["Original data file", "A   B   C"], BLUE);
    d.arrow(260, 138, 174, 181);
    d.arrow(460, 138, 625, 181);
    d.text(24, 171, "Copy-on-write", "strong");
    d.text(354, 171, "Merge-on-read", "strong");
    d.card(24, 193, 300, &["Write a replacement", "A        C"], GREEN);
    d.card(
        354,
        193,
        300,
        &["Keep original + add delete", "A   B   C    +    delete B"],
        GOLD,
    );
    d.text(24, 292, "Writer rewrites the data file.", "small");
    d.text(354, 292, "Reader applies the delete.", "small");
    d.arrow(510, 309, 510, 336);
    d.card(
        354,
        348,
        300,
        &["Compact into a new file", "A        C"],
        GREEN,
    );
    d.text(
        24,
        455,
        "New snapshots point to the new set of files.",
        "strong",
    );
    d.text(
        24,
        487,
        "Old snapshots can still need the original files; do not erase them yet.",
        "small",
    );
    Visual{name:"visual-table-deletes",drawing:d,caption:"Copy-on-write pays during the change. Merge-on-read defers work to readers until compaction applies the deletes.".into(),source:"Conceptual example: A, B and C identify rows, not measured fixture values. Position deletes identify a data file and a row position. The adjacent tables measure the chapter's actual files.".into()}
}

fn iceberg() -> Visual {
    let mut d=Drawing::new(660,"Iceberg finds data through metadata","A catalog points to the current metadata JSON, which identifies snapshots and their manifest lists. An old and a new snapshot can share an unchanged manifest. A new manifest can describe added files. Manifest lists and manifests use Avro; the data and delete files shown here use Parquet.");
    d.card(
        175,
        64,
        330,
        &["Catalog pointer", "Current metadata location"],
        GREY,
    );
    d.arrow(340, 137, 340, 157);
    d.card(
        175,
        165,
        330,
        &["Metadata file · JSON", "Schemas and snapshot references"],
        BLUE,
    );
    d.arrow(245, 239, 175, 272);
    d.arrow(435, 239, 505, 272);
    d.card(
        24,
        280,
        300,
        &["Earlier snapshot", "Manifest list · Avro"],
        GREY,
    );
    d.card(
        354,
        280,
        300,
        &["Current snapshot", "Manifest list · Avro"],
        BLUE,
    );
    d.arrow(174, 349, 174, 412);
    d.arrow(475, 349, 195, 412);
    d.arrow(525, 349, 505, 412);
    d.card(
        24,
        420,
        300,
        &["Shared manifest · Avro", "File paths, partitions, bounds"],
        GREEN,
    );
    d.card(
        354,
        420,
        300,
        &["New manifest · Avro", "New file entries"],
        GOLD,
    );
    d.arrow(174, 489, 174, 517);
    d.arrow(504, 489, 504, 517);
    d.card(24, 525, 300, &["Existing Parquet files"], GREEN);
    d.card(354, 525, 300, &["Added Parquet files"], GOLD);
    d.text(
        24,
        604,
        "Manifests list data files or delete files, never both in one manifest.",
        "small",
    );
    d.text(
        24,
        634,
        "File bounds → row-group bounds → page bounds: progressively less data.",
        "small",
    );
    Visual{name:"visual-iceberg-tree",drawing:d,caption:"A new snapshot can reuse unchanged manifests and data files. The catalog pointer selects the current metadata file.".into(),source:"Conceptual metadata graph for an append, following Iceberg's metadata structure. Shared arrows represent references, not duplicated files. The book's simplified snapshot fixture does not implement this tree.".into()}
}
