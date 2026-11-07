"""Build lookup views from the glossary's canonical MyST definitions."""

from __future__ import annotations

import html
from dataclasses import dataclass

from tools import render as renderer


@dataclass
class Entry:
    title: str
    ident: str
    heading: dict
    nodes: list[dict]

    @property
    def href(self) -> str:
        return f"glossary.html#{self.ident}"


# Alternate names in lesson prose refer to the same definition, not copies of its wording.
ALIASES = {
    "column projection": "Projection",
    "prefetching": "Prefetch",
    "magic number": "Magic",
    "file signature": "Magic",
    "hex": "Hexadecimal",
    "rle": "Run-length encoding",
    "run-length": "Run-length encoding",
    "leaf column": "Leaf",
    "leaf field": "Leaf",
    "null value": "Null",
    "columnar layout": "Column layout",
    "row-oriented layout": "Row layout",
    "byte_stream_split": "Byte-stream split",
    "crc-32": "CRC",
    "cyclic redundancy check": "CRC",
    "delta": "Delta encoding",
    "two's complement": "Two’s complement",
    "float": "Floating-point number",
    "floating point": "Floating-point number",
    "columnindex": "Column index",
    "offsetindex": "Offset index",
    "object keys": "Object key",
    "dependency phases": "Dependency phase",
}


def entries(mdast: dict) -> tuple[list[dict], list[Entry]]:
    def blocks(node):
        if node.get("type") in ("root", "block"):
            for child in node.get("children", []):
                yield from blocks(child)
        else:
            yield node

    intro, terms = [], []
    for node in blocks(mdast):
        if node.get("type") == "heading" and node.get("depth") == 2:
            title = renderer.text_of(node)
            ident = "term-" + renderer.heading_id(node)
            if any(term.ident == ident for term in terms):
                raise ValueError(f"duplicate glossary definition: {title}")
            terms.append(Entry(title, ident, node, []))
        elif terms:
            terms[-1].nodes.append(node)
        else:
            intro.append(node)
    if not terms or any(not term.nodes for term in terms):
        raise ValueError("glossary needs named definitions, each with explanatory content")
    return intro, sorted(terms, key=lambda term: term.title.casefold())


def targets(terms: list[Entry]) -> dict[str, str]:
    result = {term.title.casefold(): term.href for term in terms}
    for alias, title in ALIASES.items():
        if title.casefold() in result:
            result.setdefault(alias, result[title.casefold()])
    return result


def render_glossary(intro: list[dict], terms: list[Entry]) -> str:
    names = targets(terms)
    letters = sorted({term.title[0].upper() for term in terms})
    alphabet = "".join(f'<a href="#glossary-{letter.lower()}">{letter}</a>' for letter in letters)
    out = [
        renderer.render({"type": "root", "children": intro}),
        '<div class="glossary-search" hidden><label for="glossary-search">Find a term</label>',
        '<input id="glossary-search" type="search" placeholder="Search terms and definitions" '
        'autocomplete="off" spellcheck="false" aria-controls="glossary-entries">',
        '<p id="glossary-status" role="status" aria-live="polite"></p></div>',
        f'<nav class="glossary-alphabet" aria-label="Glossary alphabet">{alphabet}</nav>',
        '<div id="glossary-entries">',
    ]
    previous = None
    for term in terms:
        letter = term.title[0].upper()
        if letter != previous:
            out.append(f'<p class="glossary-letter" id="glossary-{letter.lower()}">{letter}</p>')
            previous = letter
        aliases = " ".join(name for name, href in names.items() if href == term.href)
        out.append(
            f'<section class="glossary-entry" id="{html.escape(term.ident)}" data-letter="{letter}" '
            f'data-aliases="{html.escape(aliases)}">'
            + renderer.render(term.heading)
            + renderer.render({"type": "root", "children": term.nodes})
            + "</section>"
        )
    return "".join(out) + "</div>"
