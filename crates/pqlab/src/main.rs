//! `pqlab`: the book's Parquet reader on the command line.
//!
//! ```text
//! pqlab inspect FILE                 the structure of a file, as an indented tree
//! pqlab footer FILE [options]        open FILE through the simulated object store
//! pqlab structure FILE               the structure, as JSON
//! pqlab schema FILE                  the schema: flat, rebuilt, and read through logical types
//! pqlab interpret FILE OFFSET        every reading of the bytes at OFFSET, as JSON
//! pqlab layouts --columns 2,3 [--row N]
//!                                    ch01's row and column layouts, queried, as JSON
//! pqlab figures [--out DIR] [--check]
//!                                    write the book's generated fragments, or check them
//! ```
//!
//! `footer` takes `--size head|known|suffix`, `--prefetch BYTES`, `--latency-us N`,
//! `--bandwidth BYTES_PER_SEC` and `--json`.
//!
//! Every subcommand prints what `parquet_lab::report` returns: the same JSON the browser gets
//! from the WebAssembly build.

mod figures;

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use parquet_lab::json::Json;
use parquet_lab::object_store::NetworkModel;
use parquet_lab::reader::{FooterOptions, SizeSource};
use parquet_lab::report;

const USAGE: &str = "usage:
  pqlab inspect FILE
  pqlab footer FILE [--size head|known|suffix] [--prefetch BYTES] [--latency-us N] [--bandwidth BYTES_PER_SEC] [--json]
  pqlab structure FILE
  pqlab schema FILE
  pqlab interpret FILE OFFSET
  pqlab layouts --columns 2,3 [--row N] [--latency-us N] [--bandwidth BYTES_PER_SEC]
  pqlab figures [--out DIR] [--check]";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(code) => code,
        Err(message) => {
            eprintln!("pqlab: {message}");
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
    }
}

fn read(path: &str) -> Result<Vec<u8>, String> {
    std::fs::read(path).map_err(|e| format!("cannot read {path}: {e}"))
}

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

fn run(args: &[String]) -> Result<ExitCode, String> {
    let command = args.first().ok_or("no command given")?.as_str();
    let file = || args.get(1).ok_or(format!("{command} needs a FILE"));
    match command {
        "schema" => {
            println!("{}", report::schema(&read(file()?)?).to_json_pretty());
        }
        "structure" => {
            println!("{}", report::structure(&read(file()?)?).to_json_pretty());
        }
        "interpret" => {
            let offset: u64 = args
                .get(2)
                .ok_or("interpret needs an OFFSET")?
                .parse()
                .map_err(|_| "OFFSET must be a whole number")?;
            println!(
                "{}",
                report::interpret(&read(file()?)?, offset).to_json_pretty()
            );
        }
        "inspect" => {
            let json = report::structure(&read(file()?)?);
            if json.get("ok") != Some(&Json::Bool(true)) {
                return Err(json.get("error").map(|e| e.to_json()).unwrap_or_default());
            }
            print_tree(json.get("tree").unwrap(), 0);
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
                println!("{}", json.to_json_pretty());
            } else {
                print_footer(&json);
            }
            if json.get("ok") != Some(&Json::Bool(true)) {
                return Ok(ExitCode::from(1));
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
            println!("{}", report::layouts(mask, row, model).to_json_pretty());
        }
        "figures" => {
            let out = PathBuf::from(flag(args, "--out").unwrap_or("chapters/_generated"));
            let check = args.iter().any(|a| a == "--check");
            return figures::run(Path::new("."), &out, check);
        }
        other => return Err(format!("unknown command {other:?}")),
    }
    Ok(ExitCode::SUCCESS)
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

fn print_tree(node: &Json, depth: usize) {
    let value = text(node.get("value"));
    println!(
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
            print_tree(c, depth + 1);
        }
    }
}

fn print_footer(j: &Json) {
    if let Some(Json::Arr(requests)) = j.get("requests") {
        for r in requests {
            println!(
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
        println!(
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
        println!("error: {}", text(j.get("error")));
    }
}
