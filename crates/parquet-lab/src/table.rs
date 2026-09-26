//! A table of many files: finding them, ruling them out, and querying them together (ch14).
//!
//! A table is a directory of Parquet files in an object store. Before a query engine can read
//! any of them it must know which files there are, and it would rather not open the ones that
//! cannot hold an answer. There are two ways to find out:
//!
//! - **List the directory.** One `LIST` request returns every key under the table's prefix.
//!   Files laid out in Hive-style partitions carry values in their paths,
//!   `country=UK/part-0.parquet`, so a condition on `country` rules files out by name. Anything
//!   else about a file is in its footer, which costs requests to read.
//! - **Read the table's log.** Table formats such as Delta Lake and Apache Iceberg keep a list of
//!   the table's files, and with each file its partition values and statistics. One request for
//!   the log tells the reader which files exist and what each holds, before it opens any.
//!
//! This module does both, then fetches the files that survive, whole, and runs
//! [`crate::engine`] over them. It reads only what the log format needs here: `add` and
//! `remove` actions in one log file.

use crate::engine::{self, Answer, Value};
use crate::json::Json;
use crate::object_store::{
    GetRange, MemoryStore, NetworkModel, ObjectStore, Request, TracingStore,
};
use crate::prune::Op;

/// Where the log is, under the table's prefix. A real log has many versions; this reads one.
pub const LOG: &str = "_delta_log/00000000000000000000.json";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Discovery {
    /// `LIST`, and read every file.
    List,
    /// `LIST`, and rule out files by the partition values in their paths.
    ListAndPrune,
    /// Read the log, and rule out files by partition values and by the statistics it records.
    Log,
}

/// A file's statistics as a log records them: values as JSON, by column.
#[derive(Clone, Debug, PartialEq)]
pub struct FileStats {
    pub num_records: i64,
    pub min: Vec<(String, Json)>,
    pub max: Vec<(String, Json)>,
    pub null_count: Vec<(String, i64)>,
}

/// One file of the table, and what the plan decided about it.
#[derive(Clone, Debug, PartialEq)]
pub struct TableFile {
    pub key: String,
    pub partition: Vec<(String, String)>,
    pub size: u64,
    pub stats: Option<FileStats>,
    pub read: bool,
    pub why: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TableAnswer {
    pub answer: Answer,
    pub files: Vec<TableFile>,
    pub requests: Vec<Request>,
    pub elapsed_us: u64,
    pub bytes_fetched: u64,
}

/// The partition values in a Hive-style path: every `name=value` directory, in order. Values
/// are percent-encoded when they hold characters a path cannot, such as `/` or `=`.
pub fn partition_values(path: &str) -> Vec<(String, String)> {
    let dirs = path.split('/').collect::<Vec<_>>();
    dirs[..dirs.len().saturating_sub(1)]
        .iter()
        .filter_map(|d| d.split_once('='))
        .map(|(k, v)| (unescape(k), unescape(v)))
        .collect()
}

fn unescape(s: &str) -> String {
    let b = s.as_bytes();
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        match (b[i], b.get(i + 1..i + 3)) {
            (b'%', Some(h)) if h.iter().all(u8::is_ascii_hexdigit) => {
                out.push(
                    u8::from_str_radix(std::str::from_utf8(h).unwrap_or("0"), 16).unwrap_or(b'%'),
                );
                i += 3;
            }
            (c, _) => {
                out.push(c);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// The files a log says the table holds, with their partition values, sizes and statistics,
/// and the table's columns from its schema. Each line is one action; `remove` undoes an `add`.
pub fn read_log(text: &str) -> Result<(Vec<TableFile>, Vec<String>), String> {
    let mut files: Vec<TableFile> = Vec::new();
    let mut columns = Vec::new();
    for (n, line) in text
        .lines()
        .enumerate()
        .filter(|(_, l)| !l.trim().is_empty())
    {
        let action = Json::parse(line).map_err(|e| format!("log line {}: {e}", n + 1))?;
        if let Some(meta) = action.get("metaData") {
            let schema = meta
                .get("schemaString")
                .and_then(Json::as_str)
                .unwrap_or("{}");
            let schema = Json::parse(schema).map_err(|e| format!("the log's schema: {e}"))?;
            columns = schema
                .get("fields")
                .and_then(Json::as_array)
                .map(|f| {
                    f.iter()
                        .filter_map(|x| x.get("name").and_then(Json::as_str).map(str::to_string))
                        .collect()
                })
                .unwrap_or_default();
        }
        if let Some(remove) = action.get("remove") {
            let path = remove
                .get("path")
                .and_then(Json::as_str)
                .unwrap_or_default();
            files.retain(|f| f.key != path);
        }
        let Some(add) = action.get("add") else {
            continue;
        };
        let key = add
            .get("path")
            .and_then(Json::as_str)
            .ok_or(format!("log line {}: an add with no path", n + 1))?;
        let partition = match add.get("partitionValues") {
            Some(Json::Obj(kv)) => kv
                .iter()
                .map(|(k, v)| (k.clone(), v.as_str().unwrap_or_default().to_string()))
                .collect(),
            _ => Vec::new(),
        };
        // The statistics are themselves JSON, stored as a string.
        let stats = add
            .get("stats")
            .and_then(Json::as_str)
            .and_then(|s| Json::parse(s).ok())
            .map(|s| {
                let pairs = |k: &str| match s.get(k) {
                    Some(Json::Obj(kv)) => kv.clone(),
                    _ => Vec::new(),
                };
                FileStats {
                    num_records: s.get("numRecords").and_then(Json::as_i64).unwrap_or(0),
                    min: pairs("minValues"),
                    max: pairs("maxValues"),
                    null_count: pairs("nullCount")
                        .into_iter()
                        .map(|(k, v)| (k, v.as_i64().unwrap_or(0)))
                        .collect(),
                }
            });
        files.push(TableFile {
            key: key.to_string(),
            partition,
            size: add.get("size").and_then(Json::as_u64).unwrap_or(0),
            stats,
            read: true,
            why: String::new(),
        });
    }
    Ok((files, columns))
}

/// A literal as the engine's value: a number if it reads as one, text otherwise.
fn literal(text: &str) -> Value {
    text.parse::<i64>()
        .map(Value::Int)
        .or_else(|_| text.parse::<f64>().map(Value::Float))
        .unwrap_or_else(|_| Value::Str(text.to_string()))
}

fn json_value(j: &Json) -> Value {
    match j {
        Json::Int(v) => Value::Int(*v),
        Json::UInt(v) => Value::Int(*v as i64),
        Json::Float(v) => Value::Float(*v),
        Json::Str(s) => Value::Str(s.clone()),
        Json::Bool(b) => Value::Bool(*b),
        _ => Value::Null,
    }
}

/// Whether a value of one kind can be compared with another: numbers with numbers, text with
/// text. A log's statistics are JSON, and a comparison across kinds proves nothing.
fn comparable(a: &Value, b: &Value) -> bool {
    matches!(
        (a, b),
        (
            Value::Int(_) | Value::Float(_),
            Value::Int(_) | Value::Float(_)
        ) | (Value::Str(_), Value::Str(_))
    )
}

/// Why a condition rules a file out, if it does: from its partition values, then from the
/// statistics a log records for it.
fn rules_out(file: &TableFile, c: &engine::Condition, use_stats: bool) -> Option<String> {
    use std::cmp::Ordering::*;
    let v = literal(&c.value);
    if let Some((_, p)) = file.partition.iter().find(|(k, _)| k == &c.column) {
        let ok = match c.op {
            Op::IsNull => false,
            Op::IsNotNull => true,
            op => op.matches(Some(p.as_bytes().cmp(c.value.as_bytes()))),
        };
        return (!ok).then(|| format!("its partition is {}={p}", c.column));
    }
    let s = file.stats.as_ref().filter(|_| use_stats)?;
    let nulls = s
        .null_count
        .iter()
        .find(|(k, _)| k == &c.column)
        .map(|(_, n)| *n);
    match c.op {
        Op::IsNull => {
            return (nulls == Some(0)).then(|| format!("the log counts no nulls in {}", c.column))
        }
        Op::IsNotNull => {
            return (nulls == Some(s.num_records))
                .then(|| format!("the log says {} is always null", c.column))
        }
        _ => {}
    }
    let min = s
        .min
        .iter()
        .find(|(k, _)| k == &c.column)
        .map(|(_, j)| json_value(j))?;
    let max = s
        .max
        .iter()
        .find(|(k, _)| k == &c.column)
        .map(|(_, j)| json_value(j))?;
    if !comparable(&v, &min) || !comparable(&v, &max) {
        return None;
    }
    let (lo, hi) = (v.order(&min), v.order(&max));
    let out = match c.op {
        Op::Eq => lo == Less || hi == Greater,
        Op::NotEq => lo == Equal && hi == Equal,
        Op::Lt => lo != Greater,
        Op::LtEq => lo == Less,
        Op::Gt => hi != Less,
        Op::GtEq => hi == Greater,
        Op::IsNull | Op::IsNotNull => false,
    };
    let show = |x: &Value| x.to_json().to_json();
    out.then(|| {
        format!(
            "the log says {} runs from {} to {}",
            c.column,
            show(&min),
            show(&max)
        )
    })
}

/// Answer `sql` from the table under `prefix` in `store`.
pub fn query(
    store: MemoryStore,
    prefix: &str,
    sql: &str,
    discovery: Discovery,
    connections: usize,
    model: NetworkModel,
) -> Result<TableAnswer, String> {
    let q = engine::parse(sql)?;
    let mut s = TracingStore::with_connections(store, model, connections);
    let (mut files, log_columns) = match discovery {
        Discovery::List | Discovery::ListAndPrune => {
            let keys = s.list(prefix, "list the table's files");
            let files = keys
                .into_iter()
                .filter(|(k, _)| k.ends_with(".parquet"))
                .map(|(k, size)| {
                    let key = k[prefix.len()..].to_string();
                    TableFile {
                        partition: partition_values(&key),
                        key,
                        size,
                        stats: None,
                        read: true,
                        why: String::new(),
                    }
                })
                .collect();
            (files, Vec::new())
        }
        Discovery::Log => {
            let got = s
                .get(
                    &format!("{prefix}{LOG}"),
                    GetRange::All,
                    "read the table's log",
                )
                .map_err(|e| e.to_string())?;
            read_log(&String::from_utf8_lossy(&got.bytes))?
        }
    };
    // Rule files out before reading any: by path, and with a log by its statistics too.
    for f in &mut files {
        if discovery == Discovery::List {
            f.why = "read: listing gives no reason to skip".into();
            continue;
        }
        match q
            .conditions
            .iter()
            .find_map(|c| rules_out(f, c, discovery == Discovery::Log).map(|w| (c, w)))
        {
            Some((c, why)) => {
                f.read = false;
                f.why = format!(
                    "skipped: {} {} {}, and {why}",
                    c.column,
                    c.op.symbol(),
                    c.value
                );
            }
            None => f.why = "read: nothing rules it out".into(),
        }
    }
    // Fetch the survivors, whole: they are small, and ch10 found one request best for small files.
    s.next_phase();
    let mut fetched = Vec::new();
    for f in files.iter().filter(|f| f.read) {
        let got = s
            .get(
                &format!("{prefix}{}", f.key),
                GetRange::All,
                "read a file the plan kept",
            )
            .map_err(|e| e.to_string())?;
        fetched.push((f.key.clone(), f.partition.clone(), got.bytes));
    }
    let answer = if fetched.is_empty() {
        let mut columns = log_columns;
        if columns.is_empty() {
            columns = q
                .items
                .iter()
                .filter_map(|i| match i {
                    engine::Item::Column(c) | engine::Item::Aggregate(_, Some(c)) => {
                        Some(c.clone())
                    }
                    _ => None,
                })
                .chain(q.conditions.iter().map(|c| c.column.clone()))
                .chain(q.group_by.iter().cloned())
                .collect();
        }
        engine::run_empty(sql, &columns, "every file was ruled out before reading")?
    } else {
        let sources: Vec<engine::Source> = fetched
            .iter()
            .map(|(key, partition, bytes)| engine::Source {
                name: key.clone(),
                bytes,
                partition: partition.clone(),
            })
            .collect();
        engine::run_sources(&sources, sql)?
    };
    Ok(TableAnswer {
        answer,
        files,
        elapsed_us: s.elapsed_us(),
        bytes_fetched: s.bytes_returned(),
        requests: s.requests,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paths_carry_partition_values() {
        assert_eq!(
            partition_values("country=UK/part-0.parquet"),
            vec![("country".into(), "UK".into())]
        );
        assert_eq!(
            partition_values("year=2026/month=01/f.parquet"),
            vec![
                ("year".into(), "2026".into()),
                ("month".into(), "01".into())
            ]
        );
        assert_eq!(
            partition_values("city=S%C3%A3o%20Paulo/f.parquet")[0].1,
            "São Paulo"
        );
        assert!(partition_values("part-0.parquet").is_empty());
    }
}
