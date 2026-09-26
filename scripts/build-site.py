#!/usr/bin/env python3
"""The book as static pages, rendered from MyST's parse rather than MyST's theme.

    python3 scripts/build-site.py                 # every page, into _build/html/
    python3 scripts/build-site.py --out DIR

This is the published site, not a preview of one: the deploy runs this file against the same
parse ``make check`` does. It rests on three facts.

**MyST parses; this repository renders.** ``myst build --strict`` without ``--html`` produces the
AST and resolves every cross-reference, offline. ``tools/render.py`` walks the AST and raises on
anything it does not know. This file wraps the result in the site's chrome and writes it.

**The page is not somebody else's application.** Nothing hydrates, so the lab's script can own
the parts of the page it mounts into.

**Every URL is relative.** Pages are flat, and every asset is addressed from the page, so the
site works at a domain root, under a GitHub Pages project path, or opened from a disk.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import render as renderer  # noqa: E402
from tools.outline import APPENDICES, CHAPTERS, PARTS, UNWRITTEN  # noqa: E402

CONTENT = ROOT / "_build" / "site" / "content"
WASM = ROOT / "target" / "wasm32-unknown-unknown" / "release" / "parquet_lab_wasm.wasm"
TITLE = "Parquet, byte by byte"
SUBTITLE = "Build a Parquet reader while you read about one"


def page_list() -> list[dict]:
    """Every page, in reading order, with what the chrome needs to know about it."""
    pages = [{"source": "index.md", "href": "index.html", "title": "Preface", "label": None}]
    for part in PARTS:
        pages.append(
            {
                "source": part.path,
                "href": f"{part.slug.replace('_', '-')}.html",
                "title": part.title,
                "label": None,
            }
        )
        for c in CHAPTERS:
            if c.part == part.title:
                pages.append(
                    {
                        "source": c.path,
                        "href": f"{c.anchor}.html",
                        "title": c.title,
                        "label": c.label,
                        "chapter": c,
                    }
                )
    for a in APPENDICES:
        pages.append({"source": a.path, "href": f"{a.anchor}.html", "title": a.title, "label": a.label})
    return pages


def load_parse() -> dict[str, dict]:
    if not CONTENT.exists():
        sys.exit("no MyST parse at _build/site/content; run `myst build --strict` first")
    by_source = {}
    for path in CONTENT.glob("*.json"):
        data = json.loads(path.read_text())
        by_source[data["location"].lstrip("/")] = data
    return by_source


def is_unwritten(source: str) -> bool:
    return UNWRITTEN in (ROOT / source).read_text()


def nav_html(pages: list[dict], here: str) -> str:
    out = ['<nav class="nav" id="nav" aria-label="Chapters"><ol>']
    for p in pages:
        cls = ["here"] if p["href"] == here else []
        if p.get("chapter") is not None and is_unwritten(p["source"]):
            cls.append("unwritten")
        c = f' class="{" ".join(cls)}"' if cls else ""
        aria = ' aria-current="page"' if p["href"] == here else ""
        if p["source"].startswith("parts/"):
            out.append(f'<li class="part"><a href="{p["href"]}"{aria}>{html.escape(p["title"])}</a></li>')
        elif p["label"]:
            num = p["label"].replace("Appendix ", "").replace("ch", "")
            out.append(
                f'<li><a href="{p["href"]}"{c}{aria}><span class="num">{html.escape(num)}</span>'
                f"{html.escape(p['title'])}</a></li>"
            )
        else:
            out.append(f'<li><a href="{p["href"]}"{c}{aria}>{html.escape(p["title"])}</a></li>')
    out.append("</ol></nav>")
    return "".join(out)


def toc_html(mdast: dict) -> str:
    items = []
    for node in walk(mdast):
        if node.get("type") == "heading" and node.get("depth") in (2, 3):
            hid = renderer.heading_id(node)
            items.append(
                f'<li class="d{node["depth"]}"><a href="#{html.escape(hid)}">'
                f"{html.escape(renderer.text_of(node))}</a></li>"
            )
    if not items:
        return '<aside class="toc"></aside>'
    return (
        f'<aside class="toc" aria-label="On this page"><p>On this page</p><ol>{"".join(items)}</ol></aside>'
    )


def walk(node):
    if isinstance(node, dict):
        yield node
        for c in node.get("children", []):
            yield from walk(c)


def normalise_headings(mdast: dict) -> None:
    """Make the shallowest section heading an ``h2``: the page title is the only ``h1``.

    MyST drops a leading heading that repeats the frontmatter title and leaves the sections at
    depth 2. A page written without that heading would have its sections one level higher, so
    this moves them rather than trusting every author to write the same way.
    """
    depths = [n["depth"] for n in walk(mdast) if n.get("type") == "heading"]
    if not depths:
        return
    shift = 2 - min(depths)
    for n in walk(mdast):
        if n.get("type") == "heading":
            n["depth"] = max(2, min(6, n["depth"] + shift))


def commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "uncommitted"


HEAD_SCRIPT = r"""<script>
(() => {
  const root = document.documentElement;
  let theme = "system";
  try { const kept = localStorage.getItem("theme"); if (kept === "light" || kept === "dark") theme = kept; } catch (e) {}
  const apply = () => {
    if (theme === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
  };
  apply();
  // The language the book's code is shown in: Python unless the reader chose Rust. Every tab set
  // on every page follows it; the stylesheet hides the other language's panels.
  let code = "python";
  try { if (localStorage.getItem("code-language") === "rust") code = "rust"; } catch (e) {}
  root.setAttribute("data-code", code);
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".tab-bar button[data-code]");
    if (!b) return;
    const top = b.getBoundingClientRect().top;
    root.setAttribute("data-code", b.dataset.code);
    try { localStorage.setItem("code-language", b.dataset.code); } catch (e) {}
    // Keep the clicked tab where it was: panels above it may change height.
    scrollBy(0, b.getBoundingClientRect().top - top);
  });
  document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("theme");
    const names = { system: "System", light: "Light", dark: "Dark" };
    const order = ["system", "light", "dark"];
    const show = () => { button.textContent = names[theme]; button.setAttribute("aria-label", `Colours: ${names[theme]}`); };
    button.hidden = false;
    show();
    button.addEventListener("click", () => {
      theme = order[(order.indexOf(theme) + 1) % order.length];
      try { if (theme === "system") localStorage.removeItem("theme"); else localStorage.setItem("theme", theme); } catch (e) {}
      apply(); show();
    });
    document.getElementById("menu").addEventListener("click", () => document.body.classList.toggle("nav-open"));
  });
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  }
})();
</script>"""


def page_html(
    p: dict, body: str, nav: str, toc: str, prev: dict | None, nxt: dict | None, stamp: str, has_lab: bool
) -> str:
    chapter = p.get("chapter")
    if p["label"]:
        h1 = f'<h1><span class="label">{html.escape(p["label"])}</span>{html.escape(p["title"])}</h1>'
    else:
        h1 = f"<h1>{html.escape(p['title'])}</h1>"
    builds = ""
    if chapter is not None:
        builds = f'<p class="builds"><strong>What you build:</strong> {html.escape(chapter.builds)}</p>'

    def link(q, cls, word):
        if q is None:
            return ""
        label = f"{q['label']} · " if q["label"] else ""
        return (
            f'<a class="{cls}" href="{q["href"]}"><small>{word}</small>{html.escape(label + q["title"])}</a>'
        )

    lab = (
        '<link rel="stylesheet" href="lab/lab.css"><script type="module" src="lab/lab.js"></script>'
        if has_lab
        else ""
    )
    title = f"{p['label']} · {p['title']}" if p["label"] else p["title"]
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {TITLE}</title>
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="book.css">
{lab}
{HEAD_SCRIPT}
</head>
<body>
<header class="top">
<button id="menu" type="button" aria-controls="nav">Chapters</button>
<a class="brand" href="index.html">{TITLE} <span>· {SUBTITLE}</span></a>
<button id="theme" type="button" hidden>System</button>
</header>
<div class="layout">
{nav}
<main id="main"><article class="page">
{h1}
{builds}
{body}
<nav class="prevnext" aria-label="Previous and next">{link(prev, "prev", "Previous")}{link(nxt, "next", "Next")}</nav>
<p class="stamp">{html.escape(stamp)}</p>
</article></main>
{toc}
</div>
</body>
</html>
"""


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect width="32" height="32" rx="6" fill="#35648f"/>
<rect x="6" y="7" width="4" height="18" rx="1" fill="#fff"/>
<rect x="12" y="7" width="4" height="18" rx="1" fill="#fff" opacity=".8"/>
<rect x="18" y="7" width="4" height="18" rx="1" fill="#fff" opacity=".6"/>
<rect x="24" y="7" width="2.5" height="18" rx="1" fill="#fff" opacity=".4"/>
</svg>
"""


def service_worker(files: list[str], version: str) -> str:
    """Keep every file of the site on first visit, so the book reads with no network after it.

    The list is every file the build wrote, and the cache name carries a hash of their contents,
    so a new deploy replaces the old copy instead of mixing with it.
    """
    return f"""// Written by scripts/build-site.py. Keeps the whole book for offline reading.
const CACHE = "parquet-book-{version}";
const FILES = {json.dumps(files)};
self.addEventListener("install", (e) => {{
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
}});
self.addEventListener("activate", (e) => {{
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
}});
self.addEventListener("fetch", (e) => {{
  // Only the book's own files: Pyodide, fetched from a CDN for the labs' Python engine, is
  // cached by the browser as any other download.
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(caches.match(e.request, {{ ignoreSearch: true }}).then((hit) => hit || fetch(e.request)));
}});
"""


def build(out: Path) -> None:
    parse = load_parse()
    pages = page_list()
    missing = [p["source"] for p in pages if p["source"] not in parse]
    if missing:
        sys.exit(f"MyST produced no parse for: {', '.join(missing)}. Is each page in myst.yml's toc?")
    renderer.PAGES.clear()
    for p in pages:
        renderer.PAGES[parse[p["source"]]["slug"]] = p["href"]

    if out.exists():
        shutil.rmtree(out)
    (out / "lab").mkdir(parents=True)
    (out / "fixtures").mkdir()

    stamp = f"Built from commit {commit()}."
    for i, p in enumerate(pages):
        mdast = parse[p["source"]]["mdast"]
        normalise_headings(mdast)
        body = renderer.render_page(mdast)
        # The lab script also puts buttons on the commands a page prints: Run, or Open in Codespaces.
        has_lab = any(m in body for m in ('class="lab"', 'class="workbench"', "python3 -m ", "cargo "))
        text = page_html(
            p,
            body,
            nav_html(pages, p["href"]),
            toc_html(mdast),
            pages[i - 1] if i > 0 else None,
            pages[i + 1] if i + 1 < len(pages) else None,
            stamp,
            has_lab,
        )
        (out / p["href"]).write_text(text)

    shutil.copy(ROOT / "web" / "book.css", out / "book.css")
    (out / "favicon.svg").write_text(FAVICON)
    for f in (ROOT / "web" / "lab").iterdir():
        if f.suffix in (".js", ".css"):
            shutil.copy(f, out / "lab" / f.name)
    if not WASM.exists():
        sys.exit(f"{WASM.relative_to(ROOT)} is missing; run `make wasm` first")
    shutil.copy(WASM, out / "lab" / "parquet_lab.wasm")
    # The Python reader, for the labs' Python engine: the same files the tests import.
    package = ROOT / "python" / "parquet_lab"
    (out / "lab" / "py" / "parquet_lab").mkdir(parents=True)
    modules = sorted(f.name for f in package.glob("*.py"))
    for name in modules:
        shutil.copy(package / name, out / "lab" / "py" / "parquet_lab" / name)
    # Which labs the Python engine can run: the lab offers the choice only for those.
    tree = ast.parse((package / "browser.py").read_text())
    experiments = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "EXPERIMENTS"
    )
    # The problems and their graders, for the page's workbench, which runs them under Pyodide
    # exactly as `pytest --problems` runs them at a desk.
    exercises = ROOT / "exercises" / "python"
    problems = sorted(
        str(f.relative_to(exercises)) for f in exercises.rglob("*.py") if "__pycache__" not in f.parts
    )
    for name in problems:
        (out / "lab" / "py" / "exercises" / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(exercises / name, out / "lab" / "py" / "exercises" / name)
    # The Python reader's own tests, and the pytest configuration, for the Run buttons on
    # `python3 -m pytest python/tests …`.
    tests = sorted(f.name for f in (ROOT / "python" / "tests").glob("*.py"))
    (out / "lab" / "py" / "tests").mkdir()
    for name in tests:
        shutil.copy(ROOT / "python" / "tests" / name, out / "lab" / "py" / "tests" / name)
    shutil.copy(ROOT / "pyproject.toml", out / "lab" / "py" / "pyproject.toml")
    # Every fixture, with the manifest pyarrow wrote about it: the graders read both. ch14's
    # table keeps its directories.
    for f in sorted((ROOT / "fixtures").glob("*")):
        if f.suffix in (".parquet", ".json"):
            shutil.copy(f, out / "fixtures" / f.name)
    shutil.copytree(ROOT / "fixtures" / "table", out / "fixtures" / "table")
    fixtures = sorted(
        str(f.relative_to(out / "fixtures")) for f in (out / "fixtures").rglob("*") if f.is_file()
    )
    (out / "lab" / "py" / "package.json").write_text(
        json.dumps(
            {
                "modules": modules,
                "experiments": list(experiments),
                "exercises": problems,
                "tests": tests,
                "fixtures": fixtures,
            }
        )
    )
    (out / ".nojekyll").write_text("")

    files = sorted(str(f.relative_to(out)) for f in out.rglob("*") if f.is_file() and f.name != ".nojekyll")
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.encode())
        digest.update((out / f).read_bytes())
    (out / "sw.js").write_text(service_worker(["./", *files], digest.hexdigest()[:12]))
    print(f"wrote {len(pages)} pages and {len(files) - len(pages)} assets to {out.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "_build" / "html"))
    args = parser.parse_args()
    build(Path(args.out).resolve())


if __name__ == "__main__":
    main()
