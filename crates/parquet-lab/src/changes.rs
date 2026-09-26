//! Changing a table: finding one row, deleting rows, and compacting (ch15).
//!
//! Parquet files are written once. A table made of them still changes, and a table format such
//! as Apache Iceberg or Delta Lake records each version as a *snapshot*: the list of files that
//! make it up. This module reads a table through its snapshots, and measures what each way of
//! changing it costs:
//!
//! - **Finding one row.** A reader opens the files whose statistics could hold the key, then
//!   their footers, indexes and pages: a chain of requests, each waiting for the last.
//! - **Deleting a row by copy-on-write.** The file that holds the row is rewritten without it.
//!   Reads stay as cheap as before; the write costs a whole file.
//! - **Deleting a row by merge-on-read.** A small *position delete file* names the row's file
//!   and position. The write is cheap; every later read of that file must fetch the delete file
//!   and take the row out.
//! - **Compaction.** Small files and files with deletes are rewritten into a few whole ones,
//!   which costs a read and a write of everything they hold, and makes later reads cheap again.
//!
//! The snapshots are a JSON file, `_snapshots.json`, under the table's prefix. It records for
//! each data file its row count, its size and the range of its `order_id` column, and for each
//! delete file the data file it names: what an Iceberg manifest records, in the plainest form.

use crate::engine::{self, Value};
use crate::json::Json;
use crate::object_store::{
    GetRange, MemoryStore, NetworkModel, ObjectStore, Request, TracingStore,
};
use crate::prune::{Mechanisms, Op};
use crate::reader::{FooterOptions, SizeSource};
use crate::scan::{self, Query, Strategy};

/// Where the snapshots are, under the table's prefix.
pub const SNAPSHOTS: &str = "_snapshots.json";

/// The column the table is keyed on: a lookup finds one value of it.
pub const KEY: &str = "order_id";

#[derive(Clone, Debug, PartialEq)]
pub struct DataFile {
    pub path: String,
    pub record_count: i64,
    pub file_size: u64,
    /// The smallest and largest `order_id` in the file.
    pub min_key: i64,
    pub max_key: i64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct DeleteFile {
    pub path: String,
    pub record_count: i64,
    pub file_size: u64,
    /// The one data file whose rows it deletes.
    pub data_file: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Snapshot {
    pub id: String,
    pub summary: String,
    pub data_files: Vec<DataFile>,
    pub delete_files: Vec<DeleteFile>,
}

impl Snapshot {
    /// The delete files that name `data_file`.
    pub fn deletes_for(&self, data_file: &str) -> Vec<&DeleteFile> {
        self.delete_files
            .iter()
            .filter(|d| d.data_file == data_file)
            .collect()
    }

    /// The rows a data file still holds, by the snapshot's own counts: its records, less the
    /// positions its delete files name.
    pub fn live_rows(&self, f: &DataFile) -> i64 {
        f.record_count
            - self
                .deletes_for(&f.path)
                .iter()
                .map(|d| d.record_count)
                .sum::<i64>()
    }
}

/// Every snapshot in a `_snapshots.json`, oldest first.
pub fn read_snapshots(text: &str) -> Result<Vec<Snapshot>, String> {
    let j = Json::parse(text).map_err(|e| format!("{SNAPSHOTS}: {e}"))?;
    let list = |v: &Json, k: &str| v.get(k).and_then(Json::as_array).cloned();
    let text = |v: &Json, k: &str| {
        v.get(k)
            .and_then(Json::as_str)
            .map(str::to_string)
            .ok_or(format!("{SNAPSHOTS}: no {k}"))
    };
    let int = |v: &Json, k: &str| {
        v.get(k)
            .and_then(Json::as_i64)
            .ok_or(format!("{SNAPSHOTS}: no {k}"))
    };
    list(&j, "snapshots")
        .ok_or(format!("{SNAPSHOTS}: no snapshots"))?
        .iter()
        .map(|s| {
            let data_files = list(s, "data_files")
                .unwrap_or_default()
                .iter()
                .map(|f| {
                    let range = list(f, KEY).unwrap_or_default();
                    let bound = |i: usize| {
                        range
                            .get(i)
                            .and_then(Json::as_i64)
                            .ok_or(format!("{SNAPSHOTS}: a data file with no {KEY} range"))
                    };
                    Ok(DataFile {
                        path: text(f, "path")?,
                        record_count: int(f, "record_count")?,
                        file_size: int(f, "file_size")? as u64,
                        min_key: bound(0)?,
                        max_key: bound(1)?,
                    })
                })
                .collect::<Result<_, String>>()?;
            let delete_files = list(s, "delete_files")
                .unwrap_or_default()
                .iter()
                .map(|f| {
                    Ok(DeleteFile {
                        path: text(f, "path")?,
                        record_count: int(f, "record_count")?,
                        file_size: int(f, "file_size")? as u64,
                        data_file: text(f, "data_file")?,
                    })
                })
                .collect::<Result<_, String>>()?;
            Ok(Snapshot {
                id: text(s, "id")?,
                summary: text(s, "summary")?,
                data_files,
                delete_files,
            })
        })
        .collect()
}

/// The rows of a position delete file: which data file, and which position in it, counting
/// from 0. Its columns are `file_path` and `pos`, as Iceberg defines them.
pub fn read_position_deletes(bytes: &[u8]) -> Result<Vec<(String, i64)>, String> {
    let answer = engine::run(bytes, "SELECT file_path, pos FROM deletes")?;
    answer
        .rows
        .into_iter()
        .map(|row| match &row[..] {
            [Value::Str(path), Value::Int(pos)] => Ok((path.clone(), *pos)),
            _ => Err("a position delete file holds a path and a position".to_string()),
        })
        .collect()
}

/// The snapshot a table's snapshots file names `id`.
fn find(snapshots: Vec<Snapshot>, id: &str) -> Result<Snapshot, String> {
    snapshots
        .into_iter()
        .find(|s| s.id == id)
        .ok_or(format!("no snapshot {id}"))
}

/// What a reader is asked to do with a table (ch15's laboratory).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Operation {
    /// Read every live row.
    Scan,
    /// Find the row with this `order_id`.
    Lookup(i64),
    /// Plan a compaction.
    Compact { target_rows: i64, small_rows: i64 },
}

/// Read the snapshots file: the first request of every operation on the table.
pub fn open(s: &mut TracingStore<MemoryStore>, prefix: &str, id: &str) -> Result<Snapshot, String> {
    let got = s
        .get(
            &format!("{prefix}{SNAPSHOTS}"),
            GetRange::All,
            "read the table's snapshots",
        )
        .map_err(|e| e.to_string())?;
    find(read_snapshots(&String::from_utf8_lossy(&got.bytes))?, id)
}

// ---- Reading every row -------------------------------------------------------------------

/// A scan of the whole table: `SELECT count(*), sum(amount_cents)` over its live rows.
#[derive(Clone, Debug, PartialEq)]
pub struct TableScan {
    pub snapshot: Snapshot,
    /// Rows decoded from the data files, deleted ones included.
    pub rows_decoded: i64,
    pub live_rows: i64,
    pub sum_amount_cents: i64,
    pub requests: Vec<Request>,
    pub elapsed_us: u64,
    pub bytes_fetched: u64,
}

/// Read every row of snapshot `id` of the table under `prefix`: the snapshots, then every data
/// file and every delete file, whole and all at once, since none depends on another. A data
/// file's rows are decoded in order, and the positions its delete files name are left out.
pub fn scan_table(
    store: MemoryStore,
    prefix: &str,
    id: &str,
    connections: usize,
    model: NetworkModel,
) -> Result<TableScan, String> {
    let mut s = TracingStore::with_connections(store, model, connections);
    let snapshot = open(&mut s, prefix, id)?;
    s.next_phase();
    let mut fetch = |key: &str, why: &str| {
        s.get(&format!("{prefix}{key}"), GetRange::All, why)
            .map(|g| g.bytes)
            .map_err(|e| e.to_string())
    };
    let mut deleted: Vec<(String, i64)> = Vec::new();
    for d in &snapshot.delete_files {
        let bytes = fetch(&d.path, "read a delete file")?;
        deleted.extend(read_position_deletes(&bytes)?);
    }
    let (mut rows_decoded, mut live_rows, mut sum) = (0, 0, 0);
    for f in &snapshot.data_files {
        let bytes = fetch(&f.path, "read a data file")?;
        let amounts = engine::run(&bytes, "SELECT amount_cents FROM orders")?.rows;
        for (pos, row) in amounts.iter().enumerate() {
            rows_decoded += 1;
            if deleted.contains(&(f.path.clone(), pos as i64)) {
                continue; // a delete file names this row: it is no longer in the table
            }
            live_rows += 1;
            if let Some(Value::Int(v)) = row.first() {
                sum += v;
            }
        }
    }
    Ok(TableScan {
        snapshot,
        rows_decoded,
        live_rows,
        sum_amount_cents: sum,
        elapsed_us: s.elapsed_us(),
        bytes_fetched: s.bytes_returned(),
        requests: s.requests,
    })
}

// ---- Finding one row ---------------------------------------------------------------------

/// A lookup of one `order_id`, and what it cost.
#[derive(Clone, Debug, PartialEq)]
pub struct Lookup {
    pub snapshot: Snapshot,
    pub key: i64,
    /// The data files whose `order_id` range holds the key, and the delete files naming them.
    pub data_files: Vec<String>,
    pub delete_files: Vec<String>,
    /// Where the key was found: the file and the position in it.
    pub found: Option<(String, u64)>,
    /// The delete file that removes the row found, if one does.
    pub deleted_by: Option<String>,
    /// The row, column by column, when it is found and not deleted.
    pub row: Vec<(String, Json)>,
    pub rows_decoded: u64,
    pub requests: Vec<Request>,
    pub elapsed_us: u64,
    pub bytes_fetched: u64,
}

/// The files a lookup of `key` must open: every data file whose `order_id` range holds it, and
/// every delete file that names one of those.
pub fn files_to_open(snapshot: &Snapshot, key: i64) -> (Vec<&DataFile>, Vec<&DeleteFile>) {
    let data: Vec<&DataFile> = snapshot
        .data_files
        .iter()
        .filter(|f| f.min_key <= key && key <= f.max_key)
        .collect();
    let deletes = snapshot
        .delete_files
        .iter()
        .filter(|d| data.iter().any(|f| f.path == d.data_file))
        .collect();
    (data, deletes)
}

/// Find the row whose `order_id` is `key` in snapshot `id`. After the snapshots, the delete
/// files that could remove it are fetched while the data file is opened, since neither depends
/// on the other; then the data file is read as ch10's scan reads any file, with statistics and
/// the page index, `prefetch` bytes of its tail in the first request.
pub fn lookup(
    store: MemoryStore,
    prefix: &str,
    id: &str,
    key: i64,
    prefetch: u64,
    connections: usize,
    model: NetworkModel,
) -> Result<Lookup, String> {
    let mut objects = store.clone();
    let mut s = TracingStore::with_connections(store, model, connections);
    let snapshot = open(&mut s, prefix, id)?;
    let (data, deletes) = files_to_open(&snapshot, key);
    let (data, deletes): (Vec<DataFile>, Vec<DeleteFile>) = (
        data.into_iter().cloned().collect(),
        deletes.into_iter().cloned().collect(),
    );
    s.next_phase();
    let mut deleted: Vec<(String, i64, String)> = Vec::new();
    for d in &deletes {
        let got = s
            .get(
                &format!("{prefix}{}", d.path),
                GetRange::All,
                "read a delete file that names a file the key may be in",
            )
            .map_err(|e| e.to_string())?;
        for (path, pos) in read_position_deletes(&got.bytes)? {
            deleted.push((path, pos, d.path.clone()));
        }
    }
    let (mut found, mut deleted_by, mut row, mut rows_decoded) = (None, None, Vec::new(), 0);
    for f in &data {
        let key_path = format!("{prefix}{}", f.path);
        let bytes = objects
            .get(&key_path, GetRange::All, "")
            .map_err(|e| e.to_string())?
            .bytes;
        let md = crate::report::open_bytes(&bytes).map_err(|e| e.to_string())?;
        let root = crate::schema::build(&md.schema).map_err(|e| e.to_string())?;
        let flat = crate::schema::leaves(&root);
        let column = flat
            .iter()
            .find(|l| l.dotted_path() == KEY)
            .ok_or(format!("{}: no column {KEY}", f.path))?
            .column;
        let query = Query {
            columns: flat.iter().map(|l| l.column).collect(),
            condition: Some((column, Op::Eq, key.to_string())),
        };
        let strategy = Strategy {
            footer: FooterOptions {
                size: SizeSource::Known(f.file_size),
                prefetch,
            },
            connections,
            coalesce_gap: Some(0),
            whole_chunks: false,
            mechanisms: Mechanisms {
                statistics: true,
                bloom: false,
                page_index: true,
            },
        };
        let r = scan::scan_in(&mut s, &bytes, &key_path, &query, strategy)?;
        rows_decoded += r.rows_decoded;
        if let Some(&pos) = r.matches.first() {
            found = Some((f.path.clone(), pos));
            deleted_by = deleted
                .iter()
                .find(|(p, n, _)| p == &f.path && *n as u64 == pos)
                .map(|(_, _, by)| by.clone());
            if deleted_by.is_none() {
                row = r
                    .column_names
                    .iter()
                    .cloned()
                    .zip(r.rows[0].iter().cloned())
                    .collect();
            }
            break;
        }
        s.next_phase();
    }
    Ok(Lookup {
        snapshot,
        key,
        data_files: data.iter().map(|f| f.path.clone()).collect(),
        delete_files: deletes.iter().map(|d| d.path.clone()).collect(),
        found,
        deleted_by,
        row,
        rows_decoded,
        elapsed_us: s.elapsed_us(),
        bytes_fetched: s.bytes_returned(),
        requests: s.requests,
    })
}

// ---- Compaction --------------------------------------------------------------------------

/// Data files rewritten together into one, with the delete files they no longer need.
#[derive(Clone, Debug, PartialEq)]
pub struct Group {
    pub data_files: Vec<String>,
    pub delete_files: Vec<String>,
    pub rows_in: i64,
    pub rows_out: i64,
    /// What the rewrite must read: every data file and delete file in the group.
    pub bytes_in: u64,
}

/// Plan a compaction of `snapshot`. A data file is rewritten if it has deletes, or if it holds
/// fewer than `small_rows` live rows. In order of their smallest `order_id`, those files are
/// packed into groups: a file joins the current group if the group's live rows stay within
/// `target_rows`, and starts a new group otherwise. A group of one file with no deletes would
/// be rewritten unchanged, so it is dropped. Files that are neither small nor deleted from are
/// left as they are.
pub fn plan_compaction(snapshot: &Snapshot, target_rows: i64, small_rows: i64) -> Vec<Group> {
    let mut candidates: Vec<&DataFile> = snapshot
        .data_files
        .iter()
        .filter(|f| !snapshot.deletes_for(&f.path).is_empty() || snapshot.live_rows(f) < small_rows)
        .collect();
    candidates.sort_by_key(|f| f.min_key);
    let mut groups: Vec<Vec<&DataFile>> = Vec::new();
    let mut rows = 0;
    for f in candidates {
        let live = snapshot.live_rows(f);
        match groups.last_mut() {
            Some(g) if rows + live <= target_rows => {
                g.push(f);
                rows += live;
            }
            _ => {
                groups.push(vec![f]);
                rows = live;
            }
        }
    }
    groups
        .into_iter()
        .filter(|g| g.len() > 1 || !snapshot.deletes_for(&g[0].path).is_empty())
        .map(|g| {
            let deletes: Vec<&DeleteFile> = g
                .iter()
                .flat_map(|f| snapshot.deletes_for(&f.path))
                .collect();
            Group {
                data_files: g.iter().map(|f| f.path.clone()).collect(),
                delete_files: deletes.iter().map(|d| d.path.clone()).collect(),
                rows_in: g.iter().map(|f| f.record_count).sum(),
                rows_out: g.iter().map(|f| snapshot.live_rows(f)).sum(),
                bytes_in: g.iter().map(|f| f.file_size).sum::<u64>()
                    + deletes.iter().map(|d| d.file_size).sum::<u64>(),
            }
        })
        .collect()
}

/// What a compaction cost, from the snapshot before it and the snapshot it wrote.
#[derive(Clone, Debug, PartialEq)]
pub struct CompactionCost {
    /// The files the compaction wrote: in `after` and not in `before`.
    pub outputs: Vec<(String, u64)>,
    pub bytes_read: u64,
    pub bytes_written: u64,
    /// Every input read, then every output written, one request each over one connection, a
    /// write priced as a read of the same size.
    pub elapsed_us: u64,
}

/// The cost of carrying out `plan`, which turned `before` into `after`. Fails if the files
/// `after` dropped are not the ones the plan rewrites, or if the rows do not add up.
pub fn compaction_cost(
    before: &Snapshot,
    after: &Snapshot,
    plan: &[Group],
    model: NetworkModel,
) -> Result<CompactionCost, String> {
    let kept = |f: &DataFile| after.data_files.iter().any(|a| a.path == f.path);
    let mut dropped: Vec<&str> = before
        .data_files
        .iter()
        .filter(|f| !kept(f))
        .map(|f| f.path.as_str())
        .collect();
    let mut planned: Vec<&str> = plan
        .iter()
        .flat_map(|g| g.data_files.iter().map(String::as_str))
        .collect();
    dropped.sort_unstable();
    planned.sort_unstable();
    if dropped != planned {
        return Err(format!(
            "snapshot {} replaced {}, but the plan rewrites {}",
            after.id,
            dropped.join(", "),
            planned.join(", ")
        ));
    }
    let outputs: Vec<(String, u64)> = after
        .data_files
        .iter()
        .filter(|a| !before.data_files.iter().any(|f| f.path == a.path))
        .map(|a| (a.path.clone(), a.file_size))
        .collect();
    let rows_out: i64 = after
        .data_files
        .iter()
        .filter(|a| outputs.iter().any(|(p, _)| p == &a.path))
        .map(|a| a.record_count)
        .sum();
    if rows_out != plan.iter().map(|g| g.rows_out).sum::<i64>() {
        return Err(format!(
            "the plan keeps {} rows, but snapshot {} wrote {rows_out}",
            plan.iter().map(|g| g.rows_out).sum::<i64>(),
            after.id
        ));
    }
    let reads: Vec<u64> = plan
        .iter()
        .flat_map(|g| {
            let data = g.data_files.iter().map(|p| {
                before
                    .data_files
                    .iter()
                    .find(|f| &f.path == p)
                    .map_or(0, |f| f.file_size)
            });
            let deletes = g.delete_files.iter().map(|p| {
                before
                    .delete_files
                    .iter()
                    .find(|d| &d.path == p)
                    .map_or(0, |d| d.file_size)
            });
            data.chain(deletes).collect::<Vec<_>>()
        })
        .collect();
    let elapsed_us = reads.iter().map(|&b| model.cost_us(b)).sum::<u64>()
        + outputs.iter().map(|(_, b)| model.cost_us(*b)).sum::<u64>();
    Ok(CompactionCost {
        bytes_read: reads.iter().sum(),
        bytes_written: outputs.iter().map(|(_, b)| b).sum(),
        outputs,
        elapsed_us,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn file(path: &str, rows: i64, lo: i64, hi: i64) -> DataFile {
        DataFile {
            path: path.into(),
            record_count: rows,
            file_size: 100 * rows as u64,
            min_key: lo,
            max_key: hi,
        }
    }

    fn delete(path: &str, of: &str) -> DeleteFile {
        DeleteFile {
            path: path.into(),
            record_count: 1,
            file_size: 50,
            data_file: of.into(),
        }
    }

    fn snapshot() -> Snapshot {
        Snapshot {
            id: "s".into(),
            summary: String::new(),
            data_files: vec![
                file("a", 100, 1, 100),
                file("b", 100, 101, 200),
                file("c", 10, 201, 210),
                file("d", 10, 211, 220),
            ],
            delete_files: vec![delete("x", "b"), delete("y", "b")],
        }
    }

    #[test]
    fn a_lookup_opens_only_the_files_that_could_hold_the_key() {
        let s = snapshot();
        let (data, deletes) = files_to_open(&s, 150);
        assert_eq!(data.iter().map(|f| &f.path[..]).collect::<Vec<_>>(), ["b"]);
        assert_eq!(deletes.len(), 2);
        let (data, deletes) = files_to_open(&s, 205);
        assert_eq!(data.len(), 1);
        assert!(deletes.is_empty());
        assert!(files_to_open(&s, 500).0.is_empty());
    }

    #[test]
    fn compaction_rewrites_deleted_and_small_files_and_leaves_the_rest() {
        let s = snapshot();
        assert_eq!(s.live_rows(&s.data_files[1]), 98);
        let plan = plan_compaction(&s, 115, 50);
        // b has deletes; c and d are small. b and c fit in 115 rows together; d starts a group
        // of its own, which would rewrite one clean file unchanged, so it is dropped.
        assert_eq!(plan.len(), 1);
        assert_eq!(plan[0].data_files, ["b", "c"]);
        assert_eq!(plan[0].delete_files, ["x", "y"]);
        assert_eq!((plan[0].rows_in, plan[0].rows_out), (110, 108));
        assert_eq!(plan[0].bytes_in, 10_000 + 1_000 + 100);
        let wide = plan_compaction(&s, 200, 50);
        assert_eq!(wide[0].data_files, ["b", "c", "d"]);
    }
}
