// Mount every experiment on the page.
//
// A chapter marks an experiment with a fenced block in the language `lab`; tools/render.py turns
// it into <div class="lab" data-experiment=… data-fixture=…>. This script loads the reader once
// per page, fetches the fixtures the experiments name, and hands each mount point to its
// experiment. Paths are resolved from this script's own URL, so the book works wherever it is
// served from, including a GitHub Pages project path.
//
// The reader exists twice, in Rust and in Python, and the tests hold them to the same JSON. A lab
// runs on the Rust reader compiled to WebAssembly unless the reader chooses Python, which runs the
// book's Python files under Pyodide. The choice is remembered, and offered for every lab the
// Python reader can run, which the build reads from its EXPERIMENTS list.

import { Lab } from "./wasm.js";
import { PyLab } from "./python.js";
import { mountFooter, mountAnatomy } from "./footer.js";
import { mountLayouts } from "./layouts.js";
import { mountSchema } from "./schema.js";
import { mountLevels } from "./levels.js";
import { mountEncodings } from "./encodings.js";
import { mountPages } from "./pages.js";
import { mountCompression } from "./compression.js";
import { mountStatistics } from "./statistics.js";
import { mountSkipping } from "./skipping.js";
import { mountScan } from "./scan.js";
import { mountWriting } from "./writing.js";
import { mountEngine } from "./engine.js";
import { mountEncryption } from "./encryption.js";
import { mountTable } from "./table.js";

const EXPERIMENTS = {
  footer: mountFooter, anatomy: mountAnatomy, layouts: mountLayouts, schema: mountSchema, levels: mountLevels,
  encodings: mountEncodings, pages: mountPages, compression: mountCompression,
  statistics: mountStatistics,
  skipping: mountSkipping,
  scan: mountScan,
  writing: mountWriting,
  engine: mountEngine,
  encryption: mountEncryption,
  table: mountTable,
};

class Fixtures {
  constructor(names) {
    this.list = names;
    this.cache = new Map();
  }
  names() {
    return this.list;
  }
  async get(name) {
    if (!this.cache.has(name)) {
      const url = new URL(`../fixtures/${name}`, import.meta.url);
      this.cache.set(name, fetch(url).then(async (r) => {
        if (!r.ok) throw new Error(`could not fetch ${name}: ${r.status}`);
        return new Uint8Array(await r.arrayBuffer());
      }));
    }
    return this.cache.get(name);
  }
}

const ENGINES = {
  rust: { name: "Rust", detail: "compiled to WebAssembly", load: () => Lab.fromUrl(new URL("parquet_lab.wasm", import.meta.url)) },
  python: { name: "Python", detail: "run by Pyodide", load: () => PyLab.load(import.meta.url) },
};
const loading = {};
function loadEngine(engine) {
  loading[engine] ||= ENGINES[engine].load();
  return loading[engine];
}

function chosenEngine() {
  try {
    return localStorage.getItem("lab-engine") === "python" ? "python" : "rust";
  } catch {
    return "rust";
  }
}

// The labs the Python reader can run, from the list the site build wrote from browser.py.
const pythonLabs = fetch(new URL("py/package.json", import.meta.url))
  .then((r) => (r.ok ? r.json() : { experiments: [] }))
  .then((p) => new Set(p.experiments))
  .catch(() => new Set());

function engineBar(el, engine) {
  const bar = document.createElement("div");
  bar.className = "engine-bar";
  bar.innerHTML = `<span>Run on the reader in</span>` + Object.entries(ENGINES).map(([key, e]) =>
    `<button type="button" data-engine="${key}" aria-pressed="${key === engine}" title="The book's ${e.name} reader, ${e.detail}">${e.name}</button>`).join("");
  bar.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-engine]");
    if (!b || b.dataset.engine === el.dataset.engine) return;
    try {
      localStorage.setItem("lab-engine", b.dataset.engine);
    } catch {}
    // Every lab on the page follows the choice.
    for (const other of document.querySelectorAll(".lab[data-experiment]")) mount(other);
  });
  return bar;
}

async function mount(el) {
  // What the page asked for, kept from the first mount: a remount must not see what the last
  // run wrote into the element's data attributes, so those are cleared.
  const config = (el.labConfig ||= { ...el.dataset });
  for (const key of Object.keys(el.dataset)) if (!(key in config)) delete el.dataset[key];
  const run = EXPERIMENTS[config.experiment];
  const offersPython = (await pythonLabs).has(config.experiment);
  const engine = offersPython ? chosenEngine() : "rust";
  el.dataset.engine = engine;
  el.dataset.ready = "loading";
  el.innerHTML = engine === "python"
    ? '<p class="lab-loading">Loading Python in your browser (Pyodide, a few megabytes the first time)…</p>'
    : '<p class="lab-loading">Loading the reader…</p>';
  const bar = offersPython ? engineBar(el, engine) : null;
  if (bar) el.prepend(bar);
  try {
    const lab = await loadEngine(engine);
    if (el.dataset.engine !== engine) return; // the reader switched engines while this loaded
    const names = (config.fixtures || config.fixture || "").split(",").map((s) => s.trim()).filter(Boolean);
    const files = new Fixtures(names);
    el.innerHTML = "";
    if (bar) el.append(bar);
    await run(el, lab, files, config.fixture || names[0], config);
    el.dataset.ready = "true";
  } catch (error) {
    el.innerHTML = `<p class="lab-error">The experiment could not start: ${String(error.message || error)}</p>`;
    if (bar) el.prepend(bar);
    el.dataset.ready = "error";
    throw error;
  }
}

for (const el of document.querySelectorAll(".lab[data-experiment]")) mount(el);
