// Buttons on the commands a page prints: Run for the ones the page can run itself, and Open in
// Codespaces for the ones that need a toolchain.
//
// A `bash` block whose every command is one of these gets a Run button:
//
//     python3 -m pytest python/tests …            the Python reader's tests
//     python3 -m pytest exercises/python/… …      a chapter's problems, on your workbench answers
//     PYTHONPATH=python python3 -m parquet_lab …  the Python reader's command line
//     cargo run -p pqlab -- …                     the Rust reader's command line
//
// The Python commands run in the page's Python worker (runner.js), under Pyodide, from the
// repository's root with the repository's own files. `pqlab` runs in the Rust reader compiled to
// WebAssembly, which the labs use: `pl_cli` runs the binary's own command code (pqlab::cli) on
// the fixtures, and tests/test_wasm.py holds its output to the binary's, byte for byte.
//
// Anything else (cargo test, make, a test that needs the Rust reader) needs a compiler, which a
// page does not have. Those blocks get Open in Codespaces instead: the repository, its toolchains
// and an editor in the browser, where the command runs as it does at a desk, on your edits. The
// page never pretends to run what it cannot.

import { Lab } from "./wasm.js";
import { packageList } from "./pyodide.js";
import { runPython, stopPython } from "./runner.js";
import { CODESPACES, CODESPACES_COST } from "./workbench.js";

/** A shell line as words: quotes group, a backslash escapes the next character. */
function words(line) {
  const out = [];
  let word = null;
  let quote = null;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quote) {
      if (c === quote) quote = null;
      else if (c === "\\" && quote === '"' && i + 1 < line.length) word += line[++i];
      else word += c;
    } else if (c === "'" || c === '"') {
      quote = c;
      word ??= "";
    } else if (c === "\\" && i + 1 < line.length) {
      word = (word ?? "") + line[++i];
    } else if (/\s/.test(c)) {
      if (word !== null) out.push(word);
      word = null;
    } else {
      word = (word ?? "") + c;
    }
  }
  if (quote) return null;
  if (word !== null) out.push(word);
  return out;
}

/** How the page can run one command: {engine: "python" | "rust", argv}, or null. */
export function runnable(line) {
  const w = words(line);
  if (!w) return null;
  if (w[0] === "PYTHONPATH=python" && w[1] === "python3" && w[2] === "-m" && w[3] === "parquet_lab") {
    return { engine: "python", argv: ["parquet_lab", ...w.slice(4)] };
  }
  if (w[0] === "python3" && w[1] === "-m" && w[2] === "pytest") {
    // The paths it names, skipping options and the values of the options that take one.
    const paths = [];
    for (let i = 3; i < w.length; i++) {
      if (["-k", "-m", "-p"].includes(w[i])) i++;
      else if (!w[i].startsWith("-")) paths.push(w[i]);
    }
    const here = (p) => p.startsWith("python/tests") || p.startsWith("exercises/python");
    if (paths.length && paths.every(here)) return { engine: "python", argv: ["pytest", ...w.slice(3)] };
  }
  if (w[0] === "cargo" && w[1] === "run" && w[2] === "-p" && w[3] === "pqlab" && w[4] === "--") {
    return { engine: "rust", argv: w.slice(5) };
  }
  return null;
}

/** A block's commands, one per logical line. */
function commands(text) {
  return text.replace(/\\\n\s*/g, " ").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"))
    .map((line) => ({ line, run: runnable(line) }));
}

/** A command a Codespace runs: the repository's own tools, from its root. */
const forCodespace = (line) => /^(cargo|make|python3|PYTHONPATH=python) /.test(line);

// The Rust reader for pqlab commands: its own instance, so the labs' files are untouched, with
// every fixture loaded under the path a command names it by.
let rust = null;
function rustReader() {
  rust ||= (async () => {
    const lab = await Lab.fromUrl(new URL("parquet_lab.wasm", import.meta.url));
    const { fixtures } = await packageList(import.meta.url);
    await Promise.all(fixtures.map(async (name) => {
      const r = await fetch(new URL(`../fixtures/${name}`, import.meta.url));
      if (!r.ok) throw new Error(`could not fetch fixtures/${name}: ${r.status}`);
      lab.load(`fixtures/${name}`, new Uint8Array(await r.arrayBuffer()));
    }));
    return lab;
  })().catch((error) => {
    rust = null;
    throw error;
  });
  return rust;
}

async function runOne({ engine, argv }, onStatus) {
  if (engine === "python") {
    const r = await runPython(argv, { onStatus });
    return { exit: r.exit, output: r.output };
  }
  onStatus("Loading the Rust reader…");
  const lab = await rustReader();
  onStatus("Running…");
  const r = lab.cli(argv);
  return { exit: r.exit, output: r.stdout + r.stderr };
}

function button(box, label, title) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "run-button";
  b.textContent = label;
  b.title = title;
  box.append(b);
  return b;
}

function wrap(pre) {
  const box = document.createElement("div");
  box.className = "runnable";
  pre.before(box);
  box.append(pre);
  return box;
}

function mountRun(pre, runs) {
  const box = wrap(pre);
  const rust = runs.every((r) => r.run.engine === "rust");
  const problems = runs.some((r) => r.run.argv[1]?.startsWith("exercises/python"));
  const run = button(box, "▶ Run", rust
    ? "Run in your browser, on the book's Rust reader compiled to WebAssembly"
    : problems
      ? "Run in your browser, on your answers from this chapter's workbench (or the stub)"
      : "Run in your browser, with Python under Pyodide");
  const result = document.createElement("div");
  result.className = "run-result";
  result.hidden = true;
  result.innerHTML = '<div class="run-head"><span class="status" role="status"></span></div><pre class="run-output"></pre>';
  box.after(result);
  const status = result.querySelector(".status");
  const output = result.querySelector(".run-output");
  box.dataset.state = "idle";

  run.addEventListener("click", async () => {
    if (box.dataset.state === "running") {
      stopPython();
      return;
    }
    box.dataset.state = "running";
    run.textContent = "■ Stop";
    result.hidden = false;
    output.textContent = "";
    const started = Date.now();
    let phase = "Waiting for the page's other Python runs…";
    const tick = setInterval(() => {
      status.textContent = `${phase} ${Math.round((Date.now() - started) / 1000)} s`;
    }, 1000);
    status.textContent = phase;
    const codes = [];
    try {
      for (const { line, run: how } of runs) {
        const r = await runOne(how, (t) => { phase = t; });
        output.textContent += `${runs.length > 1 ? `$ ${line}\n` : ""}${r.output}${runs.length > 1 ? "\n" : ""}`;
        codes.push(r.exit);
      }
      const failed = codes.find((c) => c !== 0);
      status.textContent = `Ran in your browser in ${Math.round((Date.now() - started) / 100) / 10} s` +
        (rust ? ", on the Rust reader compiled to WebAssembly" : "") +
        (failed === undefined ? "" : `; exit status ${failed}`);
      box.dataset.exit = String(failed ?? 0);
    } catch (error) {
      status.textContent = error.message === "Stopped." ? "Stopped." : `Could not run: ${error.message}`;
      box.dataset.exit = "";
    } finally {
      clearInterval(tick);
      box.dataset.state = "idle";
      run.textContent = "▶ Run";
    }
  });
}

function mountCodespace(pre, lines) {
  const box = wrap(pre);
  box.dataset.codespace = "true";
  const open = button(box, "Open in Codespaces",
    "Rust needs a compiler, which a page does not have. A Codespace is the repository with its " +
    "toolchains and an editor, in your browser: edit the code and run this there. It runs on your own " +
    "GitHub account, within its free monthly allowance or at GitHub's charges past it.");
  const note = document.createElement("p");
  note.className = "run-note";
  note.hidden = true;
  box.after(note);
  open.addEventListener("click", async () => {
    const text = lines.join("\n");
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch {}
    window.open(CODESPACES, "_blank", "noopener");
    note.hidden = false;
    const then = "edit any file first to run it on your change. The first start takes a few minutes, " +
      "while it installs the toolchains.";
    note.innerHTML = (copied
      ? `Copied the command. When the Codespace has started, paste it into its terminal; ${then}`
      : `When the Codespace has started, run this command in its terminal; ${then}`) + ` ${CODESPACES_COST}`;
  });
}

export function mountCommands(root = document) {
  for (const code of root.querySelectorAll("pre > code.language-bash")) {
    const pre = code.parentElement;
    if (pre.parentElement.classList.contains("runnable")) continue;
    const runs = commands(code.textContent);
    if (!runs.length) continue;
    if (runs.every((r) => r.run)) mountRun(pre, runs);
    else if (runs.every((r) => forCodespace(r.line))) mountCodespace(pre, runs.map((r) => r.line));
  }
}
