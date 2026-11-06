"""Run the quoted Python examples so the book can show their answers without a runtime.

The saved results are build inputs, never hand-written answers. CI executes every example and
its named variations again. Rust and Python already have independent fact checks in
``tests/test_walkthroughs.py``; the displayed output uses Python's spelling of those facts.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "walkthroughs/_generated/results.json"

# Each substitution is an edit the surrounding prose invites. Require one exact match so a
# refactor cannot silently turn a comparison into another run of the default example.
VARIATIONS = {
    "open_with_the_reader": [
        (
            "Find the size with a suffix request",
            "The suffix response supplies the file size, so the HEAD request disappears.",
            [("size=Head(), prefetch=8", "size=SuffixRange(), prefetch=8")],
        ),
        (
            "Bring the footer with the trailer",
            "A larger suffix read includes the footer. Fewer requests now return more bytes.",
            [("size=Head(), prefetch=8", "size=SuffixRange(), prefetch=512")],
        ),
    ],
    "same_bytes_two_ways": [
        (
            "Read the decimal in the wrong byte order",
            "The date and timestamp are unchanged. Reversing the decimal's byte order produces a different amount, because its byte array uses big-endian order.",
            [('int.from_bytes(raw, "big", signed=True)', 'int.from_bytes(raw, "little", signed=True)')],
        ),
    ],
    "delta_header": [
        (
            "A counter: order_id",
            "Every delta equals the minimum delta. The adjusted deltas are all zero, so their bit width is zero.",
            [("column = 1  # ordered_at", "column = 0  # ordered_at")],
        ),
    ],
    "walk_the_pages": [
        (
            "The same rows in version-2 pages",
            "Version-2 headers also report row and null counts. The dictionary still occupies a separate page.",
            [('"fixtures/pages.parquet"', '"fixtures/pages-v2.parquet"')],
        ),
    ],
    "every_codec_one_page": [
        (
            "Compress noisy distances instead of country codes",
            "The codecs still recover the same bytes, but noisy values leave less repetition to remove.",
            [("column = 1", "column = 5")],
        ),
    ],
    "signed_or_unsigned": [
        (
            "A signed column: delta",
            "For this column, use the signed interpretation. The logical type decides how to interpret the same physical integer storage.",
            [("column = 1", "column = 2")],
        ),
    ],
    "row_group_bounds": [
        (
            "Shuffle the same orders",
            "Every row group's range now admits the wanted value. Statistics cannot prove that any group is safe to skip.",
            [('path = "fixtures/pruning-sorted.parquet"', 'path = "fixtures/pruning-shuffled.parquet"')],
        ),
        (
            "The last order in a band",
            "The maximum is inclusive, so the group ending at the wanted value must be read.",
            [("wanted = 431", "wanted = 200")],
        ),
        (
            "The first order in the next band",
            "Moving past that maximum changes which group must be read.",
            [("wanted = 431", "wanted = 201")],
        ),
    ],
    "query_every_file": [
        (
            "Filter on country instead of order_id",
            "The layout sorted by country now prunes effectively. A useful sort order depends on the query.",
            [('(0, Op.EQ, "431")', '(3, Op.EQ, "FR")')],
        ),
    ],
    "run_a_query": [
        (
            "Count all rows without a filter",
            "The footer already holds the row counts. This query needs no column data.",
            [
                (
                    "SELECT country, count(*) FROM orders WHERE order_id < 300\n         GROUP BY country ORDER BY country",
                    "SELECT count(*) FROM orders",
                )
            ],
        ),
    ],
    "field_ids_by_hand": [
        (
            "Reuse an existing field id for channel",
            "The new name now selects the old status column. A field id carries identity, so reusing it changes what the column means.",
            [('7: "channel"', '5: "channel"')],
        ),
    ],
}


def source_digest(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


def edited(source: str, changes: list[tuple[str, str]]) -> str:
    for old, new in changes:
        if source.count(old) != 1:
            raise ValueError(f"comparison edit must match once: {old!r}")
        source = source.replace(old, new)
    return source


def execute(source: str) -> str:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "python"), "PYTHONHASHSEED": "0"}
    run = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return run.stdout


def result_for(path: Path) -> tuple[str, dict]:
    source = path.read_text()
    cases = []
    for title, explanation, changes in VARIATIONS.get(path.stem, []):
        cases.append(
            {
                "title": title,
                "explanation": explanation,
                "changes": changes,
                "stdout": execute(edited(source, changes)),
            }
        )
    return path.relative_to(ROOT).as_posix(), {
        "source_sha256": source_digest(source),
        "stdout": execute(source),
        "comparisons": cases,
    }


def generate() -> dict:
    paths = sorted((ROOT / "walkthroughs/python").glob("*/*.py"))
    unknown = set(VARIATIONS) - {p.stem for p in paths}
    if unknown:
        raise ValueError(f"comparisons refer to missing examples: {sorted(unknown)}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(result_for, paths))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = generate()
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not RESULTS.exists() or RESULTS.read_text() != text:
            print("Walkthrough results are stale. Run make figures and commit the results.")
            return 1
    else:
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(text)
    print(
        f"  {len(data)} walkthrough results and {sum(len(v['comparisons']) for v in data.values())} comparisons {'match' if args.check else 'written'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
