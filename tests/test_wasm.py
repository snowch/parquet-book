"""The browser and the command line give identical answers, because they run the same code.

Every call the pages make into the WebAssembly reader is made here twice: through the WASM build,
under Node, with the loader the pages use (``web/lab/wasm.js``), and natively through ``pqlab``.
The JSON must match exactly. If it ever does not, the browser is showing something the tests
never checked.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WASM = ROOT / "target" / "wasm32-unknown-unknown" / "release" / "parquet_lab_wasm.wasm"
FIXTURES = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "fixtures").glob("*.parquet"))

pytestmark = [
    pytest.mark.skipif(not WASM.exists(), reason="WASM not built; run `make wasm`"),
    pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed"),
]

SIZE_FLAG = {"head": "head", "known": "known", "suffix": "suffix"}


PQLAB = ROOT / "target" / "debug" / "pqlab"


@pytest.fixture(scope="module", autouse=True)
def built_pqlab():
    # Build once, then run the binary: hundreds of `cargo run`s would each check the build.
    subprocess.run(["cargo", "build", "--quiet", "-p", "pqlab"], cwd=ROOT, check=True)


def pqlab(*args: str) -> dict:
    out = subprocess.run([str(PQLAB), *args], cwd=ROOT, capture_output=True, text=True)
    return json.loads(out.stdout)


def cases():
    calls, native = [], []
    for f in FIXTURES:
        size = (ROOT / f).stat().st_size
        for mode in ("head", "known", "suffix"):
            for prefetch in (8, 300, 65536):
                for latency, bandwidth in ((20000, 100_000_000), (0, 0), (150000, 1_000_000)):
                    calls.append(
                        {
                            "call": "footer",
                            "file": f,
                            "options": {
                                "size": mode,
                                "prefetch": prefetch,
                                "latencyUs": latency,
                                "bandwidth": bandwidth,
                            },
                        }
                    )
                    native.append(
                        (
                            "footer",
                            f,
                            "--size",
                            SIZE_FLAG[mode],
                            "--prefetch",
                            str(prefetch),
                            "--latency-us",
                            str(latency),
                            "--bandwidth",
                            str(bandwidth),
                            "--json",
                        )
                    )
        calls.append({"call": "encryption", "file": f})
        native.append(("encryption", f))
        calls.append({"call": "structure", "file": f})
        native.append(("structure", f))
        calls.append({"call": "schema", "file": f})
        native.append(("schema", f))
        for column in range(12):
            calls.append({"call": "levels", "file": f, "column": column})
            native.append(("levels", f, str(column)))
            calls.append({"call": "encodings", "file": f, "column": column})
            native.append(("encodings", f, str(column)))
            calls.append({"call": "pages", "file": f, "column": column})
            native.append(("pages", f, str(column)))
            calls.append({"call": "compression", "file": f, "column": column})
            native.append(("compression", f, str(column)))
        for row_group in range(3):
            for column in range(0, 12, 2):
                calls.append({"call": "statistics", "file": f, "row_group": row_group, "column": column})
                native.append(("statistics", f, str(row_group), str(column)))
        if "pruning" in f or f.endswith("tiny.parquet"):
            for where, strat, extra in (
                (
                    None,
                    {"footer": "head", "prefetch": 8, "connections": 1, "gap": None},
                    ["--size", "head", "--prefetch", "8", "--chunks"],
                ),
                (
                    {"column": 0, "op": "=", "value": "431"},
                    {"footer": "suffix", "prefetch": 8192, "connections": 4, "gap": 1024},
                    ["--size", "suffix", "--prefetch", "8192", "--connections", "4", "--gap", "1024"],
                ),
                (
                    {"column": 2, "op": "is null", "value": ""},
                    {"footer": "head", "prefetch": 8, "connections": 2, "gap": None},
                    ["--size", "head", "--prefetch", "8", "--connections", "2"],
                ),
            ):
                s = {
                    **strat,
                    "statistics": True,
                    "bloom": True,
                    "pageIndex": True,
                    "wholeChunks": "--chunks" in extra,
                    "latencyUs": 20000,
                    "bandwidth": 100000000,
                }
                calls.append({"call": "scan", "file": f, "columns": [], "where": where, "strategy": s})
                args = ["scan", f] + extra
                if where:
                    args += ["--where", str(where["column"]), where["op"]] + (
                        [where["value"]] if where["value"] else []
                    )
                native.append(tuple(args))
        if "pruning" in f or f.endswith("statistics.parquet"):
            for column, op, value, mechanisms in (
                (0, "=", "431", 7),
                (0, ">", "700", 1),
                (1, "=", "424242", 3),
                (1, "=", "7", 7),
                (2, "is null", "", 7),
                (2, "=", "SE", 5),
                (3, "<=", "150", 4),
                (0, "!=", "5", 0),
            ):
                calls.append(
                    {
                        "call": "skipping",
                        "file": f,
                        "column": column,
                        "op": op,
                        "value": value,
                        "mechanisms": mechanisms,
                    }
                )
                flags = ",".join(
                    n for bit, n in ((1, "statistics"), (2, "bloom"), (4, "page-index")) if mechanisms & bit
                )
                native.append(("skipping", f, str(column), op, value, "--use", flags))
        for page in range(4):
            calls.append({"call": "compression", "file": f, "column": 1, "page": page})
            native.append(("compression", f, "1", str(page)))
        for offset in (0, 4, size // 2, size - 8, size - 1):
            calls.append({"call": "interpret", "file": f, "offset": offset})
            native.append(("interpret", f, str(offset)))
    for q in json.loads((ROOT / "fixtures" / "queries.json").read_text()):
        if q["file"] == "table":
            continue
        f = f"fixtures/{q['file']}"
        calls.append({"call": "query", "file": f, "sql": q["sql"]})
        native.append(("query", f, q["sql"]))
    listing = json.loads((ROOT / "fixtures" / "table.json").read_text())
    keys = [o["key"] for o in listing["objects"]]
    for q in json.loads((ROOT / "fixtures" / "queries.json").read_text()):
        if q["file"] != "table":
            continue
        for discovery, flag in (("list", "list"), ("prune", "prune"), ("log", "log")):
            calls.append({"call": "table", "keys": keys, "sql": q["sql"], "discovery": discovery})
            native.append(("table", "fixtures/table.json", q["sql"], "--discovery", flag))
    listing = json.loads((ROOT / "fixtures" / "changes.json").read_text())
    keys = [o["key"] for o in listing["objects"]]
    for snapshot in listing["snapshots"]:
        calls.append({"call": "changes", "keys": keys, "snapshot": snapshot, "op": "scan", "options": {}})
        native.append(("changes", "fixtures/changes.json", "--snapshot", snapshot))
        for key in (250, 300, 805):
            calls.append(
                {
                    "call": "changes",
                    "keys": keys,
                    "snapshot": snapshot,
                    "op": "lookup",
                    "options": {"key": key},
                }
            )
            native.append(("changes", "fixtures/changes.json", "--snapshot", snapshot, "--lookup", str(key)))
        calls.append({"call": "changes", "keys": keys, "snapshot": snapshot, "op": "compact", "options": {}})
        native.append(("changes", "fixtures/changes.json", "--snapshot", snapshot, "--compact"))
    calls.append({"call": "query", "file": "fixtures/tiny.parquet", "sql": "SELECT nonsense FROM"})
    native.append(("query", "fixtures/tiny.parquet", "SELECT nonsense FROM"))
    for columns, row in (([2, 3], -1), ([3], -1), ([0, 1, 2, 3, 4], 3), ([0, 4], -1), ([], -1)):
        calls.append({"call": "layouts", "options": {"columns": columns, "row": row}})
        args = ["layouts", "--columns", ",".join(map(str, columns))]
        if row >= 0:
            args += ["--row", str(row)]
        native.append(tuple(args))
    return calls, native


def _numbers(v):
    """JSON as a browser reads it. The reader writes every integer above 2^53 as a string, so a
    bare number that large can only be a float, which ``JSON.stringify`` writes without an
    exponent (1e20 as 100000000000000000000) and Python then parses as an exact integer."""
    if isinstance(v, dict):
        return {k: _numbers(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_numbers(x) for x in v]
    if isinstance(v, int) and not isinstance(v, bool) and abs(v) > 2**53:
        return float(v)
    return v


def test_every_browser_call_matches_the_native_reader(tmp_path):
    calls, native = cases()
    spec = tmp_path / "calls.json"
    spec.write_text(json.dumps(calls))
    out = subprocess.run(
        ["node", str(ROOT / "tests" / "wasm_calls.mjs"), str(WASM), str(spec)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    browser = _numbers(json.loads(out.stdout))
    assert len(browser) == len(native)
    for call, args, got in zip(calls, native, browser, strict=True):
        assert got == _numbers(pqlab(*args)), f"browser and native disagree on {call}"


# Commands the book prints for the Rust reader, and some that fail, as the page's Run buttons send
# them to `pl_cli`.
CLI = [
    ["inspect", "fixtures/tiny.parquet"],
    ["footer", "fixtures/tiny.parquet"],
    ["footer", "fixtures/tiny.parquet", "--json"],
    ["footer", "fixtures/tiny.parquet", "--size", "suffix", "--prefetch", "65536", "--json"],
    ["interpret", "fixtures/tiny.parquet", "629"],
    ["query", "fixtures/table/country=UK/part-0.parquet", "SELECT country FROM orders"],
    [
        "table",
        "fixtures/table.json",
        "SELECT count(*) FROM orders WHERE country = 'UK'",
        "--discovery",
        "prune",
    ],
    ["scan", "fixtures/writing-baseline.parquet", "--where", "0", "=", "431"],
    ["changes", "fixtures/changes.json", "--snapshot", "after-a-day", "--lookup", "300"],
    ["levels", "fixtures/nested.parquet"],
    ["no-such-command"],
]


def test_pqlab_runs_in_the_page_as_it_does_at_a_desk(tmp_path):
    """A Run button on `cargo run -p pqlab -- ARGS` runs the same code, compiled to WebAssembly:
    it prints what the binary prints, to the byte, and exits as it exits."""
    spec = tmp_path / "calls.json"
    spec.write_text(json.dumps([{"call": "cli", "args": args} for args in CLI]))
    out = subprocess.run(
        ["node", str(ROOT / "tests" / "wasm_calls.mjs"), str(WASM), str(spec)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    for args, got in zip(CLI, json.loads(out.stdout), strict=True):
        native = subprocess.run([str(PQLAB), *args], cwd=ROOT, capture_output=True, text=True)
        assert (got["stdout"], got["stderr"], got["exit"]) == (
            native.stdout,
            native.stderr,
            native.returncode,
        ), args
