// The problems workbench's test runner: a chapter's graders, run by pytest under Pyodide, in a
// worker so the page stays responsive while they run and a reader can stop them.
//
// It lays out the repository as a desk has it (the reader, the problems and their graders, every
// fixture and its manifest) and runs `pytest exercises/python/tests/test_<chapter>.py
// --problems`, the command the chapter prints. The graders are the files the repository's tests
// run; nothing about them is changed for the page. They compare your answers with the book's
// reader as it ships, not with any edits you made to it in the labs.
//
// Every chapter's stub is written on each run, as your saved answer or as the book ships it,
// because one chapter's problems can use another's, as they do at a desk (5.3 uses 4.1).

import { ROOT, fetchBytes, fetchText, packageList, readerSources, startPyodide, writeFile, writeReader } from "./pyodide.js";

const BASE = import.meta.url;

const RUNNER = `
import io, json, sys, time
from contextlib import redirect_stderr, redirect_stdout

import pytest

HERE = "${ROOT}/exercises/python"


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


STUBS = json.loads(STUBS_JSON)


def run(chapter, answers_json):
    answers = json.loads(answers_json)
    for name, stub in STUBS.items():
        with open(f"{HERE}/{name}.py", "w") as f:
            f.write(answers.get(name, stub))
    # Forget the last run's graders and stubs, so this run imports what is on disk now.
    for name, module in list(sys.modules.items()):
        if (getattr(module, "__file__", None) or "").startswith(HERE) or name.startswith("problems_"):
            del sys.modules[name]
    collect = Collect()
    out = io.StringIO()
    start = time.perf_counter()
    with redirect_stdout(out), redirect_stderr(out):
        code = pytest.main(
            [f"{HERE}/tests/test_{chapter}.py", "--problems", "-q", "--tb=short", "--color=no",
             "--capture=sys", "-p", "no:cacheprovider", f"--rootdir={HERE}"],
            plugins=[collect],
        )
    seconds = round(time.perf_counter() - start, 2)
    return json.dumps({"exit": int(code), "tests": collect.tests, "output": out.getvalue(), "seconds": seconds})
`;

let ready = null;

async function setup() {
  postMessage({ type: "status", text: "Loading Python and pytest in your browser (a few megabytes the first time)…" });
  const [pyodide, reader, list] = await Promise.all([startPyodide(), readerSources(BASE), packageList(BASE)]);
  pyodide.runPython("import sys; sys.dont_write_bytecode = True");
  await pyodide.loadPackage("pytest", { messageCallback: () => {} });
  postMessage({ type: "status", text: "Fetching the problems and the fixtures…" });
  writeReader(pyodide, reader);
  const [exercises, fixtures] = await Promise.all([
    Promise.all(list.exercises.map((name) => fetchText(new URL(`py/exercises/${name}`, BASE)))),
    Promise.all(list.fixtures.map((name) => fetchBytes(new URL(`../fixtures/${name}`, BASE)))),
  ]);
  list.exercises.forEach((name, i) => writeFile(pyodide, `${ROOT}/exercises/python/${name}`, exercises[i]));
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
    postMessage({ type: "status", text: "Running the tests…" });
    postMessage({ type: "result", result: JSON.parse(run(data.chapter, JSON.stringify(data.answers))) });
  } catch (error) {
    // A run that failed to start (a network error, say) is tried afresh next time.
    if (!(await ready.then(() => true, () => false))) ready = null;
    postMessage({ type: "error", message: String(error.message || error) });
  }
};
