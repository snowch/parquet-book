// The browser's half of the C ABI in crates/parquet-lab-wasm/src/lib.rs.
//
// Everything Parquet-shaped happens in Rust. This file moves bytes across the boundary and
// parses the JSON that comes back. It works the same in a page and under Node, which is how
// tests/test_wasm.py checks that the browser and the command line say the same thing.

const encoder = new TextEncoder();
const decoder = new TextDecoder();

// How the reader learns the file size. The numbers are the ones pl_footer_lab expects.
export const SIZE_SOURCES = { head: 0, known: 1, suffix: 2 };

export class Lab {
  constructor(instance) {
    this.exports = instance.exports;
  }

  // Instantiate from the bytes of parquet_lab.wasm. The module imports nothing: it cannot
  // reach the network, the clock or the page, which is what makes its answers reproducible.
  static async fromBytes(bytes) {
    const { instance } = await WebAssembly.instantiate(bytes, {});
    return new Lab(instance);
  }

  static async fromUrl(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`could not fetch ${url}: ${response.status}`);
    return Lab.fromBytes(await response.arrayBuffer());
  }

  // Copy bytes into a buffer the module allocated, and return its address.
  #copyIn(bytes) {
    const ptr = this.exports.pl_alloc(bytes.length);
    new Uint8Array(this.exports.memory.buffer, ptr, bytes.length).set(bytes);
    return ptr;
  }

  #result(len) {
    const ptr = this.exports.pl_out_ptr();
    const text = decoder.decode(new Uint8Array(this.exports.memory.buffer, ptr, len));
    return JSON.parse(text);
  }

  // Hand a file to the module. Returns the id every other call takes.
  load(name, bytes) {
    const nameBytes = encoder.encode(name);
    const namePtr = this.#copyIn(nameBytes);
    const dataPtr = this.#copyIn(bytes);
    return this.exports.pl_load(namePtr, nameBytes.length, dataPtr, bytes.length);
  }

  // A view of the file's bytes inside the module. Read it straight away: the view is detached
  // if the module's memory grows.
  bytes(id) {
    const ptr = this.exports.pl_file_ptr(id);
    const len = this.exports.pl_file_len(id);
    return new Uint8Array(this.exports.memory.buffer, ptr, len).slice();
  }

  setByte(id, offset, value) {
    return this.exports.pl_set_byte(id, offset, value);
  }

  footerLab(id, { size = "head", prefetch = 8, latencyUs = 20000, bandwidth = 100e6 } = {}) {
    return this.#result(
      this.exports.pl_footer_lab(id, SIZE_SOURCES[size], prefetch, latencyUs, bandwidth));
  }

  structure(id) {
    return this.#result(this.exports.pl_structure(id));
  }

  schema(id) {
    return this.#result(this.exports.pl_schema(id));
  }

  /**
   * SQL over a table: `ids` are loaded files named by their object keys. `discovery` is "list",
   * "prune" or "log".
   */
  table(ids, sql, discovery = "log", connections = 4, latencyUs = 20000, bandwidth = 100000000) {
    const idBytes = new Uint8Array(ids.length * 4);
    const view = new DataView(idBytes.buffer);
    ids.forEach((id, i) => view.setUint32(i * 4, id, true));
    const idPtr = this.#copyIn(idBytes);
    const text = encoder.encode(sql);
    const sqlPtr = this.#copyIn(text);
    const d = { list: 0, prune: 1, log: 2 }[discovery] ?? 2;
    return this.#result(this.exports.pl_table(idPtr, ids.length, sqlPtr, text.length, d, connections, latencyUs, bandwidth));
  }

  encryption(id) {
    return this.#result(this.exports.pl_encryption(id));
  }

  /**
   * `pqlab ARGS`, run on the files loaded under the names the command uses
   * (`fixtures/tiny.parquet`). Returns {exit, stdout, stderr}, as the binary would.
   */
  cli(args) {
    const text = encoder.encode(args.join("\0"));
    const ptr = this.#copyIn(text);
    return this.#result(this.exports.pl_cli(ptr, text.length));
  }

  /** Answer SQL from the file, stage by stage. */
  query(id, sql) {
    const text = encoder.encode(sql);
    const ptr = this.#copyIn(text);
    return this.#result(this.exports.pl_query(id, ptr, text.length));
  }

  /**
   * Run a query through the simulated object store. `where` is null or {column, op, value};
   * `s` is the strategy: {footer: "head"|"suffix", prefetch, connections, gap (null: never merge), statistics, bloom,
   * pageIndex, wholeChunks, latencyUs, bandwidth}.
   */
  scan(id, columns, where, s) {
    const OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];
    const text = encoder.encode(where ? where.value ?? "" : "");
    const ptr = this.#copyIn(text);
    const mask = (columns || []).reduce((m, c) => m | (1 << c), 0);
    const flags = (s.statistics ? 1 : 0) | (s.bloom ? 2 : 0) | (s.pageIndex ? 4 : 0) | (s.wholeChunks ? 8 : 0);
    return this.#result(this.exports.pl_scan(id, mask, where ? where.column : 0xffffffff,
      where ? OPS.indexOf(where.op) : 0, ptr, text.length, s.footer === "suffix" ? 1 : 0, s.prefetch,
      s.connections, s.gap === null || s.gap === undefined ? 0xffffffff : s.gap, flags, s.latencyUs, s.bandwidth));
  }

  /** `mechanisms`: 1 row group statistics, 2 Bloom filters, 4 the page index, added together. */
  skipping(id, column, op, value, mechanisms = 7) {
    const OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];
    const text = encoder.encode(value ?? "");
    const ptr = this.#copyIn(text);
    return this.#result(this.exports.pl_skipping(id, column, OPS.indexOf(op), ptr, text.length, mechanisms));
  }

  statistics(id, rowGroup, column) {
    return this.#result(this.exports.pl_statistics(id, rowGroup, column));
  }

  /** `page` omitted or null: the first data page. */
  compression(id, column, page = null) {
    return this.#result(this.exports.pl_compression(id, column, page === null ? 0xffffffff : page));
  }

  pages(id, column) {
    return this.#result(this.exports.pl_pages(id, column));
  }

  encodings(id, column) {
    return this.#result(this.exports.pl_encodings(id, column));
  }

  levels(id, column) {
    return this.#result(this.exports.pl_levels(id, column));
  }

  layouts({ columns = [], row = -1, latencyUs = 20000, bandwidth = 100e6 } = {}) {
    const mask = columns.reduce((m, c) => m | (1 << c), 0);
    return this.#result(this.exports.pl_layouts(mask, row, latencyUs, bandwidth));
  }

  interpret(id, offset) {
    return this.#result(this.exports.pl_interpret(id, offset));
  }
}
