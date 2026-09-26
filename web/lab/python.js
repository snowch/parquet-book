// The labs' Python engine: the book's Python reader, run in the page by Pyodide.
//
// It has the same methods as the WebAssembly Lab in wasm.js and returns the same JSON, so an
// experiment draws either without knowing which ran. tests/test_python.py holds the two readers
// to identical JSON natively; tests/browser/smoke.mjs checks this engine in a page.
//
// Pyodide is CPython compiled to WebAssembly. It is several megabytes, so it is fetched only when
// a reader chooses the Python engine, from a pinned release on a public CDN. The reader's own
// Python files come from this site: the same files the tests import.

import { SIZE_SOURCES } from "./wasm.js";

const OPS = ["=", "!=", "<", "<=", ">", ">=", "is null", "is not null"];

export const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/";

export class PyLab {
  constructor(pyodide, api) {
    this.pyodide = pyodide;
    this.api = api;
  }

  static async load(base) {
    const { loadPyodide } = await import(`${PYODIDE}pyodide.mjs`);
    const pyodide = await loadPyodide({ indexURL: PYODIDE });
    const { modules } = await (await fetch(new URL("py/package.json", base))).json();
    pyodide.FS.mkdirTree("/lab/parquet_lab");
    await Promise.all(modules.map(async (name) => {
      const r = await fetch(new URL(`py/parquet_lab/${name}`, base));
      if (!r.ok) throw new Error(`could not fetch ${name}: ${r.status}`);
      pyodide.FS.writeFile(`/lab/parquet_lab/${name}`, await r.text());
    }));
    pyodide.runPython("import sys; sys.path.insert(0, '/lab')");
    return new PyLab(pyodide, pyodide.pyimport("parquet_lab.browser"));
  }

  #json(text) {
    return JSON.parse(text);
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
    return this.#json(this.api.footer_lab(id, SIZE_SOURCES[size], prefetch, latencyUs, bandwidth));
  }

  structure(id) {
    return this.#json(this.api.structure(id));
  }

  schema(id) {
    return this.#json(this.api.schema(id));
  }

  levels(id, column) {
    return this.#json(this.api.levels(id, column));
  }

  encodings(id, column) {
    return this.#json(this.api.encodings(id, column));
  }

  pages(id, column) {
    return this.#json(this.api.pages(id, column));
  }

  /** `page` omitted or null: the first data page. */
  compression(id, column, page = null) {
    return this.#json(this.api.compression(id, column, page === null ? 0xffffffff : page));
  }

  statistics(id, rowGroup, column) {
    return this.#json(this.api.statistics(id, rowGroup, column));
  }

  /** `mechanisms`: 1 row group statistics, 2 Bloom filters, 4 the page index, added together. */
  skipping(id, column, op, value, mechanisms = 7) {
    return this.#json(this.api.skipping(id, column, OPS.indexOf(op), value ?? "", mechanisms));
  }

  /** The same arguments as the WebAssembly Lab's `scan`. */
  scan(id, columns, where, s) {
    const mask = (columns || []).reduce((m, c) => m | (1 << c), 0);
    const flags = (s.statistics ? 1 : 0) | (s.bloom ? 2 : 0) | (s.pageIndex ? 4 : 0) | (s.wholeChunks ? 8 : 0);
    return this.#json(this.api.scan(id, mask, where ? where.column : 0xffffffff,
      where ? OPS.indexOf(where.op) : 0, where ? where.value ?? "" : "", s.footer === "suffix" ? 1 : 0, s.prefetch,
      s.connections, s.gap === null || s.gap === undefined ? 0xffffffff : s.gap, flags, s.latencyUs, s.bandwidth));
  }

  /** Answer SQL from the file, stage by stage. */
  query(id, sql) {
    return this.#json(this.api.query(id, sql));
  }

  encryption(id) {
    return this.#json(this.api.encryption(id));
  }

  table(ids, sql, discovery = "log", connections = 4, latencyUs = 20000, bandwidth = 100000000) {
    const d = { list: 0, prune: 1, log: 2 }[discovery] ?? 2;
    const list = this.pyodide.toPy(ids);
    try {
      return this.#json(this.api.table(list, sql, d, connections, latencyUs, bandwidth));
    } finally {
      list.destroy();
    }
  }

  interpret(id, offset) {
    return this.#json(this.api.interpret(id, offset));
  }

  layouts({ columns = [], row = -1, latencyUs = 20000, bandwidth = 100e6 } = {}) {
    const mask = columns.reduce((m, c) => m | (1 << c), 0);
    return this.#json(this.api.layouts(mask, row, latencyUs, bandwidth));
  }
}
