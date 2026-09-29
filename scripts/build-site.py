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
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import render as renderer  # noqa: E402
from tools.outline import APPENDICES, CHAPTERS, PARTS, UNWRITTEN  # noqa: E402

CONTENT = ROOT / "_build" / "site" / "content"
WASM = ROOT / "target" / "wasm32-unknown-unknown" / "release" / "parquet_lab_wasm.wasm"
TITLE = "Parquet, byte by byte"
SUBTITLE = "Build a Parquet reader while you read about one"


def page_list() -> list[dict]:
    """Every page, in reading order, with what the chrome needs to know about it.

    The cover is published as index.html, where a reader arriving at the site lands, and the
    preface as preface.html. MyST names its pages by their place in the table of contents (the
    cover is its ``index``, the preface ``index-1``), so a link is resolved through MyST's slug,
    never through the name a page is published under (``build``).
    """
    pages = [
        {
            "source": "cover.md",
            "href": "index.html",
            "title": TITLE,
            "nav": "Cover",
            "label": None,
            "cover": True,
        },
        {"source": "index.md", "href": "preface.html", "title": "Preface", "label": None},
    ]
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
    appendices = False
    for p in pages:
        # The appendices get a heading as the parts do, though they have no page of their own.
        if p["source"].startswith("appendices/") and not appendices:
            appendices = True
            out.append('<li class="part">Appendices</li>')
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
            name = p.get("nav", p["title"])
            out.append(f'<li><a href="{p["href"]}"{c}{aria}>{html.escape(name)}</a></li>')
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
        return '<aside class="toc" id="toc"></aside>'
    return (
        f'<aside class="toc" id="toc" aria-label="On this page"><p>On this page</p>'
        f"<ol>{''.join(items)}</ol></aside>"
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
  });
  // Where the reader is: the page and how far down it, kept as they read. Opened from a home
  // screen, the book starts at the cover, index.html?resume (manifest.webmanifest), and goes
  // back there; the cover also offers a link back, however it was reached, since it is where a
  // returning reader lands.
  const page = location.pathname.split("/").pop() || "index.html";
  let last = null;
  try { last = JSON.parse(localStorage.getItem("last-read")); } catch (e) {}
  // A launch is the start URL (?resume), which only a home screen opens, or, since some home
  // screens open the page that was added rather than the manifest's start_url, the first page of
  // a session in an installed book. Not "no referrer": an installed app on Android sends none for
  // a link within the book, so the cover's own link was taken for a launch and went back to the
  // last page read.
  let first = true;
  try { first = !sessionStorage.getItem("in-book"); sessionStorage.setItem("in-book", "1"); } catch (e) {}
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const launched = new URLSearchParams(location.search).has("resume") || (standalone && first);
  if (page === "index.html" && launched && last && last.page && last.page !== "index.html") {
    try { sessionStorage.setItem("resume-scroll", String(last.y || 0)); } catch (e) {}
    location.replace(last.page);
    return;
  }
  // The cover is where the book starts anyway, so it is never the place to go back to. The
  // preface is read like any other page, so it is.
  const remember = () => {
    if (page === "index.html") return;
    try {
      localStorage.setItem("last-read", JSON.stringify({ page, title: document.title.split(" · ").slice(0, -1).join(" · "), y: Math.round(scrollY) }));
    } catch (e) {}
  };
  let pending = 0;
  addEventListener("scroll", () => { clearTimeout(pending); pending = setTimeout(remember, 400); }, { passive: true });
  addEventListener("pagehide", remember);
  addEventListener("load", () => {
    let y = null;
    try { y = sessionStorage.getItem("resume-scroll"); sessionStorage.removeItem("resume-scroll"); } catch (e) {}
    if (y === null) return remember();
    // Labs draw after load and push the page down, so the place is kept while the page settles:
    // for a few seconds, or until the reader scrolls for themselves.
    const target = Number(y);
    const until = Date.now() + 3000;
    let moved = false;
    for (const kind of ["wheel", "touchstart", "keydown"]) addEventListener(kind, () => { moved = true; }, { once: true, passive: true });
    const hold = () => { if (!moved && Date.now() < until) scrollTo(0, target); };
    hold();
    const watch = new ResizeObserver(hold);
    watch.observe(document.body);
    setTimeout(() => watch.disconnect(), 3000);
  });
  if (page === "index.html" && last && last.page && last.page !== "index.html") {
    document.addEventListener("DOMContentLoaded", () => {
      const h1 = document.querySelector("article.page h1");
      if (!h1) return;
      const p = document.createElement("p");
      p.className = "resume";
      const a = document.createElement("a");
      a.href = last.page;
      a.textContent = `Continue reading: ${last.title || last.page}`;
      a.addEventListener("click", () => { try { sessionStorage.setItem("resume-scroll", String(last.y || 0)); } catch (e) {} });
      p.append(a);
      h1.after(p);
    });
  }
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  }
})();
</script>"""


#: The two rails, and whether the reader wants them. Below 58rem the chapter list is closed and
#: the Chapters button opens it over the page; where there is room it is open, and the same
#: button closes it. The outline exists only from 72rem, so its button is there and nowhere
#: else. Either choice is remembered, per browser rather than per page, and read before the page
#: paints, so a reader who closed a rail does not watch it close again on every chapter.
#:
#: The outline also hides itself when showing it would leave the chapter narrower than what it
#: holds: the prose's measure, or, on a page with code, a hundred columns of it, which is where
#: the book's Rust stops. A media query cannot decide that, because `rem` inside one is 16px
#: whatever the reader's text size, so it is decided here, from the rails' own computed widths
#: (neither depends on whether the outline is shown, so this cannot chase itself) and a block of
#: a hundred zeros measured in whatever monospace font this device has. Closing the chapter list
#: gives the outline its room back.
RAILS = r"""<script>
(() => {
  const root = document.documentElement;
  try {
    if (localStorage.getItem("nav") === "closed") root.classList.add("nav-closed");
    if (localStorage.getItem("toc") === "closed") root.classList.add("toc-closed");
  } catch (e) {}
  const wide = matchMedia("(min-width: 58rem)"), roomy = matchMedia("(min-width: 72rem)");
  const px = (name) => parseFloat(getComputedStyle(root).getPropertyValue(name)) || 0;
  let columns = null;
  const columnsNeed = () => {
    if (!root.classList.contains("has-code")) return 0;
    if (columns === null) {
      // Before the body exists the probe goes in the root element; the stylesheet has loaded,
      // since a script waits for the stylesheets above it, so it is styled as a block of code.
      const probe = document.createElement("pre");
      probe.textContent = "0".repeat(100);
      probe.style.cssText = "position:absolute;visibility:hidden;width:max-content;margin:0";
      (document.body || root).appendChild(probe);
      columns = probe.getBoundingClientRect().width;
      probe.remove();
    }
    return columns;
  };
  // The window less a classic scrollbar, measured rather than read from the page: before the
  // page has a body it does not scroll yet, and every page of the book does once it has.
  let bar = null;
  const room = () => {
    if (bar === null) {
      const probe = document.createElement("div");
      probe.style.cssText = "position:absolute;visibility:hidden;overflow:scroll;width:100px;height:50px";
      (document.body || root).appendChild(probe);
      bar = probe.offsetWidth - probe.clientWidth;
      probe.remove();
    }
    return innerWidth - bar;
  };
  const cramped = () => {
    if (!roomy.matches) return false;
    const rails = (root.classList.contains("nav-closed") ? 0 : px("--nav")) + px("--toc");
    return room() - rails - 2 * px("--pad") < Math.max(px("--measure"), columnsNeed());
  };
  const reflect = () => {
    root.classList.toggle("toc-cramped", cramped());
    const menu = document.getElementById("menu"), outline = document.getElementById("outline");
    if (menu) {
      const shown = wide.matches ? !root.classList.contains("nav-closed")
                                 : document.body.classList.contains("nav-open");
      menu.setAttribute("aria-expanded", String(shown));
      menu.title = `${shown ? "Hide" : "Show"} the list of chapters`;
    }
    if (outline) {
      // Where the rail cannot be laid out, neither is its button: a control for something the
      // reader cannot see is worse than none.
      outline.hidden = !roomy.matches || root.classList.contains("toc-cramped")
        || root.classList.contains("toc-none");
      const shown = !root.classList.contains("toc-closed");
      outline.setAttribute("aria-expanded", String(shown));
      outline.title = `${shown ? "Hide" : "Show"} this page's outline`;
    }
  };
  const remember = (key, closed) => {
    try { if (closed) localStorage.setItem(key, "closed"); else localStorage.removeItem(key); } catch (e) {}
  };
  reflect();
  addEventListener("resize", reflect);
  wide.addEventListener("change", () => { document.body.classList.remove("nav-open"); reflect(); });
  roomy.addEventListener("change", reflect);
  document.addEventListener("DOMContentLoaded", () => {
    // On a phone the list covers the page and reads as a screen of its own, so Back closes it
    // rather than leaving the chapter: opening adds a history entry, and closing goes back
    // through it. A chapter chosen from the list replaces that entry, so Back from the chapter
    // returns to the page the list was opened on, not to the list.
    const body = document.body, listed = () => !!(history.state && history.state.list);
    const shut = () => { body.classList.remove("nav-open"); reflect(); };
    document.getElementById("menu").addEventListener("click", () => {
      if (wide.matches) { remember("nav", root.classList.toggle("nav-closed")); reflect(); return; }
      if (!body.classList.contains("nav-open")) {
        body.classList.add("nav-open");
        history.pushState({ list: true }, "");
        reflect();
      } else if (listed()) history.back();
      else shut();
    });
    addEventListener("popstate", () => { if (!listed() && body.classList.contains("nav-open")) shut(); });
    // A page Back brings from the browser's memory comes back as it was left: close the list.
    addEventListener("pageshow", (event) => {
      if ((event.persisted || !listed()) && body.classList.contains("nav-open")) shut();
    });
    document.getElementById("nav").addEventListener("click", (event) => {
      const link = event.target.closest("a[href]");
      if (!link || wide.matches || !listed()) return;
      event.preventDefault();
      location.replace(link.href);
    });
    document.getElementById("outline").addEventListener("click", () => {
      remember("toc", root.classList.toggle("toc-closed"));
      reflect();
    });
    columns = null;
    reflect();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { columns = null; reflect(); });
  });
})();
</script>"""


#: What the column cannot hold. A block of code or a table sits at the prose's measure, and takes
#: the wide column only when it would be cut off at the measure: the `wide` class, decided here,
#: because only the page knows the fonts it got. Each is measured once, as a copy with nothing
#: squeezing it, so a table that would wrap its cells to fit counts as cut off too, and a tab set
#: is sized by the wider of its two languages, so switching language never moves the column. A
#: widened block also gets `fits` and its own width, so it starts at the prose's left edge: a table
#: as wide as its content, and every block of code one width, the code column of a hundred
#: characters, so the code on a page lines up (book.css).
#:
#: Anything still cut off at the width it was given gets an Expand button, which gives it the
#: window: the same element, so an edit in progress and the reader's place both survive. On a
#: phone an expanded block reads as a page of its own, so Back closes it rather than leaving the
#: chapter: opening adds a history entry, and every way of closing goes back through it.
EXPAND = r"""<script>
document.addEventListener("DOMContentLoaded", () => {
  const root = document.documentElement;
  const article = document.querySelector("#main > .page");
  if (!article) return;
  const px = (name) => parseFloat(getComputedStyle(root).getPropertyValue(name)) || 0;
  const phone = matchMedia("(max-width: 40rem)");
  // Panels, the workbench and a run's output look after their own widths.
  const OWN = ".lab, .workbench, .run-result, .results";
  const PROMOTE = "pre, .runnable, .wide-block, .table-wrap, .generated, .tab-set, figure.quoted";

  let scrolled = 0;
  const label = (button, open) => {
    button.querySelector("span").textContent = open ? "Close" : "Expand";
    button.setAttribute("aria-expanded", String(open));
  };
  const shut = () => {
    const box = article.querySelector(".expanded");
    if (!box) return;
    box.classList.remove("expanded");
    root.classList.remove("expand-open");
    const button = box.querySelector(".expand");
    label(button, false);
    // It left the flow while it was open, so the page under it moved. Put the reader back where
    // they were rather than wherever the shorter page ended up.
    scrollTo({ top: scrolled, behavior: "instant" });
    button.focus({ preventScroll: true });
    schedule();
  };
  const close = () => {
    if (!article.querySelector(".expanded")) return;
    if (history.state && history.state.expanded) history.back();
    else shut();
  };
  addEventListener("popstate", shut);
  // Likewise a block left expanded, which would come back filling the window.
  addEventListener("pageshow", (event) => { if (event.persisted) shut(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });

  const control = (box) => {
    const button = document.createElement("button");
    button.className = "expand";
    button.type = "button";
    button.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.title = "Show all of it, in the whole window";
    button.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">'
      + '<path d="M6 2H2v4M10 14h4v-4M2 10v4h4M14 6V2h-4" fill="none" stroke="currentColor"'
      + ' stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg><span>Expand</span>';
    button.addEventListener("click", () => {
      if (box.classList.contains("expanded")) { close(); return; }
      scrolled = scrollY;
      history.pushState({ expanded: true }, "");
      box.classList.add("expanded");
      root.classList.add("expand-open");
      label(button, true);
    });
    return button;
  };
  // The box a block opens in: a quoted file is its own, with the button in its bar; anything
  // else is wrapped, with a command's Run button and its output inside the wrapper.
  const boxOf = (el) => {
    const quoted = el.closest("figure.quoted");
    if (quoted) {
      if (!quoted.querySelector(":scope > .source-bar > .expand")) {
        quoted.querySelector(":scope > .source-bar").append(control(quoted));
      }
      return quoted;
    }
    const wrapped = el.closest(".wide-block");
    if (wrapped) return wrapped;
    const target = el.parentElement.classList.contains("runnable") ? el.parentElement : el;
    const box = document.createElement("div");
    box.className = "wide-block";
    target.before(box);
    box.append(control(box), target);
    while (box.nextElementSibling && box.nextElementSibling.matches(".run-result, .run-note")) {
      box.append(box.nextElementSibling);
    }
    return box;
  };

  // What each block needs with nothing squeezing it: a copy, laid out out of sight at its
  // content's width. A block of code never changes, so its answer is kept; an edited step's
  // text area is measured each time, as a block of its text in its own font.
  const kept = new WeakMap();
  const needs = (els) => {
    const meter = document.createElement("div");
    meter.style.cssText = "position:fixed;left:0;top:0;visibility:hidden;pointer-events:none;"
      + "width:max-content;height:0;overflow:hidden";
    const copies = els.map((el) => {
      if (kept.has(el)) return null;
      let copy;
      if (el.matches("textarea")) {
        const cs = getComputedStyle(el);
        copy = document.createElement("pre");
        copy.textContent = el.value;
        copy.style.cssText = `font:${cs.font};padding:0 ${cs.paddingRight} 0 ${cs.paddingLeft};`
          + `border:0 solid;border-width:0 ${cs.borderRightWidth} 0 ${cs.borderLeftWidth};`
          + `tab-size:${cs.tabSize}`;
      } else if (el.matches(".table-wrap")) {
        const table = el.querySelector("table");
        // On a phone a table of many columns is a card per row, which is never cut off.
        if (!table || (table.matches(".cards") && phone.matches)) return null;
        copy = table.cloneNode(true);
        copy.style.display = "table";
      } else {
        copy = el.cloneNode(true);
      }
      copy.style.width = "max-content";
      copy.style.maxWidth = "none";
      copy.style.margin = "0";
      copy.style.overflow = "visible";
      meter.append(copy);
      return copy;
    });
    document.body.append(meter);
    const out = els.map((el, i) => {
      if (!copies[i]) return kept.get(el) || 0;
      const width = copies[i].getBoundingClientRect().width;
      if (!el.matches("textarea")) kept.set(el, width);
      return width;
    });
    meter.remove();
    return out;
  };
  // The code column: a hundred characters of the code's own font, where the Rust reader's lines
  // stop, with the block's padding and border. Measured, because only the page knows the font
  // it got. A longer line is cut off at it and gets the Expand button.
  let column = 0;
  const codeColumn = (pre) => {
    if (column || !pre) return column;
    const cs = getComputedStyle(pre);
    const probe = document.createElement("span");
    probe.style.cssText = "position:absolute;visibility:hidden;white-space:pre;"
      + `font-family:${cs.fontFamily};font-size:${cs.fontSize}`;
    probe.textContent = "0".repeat(100);
    document.body.append(probe);
    column = probe.getBoundingClientRect().width + parseFloat(cs.paddingLeft)
      + parseFloat(cs.paddingRight) + parseFloat(cs.borderLeftWidth) * 2;
    probe.remove();
    return column;
  };
  const topOf = (el) => {
    while (el && el.parentElement !== article) el = el.parentElement;
    return el;
  };

  let width = -1;
  const layout = () => {
    pending = false;
    if (root.classList.contains("expand-open")) return;
    const blocks = [...article.querySelectorAll("pre, textarea.code-area, .table-wrap")]
      .filter((el) => !el.closest(OWN) && !el.matches(".table-wrap pre"));
    const boxes = blocks.map(boxOf);
    const need = needs(blocks);
    const code = codeColumn(blocks.find((el) => el.matches("pre") && el.offsetParent !== null));
    const prose = Math.min(article.clientWidth, px("--measure"));
    width = article.clientWidth;
    // Each top-level block takes the wide column if anything in it would be cut off at the
    // measure. A block inside a list or a note keeps its place, and gets the button if it needs it.
    const units = new Map();
    blocks.forEach((el, i) => {
      const unit = topOf(el);
      if (!unit || !unit.matches(PROMOTE)) return;
      const u = units.get(unit) || { need: 0, tables: true };
      // Every block of code is one width, the code column, so their edges line up down the page;
      // a table is as wide as its content.
      u.need = Math.max(u.need, el.matches(".table-wrap") ? need[i] : code);
      u.tables = u.tables && el.matches(".table-wrap");
      units.set(unit, u);
    });
    for (const el of article.querySelectorAll(":scope > .wide")) {
      if (!units.has(el)) el.classList.remove("wide", "fits");
    }
    for (const [unit, u] of units) {
      const wide = u.need > prose + 1;
      unit.classList.toggle("wide", wide);
      // Only as wide as it needs: a block of code one line too long for the measure grows by that
      // much, not to the whole wide column with empty space on its right.
      unit.classList.toggle("fits", wide);
      if (wide) unit.style.setProperty("--need", `${Math.ceil(u.need) + 2}px`);
    }
    // Then, at the width each was given, which are still cut off. A block in the other language's
    // tab is not laid out; it is asked again when the reader switches.
    const cut = blocks.map((el, i) => el.offsetParent !== null
      && need[i] > (el.matches(".table-wrap") ? el.clientWidth : el.offsetWidth) + 1);
    blocks.forEach((el, i) => {
      if (el.offsetParent === null) return;
      const button = boxes[i].querySelector(":scope > .expand, :scope > .source-bar > .expand");
      button.hidden = !cut[i];
    });
  };
  let pending = false;
  const schedule = () => {
    if (!pending) { pending = true; requestAnimationFrame(layout); }
  };
  layout();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { column = 0; schedule(); });
  // The column changes width with the window and when a rail opens or closes.
  new ResizeObserver(() => { if (article.clientWidth !== width) schedule(); }).observe(article);
  document.addEventListener("click", (event) => { if (event.target.closest(".tab-bar")) schedule(); });
  // A walkthrough step swaps its code for a text area and back, and the reader types into it.
  new MutationObserver((records) => {
    if (records.some((r) => [...r.addedNodes].some((n) => n.nodeName === "PRE" || n.nodeName === "TEXTAREA"))) {
      schedule();
    }
  }).observe(article, { childList: true, subtree: true });
  article.addEventListener("input", (event) => { if (event.target.matches("textarea.code-area")) schedule(); });
});
</script>"""


#: How the book was written, said the same way on the cover and at the foot of every page.
WRITTEN_WITH = "in collaboration with Claude (Anthropic)"

#: What each licence ``myst.yml`` may declare is called, and the file that holds its text.
LICENCES = {"CC-BY-NC-4.0": ("CC BY-NC 4.0", "LICENSE"), "Apache-2.0": ("Apache 2.0", "LICENSE-CODE")}


def colophon() -> str:
    """The foot of every page but the cover: who wrote the book, and the terms each part of it is
    under. Read from ``myst.yml``, the one place the licences are declared, so a page cannot name
    other terms than the repository's. Most readers arrive on a chapter rather than the cover, and
    code copied from any page carries these terms with it. The cover says it in its own words."""
    config = yaml.safe_load((ROOT / "myst.yml").read_text())["project"]
    repo = config["github"].rstrip("/")
    author = config["authors"][0]["name"]

    def terms(spdx: str) -> str:
        name, file = LICENCES[spdx]
        return f'<a href="{repo}/blob/main/{file}">{html.escape(name)}</a>'

    return (
        f'<footer class="colophon">By {html.escape(author)}, {WRITTEN_WITH} · Prose and figures: '
        f"{terms(config['license']['content'])} · Code: {terms(config['license']['code'])}</footer>"
    )


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
        # A chapter that explains and builds nothing says what it shows instead.
        what = "What you see" if chapter.explainer else "What you build"
        builds = f'<p class="builds"><strong>{what}:</strong> {html.escape(chapter.builds)}</p>'

    def link(q, cls, word):
        if q is None:
            return ""
        label = f"{q['label']} · " if q["label"] else ""
        name = q.get("nav", q["title"])
        return f'<a class="{cls}" href="{q["href"]}"><small>{word}</small>{html.escape(label + name)}</a>'

    lab = (
        '<link rel="stylesheet" href="lab/lab.css"><script type="module" src="lab/lab.js"></script>'
        if has_lab
        else ""
    )
    title = f"{p['label']} · {p['title']}" if p["label"] else p["title"]
    # The cover's title is the book's, said once.
    title = TITLE if p.get("cover") else f"{title} · {TITLE}"
    # What the rails' script needs to know before the page has a body: whether this page has
    # sections for an outline to list, and whether it shows code, which asks more of the column.
    classes = [c for c, on in (("toc-none", "<ol>" not in toc), ("has-code", "<pre" in body)) if on]
    attrs = f' class="{" ".join(classes)}"' if classes else ""
    return f"""<!doctype html>
<html lang="en-GB"{attrs}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="theme-color" content="#35648f">
<link rel="stylesheet" href="book.css">
{lab}
{HEAD_SCRIPT}
{RAILS}
{EXPAND}
</head>
<body>
<header class="top">
<button id="menu" type="button" aria-controls="nav" aria-expanded="false">Chapters</button>
<a class="brand" href="index.html">{TITLE} <span>· {SUBTITLE}</span></a>
<button id="outline" type="button" aria-controls="toc" aria-expanded="true" hidden>On this page</button>
<button id="theme" type="button" hidden>System</button>
</header>
<div class="layout">
{nav}
<main id="main"><article class="{"page cover" if p.get("cover") else "page"}">
{h1}
{builds}
{body}
<nav class="prevnext" aria-label="Previous and next">{link(prev, "prev", "Previous")}{link(nxt, "next", "Next")}</nav>
{"" if p.get("cover") else colophon()}
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


def icon_png(size: int, maskable: bool = False) -> bytes:
    """The favicon's picture as a PNG ``size`` pixels square: home screens want a bitmap. Drawn
    here, from the same shapes, so the build needs no image library and writes the same bytes
    every time.

    ``maskable`` is Android's kind: the blue fills the whole square, since the launcher cuts its
    own shape out of it, and the bars shrink into the middle four fifths, the part every shape
    keeps."""
    import struct
    import zlib

    blue = (0x35, 0x64, 0x8F)
    # (x, y, width, height, corner radius, opacity of white over the blue), in the SVG's 32 units.
    bars = [(6, 7, 4, 18, 1, 1.0), (12, 7, 4, 18, 1, 0.8), (18, 7, 4, 18, 1, 0.6), (24, 7, 2.5, 18, 1, 0.4)]

    def inside(x: float, y: float, rx: float, ry: float, w: float, h: float, r: float) -> bool:
        cx = min(max(x, rx + r), rx + w - r)
        cy = min(max(y, ry + r), ry + h - r)
        return rx <= x <= rx + w and ry <= y <= ry + h and (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    samples = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))
    raw = bytearray()
    for py in range(size):
        raw.append(0)  # no filter on this scanline
        for px in range(size):
            rgb, alpha = [0.0, 0.0, 0.0], 0.0
            for sx, sy in samples:
                x, y = (px + sx) * 32 / size, (py + sy) * 32 / size
                if maskable:
                    x, y = (x - 16) / 0.8 + 16, (y - 16) / 0.8 + 16
                elif not inside(x, y, 0, 0, 32, 32, 6):
                    continue
                white = next((o for bx, by, bw, bh, br, o in bars if inside(x, y, bx, by, bw, bh, br)), 0.0)
                for i in range(3):
                    rgb[i] += blue[i] * (1 - white) + 255 * white
                alpha += 1
            n = len(samples)
            colour = [round(c / alpha) if alpha else 0 for c in rgb]
            raw += bytes([*colour, round(255 * alpha / n)])

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def manifest() -> str:
    """The book as an app on a home screen. It starts at ``index.html?resume``, which the page's
    script turns into the page the reader was last on (HEAD_SCRIPT)."""
    return json.dumps(
        {
            "name": TITLE,
            "short_name": "Parquet",
            "start_url": "index.html?resume",
            "scope": "./",
            "display": "standalone",
            "background_color": "#fdfdfc",
            "theme_color": "#35648f",
            "icons": [
                {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
                {
                    "src": "icon-maskable-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
        },
        indent=2,
    )


def service_worker(files: list[str], version: str) -> str:
    """Keep every file of the site on first visit, so the book reads with no network after it.

    The list is every file the build wrote, and the cache name carries a hash of their contents,
    so a new deploy replaces the old copy instead of mixing with it. Online, every file comes
    from the network, so a reader sees a new deploy on the next page they open.
    """
    return f"""// Written by scripts/build-site.py. Keeps the whole book for offline reading.
const CACHE = "parquet-book-{version}";
const FILES = {json.dumps(files)};
self.addEventListener("install", (e) => {{
  // Straight from the server, not the browser's HTTP cache, which may hold a page from before
  // this deploy for as long as the host allows (ten minutes on GitHub Pages).
  e.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(FILES.map((f) => new Request(f, {{ cache: "reload" }}))))
    .then(() => self.skipWaiting()));
}});
self.addEventListener("activate", (e) => {{
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
}});
self.addEventListener("fetch", (e) => {{
  // Only the book's own files: Pyodide, fetched from a CDN for the Python the page runs, is
  // cached by the browser as any other download.
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  // The network first, and the kept copy only when there is none. Served from the copy first,
  // a reader saw the book as it was when the copy was taken until a new service worker had
  // installed and the page had been loaded again: on a phone's home screen, often not for days.
  // Each answer from the network refreshes the copy, so offline reading gets the latest pages.
  // `no-cache` asks the server every time, so the browser's HTTP cache cannot hand back a page
  // from before a deploy; an unchanged file costs a "not modified" reply and no body.
  // A page load is asked for afresh, by its URL: copying the browser's own request with new
  // options is refused for a page load by some browsers (Firefox), which left the book showing
  // its kept copy, or nothing, on Back.
  const fresh = e.request.mode === "navigate"
    ? fetch(e.request.url, {{ cache: "no-cache", credentials: "same-origin" }})
    : fetch(e.request, {{ cache: "no-cache" }});
  e.respondWith(fresh.then((response) => {{
    if (response.ok) {{
      const copy = response.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
    }}
    return response;
  }}).catch(() => caches.match(e.request, {{ ignoreSearch: true }}).then((hit) => hit || Response.error())));
}});
"""


def build(out: Path) -> None:
    parse = load_parse()
    pages = page_list()
    missing = [p["source"] for p in pages if p["source"] not in parse]
    if missing:
        sys.exit(f"MyST produced no parse for: {', '.join(missing)}. Is each page in myst.yml's toc?")
    renderer.PAGES.clear()
    renderer.IMAGES.clear()
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
        # The lab script also puts buttons on the commands a page prints (Run, or Open in Codespaces)
        # and on its walkthrough steps (Run and Edit), so a page with any of those loads it.
        markers = ('class="lab"', 'class="workbench"', "python3 -m ", "cargo ", 'class="quoted walkthrough"')
        has_lab = any(m in body for m in markers)
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
    # The pictures the pages show, such as the cover's, under the names the pages use.
    for name, source in sorted(renderer.IMAGES.items()):
        shutil.copy(source, out / name)
    (out / "favicon.svg").write_text(FAVICON)
    for size in (192, 512):
        (out / f"icon-{size}.png").write_bytes(icon_png(size))
    (out / "icon-maskable-512.png").write_bytes(icon_png(512, maskable=True))
    (out / "manifest.webmanifest").write_text(manifest())
    for f in (ROOT / "web" / "lab").iterdir():
        if f.suffix in (".js", ".css"):
            shutil.copy(f, out / "lab" / f.name)
    if not WASM.exists():
        sys.exit(f"{WASM.relative_to(ROOT)} is missing; run `make wasm` first")
    shutil.copy(WASM, out / "lab" / "parquet_lab.wasm")
    # The Python reader, for the walkthrough steps, the Run buttons and the workbench, which run
    # it in the page: the same files the tests import.
    package = ROOT / "python" / "parquet_lab"
    (out / "lab" / "py" / "parquet_lab").mkdir(parents=True)
    modules = sorted(f.name for f in package.glob("*.py"))
    for name in modules:
        shutil.copy(package / name, out / "lab" / "py" / "parquet_lab" / name)
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
    for table in ("table", "changes", "formats"):
        shutil.copytree(ROOT / "fixtures" / table, out / "fixtures" / table)
    fixtures = sorted(
        str(f.relative_to(out / "fixtures")) for f in (out / "fixtures").rglob("*") if f.is_file()
    )
    (out / "lab" / "py" / "package.json").write_text(
        json.dumps(
            {
                "modules": modules,
                "exercises": problems,
                "tests": tests,
                "fixtures": fixtures,
            }
        )
    )
    rust_trial(out / "rust-trial")
    (out / ".nojekyll").write_text("")

    # The book's offline cache leaves out the Rust trial, which is not part of the book and has
    # its own service worker.
    files = sorted(
        str(f.relative_to(out))
        for f in out.rglob("*")
        if f.is_file() and f.name != ".nojekyll" and f.relative_to(out).parts[0] != "rust-trial"
    )
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.encode())
        digest.update((out / f).read_bytes())
    (out / "sw.js").write_text(service_worker(["./", *files], digest.hexdigest()[:12]))
    print(f"wrote {len(pages)} pages and {len(files) - len(pages)} assets to {out.relative_to(ROOT)}")


def flattened_reader() -> str:
    """The Rust reader (crates/parquet-lab) as one file, unit tests included, for the trial page:
    rubrc's rustc compiles one file. Each module becomes an inline `mod`, and `crate::` paths gain
    the `parquet_lab` module they now sit in."""
    src = ROOT / "crates" / "parquet-lab" / "src"

    def module(text: str) -> str:
        return text.replace("crate::", "crate::parquet_lab::")

    def inline(m) -> str:
        return f"pub mod {m.group(1)} {{\n{module((src / f'{m.group(1)}.rs').read_text())}\n}}"

    lib = re.sub(r"^pub mod (\w+);$", inline, module((src / "lib.rs").read_text()), flags=re.M)
    return (
        "// The book's Rust reader, crates/parquet-lab, flattened into one file by scripts/build-site.py\n"
        "// for the Rust-in-the-browser trial (rust-trial/). Compile it with --test to run its unit tests.\n"
        "#![allow(dead_code)]\n\n"
        f"pub mod parquet_lab {{\n{lib}\n}}\n"
    )


def rust_trial(out: Path) -> None:
    """The hidden trial page: web/rust-trial, the sources it compiles, and nothing else. Its
    toolchain is fetched into the same directory by scripts/fetch-rust-trial.mjs at deploy time;
    without it the page says the toolchain is missing."""
    shutil.copytree(ROOT / "web" / "rust-trial", out)
    (out / "hello.rs").write_text('fn main() {\n    println!("Hello from rustc in your browser");\n}\n')
    (out / "reader.rs").write_text(flattened_reader())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "_build" / "html"))
    args = parser.parse_args()
    build(Path(args.out).resolve())


if __name__ == "__main__":
    main()
