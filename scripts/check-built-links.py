#!/usr/bin/env python3
"""Fail if a built page links to a file or an anchor the build did not produce.

    python3 scripts/check-built-links.py _build/html

Every link in the site is relative, so the site works under any base path. This walks every
page, resolves every relative ``href`` and ``src`` against it, and checks that the file exists
and, for a ``#fragment``, that the target page has an element with that id. The lab's own
imports and fetches are checked too: a page that mounts an experiment must be able to reach
``lab/lab.js``, the WebAssembly module, and the fixtures it names.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.fixtures: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.links.append(a[key])
        for key in ("data-fixture", "data-fixtures"):
            if a.get(key):
                self.fixtures += [f.strip() for f in a[key].split(",") if f.strip()]


def main() -> int:
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/html").resolve()
    pages = {p: Links() for p in site.rglob("*.html")}
    for p, parser in pages.items():
        parser.feed(p.read_text())
    bad = []
    for page, parser in pages.items():
        for link in parser.links:
            u = urlparse(link)
            if u.scheme or link.startswith("//") or link.startswith("mailto:"):
                continue
            target = (page.parent / unquote(u.path)).resolve() if u.path else page
            if not target.is_file():
                bad.append(f"{page.relative_to(site)}: {link} -> no such file")
                continue
            if u.fragment and target.suffix == ".html" and u.fragment not in pages[target].ids:
                bad.append(f"{page.relative_to(site)}: {link} -> no element with id {u.fragment!r}")
        for fixture in parser.fixtures:
            if not (site / "fixtures" / fixture).is_file():
                bad.append(f"{page.relative_to(site)}: experiment needs fixtures/{fixture}, not built")
        if 'class="lab"' in page.read_text():
            for needed in ("lab/lab.js", "lab/parquet_lab.wasm", "lab/lab.css"):
                if not (site / needed).is_file():
                    bad.append(f"{page.relative_to(site)}: experiment needs {needed}, not built")
    js = "".join(p.read_text() for p in (site / "lab").glob("*.js"))
    for imported in re.findall(r'from "\./([\w.-]+)"', js):
        if not (site / "lab" / imported).is_file():
            bad.append(f"lab: imports {imported}, not built")
    if bad:
        print("Broken links in the built site:")
        for b in bad:
            print("  " + b)
        return 1
    print(f"  {len(pages)} pages, every link resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
