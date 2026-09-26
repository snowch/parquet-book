// Run buttons on the commands a page prints, for the ones the page can run itself.
//
// A `bash` block whose every command is one of these gets a Run button:
//
//     python3 -m pytest python/tests …            the Python reader's tests
//     python3 -m pytest exercises/python/… …      a chapter's problems, on your workbench answers
//     PYTHONPATH=python python3 -m parquet_lab …  the Python reader's command line
//
// Run sends each command to the page's Python worker (runner.js), which runs it under Pyodide
// from the repository's root, with the repository's own files, and the block shows what it
// printed. Anything else (cargo, make, a test that needs the Rust reader) needs a desk or a
// Codespace, and gets no button: the page never pretends to run what it cannot.

import { runPython, stopPython } from "./runner.js";

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

/** The worker's argv for one command, or null if the page cannot run it. */
export function argvFor(line) {
  const w = words(line);
  if (!w) return null;
  if (w[0] === "PYTHONPATH=python" && w[1] === "python3" && w[2] === "-m" && w[3] === "parquet_lab") {
    return ["parquet_lab", ...w.slice(4)];
  }
  if (w[0] === "python3" && w[1] === "-m" && w[2] === "pytest") {
    // The paths it names, skipping options and the values of the options that take one.
    const paths = [];
    for (let i = 3; i < w.length; i++) {
      if (["-k", "-m", "-p"].includes(w[i])) i++;
      else if (!w[i].startsWith("-")) paths.push(w[i]);
    }
    const runnable = (p) => p.startsWith("python/tests") || p.startsWith("exercises/python");
    if (paths.length && paths.every(runnable)) return ["pytest", ...w.slice(3)];
  }
  return null;
}

/** A block's commands, one per logical line, or null unless the page can run every one. */
function commands(text) {
  const lines = text.replace(/\\\n\s*/g, " ").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));
  const runs = lines.map((line) => ({ line, argv: argvFor(line) }));
  return runs.length && runs.every((r) => r.argv) ? runs : null;
}

export function mountCommands(root = document) {
  for (const code of root.querySelectorAll("pre > code.language-bash")) {
    const pre = code.parentElement;
    const runs = commands(code.textContent);
    if (!runs || pre.parentElement.classList.contains("runnable")) continue;
    const box = document.createElement("div");
    box.className = "runnable";
    pre.before(box);
    box.append(pre);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "run-button";
    button.textContent = "▶ Run";
    const problems = runs.some((r) => r.argv[1]?.startsWith("exercises/python"));
    button.title = problems
      ? "Run in your browser, on your answers from this chapter's workbench (or the stub)"
      : "Run in your browser, with Python under Pyodide";
    box.append(button);
    const result = document.createElement("div");
    result.className = "run-result";
    result.hidden = true;
    result.innerHTML = '<div class="run-head"><span class="status" role="status"></span></div><pre class="run-output"></pre>';
    box.after(result);
    const status = result.querySelector(".status");
    const output = result.querySelector(".run-output");
    box.dataset.state = "idle";

    button.addEventListener("click", async () => {
      if (box.dataset.state === "running") {
        stopPython();
        return;
      }
      box.dataset.state = "running";
      button.textContent = "■ Stop";
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
        for (const { line, argv } of runs) {
          const r = await runPython(argv, { onStatus: (t) => { phase = t; } });
          output.textContent += `${runs.length > 1 ? `$ ${line}\n` : ""}${r.output}${runs.length > 1 ? "\n" : ""}`;
          codes.push(r.exit);
        }
        const last = codes.at(-1);
        status.textContent = `Ran in your browser in ${Math.round((Date.now() - started) / 100) / 10} s` +
          (codes.every((c) => c === 0) ? "" : `; exit status ${codes.find((c) => c !== 0) ?? last}`);
        box.dataset.exit = String(codes.find((c) => c !== 0) ?? 0);
      } catch (error) {
        status.textContent = error.message === "Stopped." ? "Stopped." : `Could not run: ${error.message}`;
        box.dataset.exit = "";
      } finally {
        clearInterval(tick);
        box.dataset.state = "idle";
        button.textContent = "▶ Run";
      }
    });
  }
}
