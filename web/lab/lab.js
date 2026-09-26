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
// Python reader can run, which the build reads from its EXPERIMENTS list. On Python, a reader can
// edit the reader's code and run the labs on the edit (editor.js).
//
// A chapter's problems workbench (workbench.js) mounts here too, and so do the Run buttons on
// the Python commands a page prints (commands.js).

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
import { openEditor } from "./editor.js";
import { mountWorkbench } from "./workbench.js";
import { mountCommands } from "./commands.js";

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
    `<button type="button" data-engine="${key}" aria-pressed="${key === engine}" title="The book's ${e.name} reader, ${e.detail}">${e.name}</button>`).join("") +
    (engine === "python" ? `<button type="button" class="edit-code" data-edit>Edit the code</button>` : "");
  bar.addEventListener("click", (e) => {
    if (e.target.closest("button[data-edit]")) {
      loadEngine("python").then((lab) => openEditor(el, lab, remountAll));
      return;
    }
    const b = e.target.closest("button[data-engine]");
    if (!b || b.dataset.engine === el.dataset.engine) return;
    try {
      localStorage.setItem("lab-engine", b.dataset.engine);
    } catch {}
    // Every lab on the page follows the choice.
    remountAll();
  });
  return bar;
}

function remountAll() {
  for (const el of document.querySelectorAll(".lab[data-experiment]")) mount(el);
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
    const edited = engine === "python" ? Object.keys(lab.edits) : [];
    if (edited.length) {
      const note = document.createElement("span");
      note.className = "edited";
      note.textContent = `running your edits to ${edited.join(", ")}`;
      bar.querySelector("span").after(note);
    }
    if (engine === "python" && lab.error) throw new Error(`the edited Python reader does not import:\n${lab.error}`);
    const names = (config.fixtures || config.fixture || "").split(",").map((s) => s.trim()).filter(Boolean);
    const files = new Fixtures(names);
    el.innerHTML = "";
    if (bar) el.append(bar);
    await run(el, lab, files, config.fixture || names[0], config);
    el.dataset.ready = "true";
  } catch (error) {
    // As text: a Python traceback names "<module>", which is not markup.
    const message = document.createElement("p");
    message.className = "lab-error";
    message.textContent = `The experiment could not start: ${String(error.message || error)}`;
    el.replaceChildren(...(bar ? [bar] : []), message);
    el.dataset.ready = "error";
    // An error in the reader's own edits is shown, and is theirs; any other is the book's bug.
    const edited = engine === "python" && Object.keys((await loadEngine("python").catch(() => ({})))?.edits || {}).length;
    if (!edited) throw error;
  }
}

for (const el of document.querySelectorAll(".lab[data-experiment]")) mount(el);
for (const el of document.querySelectorAll(".workbench[data-chapter]")) {
  mountWorkbench(el).catch((error) => {
    const message = document.createElement("p");
    message.className = "lab-error";
    message.textContent = `The workbench could not start: ${String(error.message || error)}`;
    el.replaceChildren(message);
    el.dataset.ready = "error";
  });
}
mountCommands();
