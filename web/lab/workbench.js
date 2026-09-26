// A chapter's problems workbench: edit the Python problems and run their tests, in the page.
//
// A chapter marks it with a fenced block in the language `problems`; tools/render.py turns that
// into <div class="workbench" data-chapter=…>. The text area starts as the chapter's stub, from
// exercises/python/<chapter>.py, and keeps your edits in this browser. "Run the tests" hands it
// to workbench-worker.js, which runs the chapter's pytest graders under Pyodide, exactly as
// `pytest --problems` runs them at a desk, and the list below shows what pytest reported.
//
// Rust cannot compile in a page at reasonable cost, so the Rust problems are one click away in a
// GitHub Codespace instead: the repository, its toolchain and an editor, in the browser.

import { KEYS, codeArea } from "./code.js";
import { fetchText } from "./pyodide.js";

export const CODESPACES = "https://codespaces.new/snowch/parquet-book?quickstart=1";

const key = (chapter) => `problems:${chapter}`;

function saved(chapter) {
  try {
    return localStorage.getItem(key(chapter));
  } catch {
    return null;
  }
}

/** Every chapter's saved answers, by chapter: one chapter's problems can use another's. */
function answers() {
  const out = {};
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k.startsWith("problems:")) out[k.slice("problems:".length)] = localStorage.getItem(k);
    }
  } catch {}
  return out;
}

function save(chapter, text, stub) {
  try {
    if (text === stub) localStorage.removeItem(key(chapter));
    else localStorage.setItem(key(chapter), text);
  } catch {}
}

const escape = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

let worker = null;
let busy = null; // the workbench whose tests are running: one run at a time per page

export async function mountWorkbench(el) {
  const chapter = el.dataset.chapter;
  const file = `exercises/python/${chapter}.py`;
  const stub = await fetchText(new URL(`py/exercises/${chapter}.py`, import.meta.url));
  el.innerHTML = `
    <div class="lab-head"><span class="lab-title">Solve them here, in Python</span>
      <span class="lab-note"><code>${escape(file)}</code>, kept in this browser as you type</span></div>
    <div class="workbench-bar">
      <button type="button" class="primary" data-act="run">Run the tests</button>
      <button type="button" data-act="stop" hidden>Stop</button>
      <button type="button" data-act="restore">Restore the stub</button>
      <button type="button" data-act="download">Download</button>
      <span class="status" role="status"></span>
    </div>
    <ol class="results" aria-label="Test results"></ol>
    <details class="output" hidden><summary>What pytest printed</summary><pre></pre></details>
    <p class="workbench-note">${escape(KEYS)}. The tests are
      <code>exercises/python/tests/test_${escape(chapter)}.py</code>, run by pytest in your browser.
      Solving in Rust instead? Open the repository in
      <a href="${CODESPACES}" target="_blank" rel="noopener">GitHub Codespaces</a>, an editor and the
      Rust toolchain in your browser, and run
      <code>cargo test -p exercises --test ${escape(chapter)} -- --ignored</code>.</p>`;
  const status = el.querySelector(".status");
  const results = el.querySelector(".results");
  const output = el.querySelector(".output");
  const button = (act) => el.querySelector(`[data-act="${act}"]`);
  const area = codeArea(saved(chapter) ?? stub, {
    label: `Your answers, ${file}`,
    onRun: () => run(),
    onInput: (text) => save(chapter, text, stub),
  });
  area.rows = Math.min(Math.max(stub.split("\n").length, 14), 32);
  el.querySelector(".workbench-bar").before(area);

  const idle = (text) => {
    busy = null;
    button("run").disabled = false;
    button("stop").hidden = true;
    status.textContent = text;
    el.dataset.state = "idle";
  };

  function show(result) {
    const passed = result.tests.filter((t) => t.outcome === "passed").length;
    results.innerHTML = result.tests.map((t) => `
      <li class="${escape(t.outcome)}"><span class="mark" aria-hidden="true">${t.outcome === "passed" ? "✓" : t.outcome === "failed" ? "✗" : "–"}</span>
        <code>${escape(t.name)}</code> <span class="outcome">${escape(t.outcome)}</span>
        ${t.message ? `<pre>${escape(t.message)}</pre>` : ""}</li>`).join("");
    output.hidden = false;
    output.querySelector("pre").textContent = result.output;
    el.dataset.passed = passed;
    el.dataset.tests = result.tests.length;
    idle(result.tests.length
      ? `${passed} of ${result.tests.length} tests pass, in ${result.seconds} s`
      : "pytest collected no tests; see what it printed");
  }

  function run() {
    if (busy) {
      status.textContent = busy === el ? status.textContent : "Another workbench on this page is running its tests.";
      return;
    }
    busy = el;
    el.dataset.state = "running";
    button("run").disabled = true;
    button("stop").hidden = false;
    results.innerHTML = "";
    status.textContent = "Starting…";
    worker ||= new Worker(new URL("workbench-worker.js", import.meta.url), { type: "module" });
    worker.onmessage = ({ data }) => {
      if (data.type === "status") status.textContent = data.text;
      else if (data.type === "result") show(data.result);
      else idle(`The tests could not run: ${data.message}`);
    };
    worker.onerror = (e) => idle(`The tests could not run: ${e.message || "the worker failed"}`);
    worker.postMessage({ chapter, answers: { ...answers(), [chapter]: area.value } });
  }

  el.addEventListener("click", (e) => {
    const act = e.target.closest("button[data-act]")?.dataset.act;
    if (act === "run") run();
    if (act === "stop" && busy === el) {
      // A run cannot be interrupted from outside, so the worker goes, and the next run starts a
      // fresh one.
      worker.terminate();
      worker = null;
      idle("Stopped.");
    }
    if (act === "restore" && confirm("Replace your answers with the stub? Your edits here are lost.")) {
      area.value = stub;
      save(chapter, stub, stub);
      results.innerHTML = "";
      output.hidden = true;
      status.textContent = "Restored the stub.";
    }
    if (act === "download") {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([area.value], { type: "text/x-python" }));
      a.download = `${chapter}.py`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }
  });
  el.dataset.ready = "true";
}
