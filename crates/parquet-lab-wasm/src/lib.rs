//! parquet-lab in the browser.
//!
//! The browser runs this crate's WebAssembly build, and this crate is a thin layer over
//! `parquet-lab`: it holds the files the page has loaded, calls the reader, and hands back the
//! same JSON `pqlab` prints. There is no JavaScript implementation of anything Parquet-shaped,
//! so the page cannot disagree with the tests.
//!
//! The interface is a plain C ABI rather than a generated binding. Every function takes and
//! returns numbers; strings and byte buffers cross as a pointer and a length into this module's
//! memory. `web/lab/wasm.js` is the other half, and it is short enough to read in one sitting.
//!
//! How a call works:
//!
//! 1. JavaScript asks for a buffer with `pl_alloc`, copies a file into it, and hands it over
//!    with `pl_load`, which returns a file id.
//! 2. It calls, say, `pl_footer_lab(id, …)`. The result is written to an output buffer inside
//!    this module, and the call returns its length.
//! 3. JavaScript reads that many bytes from `pl_out_ptr()` and parses them as JSON.
//!
//! Numbers that may exceed 32 bits (sizes, bandwidth) are passed as `f64`, which JavaScript
//! numbers are, and which hold every integer up to 2^53 exactly.

use std::cell::RefCell;

use parquet_lab::json::{obj, Json};
use parquet_lab::object_store::NetworkModel;
use parquet_lab::reader::{FooterOptions, SizeSource};
use parquet_lab::report;

struct File {
    name: String,
    bytes: Vec<u8>,
}

#[derive(Default)]
struct State {
    files: Vec<File>,
    out: String,
}

thread_local! {
    static STATE: RefCell<State> = RefCell::new(State::default());
}

fn emit(json: Json) -> usize {
    STATE.with(|s| {
        let mut s = s.borrow_mut();
        s.out = json.to_json();
        s.out.len()
    })
}

fn with_file<T>(id: u32, f: impl FnOnce(&File) -> T) -> Option<T> {
    STATE.with(|s| s.borrow().files.get(id as usize).map(f))
}

fn no_such_file(id: u32) -> usize {
    emit(obj([
        ("ok", false.into()),
        ("error", format!("no file with id {id}").into()),
    ]))
}

/// Allocate `len` bytes for JavaScript to write into. Ownership passes back with `pl_load` or
/// `pl_free`.
#[no_mangle]
pub extern "C" fn pl_alloc(len: usize) -> *mut u8 {
    Box::into_raw(vec![0u8; len].into_boxed_slice()) as *mut u8
}

/// Free a buffer from `pl_alloc` that was not handed to `pl_load`.
///
/// # Safety
/// `ptr` and `len` must come from one call to `pl_alloc`, and the buffer must not be used again.
#[no_mangle]
pub unsafe extern "C" fn pl_free(ptr: *mut u8, len: usize) {
    drop(Box::from_raw(std::ptr::slice_from_raw_parts_mut(ptr, len)));
}

/// Take ownership of a file: `name` and `data` are buffers from `pl_alloc`. Returns its id.
///
/// # Safety
/// Both buffers must come from `pl_alloc` with exactly these lengths. They belong to this
/// module afterwards.
#[no_mangle]
pub unsafe extern "C" fn pl_load(
    name_ptr: *mut u8,
    name_len: usize,
    data_ptr: *mut u8,
    data_len: usize,
) -> u32 {
    let name = Box::from_raw(std::ptr::slice_from_raw_parts_mut(name_ptr, name_len));
    let data = Box::from_raw(std::ptr::slice_from_raw_parts_mut(data_ptr, data_len));
    STATE.with(|s| {
        let mut s = s.borrow_mut();
        s.files.push(File {
            name: String::from_utf8_lossy(&name).into_owned(),
            bytes: data.into_vec(),
        });
        (s.files.len() - 1) as u32
    })
}

/// Where a loaded file's bytes are, so the hex view can read them without a copy.
#[no_mangle]
pub extern "C" fn pl_file_ptr(id: u32) -> *const u8 {
    with_file(id, |f| f.bytes.as_ptr()).unwrap_or(std::ptr::null())
}

#[no_mangle]
pub extern "C" fn pl_file_len(id: u32) -> usize {
    with_file(id, |f| f.bytes.len()).unwrap_or(0)
}

/// Change one byte of a loaded file, to see what the reader makes of a damaged one. Returns the
/// byte that was there, or -1 if the offset is out of range.
#[no_mangle]
pub extern "C" fn pl_set_byte(id: u32, offset: f64, value: u32) -> i32 {
    STATE.with(|s| {
        let mut s = s.borrow_mut();
        match s
            .files
            .get_mut(id as usize)
            .and_then(|f| f.bytes.get_mut(offset as usize))
        {
            Some(b) => {
                let old = *b;
                *b = value as u8;
                i32::from(old)
            }
            None => -1,
        }
    })
}

/// The last result, for JavaScript to read `len` bytes from.
#[no_mangle]
pub extern "C" fn pl_out_ptr() -> *const u8 {
    STATE.with(|s| s.borrow().out.as_ptr())
}

/// Open a loaded file through the simulated object store. See `report::footer_lab`.
///
/// `size_source` is 0 for a `HEAD`, 1 for a size already known from a listing, and 2 for a
/// suffix range.
#[no_mangle]
pub extern "C" fn pl_footer_lab(
    id: u32,
    size_source: u32,
    prefetch: f64,
    latency_us: f64,
    bandwidth_bytes_per_sec: f64,
) -> usize {
    let Some((name, bytes)) = with_file(id, |f| (f.name.clone(), f.bytes.clone())) else {
        return no_such_file(id);
    };
    let size = match size_source {
        0 => SizeSource::Head,
        1 => SizeSource::Known(bytes.len() as u64),
        _ => SizeSource::SuffixRange,
    };
    let options = FooterOptions {
        size,
        prefetch: prefetch as u64,
    };
    let model = NetworkModel {
        latency_us: latency_us as u64,
        bandwidth_bytes_per_sec: bandwidth_bytes_per_sec as u64,
    };
    emit(report::footer_lab(&bytes, &name, options, model))
}

/// The whole file, mapped into regions. See `report::structure`.
#[no_mangle]
pub extern "C" fn pl_structure(id: u32) -> usize {
    match with_file(id, |f| report::structure(&f.bytes)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Every reading of the bytes at `offset`. See `report::interpret`.
#[no_mangle]
pub extern "C" fn pl_interpret(id: u32, offset: f64) -> usize {
    match with_file(id, |f| report::interpret(&f.bytes, offset as u64)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch01's experiment: the sales table stored by rows and by columns, queried through the
/// simulated store. See `report::layouts`. `row` below zero means every row.
#[no_mangle]
pub extern "C" fn pl_layouts(
    column_mask: u32,
    row: i32,
    latency_us: f64,
    bandwidth_bytes_per_sec: f64,
) -> usize {
    let model = NetworkModel {
        latency_us: latency_us as u64,
        bandwidth_bytes_per_sec: bandwidth_bytes_per_sec as u64,
    };
    let row = usize::try_from(row).ok();
    emit(report::layouts(column_mask, row, model))
}

/// Ch03's experiment: the flat schema, the rebuilt tree, and each column's statistics read
/// through its logical type. See `report::schema`.
#[no_mangle]
pub extern "C" fn pl_schema(id: u32) -> usize {
    match with_file(id, |f| report::schema(&f.bytes)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch04's experiment: one column's levels, values, and rebuilt records. See `report::levels`.
#[no_mangle]
pub extern "C" fn pl_levels(id: u32, column: u32) -> usize {
    match with_file(id, |f| report::levels(&f.bytes, column as usize)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch05's experiment: one column's encoding, step by step. See `report::encodings`.
#[no_mangle]
pub extern "C" fn pl_encodings(id: u32, column: u32) -> usize {
    match with_file(id, |f| report::encodings(&f.bytes, column as usize)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch14's experiment: SQL over a table of files. `ids` is a `pl_alloc` buffer of `count`
/// little-endian `u32` file ids, each file loaded under its object key; `sql` is another. This
/// call takes and frees both. `discovery`: 0 list, 1 list and prune, 2 read the log.
///
/// # Safety
/// Both buffers must come from `pl_alloc` with exactly these lengths.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn pl_table(
    ids_ptr: *mut u8,
    count: usize,
    sql_ptr: *mut u8,
    sql_len: usize,
    discovery: u32,
    connections: u32,
    latency_us: u32,
    bandwidth: u32,
) -> usize {
    use parquet_lab::table::Discovery;
    let ids = Box::from_raw(std::ptr::slice_from_raw_parts_mut(ids_ptr, count * 4));
    let sql = Box::from_raw(std::ptr::slice_from_raw_parts_mut(sql_ptr, sql_len));
    let sql = String::from_utf8_lossy(&sql).into_owned();
    let objects: Vec<(String, Vec<u8>)> = ids
        .chunks(4)
        .filter_map(|c| {
            let id = u32::from_le_bytes([c[0], c[1], c[2], c[3]]);
            with_file(id, |f| (f.name.clone(), f.bytes.clone()))
        })
        .collect();
    let discovery = match discovery {
        0 => Discovery::List,
        1 => Discovery::ListAndPrune,
        _ => Discovery::Log,
    };
    let model = NetworkModel {
        latency_us: u64::from(latency_us),
        bandwidth_bytes_per_sec: u64::from(bandwidth),
    };
    emit(report::table(
        objects,
        &sql,
        discovery,
        connections.max(1) as usize,
        model,
    ))
}

/// Ch13's experiment: what a reader without keys can see. See `report::encryption`.
#[no_mangle]
pub extern "C" fn pl_encryption(id: u32) -> usize {
    match with_file(id, |f| report::encryption(&f.bytes)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch12's experiment: SQL answered from the file, stage by stage. `sql` is a `pl_alloc` buffer
/// this call takes and frees. See `report::query`.
///
/// # Safety
/// `sql_ptr` and `sql_len` must come from one call to `pl_alloc`.
#[no_mangle]
pub unsafe extern "C" fn pl_query(id: u32, sql_ptr: *mut u8, sql_len: usize) -> usize {
    let sql = Box::from_raw(std::ptr::slice_from_raw_parts_mut(sql_ptr, sql_len));
    let sql = String::from_utf8_lossy(&sql).into_owned();
    match with_file(id, |f| report::query(&f.bytes, &sql)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch10's experiment: a query run through the simulated object store. `columns` is a bit set
/// of leaf columns to return (0 for all). `where_column` is `u32::MAX` for no condition; then
/// `op` indexes `report::OPS` and `text` (a `pl_alloc` buffer this call frees) is the value.
/// `gap` is `u32::MAX` never to merge ranges. `footer` is 0 for HEAD then a range, 1 for a suffix range. `flags`: 1 statistics, 2 Bloom
/// filters, 4 the page index, 8 whole column chunks.
///
/// # Safety
/// `text_ptr` and `text_len` must come from one call to `pl_alloc`.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn pl_scan(
    id: u32,
    columns: u32,
    where_column: u32,
    op: u32,
    text_ptr: *mut u8,
    text_len: usize,
    footer: u32,
    prefetch: u32,
    connections: u32,
    gap: u32,
    flags: u32,
    latency_us: u32,
    bandwidth: u32,
) -> usize {
    use parquet_lab::prune::{Mechanisms, Op};
    use parquet_lab::scan::{Query, Strategy};
    let text = Box::from_raw(std::ptr::slice_from_raw_parts_mut(text_ptr, text_len));
    let text = String::from_utf8_lossy(&text).into_owned();
    let condition = if where_column == u32::MAX {
        None
    } else {
        let op = report::OPS.get(op as usize).copied().unwrap_or("?");
        match Op::parse(op) {
            Ok(op) => Some((where_column as usize, op, text)),
            Err(e) => return emit(obj([("ok", false.into()), ("error", e.into())])),
        }
    };
    let strategy = Strategy {
        footer: FooterOptions {
            size: if footer == 1 {
                SizeSource::SuffixRange
            } else {
                SizeSource::Head
            },
            prefetch: u64::from(prefetch),
        },
        connections: connections.max(1) as usize,
        coalesce_gap: (gap != u32::MAX).then_some(u64::from(gap)),
        whole_chunks: flags & 8 != 0,
        mechanisms: Mechanisms {
            statistics: flags & 1 != 0,
            bloom: flags & 2 != 0,
            page_index: flags & 4 != 0,
        },
    };
    let model = NetworkModel {
        latency_us: u64::from(latency_us),
        bandwidth_bytes_per_sec: u64::from(bandwidth),
    };
    match with_file(id, |f| {
        let cols: Vec<usize> = match report::flat_columns(&f.bytes) {
            Ok(all) => all
                .into_iter()
                .filter(|c| columns == 0 || (*c < 32 && columns & (1 << c) != 0))
                .collect(),
            Err(e) => return obj([("ok", false.into()), ("error", e.into())]),
        };
        report::scan(
            &f.bytes,
            &Query {
                columns: cols,
                condition,
            },
            strategy,
            model,
        )
    }) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch09's experiment: what a condition lets the reader skip. `op` indexes
/// `report::OPS`; `text` is the condition's value, in a buffer from `pl_alloc` that this call
/// takes and frees; `mechanisms` is the bit set `report::skipping` describes.
///
/// # Safety
/// `text_ptr` and `text_len` must come from one call to `pl_alloc`.
#[no_mangle]
pub unsafe extern "C" fn pl_skipping(
    id: u32,
    column: u32,
    op: u32,
    text_ptr: *mut u8,
    text_len: usize,
    mechanisms: u32,
) -> usize {
    let text = Box::from_raw(std::ptr::slice_from_raw_parts_mut(text_ptr, text_len));
    let text = String::from_utf8_lossy(&text).into_owned();
    let op = report::OPS.get(op as usize).copied().unwrap_or("?");
    match with_file(id, |f| {
        report::skipping(&f.bytes, column as usize, op, &text, mechanisms)
    }) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch08's experiment: every column chunk's statistics, and one chunk's in detail. See
/// `report::statistics`.
#[no_mangle]
pub extern "C" fn pl_statistics(id: u32, row_group: u32, column: u32) -> usize {
    match with_file(id, |f| {
        report::statistics(&f.bytes, row_group as usize, column as usize)
    }) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch07's experiment: every column chunk's sizes, and one page decompressed token by token.
/// `page` is the page's index in the first row group's chunk, or `u32::MAX` for the first data
/// page. See `report::compression`.
#[no_mangle]
pub extern "C" fn pl_compression(id: u32, column: u32, page: u32) -> usize {
    let page = (page != u32::MAX).then_some(page as usize);
    match with_file(id, |f| report::compression(&f.bytes, column as usize, page)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}

/// Ch06's experiment: every page of one column chunk. See `report::pages`.
#[no_mangle]
pub extern "C" fn pl_pages(id: u32, column: u32) -> usize {
    match with_file(id, |f| report::pages(&f.bytes, column as usize)) {
        Some(json) => emit(json),
        None => no_such_file(id),
    }
}
