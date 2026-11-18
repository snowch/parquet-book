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
import { runPython } from "./runner.js";

export const CODESPACES = "https://codespaces.new/snowch/parquet-book/tree/main?quickstart=1";
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
    <p class="workbench-note" id="keys-${escape(chapter)}">${escape(KEYS)}</p>
    <div class="workbench-bar">
      <button type="button" class="primary" data-act="run">Run the tests</button>
      <button type="button" data-act="stop" hidden>Stop</button>
      <button type="button" data-act="restore" hidden>Restore the stub</button>
      <button type="button" data-act="recover" hidden>Recover saved work</button>
      <button type="button" data-act="download" hidden>Download code</button>
      <span class="status" role="status"></span>
    </div>
    <p class="workbench-note save-status" role="status" hidden></p>
    <p class="workbench-note checked-source" hidden></p>
    <ul class="results" aria-label="Test results"></ul>
    <details class="output" hidden><summary>Full test output</summary><pre></pre></details>`;
  const status = el.querySelector(".status");
  const saveStatus = el.querySelector(".save-status");
  const checkedSource = el.querySelector(".checked-source");
  const results = el.querySelector(".results");
  const output = el.querySelector(".output");
  const button = (act) => el.querySelector(`[data-act="${act}"]`);
  const drafts = loadDrafts(chapter);
  let previous = drafts.previous;
  let controller;
  let checked;
  const asDraft = (text) => text === stub ? null : text;
  const updateControls = () => {
    button("restore").hidden = area.value === stub;
    button("recover").hidden = previous === null || previous === area.value;
    button("download").hidden = area.value === stub && saveStatus.hidden;
    checkedSource.hidden = checked === undefined;
    checkedSource.textContent = checked === undefined ? "" :
      (checked === stub ? "Results for the starter code." : "Results for your code when you last ran the tests.") +
      (checked !== area.value ? " The editor has changed. Run the tests again to check the current code." : "");
  };
  const saving = (message) => {
    saveStatus.hidden = !message;
    saveStatus.textContent = message;
  };
  const area = codeArea(drafts.draft ?? stub, {
    label: `Your answers, ${file}`,
    onRun: () => run(),
    onInput: (text) => {
      saving(saveDrafts(chapter, { draft: asDraft(text), previous }) ? "" :
        "This browser could not save your draft. Download the code before leaving this page.");
      updateControls();
    },
  });
  area.rows = Math.min(Math.max(stub.split("\n").length, 14), 32);
  area.setAttribute("aria-describedby", `keys-${chapter}`);
  el.querySelector(".workbench-bar").before(area);
  if (!drafts.storageReadable) saving("This browser did not let the page read saved drafts.");
  updateControls();

  const idle = (text) => {
    const stopped = document.activeElement === button("stop");
    button("run").removeAttribute("aria-disabled");
    button("stop").hidden = true;
    if (stopped) button("run").focus();
    button("restore").disabled = false;
    button("recover").disabled = false;
    status.textContent = text;
    el.dataset.state = "idle";
    controller = null;
  };

  function show(result, source) {
    checked = source;
    const passed = result.tests.filter((t) => t.outcome === "passed").length;
    const setupError = result.tests.some((t) => t.outcome === "error");
    results.innerHTML = result.tests.map((t) => `
      <li class="${escape(t.outcome)}"><span class="mark" aria-hidden="true">${t.outcome === "passed" ? "✓" : t.outcome === "failed" ? "✗" : "–"}</span>
        <code>${escape(t.name)}</code> <span class="outcome">${escape(t.outcome)}</span>
        ${t.message ? `<pre>${escape(t.message)}</pre>` : ""}</li>`).join("");
    output.hidden = false;
    output.querySelector("pre").textContent = result.output;
    output.open = !result.tests.length || result.exit > 1;
    el.dataset.passed = passed;
    el.dataset.tests = result.tests.length;
    let message = `${passed} of ${result.tests.length} checks passed.`;
    if (result.exit === 5) message = "The test runner found no tests. Read the full test output.";
    else if (result.exit > 1) message = "The test runner could not complete the checks. Read the full test output.";
    else if (setupError) message += " A check could not finish. Read its error below.";
    else if (passed < result.tests.length) message += " Read any failed checks below before editing again.";
    idle(message);
    updateControls();
  }

  function run() {
    if (el.dataset.state === "running") return;
    el.dataset.state = "running";
    button("run").setAttribute("aria-disabled", "true");
    button("stop").hidden = false;
    button("restore").disabled = true;
    button("recover").disabled = true;
    controller = new AbortController();
    status.textContent = "Waiting to run the tests…";
    const argv = ["pytest", `exercises/python/tests/test_${chapter}.py`, "--problems", "-q", "--tb=short"];
    const source = area.value;
    runPython(argv, { answers: { ...savedAnswers(), [chapter]: source }, signal: controller.signal,
      onStatus: (t) => { status.textContent = t; } })
      .then((result) => show(result, source),
        (error) => idle(error.message === "Stopped." ? "Stopped." : `The tests could not run: ${error.message}`));
  }

  function switchDraft(text, message) {
    const nextPrevious = asDraft(area.value);
    if (!saveDrafts(chapter, { draft: asDraft(text), previous: nextPrevious })) {
      saving("This browser could not save a recovery copy. Your code is still in the editor. Download it before leaving.");
      updateControls();
      return;
    }
    previous = nextPrevious;
    area.value = text;
    results.innerHTML = "";
    output.hidden = true;
    checked = undefined;
    saving("");
    status.textContent = message;
    updateControls();
    area.focus();
  }

  el.addEventListener("click", (e) => {
    const act = e.target.closest("button[data-act]")?.dataset.act;
    if (act === "run") run();
    if (act === "stop") controller?.abort();
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
