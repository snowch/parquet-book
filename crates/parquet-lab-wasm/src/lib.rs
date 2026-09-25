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
