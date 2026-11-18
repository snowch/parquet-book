// The page's one Python worker (python-worker.js), shared by the problems workbenches and the Run
// buttons on commands. Runs queue: one at a time, in the order they were asked for.

import { savedAnswers } from "./answers.js";

let worker = null;
let queue = Promise.resolve();

/**
 * Run `argv` (["pytest", …], ["parquet_lab", …] or ["python", source, file name]) from the
 * repository's root, with `answers`
 * as the chapters' problem files. Resolves with {exit, output, tests, seconds}.
 */
export function runPython(argv, { answers = savedAnswers(), onStatus = () => {}, signal } = {}) {
  const stopped = new Error("Stopped.");
  if (signal?.aborted) return Promise.reject(stopped);
  let stopActive;
  let abort;
  const cancelled = new Promise((resolve, reject) => {
    abort = () => {
      stopActive?.();
      reject(stopped);
    };
    signal?.addEventListener("abort", abort, { once: true });
  });
  const job = queue.then(() => {
    if (signal?.aborted) return;
    return new Promise((resolve, reject) => {
      const active = (worker ||= new Worker(new URL("python-worker.js", import.meta.url), { type: "module" }));
      const discard = () => {
        active.terminate();
        worker = null;
      };
      // Stopping a queued run must leave the active run's worker alone.
      stopActive = () => {
        discard();
        reject(stopped);
      };
      active.onmessage = ({ data }) => {
        if (data.type === "status") return onStatus(data.text);
        stopActive = null;
        if (data.type === "result") resolve(data.result);
        else reject(new Error(data.message));
      };
      active.onerror = (e) => {
        stopActive = null;
        discard();
        reject(new Error(e.message || "the Python worker failed"));
      };
      active.postMessage({ argv, answers });
    });
  });
  queue = job.catch(() => {});
  return Promise.race([job, cancelled]).finally(() => signal?.removeEventListener("abort", abort));
}
