//! The book's generated fragments: every number a chapter prints, computed by the reader.
//!
//! A chapter never types a byte count, an offset or a request total. It `{include}`s a fragment
//! from `chapters/_generated/`, and this module writes those fragments by running the reader over
//! the committed fixtures. `pqlab figures --check` fails when a committed fragment differs from
//! what the reader now computes, so a change to the reader or a fixture cannot leave a chapter
//! printing an old number.
//!
//! Each fragment ends with the conditions it was computed under: which fixture, and which
//! simulated network. A figure without its conditions is a number without a source.

use std::path::Path;
use std::process::ExitCode;

use parquet_lab::compress::TokenKind;
use parquet_lab::format::{footer_span, parse_trailer};
use parquet_lab::json::Json;
use parquet_lab::metadata::FileMetaData;
use parquet_lab::object_store::{MemoryStore, NetworkModel, TracingStore};
use parquet_lab::reader::{read_footer, FooterOptions, SizeSource};
use parquet_lab::report::{layouts, open_bytes};

struct Figure {
    file: &'static str,
    render: fn(&Path) -> Result<String, String>,
}

const FIGURES: &[Figure] = &[
    Figure {
        file: "layouts-costs.md",
        render: layouts_costs,
    },
    Figure {
        file: "eight-orders-regions.md",
        render: |root| regions(root, "eight-orders.parquet"),
    },
    Figure {
        file: "tiny-regions.md",
        render: |root| regions(root, "tiny.parquet"),
    },
    Figure {
        file: "tiny-trailer.md",
        render: tiny_trailer,
    },
    Figure {
        file: "tiny-trace.md",
        render: tiny_trace,
    },
    Figure {
        file: "footer-strategies.md",
        render: footer_strategies,
    },
    Figure {
        file: "types-schema-flat.md",
        render: types_schema_flat,
    },
    Figure {
        file: "types-schema-text.md",
        render: types_schema_text,
    },
    Figure {
        file: "types-values.md",
        render: types_values,
    },
    Figure {
        file: "nested-schema-text.md",
        render: nested_schema_text,
    },
    Figure {
        file: "nested-columns.md",
        render: nested_columns,
    },
    Figure {
        file: "nested-levels-email.md",
        render: |root| nested_levels(root, "email"),
    },
    Figure {
        file: "nested-levels-tags.md",
        render: |root| nested_levels(root, "tags.list.element"),
    },
    Figure {
        file: "nested-levels-discounts.md",
        render: |root| nested_levels(root, "items.list.element.discounts.list.element"),
    },
    Figure {
        file: "nested-runs-discounts.md",
        render: nested_runs_discounts,
    },
    Figure {
        file: "encodings-sizes.md",
        render: encodings_sizes,
    },
    Figure {
        file: "dictionary-country.md",
        render: dictionary_country,
    },
    Figure {
        file: "delta-ordered-at.md",
        render: delta_ordered_at,
    },
    Figure {
        file: "delta-urls.md",
        render: delta_urls,
    },
    Figure {
        file: "split-weights.md",
        render: split_weights,
    },
    Figure {
        file: "pages-country-v1.md",
        render: |root| pages_table(root, "pages.parquet"),
    },
    Figure {
        file: "pages-country-v2.md",
        render: |root| pages_table(root, "pages-v2.parquet"),
    },
    Figure {
        file: "page-header-fields.md",
        render: page_header_fields,
    },
    Figure {
        file: "statistics-grid.md",
        render: statistics_grid,
    },
    Figure {
        file: "statistics-fields.md",
        render: statistics_fields,
    },
    Figure {
        file: "statistics-mistakes.md",
        render: statistics_mistakes,
    },
    Figure {
        file: "statistics-cost.md",
        render: statistics_cost,
    },
    Figure {
        file: "skipping-compare.md",
        render: skipping_compare,
    },
    Figure {
        file: "skipping-mechanisms.md",
        render: skipping_mechanisms,
    },
    Figure {
        file: "page-index-order-id.md",
        render: page_index_order_id,
    },
    Figure {
        file: "bloom-rate.md",
        render: bloom_rate,
    },
    Figure {
        file: "scan-strategies.md",
        render: scan_strategies,
    },
    Figure {
        file: "scan-full.md",
        render: scan_full,
    },
    Figure {
        file: "scan-networks.md",
        render: scan_networks,
    },
    Figure {
        file: "writing-files.md",
        render: writing_files,
    },
    Figure {
        file: "writing-queries.md",
        render: writing_queries,
    },
    Figure {
        file: "writing-lookups.md",
        render: writing_lookups,
    },
    Figure {
        file: "engine-stages.md",
        render: engine_stages,
    },
    Figure {
        file: "engine-answers.md",
        render: engine_answers,
    },
    Figure {
        file: "encryption-plaintext-footer.md",
        render: |root| encryption_view(root, "plaintext-footer.parquet"),
    },
    Figure {
        file: "encryption-encrypted-footer.md",
        render: |root| encryption_view(root, "encrypted-footer.parquet"),
    },
    Figure {
        file: "table-log.md",
        render: table_log,
    },
    Figure {
        file: "table-discovery.md",
        render: table_discovery,
    },
    Figure {
        file: "codec-files.md",
        render: codec_files,
    },
    Figure {
        file: "codec-columns.md",
        render: codec_columns,
    },
    Figure {
        file: "codec-split.md",
        render: codec_split,
    },
    Figure {
        file: "codec-country-page.md",
        render: codec_country_page,
    },
    Figure {
        file: "snappy-tokens-country.md",
        render: snappy_tokens_country,
    },
];

pub fn run(root: &Path, out: &Path, check: bool) -> Result<ExitCode, String> {
    let dir = root.join(out);
    if !check {
        std::fs::create_dir_all(&dir)
            .map_err(|e| format!("cannot create {}: {e}", dir.display()))?;
    }
    let mut stale = Vec::new();
    for fig in FIGURES {
        let body = (fig.render)(root)?;
        let path = dir.join(fig.file);
        if check {
            if std::fs::read_to_string(&path).ok().as_deref() != Some(body.as_str()) {
                stale.push(path.display().to_string());
            }
        } else {
            std::fs::write(&path, &body)
                .map_err(|e| format!("cannot write {}: {e}", path.display()))?;
            println!("wrote {}", path.display());
        }
    }
    if !stale.is_empty() {
        eprintln!("stale fragments (run `make figures` and commit):");
        for s in stale {
            eprintln!("  {s}");
        }
        return Ok(ExitCode::from(1));
    }
    if check {
        println!(
            "  {} fragments match what the reader computes",
            FIGURES.len()
        );
    }
    Ok(ExitCode::SUCCESS)
}

const HEADER: &str =
    "% Generated by `pqlab figures` (crates/pqlab/src/figures.rs). Do not edit.\n\n";

fn fixture(root: &Path, name: &str) -> Result<Vec<u8>, String> {
    let path = root.join("fixtures").join(name);
    std::fs::read(&path).map_err(|e| format!("cannot read {}: {e}", path.display()))
}

fn conditions(name: &str, bytes: &[u8], model: Option<NetworkModel>) -> String {
    let mut s = format!(
        "\n*Computed by the reader from `fixtures/{name}` ({} bytes).",
        bytes.len()
    );
    if let Some(m) = model {
        s.push_str(&format!(
            " Simulated network: {} per request, {} once data flows.",
            ms(m.latency_us),
            rate(m.bandwidth_bytes_per_sec)
        ));
    }
    s.push_str("*\n");
    s
}

fn ms(us: u64) -> String {
    let v = us as f64 / 1000.0;
    if us % 1000 == 0 {
        format!("{v:.0} ms")
    } else {
        format!("{v:.3} ms")
    }
}

fn rate(bps: u64) -> String {
    match bps {
        0 => "unlimited bandwidth".into(),
        b if b % 1_000_000 == 0 => format!("{} MB/s", b / 1_000_000),
        b => format!("{b} bytes/s"),
    }
}

/// `16777216` as `16,777,216`.
fn thousands(n: u64) -> String {
    let digits = n.to_string();
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    out
}

fn metadata(bytes: &[u8]) -> Result<FileMetaData, String> {
    open_bytes(bytes)
}

/// Every region of a file, in order: the magic, each row group and its column chunks, the footer.
fn regions(root: &Path, name: &str) -> Result<String, String> {
    let bytes = fixture(root, name)?;
    let size = bytes.len() as u64;
    let last8: [u8; 8] = bytes[bytes.len() - 8..].try_into().unwrap();
    let trailer = parse_trailer(last8, size).map_err(|e| e.to_string())?;
    let footer = footer_span(size, trailer.footer_length).map_err(|e| e.to_string())?;
    let md = metadata(&bytes)?;
    let mut rows = vec![("Opening magic `PAR1`".to_string(), 0, 4)];
    for (i, rg) in md.row_groups.iter().enumerate() {
        let spans: Vec<_> = rg.columns.iter().map(|c| c.byte_range()).collect();
        let start = spans.iter().map(|s| s.start).min().unwrap_or(4);
        let end = spans.iter().map(|s| s.end).max().unwrap_or(4);
        rows.push((format!("Row group {i}"), start, end));
        for c in &rg.columns {
            let s = c.byte_range();
            rows.push((
                format!("  Column chunk `{}`", c.dotted_path()),
                s.start,
                s.end,
            ));
        }
    }
    rows.push(("Footer (`FileMetaData`)".into(), footer.start, footer.end));
    rows.push((
        "Footer length".into(),
        trailer.length_span().start,
        trailer.length_span().end,
    ));
    rows.push((
        "Closing magic `PAR1`".into(),
        trailer.magic_span().start,
        trailer.magic_span().end,
    ));
    let mut s = String::from(HEADER);
    s.push_str("| Region | Starts at | Ends before | Length |\n|---|--:|--:|--:|\n");
    for (label, a, b) in rows {
        let label = match label.strip_prefix("  ") {
            Some(inner) => format!("↳ {inner}"),
            None => label,
        };
        s.push_str(&format!("| {label} | {a} | {b} | {} |\n", b - a));
    }
    s.push_str(&conditions(name, &bytes, None));
    Ok(s)
}

fn tiny_trailer(root: &Path) -> Result<String, String> {
    let name = "tiny.parquet";
    let bytes = fixture(root, name)?;
    let size = bytes.len() as u64;
    let last8: [u8; 8] = bytes[bytes.len() - 8..].try_into().unwrap();
    let t = parse_trailer(last8, size).map_err(|e| e.to_string())?;
    let footer = footer_span(size, t.footer_length).map_err(|e| e.to_string())?;
    let mut s = String::from(HEADER);
    s.push_str("| Offset | Byte | ASCII | Part |\n|--:|---|---|---|\n");
    for (i, b) in t.bytes.iter().enumerate() {
        let part = if i < 4 {
            "footer length"
        } else {
            "closing magic"
        };
        // A pipe would end the table cell, even inside backticks, unless it is escaped.
        let ascii = match *b {
            b'|' => "`\\|`".to_string(),
            b if b.is_ascii_graphic() => format!("`{}`", b as char),
            _ => "·".into(),
        };
        s.push_str(&format!(
            "| {} | `{b:02x}` | {ascii} | {part} |\n",
            t.span.start + i as u64
        ));
    }
    let terms: Vec<String> = t
        .length_terms()
        .iter()
        .map(|(b, w)| format!("`{b:02x}` × {}", thousands(*w)))
        .collect();
    s.push_str(&format!(
        "\nRead as a little-endian `u32`: {} = **{}**.\n\n",
        terms.join(" + "),
        t.footer_length
    ));
    s.push_str(&format!(
        "So the footer starts at {size} − 8 − {} = **{}** and ends before {size} − 8 = **{}**.\n",
        t.footer_length, footer.start, footer.end
    ));
    s.push_str(&conditions(name, &bytes, None));
    Ok(s)
}

fn trace_for(
    bytes: &[u8],
    key: &str,
    options: FooterOptions,
    model: NetworkModel,
) -> Result<TracingStore<MemoryStore>, String> {
    let mut store = MemoryStore::new();
    store.put(key, bytes.to_vec());
    let mut traced = TracingStore::new(store, model);
    read_footer(&mut traced, key, options).map_err(|e| e.to_string())?;
    Ok(traced)
}

fn tiny_trace(root: &Path) -> Result<String, String> {
    let name = "tiny.parquet";
    let bytes = fixture(root, name)?;
    let model = NetworkModel::default();
    let traced = trace_for(&bytes, name, FooterOptions::default(), model)?;
    let mut s = String::from(HEADER);
    s.push_str(
        "| # | Request | `Range` | Bytes back | Finished at | Why |\n|--:|---|---|--:|--:|---|\n",
    );
    for r in &traced.requests {
        s.push_str(&format!(
            "| {} | `{} /{}` | {} | {} | {} | {} |\n",
            r.seq,
            r.method.name(),
            r.key,
            r.range
                .as_deref()
                .map(|h| format!("`{h}`"))
                .unwrap_or("·".into()),
            r.bytes_returned,
            ms(r.end_us),
            r.why
        ));
    }
    s.push_str(&format!(
        "\n{} requests, {} bytes transferred, {} of simulated time before the first value could be read.\n",
        traced.requests.len(),
        traced.bytes_returned(),
        ms(traced.elapsed_us())
    ));
    s.push_str(&conditions(name, &bytes, Some(model)));
    Ok(s)
}

fn footer_strategies(root: &Path) -> Result<String, String> {
    let model = NetworkModel::default();
    let prefetch = 64 * 1024;
    let mut s = String::from(HEADER);
    s.push_str(
        "| File | How the size is found | Tail read | Requests | Bytes back | Simulated time |\n\
         |---|---|--:|--:|--:|--:|\n",
    );
    let mut sizes = Vec::new();
    for name in ["tiny.parquet", "multiple-row-groups.parquet"] {
        let bytes = fixture(root, name)?;
        sizes.push(format!("`{name}` is {} bytes", bytes.len()));
        let size = bytes.len() as u64;
        let strategies: [(&str, FooterOptions); 4] = [
            (
                "`HEAD`",
                FooterOptions {
                    size: SizeSource::Head,
                    prefetch: 8,
                },
            ),
            (
                "from a listing",
                FooterOptions {
                    size: SizeSource::Known(size),
                    prefetch: 8,
                },
            ),
            (
                "suffix range",
                FooterOptions {
                    size: SizeSource::SuffixRange,
                    prefetch: 8,
                },
            ),
            (
                "suffix range",
                FooterOptions {
                    size: SizeSource::SuffixRange,
                    prefetch,
                },
            ),
        ];
        for (how, options) in strategies {
            let traced = trace_for(&bytes, name, options, model)?;
            s.push_str(&format!(
                "| `{name}` | {how} | {} | {} | {} | {} |\n",
                options.prefetch,
                traced.requests.len(),
                traced.bytes_returned(),
                ms(traced.elapsed_us())
            ));
        }
    }
    s.push_str(&format!(
        "\n*Computed by the reader from the fixtures: {}. Simulated network: {} per request, {} once data flows.*\n",
        sizes.join(", "),
        ms(model.latency_us),
        rate(model.bandwidth_bytes_per_sec)
    ));
    Ok(s)
}

fn layouts_costs(_root: &Path) -> Result<String, String> {
    let model = NetworkModel::default();
    let all = |r: &Json, k: &str| -> Result<(u64, u64, u64, u64, u64, u64), String> {
        let l = r.get(k).ok_or("no layout")?;
        let n = |j: Option<&Json>| j.and_then(Json::as_u64).ok_or("missing number".to_string());
        Ok((
            n(l.get("needed_bytes"))?,
            l.get("needed")
                .and_then(Json::as_array)
                .map(|a| a.len() as u64)
                .unwrap_or(0),
            n(l.get("by_range").and_then(|b| b.get("elapsed_us")))?,
            n(l.get("whole").and_then(|b| b.get("bytes")))?,
            n(l.get("whole").and_then(|b| b.get("elapsed_us")))?,
            n(l.get("total_bytes"))?,
        ))
    };
    // Bits are column positions: order_id, customer_id, country, amount_cents, order_date.
    let queries: [(&str, u32, Option<usize>); 3] = [
        ("`SELECT country, amount_cents FROM sales`", 0b01100, None),
        ("`SELECT amount_cents FROM sales`", 0b01000, None),
        ("`SELECT * FROM sales WHERE order_id = 4`", 0b11111, Some(3)),
    ];
    let mut s = String::from(HEADER);
    s.push_str(
        "| Query | Layout | Bytes needed | Separate ranges | Fetch each range | Fetch the whole object |\n\
         |---|---|--:|--:|--:|--:|\n",
    );
    let mut total = 0;
    for (sql, mask, row) in queries {
        let r = layouts(mask, row, model);
        for (key, name) in [("rows_layout", "rows"), ("columns_layout", "columns")] {
            let (need, ranges, each_us, whole_bytes, whole_us, t) = all(&r, key)?;
            total = t;
            s.push_str(&format!(
                "| {sql} | {name} | {need} | {ranges} | {ranges} request{}, {} | {whole_bytes} bytes, {} |\n",
                if ranges == 1 { "" } else { "s" },
                ms(each_us),
                ms(whole_us)
            ));
        }
    }
    s.push_str(&format!(
        "\n*Computed by the reader from the eight-order sales table in `crates/parquet-lab/src/layout.rs`, \
         {total} bytes in either layout. Simulated network: {} per request, {} once data flows.*\n",
        ms(model.latency_us),
        rate(model.bandwidth_bytes_per_sec)
    ));
    Ok(s)
}

fn types_schema(root: &Path) -> Result<(Vec<u8>, Json), String> {
    let bytes = fixture(root, "types.parquet")?;
    let j = parquet_lab::report::schema(&bytes);
    if j.get("ok") != Some(&Json::Bool(true)) {
        return Err(format!("types.parquet: {}", j.to_json()));
    }
    Ok((bytes, j))
}

fn text_of(j: Option<&Json>) -> String {
    match j {
        Some(Json::Str(s)) => s.clone(),
        Some(Json::Null) | None => String::new(),
        Some(other) => other.to_json(),
    }
}

fn types_schema_flat(root: &Path) -> Result<String, String> {
    let (bytes, j) = types_schema(root)?;
    let mut s = String::from(HEADER);
    s.push_str("| # | Name | Children | Repetition | Physical type | Logical type |\n|--:|---|--:|---|---|---|\n");
    for e in j
        .get("elements")
        .and_then(Json::as_array)
        .ok_or("no elements")?
    {
        let physical = text_of(e.get("physical_type"));
        let physical = match e.get("type_length").and_then(Json::as_i64) {
            Some(n) if !physical.is_empty() => format!("{physical}({n})"),
            _ => physical,
        };
        s.push_str(&format!(
            "| {} | `{}` | {} | {} | {} | {} |\n",
            text_of(e.get("index")),
            text_of(e.get("name")),
            text_of(e.get("num_children")),
            text_of(e.get("repetition")).to_lowercase(),
            if physical.is_empty() {
                "(group)".into()
            } else {
                physical
            },
            text_of(e.get("logical_type")),
        ));
    }
    s.push_str(&conditions("types.parquet", &bytes, None));
    Ok(s)
}

fn types_schema_text(root: &Path) -> Result<String, String> {
    let (bytes, j) = types_schema(root)?;
    let mut s = String::from(HEADER);
    s.push_str("```text\n");
    s.push_str(&text_of(j.get("text")));
    s.push_str("```\n");
    s.push_str(&conditions("types.parquet", &bytes, None));
    Ok(s)
}

fn types_values(root: &Path) -> Result<String, String> {
    let (bytes, j) = types_schema(root)?;
    let mut s = String::from(HEADER);
    s.push_str(
        "| Column | Physical type | Logical type | Minimum, as stored | Read as the physical type | Read through the logical type |\n\
         |---|---|---|---|---|---|\n",
    );
    for l in j
        .get("leaves")
        .and_then(Json::as_array)
        .ok_or("no leaves")?
    {
        let min = l.get("statistics").and_then(|st| st.get("min"));
        let cell = |k: &str| {
            let v = text_of(min.and_then(|m| m.get(k)));
            if v.is_empty() {
                "·".to_string()
            } else {
                format!("`{}`", v.replace('`', ""))
            }
        };
        s.push_str(&format!(
            "| `{}` | {} | {} | {} | {} | {} |\n",
            text_of(l.get("path")),
            text_of(l.get("physical_type")),
            match text_of(l.get("logical_type")) {
                t if t.is_empty() => "·".to_string(),
                t => t,
            },
            cell("hex"),
            cell("physical"),
            cell("logical"),
        ));
    }
    s.push_str(&conditions("types.parquet", &bytes, None));
    Ok(s)
}

fn nested_levels_json(root: &Path, path: &str) -> Result<(Vec<u8>, Json), String> {
    let bytes = fixture(root, "nested.parquet")?;
    let all = parquet_lab::report::levels(&bytes, 0);
    let column = all
        .get("columns")
        .and_then(Json::as_array)
        .and_then(|cs| cs.iter().find(|c| text_of(c.get("path")) == path))
        .and_then(|c| c.get("column"))
        .and_then(Json::as_u64)
        .ok_or(format!("nested.parquet has no column {path}"))?;
    let j = parquet_lab::report::levels(&bytes, column as usize);
    if j.get("ok") != Some(&Json::Bool(true)) {
        return Err(format!("nested.parquet {path}: {}", j.to_json()));
    }
    Ok((bytes, j))
}

fn nested_schema_text(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, "nested.parquet")?;
    let j = parquet_lab::report::schema(&bytes);
    let mut s = String::from(HEADER);
    s.push_str("```text\n");
    s.push_str(&text_of(j.get("text")));
    s.push_str("```\n");
    s.push_str(&conditions("nested.parquet", &bytes, None));
    Ok(s)
}

fn nested_columns(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, "nested.parquet")?;
    let j = parquet_lab::report::levels(&bytes, 0);
    let mut s = String::from(HEADER);
    s.push_str("| Column | Path in the file | Max definition level | Max repetition level |\n|---|---|--:|--:|\n");
    for c in j
        .get("columns")
        .and_then(Json::as_array)
        .ok_or("no columns")?
    {
        s.push_str(&format!(
            "| `{}` | `{}` | {} | {} |\n",
            text_of(c.get("label")),
            text_of(c.get("path")),
            text_of(c.get("max_definition_level")),
            text_of(c.get("max_repetition_level")),
        ));
    }
    s.push_str(&conditions("nested.parquet", &bytes, None));
    Ok(s)
}

fn nested_levels(root: &Path, path: &str) -> Result<String, String> {
    let (bytes, j) = nested_levels_json(root, path)?;
    let mut s = String::from(HEADER);
    s.push_str("| r | d | Value | What the levels say |\n|--:|--:|---|---|\n");
    for t in j
        .get("triples")
        .and_then(Json::as_array)
        .ok_or("no triples")?
    {
        let value = match t.get("value") {
            Some(Json::Null) | None => "·".to_string(),
            Some(v) => format!("`{}`", v.to_json()),
        };
        s.push_str(&format!(
            "| {} | {} | {value} | {} |\n",
            text_of(t.get("rep")),
            text_of(t.get("def")),
            text_of(t.get("explain")),
        ));
    }
    s.push_str("\nThe records rebuilt from these triples:\n\n```text\n");
    for r in j
        .get("records")
        .and_then(Json::as_array)
        .ok_or("no records")?
    {
        s.push_str(&r.to_json());
        s.push('\n');
    }
    s.push_str("```\n");
    s.push_str(&conditions("nested.parquet", &bytes, None));
    Ok(s)
}

fn nested_runs_discounts(root: &Path) -> Result<String, String> {
    let (bytes, j) = nested_levels_json(root, "items.list.element.discounts.list.element")?;
    let page = j
        .get("pages")
        .and_then(Json::as_array)
        .and_then(|p| p.first())
        .ok_or("no pages")?;
    let mut s = String::from(HEADER);
    s.push_str("| Levels | Run | Header byte | Body bytes | Values |\n|---|---|---|---|---|\n");
    for (name, key) in [
        ("repetition", "repetition_levels"),
        ("definition", "definition_levels"),
    ] {
        let stream = page.get(key).ok_or("no levels")?;
        for run in stream
            .get("runs")
            .and_then(Json::as_array)
            .ok_or("no runs")?
        {
            let span_bytes = |k: &str| -> String {
                let sp = run
                    .get(k)
                    .and_then(Json::as_array)
                    .cloned()
                    .unwrap_or_default();
                let (a, b) = (
                    sp.first().and_then(Json::as_u64).unwrap_or(0) as usize,
                    sp.get(1).and_then(Json::as_u64).unwrap_or(0) as usize,
                );
                parquet_lab::encoding::hex(&bytes[a..b])
            };
            let values: Vec<String> = run
                .get("values")
                .and_then(Json::as_array)
                .map(|v| v.iter().map(|x| x.to_json()).collect())
                .unwrap_or_default();
            s.push_str(&format!(
                "| {name} | {} | `{}` | `{}` | {} |\n",
                text_of(run.get("kind")),
                span_bytes("header"),
                span_bytes("body"),
                values.join(", ")
            ));
        }
    }
    s.push_str(&conditions("nested.parquet", &bytes, None));
    Ok(s)
}

fn encodings_json(root: &Path, file: &str, path: &str) -> Result<(Vec<u8>, Json), String> {
    let bytes = fixture(root, file)?;
    let first = parquet_lab::report::encodings(&bytes, 0);
    let column = first
        .get("columns")
        .and_then(Json::as_array)
        .and_then(|cs| cs.iter().find(|c| text_of(c.get("path")) == path))
        .and_then(|c| c.get("column"))
        .and_then(Json::as_u64)
        .ok_or(format!("{file} has no column {path}"))?;
    let j = parquet_lab::report::encodings(&bytes, column as usize);
    if j.get("ok") != Some(&Json::Bool(true)) {
        return Err(format!("{file} {path}: {}", j.to_json()));
    }
    Ok((bytes, j))
}

fn encodings_sizes(root: &Path) -> Result<String, String> {
    let mut s = String::from(HEADER);
    s.push_str(
        "| File | Column | Encoding | Values | Stored | As PLAIN | Stored as a share of PLAIN |\n\
         |---|---|---|--:|--:|--:|--:|\n",
    );
    let mut sizes = Vec::new();
    for file in ["dictionary.parquet", "encodings.parquet"] {
        let bytes = fixture(root, file)?;
        sizes.push(format!("`{file}` is {} bytes", bytes.len()));
        let first = parquet_lab::report::encodings(&bytes, 0);
        for c in first
            .get("columns")
            .and_then(Json::as_array)
            .ok_or("no columns")?
        {
            let (_, j) = encodings_json(root, file, &text_of(c.get("path")))?;
            let sz = j.get("sizes").ok_or("no sizes")?;
            let (enc, plain) = (
                sz.get("encoded").and_then(Json::as_u64).unwrap_or(0),
                sz.get("plain").and_then(Json::as_u64).unwrap_or(0),
            );
            let encoding: Vec<String> = j
                .get("pages")
                .and_then(Json::as_array)
                .map(|ps| ps.iter().map(|p| text_of(p.get("encoding"))).collect())
                .unwrap_or_default();
            s.push_str(&format!(
                "| `{file}` | `{}` | {} | {} | {enc} bytes | {plain} bytes | {}% |\n",
                text_of(j.get("path")),
                encoding.join(", "),
                text_of(sz.get("count")),
                (enc * 100 + plain / 2).checked_div(plain).unwrap_or(0),
            ));
        }
    }
    s.push_str(&format!(
        "\n*Computed by the reader from the fixtures: {}. Stored is the encoded values, plus the dictionary page's body where there is one; levels and page headers are in neither column.*\n",
        sizes.join(", ")
    ));
    Ok(s)
}

fn dictionary_country(root: &Path) -> Result<String, String> {
    let (bytes, j) = encodings_json(root, "dictionary.parquet", "country")?;
    let mut s = String::from(HEADER);
    s.push_str("The dictionary page:\n\n| Index | Value | Bytes |\n|--:|---|---|\n");
    let dict = j.get("dictionary").ok_or("no dictionary")?;
    for e in dict
        .get("entries")
        .and_then(Json::as_array)
        .ok_or("no entries")?
    {
        let sp = e.get("span").and_then(Json::as_array).ok_or("no span")?;
        let (a, b) = (
            sp[0].as_u64().unwrap_or(0) as usize,
            sp[1].as_u64().unwrap_or(0) as usize,
        );
        s.push_str(&format!(
            "| {} | `{}` | `{}` |\n",
            text_of(e.get("index")),
            text_of(e.get("value")),
            parquet_lab::encoding::hex(&bytes[a..b])
        ));
    }
    s.push_str(
        "\nThe data page's values:\n\n| Step | Bytes | What the decoder read |\n|---|---|---|\n",
    );
    for p in j.get("pages").and_then(Json::as_array).ok_or("no pages")? {
        for st in p.get("steps").and_then(Json::as_array).ok_or("no steps")? {
            let sp = st.get("span").and_then(Json::as_array).ok_or("no span")?;
            let (a, b) = (
                sp[0].as_u64().unwrap_or(0) as usize,
                sp[1].as_u64().unwrap_or(0) as usize,
            );
            s.push_str(&format!(
                "| {} | `{}` | {} |\n",
                text_of(st.get("label")),
                parquet_lab::encoding::hex(&bytes[a..b]),
                text_of(st.get("detail"))
            ));
        }
    }
    let values: Vec<String> = j
        .get("values")
        .and_then(Json::as_array)
        .map(|v| v.iter().map(|x| text_of(x.get("value"))).collect())
        .unwrap_or_default();
    s.push_str(&format!("\nDecoded, in order: {}.\n", values.join(", ")));
    s.push_str(&conditions("dictionary.parquet", &bytes, None));
    Ok(s)
}

fn steps_table(bytes: &[u8], j: &Json, limit: usize) -> Result<String, String> {
    let mut s = String::from("| Step | Bytes | What the decoder read |\n|---|---|---|\n");
    for p in j.get("pages").and_then(Json::as_array).ok_or("no pages")? {
        for st in p
            .get("steps")
            .and_then(Json::as_array)
            .ok_or("no steps")?
            .iter()
            .take(limit)
        {
            let sp = st.get("span").and_then(Json::as_array).ok_or("no span")?;
            let (a, b) = (
                sp[0].as_u64().unwrap_or(0) as usize,
                sp[1].as_u64().unwrap_or(0) as usize,
            );
            let hex = if b - a > 12 {
                format!(
                    "{} … ({} bytes)",
                    parquet_lab::encoding::hex(&bytes[a..a + 12]),
                    b - a
                )
            } else if a == b {
                "(none)".to_string()
            } else {
                parquet_lab::encoding::hex(&bytes[a..b])
            };
            s.push_str(&format!(
                "| {} | `{hex}` | {} |\n",
                text_of(st.get("label")),
                text_of(st.get("detail"))
            ));
        }
    }
    Ok(s)
}

fn delta_ordered_at(root: &Path) -> Result<String, String> {
    let (bytes, j) = encodings_json(root, "encodings.parquet", "ordered_at")?;
    let mut s = String::from(HEADER);
    s.push_str(&steps_table(&bytes, &j, 8)?);
    let values: Vec<String> = j
        .get("values")
        .and_then(Json::as_array)
        .map(|v| v.iter().take(5).map(|x| text_of(x.get("value"))).collect())
        .unwrap_or_default();
    s.push_str(&format!("\nThe first values: {}, …\n", values.join(", ")));
    s.push_str(&conditions("encodings.parquet", &bytes, None));
    Ok(s)
}

fn delta_urls(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, "encodings.parquet")?;
    let md = open_bytes(&bytes)?;
    let rootn = parquet_lab::schema::build(&md.schema).map_err(|e| e.to_string())?;
    let leaves = parquet_lab::schema::leaves(&rootn);
    let leaf = leaves
        .iter()
        .find(|l| l.dotted_path() == "url")
        .ok_or("no url column")?;
    let data =
        parquet_lab::column::read_column(&bytes, &md.row_groups[0].columns[leaf.column], leaf)
            .map_err(|e| e.to_string())?;
    let page = data.pages.first().ok_or("no page")?;
    let body = &bytes[page.values.start as usize..page.values.end as usize];
    let deltas =
        parquet_lab::delta::binary_packed(body, page.values.start).map_err(|e| e.to_string())?;
    let (prefixes, end) = (deltas.values, deltas.end);
    let suffixes =
        parquet_lab::delta::length_byte_array(&body[(end - page.values.start) as usize..], end)
            .map_err(|e| e.to_string())?;
    let mut s = String::from(HEADER);
    s.push_str(
        "| # | Shared with the previous value | Stored suffix | Value |\n|--:|--:|---|---|\n",
    );
    for (i, (((p, _), suf), t)) in prefixes
        .iter()
        .zip(&suffixes.values)
        .zip(&data.triples)
        .take(12)
        .enumerate()
    {
        let show = |v: &parquet_lab::plain::PlainValue| text_of(Some(&v.to_json()));
        s.push_str(&format!(
            "| {i} | {p} | `{}` | `{}` |\n",
            show(&suf.value),
            t.value.as_ref().map(show).unwrap_or_default()
        ));
    }
    s.push_str(&conditions("encodings.parquet", &bytes, None));
    Ok(s)
}

fn split_weights(root: &Path) -> Result<String, String> {
    let (bytes, j) = encodings_json(root, "encodings.parquet", "weight_kg")?;
    let page = j
        .get("pages")
        .and_then(Json::as_array)
        .and_then(|p| p.first())
        .ok_or("no page")?;
    let mut s = String::from(HEADER);
    s.push_str("| Stream | Holds | First twelve bytes | Distinct bytes in the stream |\n|---|---|---|--:|\n");
    for st in page
        .get("steps")
        .and_then(Json::as_array)
        .ok_or("no steps")?
    {
        let sp = st.get("span").and_then(Json::as_array).ok_or("no span")?;
        let (a, b) = (
            sp[0].as_u64().unwrap_or(0) as usize,
            sp[1].as_u64().unwrap_or(0) as usize,
        );
        let mut distinct: Vec<u8> = bytes[a..b].to_vec();
        distinct.sort_unstable();
        distinct.dedup();
        s.push_str(&format!(
            "| {} | {} | `{}` | {} |\n",
            text_of(st.get("label")),
            text_of(st.get("detail")),
            parquet_lab::encoding::hex(&bytes[a..(a + 12).min(b)]),
            distinct.len()
        ));
    }
    s.push_str(&conditions("encodings.parquet", &bytes, None));
    Ok(s)
}

fn pages_table(root: &Path, file: &str) -> Result<String, String> {
    let bytes = fixture(root, file)?;
    let j = parquet_lab::report::pages(&bytes, 1);
    if j.get("ok") != Some(&Json::Bool(true)) {
        return Err(format!("{file}: {}", j.to_json()));
    }
    let pages = j.get("pages").and_then(Json::as_array).ok_or("no pages")?;
    let v2 = pages
        .iter()
        .any(|p| !matches!(p.get("v2"), Some(Json::Null) | None));
    let dash = |v: String| if v.is_empty() { "·".to_string() } else { v };
    let mut s = String::from(HEADER);
    if v2 {
        s.push_str("| # | Type | Starts at | Body bytes | Values | Rows | Nulls | Level bytes (def) | Checksum |\n|--:|---|--:|--:|--:|--:|--:|--:|---|\n");
    } else {
        s.push_str("| # | Type | Starts at | Body bytes | Values | First row | Rows | Nulls | Min | Max |\n|--:|---|--:|--:|--:|--:|--:|--:|---|---|\n");
    }
    for p in pages {
        let start = p
            .get("span")
            .and_then(Json::as_array)
            .and_then(|a| a.first())
            .map(|x| x.to_json())
            .unwrap_or_default();
        let st = p.get("statistics");
        let pick = |k: &str| dash(text_of(st.and_then(|x| x.get(k))));
        let v = p.get("v2");
        let vk = |k: &str| dash(text_of(v.and_then(|x| x.get(k))));
        if v2 {
            s.push_str(&format!(
                "| {} | {} | {start} | {} | {} | {} | {} | {} | {} |\n",
                text_of(p.get("index")),
                text_of(p.get("type")),
                text_of(p.get("compressed_page_size")),
                dash(text_of(p.get("num_values"))),
                vk("num_rows"),
                vk("num_nulls"),
                vk("definition_levels_byte_length"),
                match p.get("crc_ok") {
                    Some(Json::Bool(true)) => "matches",
                    Some(Json::Bool(false)) => "does not match",
                    _ => "none stored",
                },
            ));
        } else {
            s.push_str(&format!(
                "| {} | {} | {start} | {} | {} | {} | {} | {} | {} | {} |\n",
                text_of(p.get("index")),
                text_of(p.get("type")),
                text_of(p.get("compressed_page_size")),
                dash(text_of(p.get("num_values"))),
                dash(text_of(p.get("first_row"))),
                dash(text_of(p.get("rows_started"))),
                pick("null_count"),
                pick("min"),
                pick("max"),
            ));
        }
    }
    s.push_str(&format!(
        "\n*Computed by the reader from `fixtures/{file}` ({} bytes), column `{}`.*\n",
        bytes.len(),
        text_of(j.get("path"))
    ));
    Ok(s)
}

fn page_header_fields(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, "pages.parquet")?;
    let md = open_bytes(&bytes)?;
    let chunk = &md.row_groups[0].columns[2];
    let r = chunk.byte_range();
    let pages = parquet_lab::pages::walk_pages(&bytes[r.start as usize..r.end as usize], r.start)
        .map_err(|e| e.to_string())?;
    let page = pages.first().ok_or("no page")?;
    let tree = parquet_lab::report::annotate(&page.header, "PageHeader", "PageHeader", Some(chunk));
    let mut rows = Vec::new();
    fn walk(n: &Json, prefix: &str, rows: &mut Vec<(String, (u64, u64), String)>) {
        let label = text_of(n.get("label"));
        let path = if prefix.is_empty() {
            label.clone()
        } else {
            format!("{prefix}.{label}")
        };
        let kids = n
            .get("children")
            .and_then(Json::as_array)
            .cloned()
            .unwrap_or_default();
        if kids.is_empty() {
            let sp = n
                .get("span")
                .and_then(Json::as_array)
                .cloned()
                .unwrap_or_default();
            let a = sp.first().and_then(Json::as_u64).unwrap_or(0);
            let b = sp.get(1).and_then(Json::as_u64).unwrap_or(0);
            rows.push((path, (a, b), text_of(n.get("value"))));
        } else {
            for k in &kids {
                walk(
                    k,
                    if prefix.is_empty() && label == "PageHeader" {
                        ""
                    } else {
                        &path
                    },
                    rows,
                );
            }
        }
    }
    walk(&tree, "", &mut rows);
    let mut s = String::from(HEADER);
    s.push_str("| Field | Bytes | Value |\n|---|---|---|\n");
    for (path, (a, b), value) in rows {
        s.push_str(&format!(
            "| `{path}` | `{}` | {} |\n",
            parquet_lab::encoding::hex(&bytes[a as usize..b as usize]),
            value.replace('|', "\\|")
        ));
    }
    s.push_str(&format!(
        "\nThe header takes bytes {} to {} of the file; the body that follows it is {} bytes.\n",
        page.header_span.start, page.header_span.end, page.compressed_page_size
    ));
    s.push_str(&conditions("pages.parquet", &bytes, None));
    Ok(s)
}

/// The codec-* fixtures in the order the book discusses them: none, the fast codecs, then the
/// ones that trade speed for size.
const CODECS: [&str; 6] = ["none", "snappy", "lz4", "gzip", "zstd", "brotli"];

fn codec_files(root: &Path) -> Result<String, String> {
    let mut rows = vec![
        "| File | Codec in the footer | File bytes | Column chunk bytes | Share of uncompressed |"
            .to_string(),
        "|---|---|--:|--:|--:|".to_string(),
    ];
    let mut base = 0i64;
    for codec in CODECS {
        let name = format!("codec-{codec}.parquet");
        let bytes = fixture(root, &name)?;
        let md = open_bytes(&bytes)?;
        let cs = &md.row_groups[0].columns;
        let compressed: i64 = cs.iter().map(|c| c.total_compressed_size).sum();
        if codec == "none" {
            base = compressed;
        }
        rows.push(format!(
            "| `{name}` | `{}` | {} | {} | {}% |",
            cs[0].codec,
            thousands(bytes.len() as u64),
            thousands(compressed as u64),
            (compressed * 100 + base / 2) / base.max(1)
        ));
    }
    Ok(format!(
        "{}\n\n*Computed by the reader from the footers of the `fixtures/codec-*.parquet` files: \
         256 orders, PLAIN-encoded, one row group, one data page per column chunk. Column chunk \
         bytes include page headers.*\n",
        rows.join("\n")
    ))
}

fn codec_columns(root: &Path) -> Result<String, String> {
    let mut sizes = Vec::new();
    let mut paths = Vec::new();
    for codec in CODECS {
        let md = open_bytes(&fixture(root, &format!("codec-{codec}.parquet"))?)?;
        let cs = &md.row_groups[0].columns;
        paths = cs.iter().map(|c| c.dotted_path()).collect();
        sizes.push(
            cs.iter()
                .map(|c| c.total_compressed_size)
                .collect::<Vec<_>>(),
        );
    }
    let mut rows = vec![
        format!("| Column | {} |", CODECS.join(" | ")),
        format!("|---|{}", "--:|".repeat(CODECS.len())),
    ];
    for (i, path) in paths.iter().enumerate() {
        let cells: Vec<String> = sizes.iter().map(|s| thousands(s[i] as u64)).collect();
        rows.push(format!("| `{path}` | {} |", cells.join(" | ")));
    }
    Ok(format!(
        "{}\n\n*Column chunk bytes, including page headers, from the footers of the \
         `fixtures/codec-*.parquet` files.*\n",
        rows.join("\n")
    ))
}

fn codec_split(root: &Path) -> Result<String, String> {
    let plain = open_bytes(&fixture(root, "codec-zstd.parquet")?)?;
    let split = open_bytes(&fixture(root, "codec-zstd-split.parquet")?)?;
    let mut rows = vec![
        "| Column | Encoding | Before ZSTD | After ZSTD |".to_string(),
        "|---|---|--:|--:|".to_string(),
    ];
    for path in ["weight_kg", "distance_km"] {
        for md in [&plain, &split] {
            let c = md.row_groups[0]
                .columns
                .iter()
                .find(|c| c.dotted_path() == path)
                .ok_or(format!("no column {path}"))?;
            let encoding = c
                .encodings
                .iter()
                .find(|e| e.as_str() != "RLE")
                .cloned()
                .unwrap_or_default();
            rows.push(format!(
                "| `{path}` | `{encoding}` | {} | {} |",
                thousands(c.total_uncompressed_size as u64),
                thousands(c.total_compressed_size as u64)
            ));
        }
    }
    Ok(format!(
        "{}\n\n*Computed by the reader from the footers of `fixtures/codec-zstd.parquet` and \
         `fixtures/codec-zstd-split.parquet`, which differ only in these two columns' encoding.*\n",
        rows.join("\n")
    ))
}

/// One page, the three decoders' tokens counted.
fn codec_country_page(root: &Path) -> Result<String, String> {
    let mut rows = vec![
        "| Codec | Compressed bytes | Tokens | Bytes written as literals | Bytes copied from earlier | Longest copy |"
            .to_string(),
        "|---|--:|--:|--:|--:|--:|".to_string(),
    ];
    let mut size = 0;
    for codec in ["snappy", "lz4", "gzip"] {
        let (page, d) = first_page(root, &format!("codec-{codec}.parquet"), 1)?;
        size = d.bytes.len();
        let (mut literal, mut copied, mut longest) = (0u64, 0u64, 0u64);
        for t in &d.tokens {
            match t.kind {
                TokenKind::Literal => literal += t.output.len(),
                TokenKind::Copy { .. } => {
                    copied += t.output.len();
                    longest = longest.max(t.output.len());
                }
                TokenKind::Header => {}
            }
        }
        rows.push(format!(
            "| {} | {} | {} | {} | {} | {} |",
            page.0,
            thousands(page.1),
            d.tokens.len(),
            thousands(literal),
            thousands(copied),
            thousands(longest)
        ));
    }
    Ok(format!(
        "{}\n\n*The `country` column's data page, {} bytes before compression, decompressed by \
         the reader from `fixtures/codec-snappy.parquet`, `codec-lz4.parquet` and \
         `codec-gzip.parquet`. Tokens include headers and trailers.*\n",
        rows.join("\n"),
        thousands(size as u64)
    ))
}

fn snappy_tokens_country(root: &Path) -> Result<String, String> {
    let name = "codec-snappy.parquet";
    let bytes = fixture(root, name)?;
    let (_, d) = first_page(root, name, 1)?;
    let mut rows = vec![
        "| Compressed bytes | Token | Writes output | What it says |".to_string(),
        "|---|---|--:|---|".to_string(),
    ];
    let shown = 9;
    for t in d.tokens.iter().take(shown) {
        let hexed =
            parquet_lab::encoding::hex(&bytes[t.input.start as usize..t.input.end as usize]);
        rows.push(format!(
            "| `{hexed}` | {} | {} | {} |",
            t.label,
            if t.output.is_empty() {
                "·".to_string()
            } else {
                format!("{}–{}", t.output.start, t.output.end - 1)
            },
            t.detail
        ));
    }
    let rest = &d.tokens[shown.min(d.tokens.len())..];
    let copies = rest
        .iter()
        .filter(|t| matches!(t.kind, TokenKind::Copy { .. }))
        .count();
    Ok(format!(
        "{}\n\n{} more tokens follow, {copies} of them copies.\n{}",
        rows.join("\n"),
        rest.len(),
        conditions(name, &bytes, None)
    ))
}

/// The first data page of a column in the first row group: its codec's name and compressed
/// size, and the page decompressed.
fn first_page(
    root: &Path,
    name: &str,
    column: usize,
) -> Result<((String, u64), parquet_lab::compress::Decompressed), String> {
    let bytes = fixture(root, name)?;
    let md = open_bytes(&bytes)?;
    let chunk = &md.row_groups[0].columns[column];
    let r = chunk.byte_range();
    let pages = parquet_lab::pages::walk_pages(&bytes[r.start as usize..r.end as usize], r.start)
        .map_err(|e| e.to_string())?;
    let page = pages
        .iter()
        .find(|p| p.page_type == "DATA_PAGE")
        .ok_or(format!("{name}: no data page"))?;
    let body = &bytes[page.body_span.start as usize..page.body_span.end as usize];
    let d = parquet_lab::compress::decompress(
        &chunk.codec,
        body,
        page.body_span.start,
        page.uncompressed_page_size as usize,
    )?;
    Ok(((chunk.codec.clone(), page.body_span.len()), d))
}

const STATS: &str = "statistics.parquet";

fn arr(j: Option<&Json>) -> Vec<Json> {
    j.and_then(Json::as_array).cloned().unwrap_or_default()
}

/// `|` would end a table cell.
fn cell(s: &str) -> String {
    s.replace('|', "\\|")
}

fn statistics_grid(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, STATS)?;
    let r = parquet_lab::report::statistics(&bytes, 0, 0);
    let groups = arr(r.get("row_groups"));
    let mut rows = vec![
        format!(
            "| Column | Order | {} |",
            (0..groups.len())
                .map(|g| format!("Row group {g}"))
                .collect::<Vec<_>>()
                .join(" | ")
        ),
        format!("|---|---|{}", "---|".repeat(groups.len())),
    ];
    for c in arr(r.get("columns")) {
        let chunks: Vec<String> = arr(c.get("chunks"))
            .iter()
            .map(|k| {
                if matches!(k.get("usable"), Some(Json::Bool(true))) {
                    format!(
                        "{} … {}",
                        cell(&text_of(k.get("min"))),
                        cell(&text_of(k.get("max")))
                    )
                } else if text_of(k.get("reason")).starts_with("every value is null") {
                    "all null".to_string()
                } else {
                    "none".to_string()
                }
            })
            .collect();
        rows.push(format!(
            "| `{}` | {} | {} |",
            text_of(c.get("path")),
            text_of(c.get("order")),
            chunks.join(" | ")
        ));
    }
    Ok(format!(
        "{}\n{}",
        rows.join("\n"),
        conditions(STATS, &bytes, None)
    ))
}

fn statistics_fields(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, STATS)?;
    let md = open_bytes(&bytes)?;
    let rg = &md.row_groups[0];
    let tick = |b: bool| if b { "yes" } else { "·" };
    let mut rows = vec![
        "| Column | Order | `min_value`, `max_value` | `min`, `max` (deprecated) | `null_count` | exact flags |"
            .to_string(),
        "|---|---|---|---|--:|---|".to_string(),
    ];
    let r = parquet_lab::report::statistics(&bytes, 0, 0);
    for (c, j) in rg.columns.iter().zip(arr(r.get("columns"))) {
        let s = c.statistics.as_ref();
        rows.push(format!(
            "| `{}` | {} | {} | {} | {} | {} |",
            c.dotted_path(),
            text_of(j.get("order")),
            tick(s.is_some_and(|s| s.min_value.is_some())),
            tick(s.is_some_and(|s| s.min.is_some())),
            s.and_then(|s| s.null_count)
                .map(|n| n.to_string())
                .unwrap_or("·".into()),
            tick(s.is_some_and(|s| s.is_min_value_exact.is_some())),
        ));
    }
    Ok(format!(
        "{}\n\n*Row group 0 of `fixtures/{STATS}`, as its footer records it. `·` means the field is \
         absent.*\n",
        rows.join("\n")
    ))
}

fn statistics_mistakes(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, STATS)?;
    let md = open_bytes(&bytes)?;
    let mut rows = vec![
        "| Column | Row group | The footer, in the column's order | The mistaken order | What it gives |"
            .to_string(),
        "|---|--:|---|---|---|".to_string(),
    ];
    let n = parquet_lab::report::statistics(&bytes, 0, 0)
        .get("columns")
        .and_then(Json::as_array)
        .map(|a| a.len())
        .unwrap_or(0);
    for column in 0..n {
        // The first row group where the mistake changes the answer.
        for g in 0..md.row_groups.len() {
            let r = parquet_lab::report::statistics(&bytes, g, column);
            let sel = r.get("selected").cloned().unwrap_or(Json::Null);
            let values = sel.get("values").cloned().unwrap_or(Json::Null);
            let (Some(obs), Some(m)) = (values.get("observed"), values.get("mistake")) else {
                continue;
            };
            let Some(res) = m.get("result") else { continue };
            let pair = |j: &Json| {
                format!(
                    "{} … {}",
                    cell(&text_of(j.get("min"))),
                    cell(&text_of(j.get("max")))
                )
            };
            if pair(obs) == pair(res) {
                continue;
            }
            rows.push(format!(
                "| `{}` | {g} | {} | {} | {} |",
                text_of(sel.get("path")),
                pair(obs),
                text_of(m.get("comparator")),
                pair(res)
            ));
            break;
        }
    }
    Ok(format!(
        "{}\n\n*Computed by the reader from the values it decoded from `fixtures/{STATS}`. The \
         footer's minimum and maximum equal the first column in every row.*\n",
        rows.join("\n")
    ))
}

fn statistics_cost(root: &Path) -> Result<String, String> {
    let mut rows = vec![
        "| File | File bytes | Footer bytes | Statistics in the footer | Column chunks |"
            .to_string(),
        "|---|--:|--:|--:|--:|".to_string(),
    ];
    for name in [STATS, "codec-none.parquet"] {
        let bytes = fixture(root, name)?;
        let md = open_bytes(&bytes)?;
        let size = bytes.len() as u64;
        let last8: [u8; 8] = bytes[bytes.len() - 8..].try_into().unwrap();
        let footer = parse_trailer(last8, size)
            .map_err(|e| e.to_string())?
            .footer_length;
        let chunks: Vec<_> = md.row_groups.iter().flat_map(|rg| &rg.columns).collect();
        let stats: u64 = chunks
            .iter()
            .filter_map(|c| c.statistics.as_ref())
            .map(|s| s.span.len())
            .sum();
        rows.push(format!(
            "| `{name}` | {} | {} | {} | {} |",
            thousands(size),
            thousands(footer as u64),
            thousands(stats),
            chunks.len()
        ));
    }
    Ok(format!(
        "{}\n\n*Computed by the reader from the fixtures' footers. Statistics bytes are the \
         `Statistics` structures in the column chunks' metadata; page headers carry their own \
         copies, which are not counted.*\n",
        rows.join("\n")
    ))
}

const SORTED: &str = "pruning-sorted.parquet";
const SHUFFLED: &str = "pruning-shuffled.parquet";

fn num(j: &Json, key: &str) -> u64 {
    j.get(key).and_then(Json::as_u64).unwrap_or(0)
}

/// The conditions the chapter compares, as (column, op, value). The customer number that is
/// present is read from the fixture, so it stays true if the fixture changes.
fn skipping_conditions(root: &Path) -> Result<Vec<(usize, &'static str, String)>, String> {
    let bytes = fixture(root, SORTED)?;
    let md = open_bytes(&bytes)?;
    let root_node = parquet_lab::schema::build(&md.schema).map_err(|e| e.to_string())?;
    let leaves = parquet_lab::schema::leaves(&root_node);
    let data = parquet_lab::column::read_column(&bytes, &md.row_groups[2].columns[1], &leaves[1])
        .map_err(|e| e.to_string())?;
    let present = data.triples[17]
        .value
        .as_ref()
        .map(|v| v.to_json().to_json())
        .ok_or("no customer")?;
    Ok(vec![
        (0, "=", "431".into()),
        (0, "<", "100".into()),
        (3, ">", "9800".into()),
        (1, "=", present),
        (1, "=", "424242".into()),
        (2, "is null", String::new()),
    ])
}

fn skipping_compare(root: &Path) -> Result<String, String> {
    let sorted = fixture(root, SORTED)?;
    let shuffled = fixture(root, SHUFFLED)?;
    let mut rows = vec![
        "| Condition | Matching rows | Sorted: bytes read | Sorted: rows decoded | Shuffled: bytes read | Shuffled: rows decoded |"
            .to_string(),
        "|---|--:|--:|--:|--:|--:|".to_string(),
    ];
    let (mut full_a, mut full_b, mut total_rows) = (0, 0, 0);
    for (column, op, value) in skipping_conditions(root)? {
        let a = parquet_lab::report::skipping(&sorted, column, op, &value, 7);
        let b = parquet_lab::report::skipping(&shuffled, column, op, &value, 7);
        let (ta, tb) = (
            a.get("totals").cloned().unwrap_or(Json::Null),
            b.get("totals").cloned().unwrap_or(Json::Null),
        );
        (full_a, full_b, total_rows) = (
            num(&ta, "bytes_full_scan"),
            num(&tb, "bytes_full_scan"),
            num(&ta, "rows"),
        );
        rows.push(format!(
            "| `{}` | {} | {} | {} | {} | {} |",
            text_of(a.get("condition")),
            num(&ta, "rows_matching"),
            thousands(num(&ta, "bytes_read")),
            thousands(num(&ta, "rows_read")),
            thousands(num(&tb, "bytes_read")),
            thousands(num(&tb, "rows_read")),
        ));
    }
    Ok(format!(
        "{}\n\n*Computed by the reader from `fixtures/{SORTED}` and `fixtures/{SHUFFLED}`, using \
         row group statistics, Bloom filters and the page index. A full scan decodes {} rows and \
         reads {} bytes of column chunks from the sorted file, {} from the shuffled one. Bytes \
         read do not include the indexes and filters fetched to decide.*\n",
        rows.join("\n"),
        thousands(total_rows),
        thousands(full_a),
        thousands(full_b)
    ))
}

fn skipping_mechanisms(root: &Path) -> Result<String, String> {
    let mut rows = vec![
        "| File | Condition | Mechanisms | Row groups skipped | Bytes read | Bytes fetched to decide |"
            .to_string(),
        "|---|---|---|--:|--:|--:|".to_string(),
    ];
    let conditions = skipping_conditions(root)?;
    let cases = [
        (SORTED, &conditions[0], [0u32, 1, 5]),
        (SHUFFLED, &conditions[4], [0, 1, 3]),
    ];
    let names = |m: u32| {
        let v: Vec<&str> = [(1, "statistics"), (2, "Bloom filters"), (4, "page index")]
            .iter()
            .filter(|(b, _)| m & b != 0)
            .map(|(_, n)| *n)
            .collect();
        if v.is_empty() {
            "none".to_string()
        } else {
            v.join(", ")
        }
    };
    for (file, (column, op, value), masks) in cases {
        let bytes = fixture(root, file)?;
        for m in masks {
            let r = parquet_lab::report::skipping(&bytes, *column, op, value, m);
            let t = r.get("totals").cloned().unwrap_or(Json::Null);
            let skipped = arr(r.get("row_groups"))
                .iter()
                .filter(|g| matches!(g.get("skipped"), Some(Json::Bool(true))))
                .count();
            rows.push(format!(
                "| `{file}` | `{}` | {} | {skipped} of {} | {} | {} |",
                text_of(r.get("condition")),
                names(m),
                arr(r.get("row_groups")).len(),
                thousands(num(&t, "bytes_read")),
                thousands(num(&t, "index_bytes")),
            ));
        }
    }
    Ok(format!(
        "{}\n\n*Computed by the reader from the pruning fixtures, with each set of mechanisms \
         allowed in turn.*\n",
        rows.join("\n")
    ))
}

fn page_index_order_id(root: &Path) -> Result<String, String> {
    let mut cols = Vec::new();
    for file in [SORTED, SHUFFLED] {
        let bytes = fixture(root, file)?;
        let md = open_bytes(&bytes)?;
        let chunk = &md.row_groups[2].columns[0];
        let ci = parquet_lab::page_index::column_index(&bytes, chunk)?.ok_or("no column index")?;
        let oi = parquet_lab::page_index::offset_index(&bytes, chunk)?.ok_or("no offset index")?;
        let rows = oi.row_ranges(md.row_groups[2].num_rows);
        let int = |b: &[u8]| i64::from_le_bytes(b.try_into().unwrap_or([0; 8]));
        cols.push((
            ci.boundary_order.clone(),
            (0..rows.len())
                .map(|i| (rows[i], int(&ci.min_values[i]), int(&ci.max_values[i])))
                .collect::<Vec<_>>(),
        ));
    }
    let mut out = vec![
        format!("| Page | Rows | Sorted: `order_id` min … max | Shuffled: `order_id` min … max |"),
        "|--:|---|---|---|".to_string(),
    ];
    for i in 0..cols[0].1.len() {
        let (r, a0, a1) = cols[0].1[i];
        let (_, b0, b1) = cols[1].1[i];
        out.push(format!(
            "| {i} | {}–{} | {a0} … {a1} | {b0} … {b1} |",
            r.0,
            r.1 - 1
        ));
    }
    Ok(format!(
        "{}\n\n*The ColumnIndex of `order_id` in row group 2 of each pruning fixture, read by the \
         reader. Its boundary order is `{}` in the sorted file and `{}` in the shuffled one.*\n",
        out.join("\n"),
        cols[0].0,
        cols[1].0
    ))
}

fn bloom_rate(root: &Path) -> Result<String, String> {
    let mut rows = vec![
        "| File | Row group | Filter bytes | Values in the chunk | Absent values tested | Passed anyway |"
            .to_string(),
        "|---|--:|--:|--:|--:|--:|".to_string(),
    ];
    let (mut tested, mut passed) = (0u64, 0u64);
    for file in [SHUFFLED] {
        let bytes = fixture(root, file)?;
        let md = open_bytes(&bytes)?;
        let root_node = parquet_lab::schema::build(&md.schema).map_err(|e| e.to_string())?;
        let leaf = &parquet_lab::schema::leaves(&root_node)[1];
        for (g, rg) in md.row_groups.iter().enumerate() {
            let chunk = &rg.columns[1];
            let filter = parquet_lab::bloom::read(&bytes, chunk)?.ok_or("no Bloom filter")?;
            let data =
                parquet_lab::column::read_column(&bytes, chunk, leaf).map_err(|e| e.to_string())?;
            let values: Vec<Vec<u8>> = data
                .triples
                .iter()
                .filter_map(|t| t.value.as_ref())
                .map(|v| v.to_plain_bytes(leaf.physical_type))
                .collect();
            let (mut t, mut p) = (0u64, 0u64);
            for candidate in (100_000i64..1_000_000).step_by(97) {
                let b = candidate.to_le_bytes().to_vec();
                if !values.contains(&b) {
                    t += 1;
                    p += u64::from(filter.probe(&b).may_contain);
                }
            }
            tested += t;
            passed += p;
            rows.push(format!(
                "| `{file}` | {g} | {} | {} | {} | {} |",
                filter.bitset_span.end - filter.header_span.start,
                values.len(),
                thousands(t),
                thousands(p)
            ));
        }
    }
    Ok(format!(
        "{}\n\n*Computed by the reader: every customer number from 100,000 in steps of 97 that the \
         row group does not hold, probed against its `customer_id` Bloom filter. {} of {} passed, \
         {:.1}%. The writer was asked for a false positive rate of 5% at 200 distinct values.*\n",
        rows.join("\n"),
        thousands(passed),
        thousands(tested),
        100.0 * passed as f64 / tested.max(1) as f64
    ))
}

use parquet_lab::prune::{Mechanisms, Op};
use parquet_lab::scan::{Query, Strategy};

fn strategy(
    size: SizeSource,
    prefetch: u64,
    connections: usize,
    gap: Option<u64>,
    whole: bool,
    m: Mechanisms,
) -> Strategy {
    Strategy {
        footer: FooterOptions { size, prefetch },
        connections,
        coalesce_gap: gap,
        whole_chunks: whole,
        mechanisms: m,
    }
}

fn ms_of(us: u64) -> String {
    let v = us as f64 / 1000.0;
    if v >= 10.0 {
        format!("{v:.0} ms")
    } else {
        format!("{v:.1} ms")
    }
}

/// Run a scan and return (requests, bytes fetched, time).
fn scan_cost(
    bytes: &[u8],
    q: &Query,
    s: Strategy,
    m: NetworkModel,
) -> Result<(usize, u64, u64, usize), String> {
    let r = parquet_lab::scan::scan(bytes, "data.parquet", q, s, m)?;
    Ok((
        r.requests.len(),
        r.bytes_fetched,
        r.elapsed_us,
        r.matches.len(),
    ))
}

fn stats_and_index() -> Mechanisms {
    Mechanisms {
        statistics: true,
        bloom: false,
        page_index: true,
    }
}

fn scan_strategies(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, SORTED)?;
    let columns = parquet_lab::report::flat_columns(&bytes)?;
    let q = Query {
        columns,
        condition: Some((0, Op::Eq, "431".into())),
    };
    let stats = Mechanisms {
        statistics: true,
        bloom: false,
        page_index: false,
    };
    let cases: [(&str, Strategy); 7] = [
        (
            "HEAD, trailer, footer; every column chunk",
            strategy(SizeSource::Head, 8, 1, None, true, Mechanisms::NONE),
        ),
        (
            "… skipping row groups by statistics",
            strategy(SizeSource::Head, 8, 1, None, true, stats),
        ),
        (
            "… and pages by the page index",
            strategy(SizeSource::Head, 8, 1, None, false, stats_and_index()),
        ),
        (
            "… with an 8 KiB suffix read for the footer",
            strategy(
                SizeSource::SuffixRange,
                8192,
                1,
                None,
                false,
                stats_and_index(),
            ),
        ),
        (
            "… merging ranges within 4 KiB",
            strategy(
                SizeSource::SuffixRange,
                8192,
                1,
                Some(4096),
                false,
                stats_and_index(),
            ),
        ),
        (
            "… on four connections, without merging",
            strategy(
                SizeSource::SuffixRange,
                8192,
                4,
                None,
                false,
                stats_and_index(),
            ),
        ),
        (
            "One suffix read of 64 KiB: the whole file",
            strategy(
                SizeSource::SuffixRange,
                65536,
                1,
                None,
                false,
                stats_and_index(),
            ),
        ),
    ];
    let model = NetworkModel::default();
    let mut rows = vec![
        "| Strategy | Requests | Bytes fetched | Time |".to_string(),
        "|---|--:|--:|--:|".to_string(),
    ];
    for (label, s) in cases {
        let (n, b, t, _) = scan_cost(&bytes, &q, s, model)?;
        rows.push(format!(
            "| {label} | {n} | {} | {} |",
            thousands(b),
            ms_of(t)
        ));
    }
    Ok(format!(
        "{}\n\n*`SELECT * WHERE order_id = 431`, run by the reader against `fixtures/{SORTED}` ({} \
         bytes) in the simulated object store: {} per request, {} once data flows. Every strategy \
         returns the same one row.*\n",
        rows.join("\n"),
        thousands(bytes.len() as u64),
        ms(model.latency_us),
        rate(model.bandwidth_bytes_per_sec)
    ))
}

fn scan_full(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, SORTED)?;
    let md = open_bytes(&bytes)?;
    let columns = parquet_lab::report::flat_columns(&bytes)?;
    let q = Query {
        columns,
        condition: None,
    };
    let model = NetworkModel::default();
    let head = |c, gap| strategy(SizeSource::Head, 8, c, gap, true, Mechanisms::NONE);
    let cases = [
        ("one request per column chunk", head(1, None)),
        (
            "one request per column chunk, four connections",
            head(4, None),
        ),
        (
            "one request per column chunk, sixteen connections",
            head(16, None),
        ),
        (
            "chunks that touch merged into one request",
            head(1, Some(0)),
        ),
    ];
    let mut rows = vec![
        "| `SELECT *`, no condition | Requests | Bytes fetched | Time |".to_string(),
        "|---|--:|--:|--:|".to_string(),
    ];
    for (label, s) in cases {
        let (n, b, t, _) = scan_cost(&bytes, &q, s, model)?;
        rows.push(format!(
            "| {label} | {n} | {} | {} |",
            thousands(b),
            ms_of(t)
        ));
    }
    let chunks: usize = md.row_groups.iter().map(|g| g.columns.len()).sum();
    Ok(format!(
        "{}\n\n*Computed by the reader against `fixtures/{SORTED}`, which has {chunks} column chunks, \
         with the footer found by `HEAD` and an exact tail read first. {} per request, {} once \
         data flows.*\n",
        rows.join("\n"),
        ms(model.latency_us),
        rate(model.bandwidth_bytes_per_sec)
    ))
}

fn scan_networks(root: &Path) -> Result<String, String> {
    let bytes = fixture(root, SORTED)?;
    let columns = parquet_lab::report::flat_columns(&bytes)?;
    let q = Query {
        columns,
        condition: Some((0, Op::Eq, "431".into())),
    };
    let pages = strategy(
        SizeSource::SuffixRange,
        8192,
        1,
        None,
        false,
        stats_and_index(),
    );
    let whole = strategy(
        SizeSource::SuffixRange,
        65536,
        1,
        None,
        false,
        stats_and_index(),
    );
    let nets = [
        ("same data centre", 1_000u64, 1_000_000_000u64),
        ("object store", 20_000, 100_000_000),
        ("slow link", 1_000, 1_000_000),
        ("far and slow", 100_000, 1_000_000),
    ];
    let mut rows = vec![
        "| Network | Latency | Bandwidth | Pages the plan needs | The whole file |".to_string(),
        "|---|--:|--:|--:|--:|".to_string(),
    ];
    for (label, latency_us, bw) in nets {
        let m = NetworkModel {
            latency_us,
            bandwidth_bytes_per_sec: bw,
        };
        let (n1, _, t1, _) = scan_cost(&bytes, &q, pages, m)?;
        let (_, _, t2, _) = scan_cost(&bytes, &q, whole, m)?;
        let mark = |a: u64, b: u64| if a <= b { "**" } else { "" };
        rows.push(format!(
            "| {label} | {} | {} | {}{} in {n1} requests{} | {}{}{} |",
            ms(latency_us),
            rate(bw),
            mark(t1, t2),
            ms_of(t1),
            mark(t1, t2),
            mark(t2, t1),
            ms_of(t2),
            mark(t2, t1)
        ));
    }
    Ok(format!(
        "{}\n\n*`SELECT * WHERE order_id = 431` against `fixtures/{SORTED}`, by the reader, under four \
         simulated networks. The faster strategy on each is in bold.*\n",
        rows.join("\n")
    ))
}

/// ch11's files, and what each changes from the baseline.
const WRITING: [(&str, &str); 7] = [
    ("writing-baseline.parquet", "the baseline"),
    ("writing-one-group.parquet", "one row group"),
    ("writing-small-groups.parquet", "row groups of 40 rows"),
    ("writing-by-country.parquet", "sorted by country"),
    ("writing-shuffled.parquet", "shuffled"),
    ("writing-plain.parquet", "no dictionary"),
    ("writing-no-index.parquet", "no page index"),
];

/// The reader for ch11's comparison: the footer found exactly, every skipping mechanism, only
/// ranges that touch merged, one connection. What it reads after the footer is then exactly
/// what the file's layout lets it skip, and nothing else.
fn exact() -> Strategy {
    strategy(SizeSource::Head, 8, 1, Some(0), false, Mechanisms::ALL)
}

/// Bytes and requests after the footer: the indexes and pages a query needed.
fn after_footer(bytes: &[u8], q: &Query) -> Result<(u64, usize), String> {
    let r = parquet_lab::scan::scan(bytes, "data.parquet", q, exact(), NetworkModel::default())?;
    let later: Vec<_> = r
        .requests
        .iter()
        .filter(|x| x.why.starts_with("read the indexes") || x.why.starts_with("read the pages"))
        .collect();
    Ok((later.iter().map(|x| x.bytes_returned).sum(), later.len()))
}

fn writing_files(root: &Path) -> Result<String, String> {
    let mut rows = vec![
        "| File | Change | File bytes | Footer bytes | Row groups | Data pages | `country` bytes | `order_id` bytes |"
            .to_string(),
        "|---|---|--:|--:|--:|--:|--:|--:|".to_string(),
    ];
    for (name, change) in WRITING {
        let bytes = fixture(root, name)?;
        let md = open_bytes(&bytes)?;
        let size = bytes.len() as u64;
        let last8: [u8; 8] = bytes[bytes.len() - 8..].try_into().unwrap();
        let footer = parse_trailer(last8, size)
            .map_err(|e| e.to_string())?
            .footer_length;
        let mut pages = 0;
        for rg in &md.row_groups {
            for c in &rg.columns {
                let r = c.byte_range();
                pages += parquet_lab::pages::walk_pages(
                    &bytes[r.start as usize..r.end as usize],
                    r.start,
                )
                .map_err(|e| e.to_string())?
                .iter()
                .filter(|p| p.page_type != "DICTIONARY_PAGE")
                .count();
            }
        }
        let column_bytes = |path: &str| -> u64 {
            md.row_groups
                .iter()
                .flat_map(|rg| &rg.columns)
                .filter(|c| c.dotted_path() == path)
                .map(|c| c.total_compressed_size as u64)
                .sum()
        };
        rows.push(format!(
            "| `{name}` | {change} | {} | {} | {} | {pages} | {} | {} |",
            thousands(size),
            thousands(footer as u64),
            md.row_groups.len(),
            thousands(column_bytes("country")),
            thousands(column_bytes("order_id")),
        ));
    }
    Ok(format!(
        "{}\n\n*Computed by the reader from the `fixtures/writing-*.parquet` files: the same 800 \
         orders, Snappy-compressed. Column bytes are summed over row groups and include page \
         headers.*\n",
        rows.join("\n")
    ))
}

fn writing_queries(root: &Path) -> Result<String, String> {
    // A label, and a condition as column, comparison and value.
    type Condition<'a> = Option<(usize, Op, &'a str)>;
    let queries: [(&str, Condition); 5] = [
        ("`order_id = 431`", Some((0, Op::Eq, "431"))),
        ("`country = 'FR'`", Some((3, Op::Eq, "FR"))),
        ("`status = 'refunded'`", Some((4, Op::Eq, "refunded"))),
        ("`amount_cents > 9900`", Some((5, Op::Gt, "9900"))),
        ("everything", None),
    ];
    let mut rows = vec![
        format!(
            "| File | {} |",
            queries.iter().map(|q| q.0).collect::<Vec<_>>().join(" | ")
        ),
        format!("|---|{}", "--:|".repeat(queries.len())),
    ];
    for (name, change) in WRITING {
        let bytes = fixture(root, name)?;
        let columns = parquet_lab::report::flat_columns(&bytes)?;
        let mut cells = Vec::new();
        for (_, cond) in &queries {
            let q = Query {
                columns: columns.clone(),
                condition: cond.map(|(c, op, v)| (c, op, v.to_string())),
            };
            let (b, n) = after_footer(&bytes, &q)?;
            cells.push(format!("{} in {n}", thousands(b)));
        }
        rows.push(format!("| {change} | {} |", cells.join(" | ")));
    }
    Ok(format!(
        "{}\n\n*`SELECT *` with each condition, run by the reader against each file. Each cell is \
         bytes and requests after the footer, which every query reads first. The reader \
         uses statistics, Bloom filters where written and the page index, and merges only ranges \
         that touch.*\n",
        rows.join("\n")
    ))
}

fn writing_lookups(root: &Path) -> Result<String, String> {
    let mut rows = vec![
        "| File | Row groups | `order_id`: row groups per lookup | `customer_id`: row groups per lookup |"
            .to_string(),
        "|---|--:|--:|--:|".to_string(),
    ];
    for (name, change) in WRITING {
        let bytes = fixture(root, name)?;
        let md = open_bytes(&bytes)?;
        let root_node = parquet_lab::schema::build(&md.schema).map_err(|e| e.to_string())?;
        let leaves = parquet_lab::schema::leaves(&root_node);
        let mut means = Vec::new();
        for path in ["order_id", "customer_id"] {
            let leaf = leaves
                .iter()
                .find(|l| l.dotted_path() == path)
                .ok_or("no column")?;
            // Each row group's bounds, from the footer, and every distinct value, decoded.
            let int = |b: &[u8]| i64::from_le_bytes(b.try_into().unwrap_or([0; 8]));
            let mut bounds = Vec::new();
            let mut values = Vec::new();
            for rg in &md.row_groups {
                let c = &rg.columns[leaf.column];
                let s = c.statistics.as_ref().ok_or("no statistics")?;
                bounds.push((
                    int(s.min_value.as_deref().unwrap_or(&[])),
                    int(s.max_value.as_deref().unwrap_or(&[])),
                ));
                let d =
                    parquet_lab::column::read_column(&bytes, c, leaf).map_err(|e| e.to_string())?;
                values.extend(
                    d.triples
                        .iter()
                        .filter_map(|t| t.value.as_ref())
                        .map(|v| int(&v.to_plain_bytes(leaf.physical_type))),
                );
            }
            values.sort();
            values.dedup();
            let total: usize = values
                .iter()
                .map(|&v| {
                    bounds
                        .iter()
                        .filter(|&&(lo, hi)| lo <= v && v <= hi)
                        .count()
                })
                .sum();
            means.push(total as f64 / values.len() as f64);
        }
        rows.push(format!(
            "| {change} | {} | {:.2} | {:.2} |",
            md.row_groups.len(),
            means[0],
            means[1]
        ));
    }
    Ok(format!(
        "{}\n\n*For every value in the column, the row groups whose footer bounds include it, \
         averaged. Computed by the reader from the `fixtures/writing-*.parquet` files.*\n",
        rows.join("\n")
    ))
}

const ENGINE_QUERY: &str = "SELECT country, count(*), avg(amount_cents) FROM orders WHERE order_id < 300 AND status = 'refunded' GROUP BY country ORDER BY country";

fn engine_stages(root: &Path) -> Result<String, String> {
    let name = "writing-baseline.parquet";
    let bytes = fixture(root, name)?;
    let a = parquet_lab::engine::run(&bytes, ENGINE_QUERY)?;
    let mut rows = vec![
        "| Stage | What it did | Rows in | Rows out |".to_string(),
        "|---|---|--:|--:|".to_string(),
    ];
    for s in &a.stages {
        rows.push(format!(
            "| {} | {} | {} | {} |",
            s.name,
            cell(&s.detail),
            thousands(s.rows_in as u64),
            thousands(s.rows_out as u64)
        ));
    }
    Ok(format!(
        "`{ENGINE_QUERY}`\n\n{}\n{}",
        rows.join("\n"),
        conditions(name, &bytes, None)
    ))
}

fn engine_answers(root: &Path) -> Result<String, String> {
    let text = std::fs::read_to_string(root.join("fixtures/queries.json"))
        .map_err(|e| format!("cannot read queries.json: {e}"))?;
    let queries = Json::parse(&text).map_err(|e| e.to_string())?;
    let mut rows = vec![
        "| Query | File | Rows | Row groups read | Same as pyarrow |".to_string(),
        "|---|---|--:|--:|---|".to_string(),
    ];
    for q in queries.as_array().ok_or("queries.json is not a list")? {
        let file = q.get("file").and_then(Json::as_str).ok_or("no file")?;
        if file == "table" {
            continue; // ch14's queries over the whole table
        }
        let sql = q.get("sql").and_then(Json::as_str).ok_or("no sql")?;
        let bytes = fixture(root, file)?;
        let a = parquet_lab::engine::run(&bytes, sql)?;
        let theirs = q
            .get("rows")
            .and_then(Json::as_array)
            .cloned()
            .unwrap_or_default();
        let same = a.rows.len() == theirs.len()
            && a.rows.iter().zip(&theirs).all(|(m, t)| {
                m.iter()
                    .zip(t.as_array().cloned().unwrap_or_default())
                    .all(|(m, t)| match (m.to_json(), &t) {
                        (Json::Float(x), Json::Float(y)) => (x - y).abs() < 1e-9,
                        (m, t) => m.to_json() == t.to_json(),
                    })
            });
        rows.push(format!(
            "| `{}` | `{file}` | {} | {} of {} | {} |",
            cell(sql),
            a.rows.len(),
            a.row_groups_read,
            a.row_groups,
            if same { "yes" } else { "**no**" }
        ));
    }
    Ok(format!(
        "{}\n\n*Every query in `fixtures/queries.json`, answered by the engine from the file's \
         bytes and compared with the answer pyarrow computed when the fixtures were written.*\n",
        rows.join("\n")
    ))
}

fn encryption_view(root: &Path, name: &str) -> Result<String, String> {
    let bytes = fixture(root, name)?;
    let r = parquet_lab::report::encryption(&bytes);
    let mut rows = vec![
        "| A reader without keys | What | Detail |".to_string(),
        "|---|---|---|".to_string(),
    ];
    for (key, label) in [("visible", "can see"), ("hidden", "cannot see")] {
        for item in arr(r.get(key)) {
            let mut detail = text_of(item.get("value"));
            if detail.len() > 90 {
                detail = format!("{}…", detail.chars().take(88).collect::<String>());
            }
            rows.push(format!(
                "| {label} | {} | {} |",
                cell(&text_of(item.get("what"))),
                cell(&detail)
            ));
        }
    }
    Ok(format!(
        "{}\n{}",
        rows.join("\n"),
        conditions(name, &bytes, None)
    ))
}

fn table_store(root: &Path) -> Result<MemoryStore, String> {
    let text = std::fs::read_to_string(root.join("fixtures/table.json"))
        .map_err(|e| format!("cannot read table.json: {e}"))?;
    let listing = Json::parse(&text).map_err(|e| e.to_string())?;
    let mut store = MemoryStore::new();
    for o in arr(listing.get("objects")) {
        let key = o
            .get("key")
            .and_then(Json::as_str)
            .ok_or("an object with no key")?;
        store.put(key, fixture(root, key)?);
    }
    Ok(store)
}

fn table_log(root: &Path) -> Result<String, String> {
    use parquet_lab::table::{read_log, LOG};
    let bytes = fixture(root, &format!("table/{LOG}"))?;
    let (files, _) = read_log(&String::from_utf8_lossy(&bytes))?;
    let stat = |s: &[(String, Json)]| {
        s.iter()
            .find(|(k, _)| k == "order_id")
            .map(|(_, v)| v.to_json())
            .unwrap_or_default()
    };
    let mut rows = vec![
        "| File | Partition | Bytes | Rows | `order_id` from | to |".to_string(),
        "|---|---|--:|--:|--:|--:|".to_string(),
    ];
    for f in &files {
        let s = f.stats.as_ref().ok_or("an add with no statistics")?;
        rows.push(format!(
            "| `{}` | {} | {} | {} | {} | {} |",
            f.key,
            f.partition
                .iter()
                .map(|(k, v)| format!("`{k}={v}`"))
                .collect::<Vec<_>>()
                .join(", "),
            thousands(f.size),
            thousands(s.num_records as u64),
            stat(&s.min),
            stat(&s.max)
        ));
    }
    Ok(format!(
        "{}\n\n*Every `add` action in `fixtures/table/{LOG}` ({} bytes), as the reader's \
         `table::read_log` reads it.*\n",
        rows.join("\n"),
        bytes.len()
    ))
}

fn table_discovery(root: &Path) -> Result<String, String> {
    use parquet_lab::table::{query, Discovery};
    let text = std::fs::read_to_string(root.join("fixtures/queries.json"))
        .map_err(|e| format!("cannot read queries.json: {e}"))?;
    let queries = Json::parse(&text).map_err(|e| e.to_string())?;
    let model = NetworkModel::default();
    let mut rows = vec![
        "| Query | Files found by | Files read | Requests | Bytes fetched | Time | Same as pyarrow |"
            .to_string(),
        "|---|---|--:|--:|--:|--:|---|".to_string(),
    ];
    let mut files = 0;
    for q in arr(Some(&queries))
        .iter()
        .filter(|q| q.get("file").and_then(Json::as_str) == Some("table"))
    {
        let sql = q.get("sql").and_then(Json::as_str).ok_or("no sql")?;
        let theirs = q.get("rows").map(Json::to_json).unwrap_or_default();
        for (d, label) in [
            (Discovery::List, "listing"),
            (Discovery::ListAndPrune, "listing, pruned by path"),
            (Discovery::Log, "the log"),
        ] {
            let a = query(table_store(root)?, "table/", sql, d, 4, model)?;
            files = a.files.len();
            let mine = Json::Arr(
                a.answer
                    .rows
                    .iter()
                    .map(|r| Json::Arr(r.iter().map(|v| v.to_json()).collect()))
                    .collect(),
            )
            .to_json();
            rows.push(format!(
                "| `{}` | {label} | {} of {} | {} | {} | {} | {} |",
                cell(sql),
                a.files.iter().filter(|f| f.read).count(),
                a.files.len(),
                a.requests.len(),
                thousands(a.bytes_fetched),
                ms_of(a.elapsed_us),
                if mine == theirs { "yes" } else { "**no**" }
            ));
        }
    }
    Ok(format!(
        "{}\n\n*Computed by the reader over the {files} data files of `fixtures/table/`, fetching \
         through the simulated store with four connections, {} ms before each request's first \
         byte and {} MB/s after it. The answers are compared with pyarrow's, from \
         `fixtures/queries.json`.*\n",
        rows.join("\n"),
        model.latency_us / 1000,
        model.bandwidth_bytes_per_sec / 1_000_000
    ))
}
