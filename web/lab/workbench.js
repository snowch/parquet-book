// A chapter's problems workbench: edit the Python problems and run their tests, in the page.
//
// A chapter marks it with a fenced block in the language `problems`; tools/render.py turns that
// into <div class="workbench" data-chapter=…>. The text area starts as the chapter's stub, from
// exercises/python/<chapter>.py, and keeps your edits in this browser. "Run the tests" hands it
// to the page's Python worker (runner.js), which runs the chapter's pytest graders under Pyodide,
// exactly as `pytest --problems` runs them at a desk, and the list below shows what pytest
// reported.
//
// Rust cannot compile in a page at reasonable cost, so the Rust problems are one click away in a
// GitHub Codespace instead: the repository, its toolchain and an editor, in the browser.

import { loadDrafts, saveDrafts, savedAnswers } from "./answers.js";
import { KEYS, codeArea } from "./code.js";
import { fetchText } from "./pyodide.js";
import { runPython, stopPython } from "./runner.js";

export const CODESPACES = "https://codespaces.new/snowch/parquet-book?quickstart=1";
const BILLING = "https://docs.github.com/en/billing/concepts/product-billing/github-codespaces";

/**
 * What a Codespace costs, said wherever the page offers one: it runs on the reader's own GitHub
 * account, not the book's. The allowance and prices are GitHub's to change, so the note links to
 * them rather than quoting them.
 */
export const CODESPACES_COST = "A Codespace runs on your own GitHub account. Personal accounts get a free " +
  "allowance of use each month; past it, GitHub blocks further use unless you have set up billing, and " +
  `then charges you (<a href="${BILLING}" target="_blank" rel="noopener">GitHub's terms</a>). Stop or ` +
  "delete the Codespace when you are done, since a stopped one still uses its storage allowance.";

const escape = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

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
      <button type="button" data-act="restore" hidden>Restore the stub</button>
      <button type="button" data-act="recover" hidden>Recover saved work</button>
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
      <code>cargo test -p exercises --test ${escape(chapter)} -- --ignored</code>. ${CODESPACES_COST}</p>`;
  const status = el.querySelector(".status");
  const results = el.querySelector(".results");
  const output = el.querySelector(".output");
  const button = (act) => el.querySelector(`[data-act="${act}"]`);
  const drafts = loadDrafts(chapter);
  let previous = drafts.previous;
  const asDraft = (text) => text === stub ? null : text;
  const updateControls = () => {
    button("restore").hidden = area.value === stub;
    button("recover").hidden = previous === null || previous === area.value;
  };
  const area = codeArea(drafts.draft ?? stub, {
    label: `Your answers, ${file}`,
    onRun: () => run(),
    onInput: (text) => {
      if (!saveDrafts(chapter, { draft: asDraft(text), previous })) {
        status.textContent = "This browser could not save the current draft.";
      }
      updateControls();
    },
  });
  area.rows = Math.min(Math.max(stub.split("\n").length, 14), 32);
  el.querySelector(".workbench-bar").before(area);
  updateControls();

  const idle = (text) => {
    button("run").disabled = false;
    button("stop").hidden = true;
    button("restore").disabled = false;
    button("recover").disabled = false;
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
    if (el.dataset.state === "running") return;
    el.dataset.state = "running";
    button("run").disabled = true;
    button("stop").hidden = false;
    button("restore").disabled = true;
    button("recover").disabled = true;
    results.innerHTML = "";
    status.textContent = "Waiting for the page's other Python runs…";
    const argv = ["pytest", `exercises/python/tests/test_${chapter}.py`, "--problems", "-q", "--tb=short"];
    runPython(argv, { answers: { ...savedAnswers(), [chapter]: area.value }, onStatus: (t) => { status.textContent = t; } })
      .then(show, (error) => idle(error.message === "Stopped." ? "Stopped." : `The tests could not run: ${error.message}`));
  }

  function switchDraft(text, message) {
    const nextPrevious = asDraft(area.value);
    if (!saveDrafts(chapter, { draft: asDraft(text), previous: nextPrevious })) {
      status.textContent = "This browser could not save a recovery copy. Your work is still in the editor.";
      return;
    }
    previous = nextPrevious;
    area.value = text;
    results.innerHTML = "";
    output.hidden = true;
    status.textContent = message;
    updateControls();
    area.focus();
  }

  el.addEventListener("click", (e) => {
    const act = e.target.closest("button[data-act]")?.dataset.act;
    if (act === "run") run();
    if (act === "stop" && el.dataset.state === "running") stopPython();
    if (act === "restore" && area.value !== stub) {
      if (previous !== null && previous !== area.value &&
          !confirm("Replace the existing recovery copy with the code in the editor and restore the stub?")) return;
      switchDraft(stub, "The stub is ready to run. Use Recover saved work to return to your draft.");
    }
    if (act === "recover" && previous !== null) {
      switchDraft(previous, "Recovered your saved work.");
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
