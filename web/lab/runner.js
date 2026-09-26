// The page's one Python worker (python-worker.js), shared by the problems workbenches and the Run
// buttons on commands. Runs queue: one at a time, in the order they were asked for.

let worker = null;
let queue = Promise.resolve();
let current = null;

/** Every chapter's saved answers from its workbench, by chapter: `problems:<chapter>`. */
export function savedAnswers() {
  const out = {};
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k.startsWith("problems:")) out[k.slice("problems:".length)] = localStorage.getItem(k);
    }
  } catch {}
  return out;
}

/**
 * Run `argv` (["pytest", …] or ["parquet_lab", …]) from the repository's root, with `answers`
 * as the chapters' problem files. Resolves with {exit, output, tests, seconds}.
 */
export function runPython(argv, { answers = savedAnswers(), onStatus = () => {} } = {}) {
  const job = queue.then(() => new Promise((resolve, reject) => {
    current = { reject };
    worker ||= new Worker(new URL("python-worker.js", import.meta.url), { type: "module" });
    worker.onmessage = ({ data }) => {
      if (data.type === "status") return onStatus(data.text);
      current = null;
      if (data.type === "result") resolve(data.result);
      else reject(new Error(data.message));
    };
    worker.onerror = (e) => {
      current = null;
      reject(new Error(e.message || "the Python worker failed"));
    };
    worker.postMessage({ argv, answers });
  }));
  queue = job.catch(() => {});
  return job;
}

/**
 * Stop the run in progress. Python cannot be interrupted from outside, so the worker goes, and
 * the next run starts a fresh one.
 */
export function stopPython() {
  if (!current) return;
  worker.terminate();
  worker = null;
  current.reject(new Error("Stopped."));
  current = null;
}
