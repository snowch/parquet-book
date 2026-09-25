#!/usr/bin/env python3
"""Fail if a published page types a measured number into its prose.

    python3 scripts/verify-numbers.py

Every byte count, offset, request total and time in the book is computed by the reader: in a
generated fragment under ``chapters/_generated/``, included into the page, or live in an
experiment. A number typed into a sentence would be true on the day it was written and silently
wrong the day the reader or a fixture changed, so this script refuses them.

What it flags, in prose only (not code blocks, not directives, not inline code, not URLs):

- a number followed by a unit this book measures in: bytes, KB, KiB, MB, ms, requests, rows,
  row groups, pages, columns, values;
- any other integer of two or more digits, except a year, a chapter label, a problem number, or
  an RFC or section number in a citation.

Small counts written as words ("four bytes", "eight orders") pass. They are either format
constants the specification fixes, or counts of things on the page, and neither goes stale. A
number that must be typed can be exempted with ``% number-ok: <reason>`` on the line before its
paragraph, which covers the paragraph, where a reviewer will see the reason.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["index.md", "parts/*.md", "chapters/*.md", "appendices/*.md"]

UNIT = (
    r"(?:bytes?|B|KB|KiB|MB|MiB|GB|GiB|ms|µs|us|seconds?|requests?|rows?|row groups?|pages?"
    r"|columns?|values?)"
)
WITH_UNIT = re.compile(rf"(?<![\w.])\d[\d,._]*\s*{UNIT}\b")
BARE = re.compile(r"(?<![\w.#/-])\d{2,}(?![\w-])")
ALLOWED_BARE = re.compile(r"^(?:19|20)\d\d$")  # a year
INLINE_CODE = re.compile(r"`[^`]*`")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
CITATION = re.compile(r"\b(?:RFC|section|ch|Appendix|Part)\s*\d+", re.IGNORECASE)
#: A problem's number, "10.1", in its bold heading or after the word "problem".
PROBLEM = re.compile(r"(?:\*\*|\bproblems?\s+)\d+\.\d+", re.IGNORECASE)


def prose_lines(text: str):
    """Yield (line number, line) for the prose of a page, with exemptions applied."""
    in_front = text.startswith("---\n")
    fence = None
    exempt = False
    for n, line in enumerate(text.splitlines(), 1):
        if in_front:
            if n > 1 and line.strip() == "---":
                in_front = False
            continue
        stripped = line.strip()
        m = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence:
            if m and stripped.startswith(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        if stripped.startswith("%"):
            exempt = exempt or stripped.startswith("% number-ok:")
            continue
        if not stripped:
            exempt = False
        if stripped.startswith(":::") or stripped.startswith(":class:"):
            continue
        if re.match(r"^\(.*\)=$", stripped):
            continue
        if exempt:
            continue
        yield n, line


def problems(path: Path) -> list[str]:
    out = []
    for n, line in prose_lines(path.read_text()):
        text = INLINE_CODE.sub("", LINK_TARGET.sub("]", line))
        text = CITATION.sub("", text)
        text = PROBLEM.sub("", text)
        text = re.sub(r"^\s*(?:\d+\.|[-*])\s+", "", text)  # list markers
        text = re.sub(r"^#+\s", "", text)
        covered = []
        for m in WITH_UNIT.finditer(text):
            covered.append(m.span())
            out.append(f"{path.relative_to(ROOT)}:{n}: {m.group(0)!r} is a measured number in prose")
        for m in BARE.finditer(text):
            if any(a <= m.start() < b for a, b in covered):
                continue
            if not ALLOWED_BARE.match(m.group(0)):
                out.append(f"{path.relative_to(ROOT)}:{n}: {m.group(0)!r} is a number typed into prose")
    return out


def main() -> int:
    found = []
    for pattern in PAGES:
        for path in sorted(ROOT.glob(pattern)):
            found += problems(path)
    if found:
        print("Numbers typed into prose. Put them in a generated fragment (crates/pqlab/src/figures.rs)")
        print("and {include} it, or exempt the line with `% number-ok: <reason>` above it:")
        for f in found:
            print("  " + f)
        return 1
    print("  no measured numbers typed into prose")
    return 0


if __name__ == "__main__":
    sys.exit(main())
