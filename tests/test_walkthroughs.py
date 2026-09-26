"""A chapter's walkthrough steps (walkthroughs/) run, in both languages, and say what is true.

A walkthrough is a few lines the chapter asks you to run and change before it builds the reader:
reading a file's bytes by hand, and then reading the same facts with a library (pyarrow, and the
``parquet`` crate in ``walkthroughs/libraries``, a workspace of its own so that the book's reader
keeps no dependencies). Each Python step has a Rust twin of the same name. Both run
from the repository's root, and both must print what pyarrow's manifest says about the fixture.
They print in their own language's idiom (``b'PAR1'`` and ``"PAR1"``), so the check is on the
facts in the output, derived here from the manifest, never on the text.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "walkthroughs" / "python"
RUST = ROOT / "walkthroughs" / "src" / "bin"
LIBRARIES = ROOT / "walkthroughs" / "libraries"


def rust_step(step: str) -> Path:
    """A Rust step's source: the walkthroughs crate's, or the library workspace's."""
    by_hand = RUST / f"{step}.rs"
    return by_hand if by_hand.exists() else LIBRARIES / "src" / "bin" / f"{step}.rs"


def rust_binary(step: str) -> Path:
    target = ROOT if (RUST / f"{step}.rs").exists() else LIBRARIES
    return target / "target" / "debug" / step


STEPS = sorted((p.parent.name, p.stem) for p in PYTHON.glob("*/*.py"))


def tiny():
    data = (ROOT / "fixtures" / "tiny.parquet").read_bytes()
    return data, json.loads((ROOT / "fixtures" / "tiny.json").read_text())


def facts(chapter: str, step: str) -> list[str]:
    """What a step's output must contain, from the fixture and pyarrow's manifest."""
    data, manifest = tiny()
    n, length = len(data), manifest["footer_length"]
    start = n - 8 - length
    damaged = bytearray(data)
    damaged[-7] = 0xFF
    damaged_length = int.from_bytes(damaged[-8:-4], "little")
    known = {
        ("anatomy_of_a_parquet_file", "first_bytes"): [f"{manifest['file_size']} bytes", "PAR1"],
        ("anatomy_of_a_parquet_file", "last_bytes"): ["PAR1", "true"],
        ("anatomy_of_a_parquet_file", "footer_length"): [data[-8:-4].hex(" "), str(length)],
        ("anatomy_of_a_parquet_file", "footer_start"): [
            f"byte {start}",
            f"{length} bytes long",
            data[start : start + 8].hex(" "),
        ],
        ("anatomy_of_a_parquet_file", "damaged_length"): [str(damaged_length), str(n - 8 - damaged_length)],
        ("anatomy_of_a_parquet_file", "footer_with_a_library"): [
            f"footer length: {length}",
            f"rows: {manifest['num_rows']} in {manifest['num_row_groups']} row group",
            *(
                f"column chunk {c['path']}: bytes {start} to {start + c['total_compressed_size']}"
                for c in manifest["row_groups"][0]["columns"]
                for start in [c["dictionary_page_offset"] or c["data_page_offset"]]
            ),
        ],
    }
    known.update(changes_facts())
    assert (chapter, step) in known, f"add what {chapter}/{step} must print to tests/test_walkthroughs.py"
    return known[(chapter, step)]


def changes_facts() -> dict:
    """What ch15's steps must print, from the snapshots the generator wrote and pyarrow's reading
    of the files."""
    import pyarrow.parquet as pq

    table = ROOT / "fixtures" / "changes"
    snapshots = json.loads((table / "_snapshots.json").read_text())["snapshots"]
    day = next(s for s in snapshots if s["id"] == "after-a-day")
    deleted = json.loads((ROOT / "fixtures" / "changes.json").read_text())["deleted"]
    part = next(f for f in day["data_files"] if f["order_id"][0] <= 300 <= f["order_id"][1])
    names = [d for d in day["delete_files"] if d["data_file"] == part["path"]]
    first = pq.read_table(table / day["delete_files"][0]["path"]).to_pylist()[0]
    ids = pq.read_table(table / first["file_path"])["order_id"].to_pylist()
    gone = [p for d in names for p in pq.read_table(table / d["path"])["pos"].to_pylist()]
    amounts = pq.read_table(table / part["path"])["amount_cents"].to_pylist()
    live = [a for i, a in enumerate(amounts) if i not in gone]
    return {
        ("changing_a_table", "table_files"): [
            f"{len(day['data_files'])} data files and {len(day['delete_files'])} delete files",
            *(
                f"{f['path']}: {f['record_count']} rows in {f['file_size']} bytes, "
                f"{f['file_size'] // f['record_count']} bytes a row"
                for f in day["data_files"]
            ),
        ],
        ("changing_a_table", "find_the_file"): [
            f"order 300 can only be in {part['path']}",
            "may remove it: " + ", ".join(d["path"] for d in names),
        ],
        ("changing_a_table", "read_a_delete_file"): [
            f"row {first['pos']} of {first['file_path']} is deleted: order {ids[first['pos']]}",
            f"order {deleted[0]}",
        ],
        ("changing_a_table", "deletes_with_a_library"): [
            f"{part['path']} holds {len(amounts)} rows; {len(gone)} are deleted; {len(live)} are live",
            f"their amounts sum to {sum(live)}",
        ],
    }


@pytest.fixture(scope="module")
def built():
    subprocess.run(["cargo", "build", "--quiet", "-p", "walkthroughs"], cwd=ROOT, check=True)
    subprocess.run(["cargo", "build", "--quiet"], cwd=LIBRARIES, check=True)


def test_every_step_has_a_twin():
    python = {step for _, step in STEPS}
    rust = {p.stem for p in [*RUST.glob("*.rs"), *(LIBRARIES / "src" / "bin").glob("*.rs")]}
    assert python == rust, f"only in Python: {python - rust}; only in Rust: {rust - python}"


@pytest.mark.parametrize(("chapter", "step"), STEPS, ids=[f"{c}/{s}" for c, s in STEPS])
def test_a_step_prints_the_same_facts_in_both_languages(built, chapter, step):
    py = subprocess.run(
        [sys.executable, str(PYTHON / chapter / f"{step}.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rs = subprocess.run([str(rust_binary(step))], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for fact in facts(chapter, step):
        assert fact in py.replace("True", "true"), f"Python {step} should print {fact!r}:\n{py}"
        assert fact in rs, f"Rust {step} should print {fact!r}:\n{rs}"


@pytest.mark.parametrize(("chapter", "step"), STEPS, ids=[f"{c}/{s}" for c, s in STEPS])
def test_a_step_is_in_its_chapter_in_both_languages(chapter, step):
    text = (ROOT / "chapters" / f"{chapter}.md").read_text()
    python = f"```{{literalinclude}} ../walkthroughs/python/{chapter}/{step}.py"
    rust = f"```{{literalinclude}} ../{rust_step(step).relative_to(ROOT)}"
    assert python in text and rust in text, f"quote {step} in both languages in chapters/{chapter}.md"
    # The two sit in one tab set, Python first.
    between = text[text.index(python) : text.index(rust)]
    assert ":sync: rust" in between and "::::" not in between.replace("::::{tab-set}", "")
    assert re.search(r"::::\{tab-set\}\s*:::\{tab-item\} Python", text[: text.index(python)][-200:])
