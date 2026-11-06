"""Short reading routes cut from the canonical chapter parse, never copied prose."""

from __future__ import annotations

import copy
import html
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Lesson:
    slug: str
    title: str
    outcome: str
    preparation: str
    optional: bool = False

    @property
    def href(self) -> str:
        return f"{self.slug}.html"


MODULES = {
    "anatomy_of_a_parquet_file": (
        Lesson(
            "recognise-parquet",
            "Recognise Parquet and read its bytes",
            "Recognise the file signature and distinguish stored bytes from their display.",
            "Start here after Why Parquet exists. No hex viewer or programming is needed.",
        ),
        Lesson(
            "locate-the-footer",
            "Locate and validate the footer",
            "Decode the trailer length, locate the footer and reject an impossible span.",
            "Use byte offsets and hexadecimal notation from the previous lesson. A calculator is welcome.",
        ),
        Lesson(
            "read-the-footer-map",
            "Turn the footer into a byte map",
            "Follow row groups into column chunks and convert a chunk span into an HTTP range.",
            "Use the distinction between the footer and trailer, and half-open byte spans.",
        ),
        Lesson(
            "trace-footer-requests",
            "Trace the dependent reads",
            "Explain which information each request supplies to the next request.",
            "You can locate a footer and interpret its map. Storage requests are introduced here.",
        ),
        Lesson(
            "choose-a-tail-read",
            "Choose a tail-read strategy",
            "Explain when a suffix read saves a request and when the footer still needs another read.",
            "Follow the complete request chain in the previous lesson before comparing strategies.",
        ),
        Lesson(
            "build-footer-reader",
            "Build the footer reader",
            "Connect the byte calculations and request trace to the Python and Rust implementation.",
            "Optional lab after the reading lessons. The full chapter also contains the coding problems.",
            optional=True,
        ),
    ),
    "nested_data": (
        Lesson(
            "nullable-values",
            "Distinguish a null from a value",
            "Read definition levels for one optional scalar before introducing lists.",
            "Use the schema paths and optional fields introduced in The type system.",
        ),
        Lesson(
            "one-list",
            "Rebuild one list",
            "Distinguish a null list, an empty list and a null element, then rebuild the records.",
            "You can interpret definition levels for a nullable scalar. Repetition starts here.",
        ),
        Lesson(
            "nested-lists",
            "Follow lists inside lists",
            "Use repetition levels to distinguish a new record, a new item and another discount.",
            "First reconstruct one list from its definition and repetition levels.",
        ),
        Lesson(
            "stored-levels",
            "Read the stored level streams",
            "Connect decoded levels to run headers, bit widths and padding in a data page.",
            "You can already interpret the discounts stream. This lesson examines its storage.",
        ),
        Lesson(
            "build-nested-reader",
            "Build the nested-data reader",
            "Connect the stored levels to decoding and record reconstruction in Python and Rust.",
            "Optional lab after the reading lessons. The full chapter retains the coding problems.",
            optional=True,
        ),
    ),
}


def module_href(chapter) -> str:
    return f"{chapter.anchor}-lessons.html"


def reading_pages(canonical: list[dict]) -> list[dict]:
    """The default Next route omits the optional build and full-reference pages."""
    pages = []
    for page in canonical:
        chapter = page.get("chapter")
        lessons = MODULES.get(chapter.slug, ()) if chapter else ()
        if not lessons:
            pages.append(page)
            continue
        pages.append({**page, "href": module_href(chapter), "module": True})
        pages.extend(lesson_page(page, lesson) for lesson in lessons if not lesson.optional)
    return pages


def lesson_page(page: dict, lesson: Lesson) -> dict:
    return {**page, "href": lesson.href, "title": lesson.title, "lesson": lesson}


def lesson_nodes(mdast: dict, chapter_slug: str) -> dict[str, dict]:
    """Split only the document's block wrappers; preserve figures, tabs and lists whole.

    Every expected marker must occur once and in order. A missing boundary fails the build
    rather than silently swallowing an implementation lab into a reading lesson.
    """

    def blocks(node):
        for child in node.get("children", []):
            if child["type"] == "block":
                yield from blocks(child)
            else:
                yield copy.deepcopy(child)

    expected = [lesson.slug for lesson in MODULES[chapter_slug]] + ["reference"]
    found, groups, current = [], {}, None
    for node in blocks(mdast):
        if node["type"] == "code" and node.get("lang") == "lesson":
            current = node["value"].strip()
            found.append(current)
            groups[current] = {"type": "root", "children": []}
        elif current:
            groups[current]["children"].append(node)
    if found != expected:
        raise ValueError(f"{chapter_slug}: lesson markers {found!r}, expected {expected!r}")
    if any(not group["children"] for group in groups.values()):
        raise ValueError(f"{chapter_slug}: empty lesson")
    return groups


def module_card(chapter, *, reference: bool = False) -> str:
    lessons = MODULES[chapter.slug]
    core = [lesson for lesson in lessons if not lesson.optional]
    items = "".join(
        f'<li><a href="{lesson.href}">{html.escape(lesson.title)}</a>'
        f"<p>{html.escape(lesson.outcome)}</p></li>"
        for lesson in core
    )
    build = next(lesson for lesson in lessons if lesson.optional)
    opening = (
        "This is the full chapter. Prefer a smaller step? Choose a lesson below."
        if reference
        else "Follow these lessons in order. Each ends with a fresh case you can reason through without running code."
    )
    full = (
        '<a href="#the-question">Read the full chapter below</a>'
        if reference
        else f'<a href="{chapter.anchor}.html">Read the full chapter and its reference material</a>'
    )
    return (
        '<section class="module-card" aria-label="Lessons in this chapter">'
        f'<p class="eyebrow">{"Reading options" if reference else "Choose a lesson"}</p>'
        f'<p>{opening}</p><ol class="lesson-list">{items}</ol>'
        f'<p class="module-resources">{full}<br>'
        f'<a href="{build.href}">Optional: {html.escape(build.title.lower())}</a></p></section>'
    )


def lesson_intro(chapter, lesson: Lesson) -> str:
    core = [item for item in MODULES[chapter.slug] if not item.optional]
    position = "Optional build lab" if lesson.optional else f"Lesson {core.index(lesson) + 1} of {len(core)}"
    return (
        '<div class="lesson-intro reading-guide">'
        f'<p class="eyebrow">{position} · <a href="{module_href(chapter)}">{html.escape(chapter.title)}</a></p>'
        f"<p><strong>Your goal:</strong> {html.escape(lesson.outcome)}</p>"
        f"<p><strong>Before you start:</strong> {html.escape(lesson.preparation)}</p>"
        "<p>Read the worked results; opening or running the code is optional.</p></div>"
    )


def reference_links(body: str, canonical_href: str) -> str:
    """Keep local anchors local; send omitted sections to the complete reference page."""
    ids = set(re.findall(r'\bid="([^"]+)"', body))
    return re.sub(
        r'href="#([^"]+)"',
        lambda match: match[0] if match[1] in ids else f'href="{canonical_href}#{match[1]}"',
        body,
    )
