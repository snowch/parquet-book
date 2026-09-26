// Pyodide, and the book's Python files inside it: shared by the labs' Python engine (python.js),
// the reader editor (editor.js), and the worker that runs the workbenches' tests and the Run
// buttons' commands (python-worker.js).
//
// Pyodide is CPython compiled to WebAssembly. It is several megabytes, so it is fetched only when
// a reader asks for Python, from a pinned release on a public CDN. The book's own Python files
// come from this site, and go into Pyodide's file system in the repository's layout, so the
// graders find the reader and the fixtures where they find them at a desk.

export const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/";

/** Where the repository's files go in Pyodide's file system. */
export const ROOT = "/book";

export async function startPyodide() {
  const { loadPyodide } = await import(`${PYODIDE}pyodide.mjs`);
  return loadPyodide({ indexURL: PYODIDE });
}

const manifests = new Map();

/**
 * What the site build wrote about the Python files, from `base` (a URL in web/lab): the reader's
 * modules, the labs it runs, the problems and their graders, and the fixtures.
 */
export function packageList(base) {
  const url = new URL("py/package.json", base).href;
  if (!manifests.has(url)) {
    manifests.set(url, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`could not fetch the list of Python files: ${r.status}`);
      return r.json();
    }));
  }
  return manifests.get(url);
}

export async function fetchText(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`could not fetch ${url}: ${r.status}`);
  return r.text();
}

export async function fetchBytes(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`could not fetch ${url}: ${r.status}`);
  return new Uint8Array(await r.arrayBuffer());
}

/** The reader's modules as the book ships them, by file name. */
export async function readerSources(base) {
  const { modules } = await packageList(base);
  const texts = await Promise.all(modules.map((name) => fetchText(new URL(`py/parquet_lab/${name}`, base))));
  return Object.fromEntries(modules.map((name, i) => [name, texts[i]]));
}

/** Write `contents` (text or bytes) to `path`, making its directories. */
export function writeFile(pyodide, path, contents) {
  pyodide.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
  pyodide.FS.writeFile(path, contents);
}

/** Write the reader's modules, from `sources` by file name, where the tests import them. */
export function writeReader(pyodide, sources) {
  for (const [name, text] of Object.entries(sources)) writeFile(pyodide, `${ROOT}/python/parquet_lab/${name}`, text);
  pyodide.runPython(`
import sys
if "${ROOT}/python" not in sys.path:
    sys.path.insert(0, "${ROOT}/python")
`);
}
