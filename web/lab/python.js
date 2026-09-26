// The labs' Python engine: the book's Python reader, run in the page by Pyodide.
//
// It has the same methods as the WebAssembly Lab in wasm.js and returns the same JSON, so an
// experiment draws either without knowing which ran. tests/test_python.py holds the two readers
// to identical JSON natively; tests/browser/smoke.mjs checks this engine in a page.
//
// A reader can edit the Python reader in the page (editor.js). The edits are kept in this
// browser, and `use` puts them in place of the book's files and imports the reader again, so
// every lab on the page runs on the edited code.

import { SIZE_SOURCES } from "./wasm.js";
import { readerSources, startPyodide, writeReader } from "./pyodide.js";

const OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];
const EDITS = "reader-edits";

/** The reader's edits kept in this browser: file name to text. */
export function savedEdits() {
  try {
    const edits = JSON.parse(localStorage.getItem(EDITS) || "{}");
    return edits && typeof edits === "object" ? edits : {};
  } catch {
    return {};
  }
}

export function saveEdits(edits) {
  try {
    if (Object.keys(edits).length) localStorage.setItem(EDITS, JSON.stringify(edits));
    else localStorage.removeItem(EDITS);
  } catch {}
}

export class PyLab {
  constructor(pyodide, book) {
    this.pyodide = pyodide;
    /** The reader's files as the book ships them, by file name. */
    this.book = book;
    this.edits = {};
    this.module = null;
    this.error = null;
  }

  static async load(base) {
    const [pyodide, book] = await Promise.all([startPyodide(), readerSources(base)]);
    // An edit can land within a second of the file it replaces, with the same size, and a
    // cached bytecode file would then hide it.
    pyodide.runPython("import sys; sys.dont_write_bytecode = True");
    const lab = new PyLab(pyodide, book);
    lab.use(savedEdits());
    return lab;
  }

  /**
   * Run on the book's reader with `edits` (file name to text) in place of its files. Returns
   * the error if the edited reader cannot be imported, and null if it can.
   */
  use(edits) {
    this.edits = Object.fromEntries(Object.entries(edits).filter(([name, text]) =>
      name in this.book && text !== this.book[name]));
    writeReader(this.pyodide, { ...this.book, ...this.edits });
    this.pyodide.runPython(`
import importlib, sys
for name in [m for m in sys.modules if m == "parquet_lab" or m.startswith("parquet_lab.")]:
    del sys.modules[name]
importlib.invalidate_caches()
`);
    try {
      this.module = this.pyodide.pyimport("parquet_lab.browser");
      this.error = null;
    } catch (error) {
      this.module = null;
      this.error = String(error.message || error);
    }
    return this.error;
  }

  get api() {
    if (!this.module) throw new Error(`the edited Python reader does not import:\n${this.error}`);
    return this.module;
  }

  /**
   * A report, as JSON. The book's reader returns its errors as reports and never raises, so an
   * exception is a bug in the book and is thrown; in a reader's own edits it is theirs, and comes
   * back as a report the labs show.
   */
  #run(call) {
    try {
      return JSON.parse(call());
    } catch (error) {
      if (!Object.keys(this.edits).length) throw error;
      return { ok: false, error: `your edited Python reader raised an error:\n${String(error.message || error)}` };
    }
  }

  load(name, bytes) {
    return this.api.load(name, bytes);
  }

  bytes(id) {
    const proxy = this.api.file_bytes(id);
    const buffer = proxy.getBuffer("u8");
    const out = new Uint8Array(buffer.data);
    buffer.release();
    proxy.destroy();
    return out;
  }

  setByte(id, offset, value) {
    return this.api.set_byte(id, offset, value);
  }

  footerLab(id, { size = "head", prefetch = 8, latencyUs = 20000, bandwidth = 100e6 } = {}) {
    return this.#run(() => this.api.footer_lab(id, SIZE_SOURCES[size], prefetch, latencyUs, bandwidth));
  }

  structure(id) {
    return this.#run(() => this.api.structure(id));
  }

  schema(id) {
    return this.#run(() => this.api.schema(id));
  }

  levels(id, column) {
    return this.#run(() => this.api.levels(id, column));
  }

  encodings(id, column) {
    return this.#run(() => this.api.encodings(id, column));
  }

  pages(id, column) {
    return this.#run(() => this.api.pages(id, column));
  }

  /** `page` omitted or null: the first data page. */
  compression(id, column, page = null) {
    return this.#run(() => this.api.compression(id, column, page === null ? 0xffffffff : page));
  }

  statistics(id, rowGroup, column) {
    return this.#run(() => this.api.statistics(id, rowGroup, column));
  }

  /** `mechanisms`: 1 row group statistics, 2 Bloom filters, 4 the page index, added together. */
  skipping(id, column, op, value, mechanisms = 7) {
    return this.#run(() => this.api.skipping(id, column, OPS.indexOf(op), value ?? "", mechanisms));
  }

  /** The same arguments as the WebAssembly Lab's `scan`. */
  scan(id, columns, where, s) {
    const mask = (columns || []).reduce((m, c) => m | (1 << c), 0);
    const flags = (s.statistics ? 1 : 0) | (s.bloom ? 2 : 0) | (s.pageIndex ? 4 : 0) | (s.wholeChunks ? 8 : 0);
    return this.#run(() => this.api.scan(id, mask, where ? where.column : 0xffffffff,
      where ? OPS.indexOf(where.op) : 0, where ? where.value ?? "" : "", s.footer === "suffix" ? 1 : 0, s.prefetch,
      s.connections, s.gap === null || s.gap === undefined ? 0xffffffff : s.gap, flags, s.latencyUs, s.bandwidth));
  }

  /** Answer SQL from the file, stage by stage. */
  query(id, sql) {
    return this.#run(() => this.api.query(id, sql));
  }

  encryption(id) {
    return this.#run(() => this.api.encryption(id));
  }

  table(ids, sql, discovery = "log", connections = 4, latencyUs = 20000, bandwidth = 100000000) {
    const d = { list: 0, prune: 1, log: 2 }[discovery] ?? 2;
    const list = this.pyodide.toPy(ids);
    try {
      return this.#run(() => this.api.table(list, sql, d, connections, latencyUs, bandwidth));
    } finally {
      list.destroy();
    }
  }

  interpret(id, offset) {
    return this.#run(() => this.api.interpret(id, offset));
  }

  layouts({ columns = [], row = -1, latencyUs = 20000, bandwidth = 100e6 } = {}) {
    const mask = columns.reduce((m, c) => m | (1 << c), 0);
    return this.#run(() => this.api.layouts(mask, row, latencyUs, bandwidth));
  }
}
