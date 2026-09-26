"""MyST's parse, rendered to HTML: the one renderer every page of the book goes through.

The input is MyST's own parse output, the JSON ``myst build`` writes under
``_build/site/content/``, not the markdown. Directives are already resolved in it: every
``{literalinclude}`` carries the real code from the working tree and every ``{include}`` carries
the real generated fragment, so there is no second implementation of either to drift.

A node type the renderer does not know **raises**. It is never skipped: a renderer that quietly
drops what it does not recognise loses content, and the only symptom is a paragraph nobody
notices is missing.

Four node shapes are this book's own:

- A fenced block in the language ``lab`` is an experiment. It becomes a mount point that
  ``web/lab/lab.js`` fills with the WebAssembly reader, and the renderer checks that the
  experiment and fixture it names exist.
- A fenced block in the language ``problems`` is a chapter's workbench, where a reader edits the
  chapter's Python problems and runs their tests in the page (``web/lab/workbench.js``). The
  renderer checks that the chapter it names has problems.
- A ``{literalinclude}`` of a file in this repository gets a bar naming the file, because the
  book's code is quoted from the implementation, and the reader should always be able to see
  which file a block came from.
- A ``{tab-set}`` whose two tab items are synced ``python`` and ``rust`` is the same step of the reader
  in both languages. Every tab set on every page follows one choice, which the page's head script
  keeps; without JavaScript both are shown, one after the other.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from tools.highlight import highlight
from tools.outline import BY_ANCHOR, EXPERIMENTS

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/snowch/parquet-book/blob/main/"


class UnknownNodeError(Exception):
    """A node type the renderer does not handle. Raised, never skipped."""


class LabBlockError(Exception):
    """A ``lab`` block that names an experiment or fixture that does not exist."""


class TabSetError(Exception):
    """A tab set whose tabs are not the book's two languages."""


#: The languages a tab set may show, in the order the tabs appear.
LANGUAGES = {"python": "Python", "rust": "Rust"}


#: MyST page slug -> the file this build publishes it as. Filled in by the site build.
PAGES: dict[str, str] = {}

#: A reference whose text opens with a chapter label, which the renderer re-derives.
LABELLED = re.compile(r"^(ch\d+|Appendix [A-Z])\b")


def text_of(node) -> str:
    if isinstance(node, dict):
        if node.get("type") in ("text", "inlineCode"):
            return str(node.get("value", ""))
        return "".join(text_of(c) for c in node.get("children", []))
    if isinstance(node, list):
        return "".join(text_of(c) for c in node)
    return ""


def heading_id(node: dict) -> str:
    if node.get("html_id"):
        return str(node["html_id"])
    keep = "".join(c.lower() if c.isalnum() else "-" for c in text_of(node))
    return "-".join(p for p in keep.split("-") if p)


def parse_key_values(value: str, kind: str) -> dict:
    config = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        key, sep, val = line.partition(":")
        if not sep:
            raise LabBlockError(f"{kind} block line has no colon: {line!r}")
        config[key.strip()] = val.strip()
    return config


def parse_lab_block(value: str) -> dict:
    """A ``lab`` block is ``key: value`` lines. Validated here, so a typo fails the build."""
    config = parse_key_values(value, "lab")
    experiment = config.get("experiment")
    if experiment not in EXPERIMENTS:
        raise LabBlockError(f"unknown experiment {experiment!r}; known: {', '.join(EXPERIMENTS)}")
    for fixture in filter(None, (config.get("fixture"), *config.get("fixtures", "").split(","))):
        if not (ROOT / "fixtures" / fixture.strip()).exists():
            raise LabBlockError(f"lab block names fixtures/{fixture.strip()}, which does not exist")
    return config


def _lab(node: dict) -> str:
    config = parse_lab_block(str(node.get("value", "")))
    attrs = " ".join(f'data-{html.escape(k)}="{html.escape(v)}"' for k, v in config.items())
    return (
        f'<div class="lab" {attrs}>'
        '<p class="lab-fallback">This experiment runs the book\'s Parquet reader in your '
        "browser, compiled to WebAssembly. It needs JavaScript. The same reader runs at a "
        'desk: see <a href="running-the-lab.html">Appendix A</a>.</p></div>'
    )


def parse_problems_block(value: str) -> str:
    """A ``problems`` block names its chapter: ``chapter: <slug>``. The chapter must have Python
    problems, so a typo fails the build."""
    config = parse_key_values(value, "problems")
    slug = config.get("chapter", "")
    if set(config) != {"chapter"} or not (ROOT / "exercises" / "python" / f"{slug}.py").exists():
        raise LabBlockError(
            f"a problems block is `chapter: <slug>`, with exercises/python/<slug>.py; got {config}"
        )
    return slug


def _problems(node: dict) -> str:
    slug = parse_problems_block(str(node.get("value", "")))
    return (
        f'<div class="workbench" data-chapter="{html.escape(slug)}">'
        '<p class="lab-fallback">Here you can edit this chapter\'s problems and run their tests in your '
        "browser, in Python. It needs JavaScript. The same problems run at a desk: see "
        '<a href="running-the-lab.html">Appendix A</a>.</p></div>'
    )


def _code(node: dict) -> str:
    lang = node.get("lang") or ""
    code = str(node.get("value", ""))
    body = highlight(code, lang)
    cls = f' class="language-{html.escape(lang)}"' if lang else ""
    return f"<pre><code{cls}>{body}</code></pre>"


def _repo_path(include: dict) -> str:
    # MyST gives the path as written in the page, relative to it. Resolve against the
    # repository, so the bar can name the file the way the reader will find it on disk.
    clean = str(include.get("file", ""))
    while clean.startswith("../"):
        clean = clean[3:]
    return clean


def _source_bar(include: dict) -> str:
    clean = _repo_path(include)
    # A walkthrough is a short program the chapter asks you to run and change, not the reader.
    label = "Try it" if clean.startswith("walkthroughs/") else "From the implementation"
    return (
        f'<div class="source-bar"><span class="source-label">{label}</span>'
        f'<a href="{REPO_URL}{html.escape(clean)}"><code>{html.escape(clean)}</code></a></div>'
    )


def _tab_set(node: dict, footnotes: list | None) -> str:
    items = node.get("children", [])
    syncs = [str(i.get("sync", "")) for i in items]
    if any(i.get("type") != "tabItem" for i in items) or sorted(syncs) != sorted(LANGUAGES):
        raise TabSetError(
            f"a tab set must hold one tab-item synced python and one synced rust, not {syncs} "
            f"(near {json.dumps(node.get('position', {}))})"
        )
    items = sorted(items, key=lambda i: list(LANGUAGES).index(i["sync"]))
    bar = "".join(
        f'<button type="button" data-code="{i["sync"]}">{LANGUAGES[i["sync"]]}</button>' for i in items
    )
    panels = "".join(
        f'<div class="tab-panel" data-code="{i["sync"]}">'
        + "".join(render(c, footnotes) for c in i.get("children", []))
        + "</div>"
        for i in items
    )
    return f'<div class="tab-set"><div class="tab-bar" aria-label="Language">{bar}</div>{panels}</div>'


def _xref(node: dict, inner: str) -> str:
    """A link to another part of the book, as a relative URL this build publishes.

    MyST resolves a reference to a page-root URL such as ``/encodings``. The site is served under
    a base path it is not told, so every internal link is rewritten to the relative file this
    build writes. A reference to a chapter whose text opens with a label (``ch05``) gets the
    label re-derived from the outline, so it cannot go stale when chapters move.
    """
    ident = str(node.get("identifier") or "")
    target = BY_ANCHOR.get(ident)
    if target is not None:
        text = text_of(node).strip()
        m = LABELLED.match(text)
        if m:
            inner = html.escape(target.label + text[m.end() :])
        return f'<a class="xref" href="{target.anchor}.html">{inner}</a>'
    url = str(node.get("url") or "")
    path, _, fragment = url.partition("#")
    if not fragment and node.get("type") == "crossReference":
        fragment = str(node.get("html_id") or ident)
    if path.startswith("/"):
        page = PAGES.get(path.strip("/") or "index")
        if page is None:
            raise UnknownNodeError(f"internal link to {url!r}, which this build does not publish")
        href = page + (f"#{fragment}" if fragment else "")
    else:
        href = f"#{fragment}"
    return f'<a class="xref" href="{html.escape(href)}">{inner}</a>'


def render(node: dict, footnotes: list | None = None) -> str:
    kind = node.get("type")

    def children() -> str:
        return "".join(render(c, footnotes) for c in node.get("children", []))

    if kind == "text":
        return html.escape(str(node.get("value", "")))
    if kind in ("root", "block"):
        return children()
    if kind == "paragraph":
        return f"<p>{children()}</p>"
    if kind == "heading":
        level = min(max(int(node.get("depth", 2)), 1), 6)
        hid = heading_id(node)
        return (
            f'<h{level} id="{html.escape(hid)}">{children()}'
            f'<a class="anchor" href="#{html.escape(hid)}" aria-label="Link to this section">#</a></h{level}>'
        )
    if kind == "strong":
        return f"<strong>{children()}</strong>"
    if kind == "emphasis":
        return f"<em>{children()}</em>"
    if kind == "inlineCode":
        return f"<code>{html.escape(str(node.get('value', '')))}</code>"
    if kind == "keyboard":
        return f"<kbd>{children()}</kbd>"
    if kind == "break":
        return "<br>"
    if kind == "thematicBreak":
        return "<hr>"
    if kind == "comment":
        return ""
    if kind == "code":
        if node.get("lang") == "lab":
            return _lab(node)
        if node.get("lang") == "problems":
            return _problems(node)
        return _code(node)
    if kind == "include":
        if node.get("literal"):
            walkthrough = _repo_path(node).startswith("walkthroughs/")
            return (
                (
                    f'<figure class="quoted walkthrough" data-file="{html.escape(_repo_path(node))}">'
                    if walkthrough
                    else '<figure class="quoted">'
                )
                + _source_bar(node)
                + "".join(render(c, footnotes) for c in node.get("children", []))
                + "</figure>"
            )
        return f'<div class="generated">{children()}</div>'
    if kind == "tabSet":
        return _tab_set(node, footnotes)
    if kind == "blockquote":
        return f"<blockquote>{children()}</blockquote>"
    if kind == "list":
        tag = "ol" if node.get("ordered") else "ul"
        start = node.get("start")
        attr = f' start="{int(start)}"' if tag == "ol" and start not in (None, 1) else ""
        return f"<{tag}{attr}>{children()}</{tag}>"
    if kind == "listItem":
        # A tight list item holds one paragraph; unwrap it so the list does not double-space.
        kids = node.get("children", [])
        if len(kids) == 1 and kids[0].get("type") == "paragraph":
            return f"<li>{''.join(render(c, footnotes) for c in kids[0].get('children', []))}</li>"
        return f"<li>{children()}</li>"
    if kind == "table":
        rows = node.get("children", [])
        head = [r for r in rows if all(c.get("header") for c in r.get("children", []))]
        body = [r for r in rows if r not in head]
        thead = "".join(render(r, footnotes) for r in head)
        tbody = "".join(render(r, footnotes) for r in body)
        return (
            f'<div class="table-wrap"><table>'
            f"{'<thead>' + thead + '</thead>' if thead else ''}<tbody>{tbody}</tbody></table></div>"
        )
    if kind == "tableRow":
        return f"<tr>{children()}</tr>"
    if kind == "tableCell":
        tag = "th" if node.get("header") else "td"
        align = node.get("align")
        style = f' class="align-{align}"' if align in ("left", "right", "center") else ""
        return f"<{tag}{style}>{children()}</{tag}>"
    if kind == "div":
        classes = " ".join(str(node.get("class", "")).split())
        return f'<div class="{html.escape(classes)}">{children()}</div>'
    if kind == "admonition":
        return f'<aside class="admonition {html.escape(str(node.get("kind", "note")))}">{children()}</aside>'
    if kind == "admonitionTitle":
        return f'<p class="admonition-title">{children()}</p>'
    if kind == "link" and node.get("internal"):
        return _xref(node, children())
    if kind == "link":
        url = str(node.get("url", ""))
        ext = url.startswith(("http://", "https://"))
        rel = ' rel="noopener"' if ext else ""
        return f'<a href="{html.escape(url)}"{rel}>{children()}</a>'
    if kind == "crossReference":
        return _xref(node, children())
    if kind == "mystTarget":
        return f'<span id="{html.escape(str(node.get("label", "")))}"></span>'
    if kind == "footnoteReference":
        n = html.escape(str(node.get("enumerator") or node.get("label")))
        return f'<sup class="fn"><a id="fnref-{n}" href="#fn-{n}">{n}</a></sup>'
    if kind == "footnoteDefinition":
        if footnotes is not None:
            footnotes.append(node)
        return ""
    if kind == "image":
        src = html.escape(str(node.get("url", "")))
        alt = html.escape(str(node.get("alt", "")))
        return f'<img src="{src}" alt="{alt}" loading="lazy">'
    if kind == "container":
        return f"<figure>{children()}</figure>"
    if kind == "caption":
        return f"<figcaption>{children()}</figcaption>"
    if kind in ("subscript", "superscript", "delete"):
        tag = {"subscript": "sub", "superscript": "sup", "delete": "del"}[kind]
        return f"<{tag}>{children()}</{tag}>"
    if kind == "abbreviation":
        return f'<abbr title="{html.escape(str(node.get("title", "")))}">{children()}</abbr>'
    raise UnknownNodeError(
        f"no renderer for MyST node type {kind!r}; add a branch to tools/render.py "
        f"(near {json.dumps(node.get('position', {}))})"
    )


def render_page(mdast: dict) -> str:
    """The body of a page, with its footnotes collected at the end."""
    footnotes: list = []
    body = render(mdast, footnotes)
    if footnotes:
        items = "".join(
            f'<li id="fn-{html.escape(str(f.get("enumerator") or f.get("label")))}">'
            f"{''.join(render(c) for c in f.get('children', []))}</li>"
            for f in footnotes
        )
        body += f'<section class="footnotes"><ol>{items}</ol></section>'
    return body
