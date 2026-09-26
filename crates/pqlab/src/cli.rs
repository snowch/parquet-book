//! `pqlab`'s commands, as a library: the binary runs them on files from disk, and the browser
//! runs them on the files the page has loaded, through `parquet-lab-wasm`, so a command the book
//! prints runs in the page and prints what it prints at a desk.

use std::fmt::Write;
use std::path::{Path, PathBuf};

use parquet_lab::json::Json;
use parquet_lab::object_store::NetworkModel;
use parquet_lab::reader::{FooterOptions, SizeSource};
use parquet_lab::report;

/// `writeln!` into the output. Writing to a `String` cannot fail.
macro_rules! out {
    ($out:expr, $($t:tt)*) => {{
        let _ = writeln!($out, $($t)*);
    }};
}

pub const USAGE: &str = "usage:
  pqlab inspect FILE
  pqlab footer FILE [--size head|known|suffix] [--prefetch BYTES] [--latency-us N] [--bandwidth BYTES_PER_SEC] [--json]
  pqlab structure FILE
  pqlab schema FILE
  pqlab levels FILE COLUMN
  pqlab encodings FILE COLUMN
  pqlab pages FILE COLUMN
  pqlab table LISTING SQL [--discovery list|prune|log] [--connections N]
  pqlab encryption FILE
  pqlab query FILE SQL
  pqlab scan FILE [--where COLUMN OP VALUE] [--columns 0,2] [--size head|suffix] [--prefetch N] [--connections N] [--gap BYTES] [--chunks] [--use statistics,bloom,page-index] [--latency-us N] [--bandwidth N]
  pqlab skipping FILE COLUMN OP [VALUE] [--use statistics,bloom,page-index]
  pqlab statistics FILE ROW_GROUP COLUMN
  pqlab compression FILE COLUMN [PAGE]
  pqlab interpret FILE OFFSET
  pqlab layouts --columns 2,3 [--row N] [--latency-us N] [--bandwidth BYTES_PER_SEC]
  pqlab figures [--out DIR] [--check]";

fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1))
        .map(String::as_str)
}

fn number(args: &[String], name: &str, default: u64) -> Result<u64, String> {
    match flag(args, name) {
        None => Ok(default),
        Some(v) => v
            .parse()
            .map_err(|_| format!("{name} wants a whole number, not {v:?}")),
    }
}

/// Run `pqlab ARGS` (without the program name), reading the files it names through `read` and
/// writing what it prints to `out`. Returns the exit status, or a usage error.
///
/// `figures` is not here: it writes files, and only the binary can.
pub fn run(
    args: &[String],
    read: &dyn Fn(&str) -> Result<Vec<u8>, String>,
    out: &mut String,
) -> Result<u8, String> {
    let command = args.first().ok_or("no command given")?.as_str();
    let file = || args.get(1).ok_or(format!("{command} needs a FILE"));
    match command {
        "table" => {
            use parquet_lab::table::Discovery;
            let listing_path = PathBuf::from(file()?);
            let listing = Json::parse(&String::from_utf8_lossy(&read(
                &listing_path.display().to_string(),
            )?))
            .map_err(|e| format!("{}: {e}", listing_path.display()))?;
            let dir = listing_path.parent().unwrap_or(Path::new("."));
            let mut objects = Vec::new();
            for o in listing
                .get("objects")
                .and_then(Json::as_array)
                .ok_or("the listing has no objects")?
            {
                let key = o
                    .get("key")
                    .and_then(Json::as_str)
                    .ok_or("an object with no key")?;
                objects.push((key.to_string(), read(&dir.join(key).display().to_string())?));
            }
            let sql = args.get(2).ok_or("table needs SQL, in quotes")?;
            let (mut discovery, mut connections) = (Discovery::Log, 4);
            let mut i = 3;
            while let Some(a) = args.get(i) {
                match a.as_str() {
                    "--discovery" => {
                        discovery = match args.get(i + 1).map(String::as_str) {
                            Some("list") => Discovery::List,
                            Some("prune") => Discovery::ListAndPrune,
                            Some("log") => Discovery::Log,
                            _ => return Err("--discovery is list, prune or log".into()),
                        }
                    }
                    "--connections" => {
                        connections = args
                            .get(i + 1)
                            .and_then(|n| n.parse().ok())
                            .ok_or("--connections needs a number")?
                    }
                    other => return Err(format!("unknown option {other}")),
                }
                i += 2;
            }
            out!(
                out,
                "{}",
                report::table(
                    objects,
                    sql,
                    discovery,
                    connections,
                    NetworkModel::default()
                )
                .to_json_pretty()
            );
        }
        "encryption" => out!(
            out,
            "{}",
            report::encryption(&read(file()?)?).to_json_pretty()
        ),
        "query" => {
            let sql = args.get(2).ok_or("query needs SQL, in quotes")?;
            out!(
                out,
                "{}",
                report::query(&read(file()?)?, sql).to_json_pretty()
            );
        }
        "scan" => {
            use parquet_lab::prune::{Mechanisms, Op};
            use parquet_lab::scan::{Query, Strategy};
            let bytes = read(file()?)?;
            let mut columns = report::flat_columns(&bytes)?;
            let mut condition = None;
            let mut strategy = Strategy {
                footer: FooterOptions::default(),
                connections: 1,
                coalesce_gap: None,
                whole_chunks: false,
                mechanisms: Mechanisms::ALL,
            };
            let mut model = NetworkModel::default();
            let mut i = 2;
            let number = |v: Option<&String>, what: &str| -> Result<u64, String> {
                v.ok_or(format!("{what} needs a number"))?
                    .parse()
                    .map_err(|_| format!("{what} needs a whole number"))
            };
            while let Some(a) = args.get(i) {
                match a.as_str() {
                    "--where" => {
                        let c = number(args.get(i + 1), "--where")? as usize;
                        let op = Op::parse(args.get(i + 2).ok_or("--where needs an OP")?)?;
                        let takes_value = !matches!(op, Op::IsNull | Op::IsNotNull);
                        let v = if takes_value {
                            args.get(i + 3).ok_or("--where needs a VALUE")?.clone()
                        } else {
                            String::new()
                        };
                        condition = Some((c, op, v));
                        i += if takes_value { 4 } else { 3 };
                        continue;
                    }
                    "--columns" => {
                        columns = args
                            .get(i + 1)
                            .ok_or("--columns needs a list")?
                            .split(',')
                            .map(|c| c.parse().map_err(|_| format!("bad column {c}")))
                            .collect::<Result<_, String>>()?;
                    }
                    "--size" => {
                        strategy.footer.size = match args.get(i + 1).map(String::as_str) {
                            Some("head") => SizeSource::Head,
                            Some("suffix") => SizeSource::SuffixRange,
                            _ => return Err("--size is head or suffix".into()),
                        };
                    }
                    "--prefetch" => strategy.footer.prefetch = number(args.get(i + 1), a)?,
                    "--connections" => strategy.connections = number(args.get(i + 1), a)? as usize,
                    "--gap" => strategy.coalesce_gap = Some(number(args.get(i + 1), a)?),
                    "--latency-us" => model.latency_us = number(args.get(i + 1), a)?,
                    "--bandwidth" => model.bandwidth_bytes_per_sec = number(args.get(i + 1), a)?,
                    "--chunks" => {
                        strategy.whole_chunks = true;
                        i += 1;
                        continue;
                    }
                    "--use" => {
                        let list = args.get(i + 1).ok_or("--use needs a list")?;
                        strategy.mechanisms = Mechanisms::NONE;
                        for m in list.split(',').filter(|m| !m.is_empty()) {
                            match m {
                                "statistics" => strategy.mechanisms.statistics = true,
                                "bloom" => strategy.mechanisms.bloom = true,
                                "page-index" => strategy.mechanisms.page_index = true,
                                other => return Err(format!("unknown mechanism {other}")),
                            }
                        }
                    }
                    other => return Err(format!("unknown option {other}")),
                }
                i += 2;
            }
            let q = Query { columns, condition };
            out!(
                out,
                "{}",
                report::scan(&bytes, &q, strategy, model).to_json_pretty()
            );
        }
        "skipping" => {
            let column: usize = args
                .get(2)
                .ok_or("skipping needs a COLUMN number")?
                .parse()
                .map_err(|_| "COLUMN must be a whole number")?;
            let op = args
                .get(3)
                .ok_or("skipping needs an OP, such as = or \"is null\"")?;
            let mut value = "";
            let mut mechanisms = 7;
            let mut i = 4;
            while let Some(a) = args.get(i) {
                if a == "--use" {
                    let list = args.get(i + 1).ok_or("--use needs a list")?;
                    mechanisms = 0;
                    for m in list.split(',').filter(|m| !m.is_empty()) {
                        mechanisms |= match m {
                            "statistics" => 1,
                            "bloom" => 2,
                            "page-index" => 4,
                            other => return Err(format!("unknown mechanism {other}")),
                        };
                    }
                    i += 2;
                } else {
                    value = a;
                    i += 1;
                }
            }
            out!(
                out,
                "{}",
                report::skipping(&read(file()?)?, column, op, value, mechanisms).to_json_pretty()
            );
        }
        "statistics" => {
            let number = |i: usize, what: &str| -> Result<usize, String> {
                args.get(i)
                    .ok_or(format!("statistics needs a {what} number"))?
                    .parse()
                    .map_err(|_| format!("{what} must be a whole number"))
            };
            let (row_group, column) = (number(2, "ROW_GROUP")?, number(3, "COLUMN")?);
            out!(
                out,
                "{}",
                report::statistics(&read(file()?)?, row_group, column).to_json_pretty()
            );
        }
        "compression" => {
            let column: usize = args
                .get(2)
                .ok_or("compression needs a COLUMN number")?
                .parse()
                .map_err(|_| "COLUMN must be a whole number")?;
            let page = match args.get(3) {
                Some(p) => Some(p.parse().map_err(|_| "PAGE must be a whole number")?),
                None => None,
            };
            out!(
                out,
                "{}",
                report::compression(&read(file()?)?, column, page).to_json_pretty()
            );
        }
        "pages" => {
            let column: usize = args
                .get(2)
                .ok_or("pages needs a COLUMN number")?
                .parse()
                .map_err(|_| "COLUMN must be a whole number")?;
            out!(
                out,
                "{}",
                report::pages(&read(file()?)?, column).to_json_pretty()
            );
        }
        "encodings" => {
            let column: usize = args
                .get(2)
                .ok_or("encodings needs a COLUMN number")?
                .parse()
                .map_err(|_| "COLUMN must be a whole number")?;
            out!(
                out,
                "{}",
                report::encodings(&read(file()?)?, column).to_json_pretty()
            );
        }
        "levels" => {
            let column: usize = args
                .get(2)
                .ok_or("levels needs a COLUMN number")?
                .parse()
                .map_err(|_| "COLUMN must be a whole number")?;
            out!(
                out,
                "{}",
                report::levels(&read(file()?)?, column).to_json_pretty()
            );
        }
        "schema" => {
            out!(out, "{}", report::schema(&read(file()?)?).to_json_pretty());
        }
        "structure" => {
            out!(
                out,
                "{}",
                report::structure(&read(file()?)?).to_json_pretty()
            );
        }
        "interpret" => {
            let offset: u64 = args
                .get(2)
                .ok_or("interpret needs an OFFSET")?
                .parse()
                .map_err(|_| "OFFSET must be a whole number")?;
            out!(
                out,
                "{}",
                report::interpret(&read(file()?)?, offset).to_json_pretty()
            );
        }
        "inspect" => {
            let json = report::structure(&read(file()?)?);
            if json.get("ok") != Some(&Json::Bool(true)) {
                return Err(json.get("error").map(|e| e.to_json()).unwrap_or_default());
            }
            print_tree(out, json.get("tree").unwrap(), 0);
        }
        "footer" => {
            let path = file()?;
            let bytes = read(path)?;
            let defaults = NetworkModel::default();
            let size = match flag(args, "--size").unwrap_or("head") {
                "head" => SizeSource::Head,
                "known" => SizeSource::Known(bytes.len() as u64),
                "suffix" => SizeSource::SuffixRange,
                other => return Err(format!("--size is head, known or suffix, not {other:?}")),
            };
            let options = FooterOptions {
                size,
                prefetch: number(args, "--prefetch", 8)?,
            };
            let model = NetworkModel {
                latency_us: number(args, "--latency-us", defaults.latency_us)?,
                bandwidth_bytes_per_sec: number(
                    args,
                    "--bandwidth",
                    defaults.bandwidth_bytes_per_sec,
                )?,
            };
            let key = Path::new(path)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_else(|| path.to_string());
            let json = report::footer_lab(&bytes, &key, options, model);
            if args.iter().any(|a| a == "--json") {
                out!(out, "{}", json.to_json_pretty());
            } else {
                print_footer(out, &json);
            }
            if json.get("ok") != Some(&Json::Bool(true)) {
                return Ok(1);
            }
        }
        "layouts" => {
            let mut mask = 0u32;
            for c in flag(args, "--columns")
                .unwrap_or("")
                .split(',')
                .filter(|c| !c.is_empty())
            {
                let c: u32 = c
                    .parse()
                    .map_err(|_| format!("--columns wants numbers, not {c:?}"))?;
                mask |= 1 << c;
            }
            let row = match flag(args, "--row") {
                None => None,
                Some(r) => Some(
                    r.parse::<usize>()
                        .map_err(|_| format!("--row wants a number, not {r:?}"))?,
                ),
            };
            let defaults = NetworkModel::default();
            let model = NetworkModel {
                latency_us: number(args, "--latency-us", defaults.latency_us)?,
                bandwidth_bytes_per_sec: number(
                    args,
                    "--bandwidth",
                    defaults.bandwidth_bytes_per_sec,
                )?,
            };
            out!(
                out,
                "{}",
                report::layouts(mask, row, model).to_json_pretty()
            );
        }
        other => return Err(format!("unknown command {other:?}")),
    }
    Ok(0)
}

fn text(j: Option<&Json>) -> String {
    match j {
        Some(Json::Str(s)) => s.clone(),
        Some(Json::Null) | None => String::new(),
        Some(other) => other.to_json(),
    }
}

fn span(j: Option<&Json>) -> String {
    match j {
        Some(Json::Arr(v)) if v.len() == 2 => format!("[{}, {})", v[0].to_json(), v[1].to_json()),
        _ => "-".into(),
    }
}

fn print_tree(out: &mut String, node: &Json, depth: usize) {
    let value = text(node.get("value"));
    out!(
        out,
        "{:indent$}{} {}{}",
        "",
        text(node.get("label")),
        span(node.get("span")),
        if value.is_empty() {
            String::new()
        } else {
            format!("  {value}")
        },
        indent = depth * 2
    );
    if let Some(Json::Arr(children)) = node.get("children") {
        for c in children {
            print_tree(out, c, depth + 1);
        }
    }
}

fn print_footer(out: &mut String, j: &Json) {
    if let Some(Json::Arr(requests)) = j.get("requests") {
        for r in requests {
            out!(
                out,
                "{:>2}. {:<4} {:<22} {:>6} B  {:>8.1} ms  {}",
                text(r.get("seq")),
                text(r.get("method")),
                text(r.get("range")),
                text(r.get("bytes")),
                match r.get("end_us") {
                    Some(Json::UInt(e)) => *e as f64 / 1000.0,
                    _ => 0.0,
                },
                text(r.get("why")),
            );
        }
    }
    if j.get("ok") == Some(&Json::Bool(true)) {
        let t = j.get("trailer").unwrap();
        out!(
            out,
            "footer length {} → footer {} ({}prefetched)",
            text(t.get("footer_length")),
            span(j.get("footer").and_then(|f| f.get("span"))),
            if j.get("footer").and_then(|f| f.get("prefetched")) == Some(&Json::Bool(true)) {
                ""
            } else {
                "not "
            }
        );
    } else {
        out!(out, "error: {}", text(j.get("error")));
    }
}
