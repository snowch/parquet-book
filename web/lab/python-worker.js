// Python commands, run in a worker under Pyodide: a workbench's tests, and the commands a page
// prints in its Python tabs, each with a Run button (commands.js). A worker keeps the page
// responsive while they run, and lets a reader stop one.
//
// It lays out the repository as a desk has it (the reader and its tests, the problems and their
// graders, every fixture and its manifest, and pyproject.toml), changes to its root, and runs
// the command there: `python3 -m pytest …` through pytest.main, `python3 -m parquet_lab …`
// through runpy, and a chapter's walkthrough step (`python3 walkthroughs/…`) as its source. The
// files are the ones the repository's tests run; nothing about them is changed for the page.
// They use the book's reader as it ships, not any edits you made to it in the labs.
//
// Every chapter's stub is written on each run, as your saved answer or as the book ships it,
// because one chapter's problems can use another's, as they do at a desk (5.3 uses 4.1).

import { ROOT, fetchBytes, fetchText, packageList, readerSources, startPyodide, writeFile, writeReader } from "./pyodide.js";

const BASE = import.meta.url;

const RUNNER = `
import io, json, os, runpy, sys, time, traceback
from contextlib import redirect_stderr, redirect_stdout

import pytest

ROOT = "${ROOT}"
EXERCISES = f"{ROOT}/exercises/python"
STUBS = json.loads(STUBS_JSON)


class Collect:
    """Each test's outcome, as pytest reports it."""

    def __init__(self):
        self.tests = []

    def pytest_runtest_logreport(self, report):
        # A test's call decides it; a setup that fails or skips decides it before any call.
        if report.when != "call" and report.outcome == "passed":
            return
        message = ""
        if report.failed:
            crash = getattr(report.longrepr, "reprcrash", None)
            message = crash.message if crash else report.longreprtext.strip().splitlines()[-1]
        elif report.skipped and isinstance(report.longrepr, tuple):
            message = report.longrepr[2]
        self.tests.append({"name": report.nodeid.split("::")[-1], "outcome": report.outcome, "message": message})


def run(argv_json, answers_json):
    """Run \`argv\` from the repository's root: ["pytest", ...], ["parquet_lab", ...], or
    ["python", source, file name] for a walkthrough step."""
    argv, answers = json.loads(argv_json), json.loads(answers_json)
    for name, stub in STUBS.items():
        with open(f"{EXERCISES}/{name}.py", "w") as f:
            f.write(answers.get(name, stub))
    # Forget the last run's tests and stubs, so this run imports what is on disk now.
    tests = (f"{ROOT}/exercises", f"{ROOT}/python/tests")
    for name, module in list(sys.modules.items()):
        if (getattr(module, "__file__", None) or "").startswith(tests) or name.startswith("problems_"):
            del sys.modules[name]
    os.chdir(ROOT)
    collect = Collect()
    out = io.StringIO()
    start = time.perf_counter()
    with redirect_stdout(out), redirect_stderr(out):
        if argv[0] == "pytest":
            code = int(pytest.main(
                [*argv[1:], "--color=no", "--capture=sys", "-p", "no:cacheprovider"], plugins=[collect]
            ))
        elif argv[0] == "python":
            # A walkthrough step: its source (as the reader may have edited it) and its file name.
            try:
                exec(compile(argv[1], argv[2], "exec"), {"__name__": "__main__"})
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            except BaseException:
                traceback.print_exc()
                code = 1
        else:
            sys.argv = argv
            try:
                runpy.run_module("parquet_lab", run_name="__main__", alter_sys=True)
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            except Exception:
                traceback.print_exc()
                code = 1
    seconds = round(time.perf_counter() - start, 2)
    return json.dumps({"exit": code, "tests": collect.tests, "output": out.getvalue(), "seconds": seconds})
`;

let ready = null;

async function setup() {
  postMessage({ type: "status", text: "Loading Python and pytest in your browser (a few megabytes the first time)…" });
  const [pyodide, reader, list] = await Promise.all([startPyodide(), readerSources(BASE), packageList(BASE)]);
  pyodide.runPython("import sys; sys.dont_write_bytecode = True");
  await pyodide.loadPackage("pytest", { messageCallback: () => {} });
  postMessage({ type: "status", text: "Fetching the tests and the fixtures…" });
  writeReader(pyodide, reader);
  const [exercises, tests, pyproject, fixtures] = await Promise.all([
    Promise.all(list.exercises.map((name) => fetchText(new URL(`py/exercises/${name}`, BASE)))),
    Promise.all(list.tests.map((name) => fetchText(new URL(`py/tests/${name}`, BASE)))),
    fetchText(new URL("py/pyproject.toml", BASE)),
    Promise.all(list.fixtures.map((name) => fetchBytes(new URL(`../fixtures/${name}`, BASE)))),
  ]);
  list.exercises.forEach((name, i) => writeFile(pyodide, `${ROOT}/exercises/python/${name}`, exercises[i]));
  list.tests.forEach((name, i) => writeFile(pyodide, `${ROOT}/python/tests/${name}`, tests[i]));
  writeFile(pyodide, `${ROOT}/pyproject.toml`, pyproject);
  list.fixtures.forEach((name, i) => writeFile(pyodide, `${ROOT}/fixtures/${name}`, fixtures[i]));
  // The stubs as the book ships them: the chapters' own files, beside conftest.py.
  const stubs = Object.fromEntries(list.exercises.map((name, i) => [name, exercises[i]])
    .filter(([name]) => !name.includes("/") && name !== "conftest.py")
    .map(([name, text]) => [name.replace(/\.py$/, ""), text]));
  pyodide.globals.set("STUBS_JSON", JSON.stringify(stubs));
  pyodide.runPython(RUNNER);
  return pyodide.globals.get("run");
}

onmessage = async ({ data }) => {
  try {
    ready ||= setup();
    const run = await ready;
    postMessage({ type: "status", text: "Running…" });
    postMessage({ type: "result", result: JSON.parse(run(JSON.stringify(data.argv), JSON.stringify(data.answers))) });
  } catch (error) {
    // A run that failed to start (a network error, say) is tried afresh next time.
    if (!(await ready.then(() => true, () => false))) ready = null;
    postMessage({ type: "error", message: String(error.message || error) });
  }
};
