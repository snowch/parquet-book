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

  interpret(id, offset) {
    return this.#json(this.api.interpret(id, offset));
  }

  layouts({ columns = [], row = -1, latencyUs = 20000, bandwidth = 100e6 } = {}) {
    const mask = columns.reduce((m, c) => m | (1 << c), 0);
    return this.#json(this.api.layouts(mask, row, latencyUs, bandwidth));
  }
}
