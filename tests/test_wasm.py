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


def pqlab(*args: str) -> dict:
    out = subprocess.run(
        ["cargo", "run", "--quiet", "-p", "pqlab", "--", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
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
        calls.append({"call": "structure", "file": f})
        native.append(("structure", f))
        calls.append({"call": "schema", "file": f})
        native.append(("schema", f))
        for offset in (0, 4, size // 2, size - 8, size - 1):
            calls.append({"call": "interpret", "file": f, "offset": offset})
            native.append(("interpret", f, str(offset)))
    for columns, row in (([2, 3], -1), ([3], -1), ([0, 1, 2, 3, 4], 3), ([0, 4], -1), ([], -1)):
        calls.append({"call": "layouts", "options": {"columns": columns, "row": row}})
        args = ["layouts", "--columns", ",".join(map(str, columns))]
        if row >= 0:
            args += ["--row", str(row)]
        native.append(tuple(args))
    return calls, native


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
    browser = json.loads(out.stdout)
    assert len(browser) == len(native)
    for call, args, got in zip(calls, native, browser, strict=True):
        assert got == pqlab(*args), f"browser and native disagree on {call}"
