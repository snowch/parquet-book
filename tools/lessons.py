"""Short reading routes cut from the canonical chapter parse, never copied prose."""

from __future__ import annotations

import copy
import html
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Lesson:
    slug: str
    title: str
    outcome: str
    preparation: str
    optional: bool = False
    kind: str = "core"

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
            "Optional lab after the reading lessons. The coding problems are included in this lab.",
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
            "Optional lab after the reading lessons. The coding problems are included in this lab.",
            optional=True,
        ),
    ),
}


MODULES.update(
    {
        "why_parquet_exists": (
            Lesson(
                "read-fewer-columns",
                "Read fewer columns",
                "Explain why selecting columns can reduce file bytes read.",
                "Start here. You need only the idea of rows and columns.",
            ),
            Lesson(
                "choose-a-table-layout",
                "Choose a layout for a workload",
                "Choose between column scans and complete-record lookups.",
                "Use the column-read comparison from the previous lesson.",
            ),
        ),
        "the_type_system": (
            Lesson(
                "follow-schema-paths",
                "Follow the schema tree",
                "Identify leaves, groups and the path that names a stored column.",
                "You can use a footer as a map.",
            ),
            Lesson(
                "interpret-logical-types",
                "Interpret the same stored bytes",
                "Use the physical type and logical annotation to interpret a value.",
                "You can find a leaf and its schema annotation.",
            ),
            Lesson(
                "count-schema-levels",
                "Count optional and repeated ancestors",
                "Derive maximum definition and repetition levels from a leaf path.",
                "Use required, optional and repeated fields from the schema lesson.",
            ),
            Lesson(
                "build-schema-reader",
                "Build the schema and type reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "encodings": (
            Lesson(
                "dictionary-values",
                "Replace repeated values with indices",
                "Reconstruct values from a dictionary and its indices.",
                "Use the level-stream hybrid from Nested data.",
            ),
            Lesson(
                "integer-differences",
                "Reconstruct integer differences",
                "Recover values from a first value and successive deltas.",
                "You can read a sequence of integers; physical header details are optional.",
            ),
            Lesson(
                "string-prefixes",
                "Rebuild strings from lengths and prefixes",
                "Recover strings from stored lengths, shared prefixes and suffixes.",
                "Use integer deltas and byte-array values.",
            ),
            Lesson(
                "split-byte-positions",
                "Separate byte positions before compression",
                "Explain why byte-stream split can change compressibility without changing encoded length.",
                "Use fixed-width physical types.",
            ),
            Lesson(
                "choose-an-encoding",
                "Choose an encoding for a pattern",
                "Use value patterns and measured sizes to justify an encoding choice.",
                "Compare dictionaries, integer/string deltas and byte-stream split.",
            ),
            Lesson(
                "build-encoding-readers",
                "Build the encoding readers",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "pages": (
            Lesson(
                "walk-page-boundaries",
                "Walk page boundaries",
                "Locate the next page from its header and compressed body size.",
                "Use column-chunk byte ranges.",
            ),
            Lesson(
                "compare-page-versions",
                "Compare data page versions",
                "Explain how V1 and V2 separate levels, values and compression.",
                "Use definition/repetition levels and page headers.",
            ),
            Lesson(
                "check-page-corruption",
                "Distinguish corruption from decoding errors",
                "Explain what checking a page CRC establishes and what it cannot establish.",
                "Use stored page bodies and headers.",
            ),
            Lesson(
                "build-page-reader",
                "Build the page reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "compression": (
            Lesson(
                "follow-literals-and-copies",
                "Follow literals and overlapping copies",
                "Trace how a compressed copy can reuse bytes it has just produced.",
                "Use encoded page bodies from Pages.",
            ),
            Lesson(
                "compare-codec-patterns",
                "Compare codecs on different patterns",
                "Distinguish a value-pattern effect from a codec-size comparison.",
                "Use literals, copies and the role of entropy coding.",
            ),
            Lesson(
                "weigh-compression-costs",
                "Weigh encoding and decompression costs",
                "Explain the tradeoff between bytes saved and page work required.",
                "Use byte-stream split and page-version compression boundaries.",
            ),
            Lesson(
                "build-decompressors",
                "Build the decompressors",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "metadata_and_statistics": (
            Lesson(
                "compare-typed-values",
                "Compare values in their declared order",
                "Use physical/logical types to choose the correct comparison order.",
                "Use physical types and logical annotations.",
            ),
            Lesson(
                "decide-usable-bounds",
                "Decide whether bounds are usable",
                "Distinguish known typed bounds from missing or unsafe statistics.",
                "Use the column’s comparison order.",
            ),
            Lesson(
                "handle-null-and-float-statistics",
                "Handle nulls and exceptional floats",
                "Explain how nulls, absent statistics, NaN and signed zero affect a decision.",
                "Use usable bounds and null counts.",
            ),
            Lesson(
                "account-for-footer-cost",
                "Account for metadata overhead",
                "Explain why more statistics can increase the cost paid by every query.",
                "Use row groups, columns and footer discovery.",
            ),
            Lesson(
                "build-statistics-reader",
                "Build the statistics reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "skipping_data": (
            Lesson(
                "rule-out-row-groups",
                "Rule out row groups safely",
                "Use bounds and null counts to prove a row group cannot match.",
                "Use typed, trustworthy statistics.",
            ),
            Lesson(
                "map-pages-to-rows",
                "Map kept pages across columns",
                "Use row ranges to select pages when columns have different page boundaries.",
                "First rule out whole row groups.",
            ),
            Lesson(
                "test-bloom-membership",
                "Interpret Bloom-filter membership",
                "Distinguish definite absence from possible presence.",
                "Use equality predicates and row-group candidates.",
            ),
            Lesson(
                "compose-a-pruning-plan",
                "Compose a safe skipping plan",
                "Explain the distinct contributions of ranges, page indexes and Bloom filters.",
                "Use all three mechanisms before comparing their combined result.",
            ),
            Lesson(
                "build-pruning-planner",
                "Build the pruning planner",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "how_readers_read": (
            Lesson(
                "trace-a-complete-scan",
                "Trace a complete scan",
                "Follow request dependencies from metadata to selected data pages.",
                "Use footer discovery and the pruning mechanisms.",
            ),
            Lesson(
                "choose-a-read-strategy",
                "Choose a read strategy",
                "Trade request latency against extra bytes, concurrency and merging.",
                "Keep the complete scan trace from the previous lesson in view.",
            ),
            Lesson(
                "build-scan-planner",
                "Build the scan planner",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "writing_parquet_well": (
            Lesson(
                "compare-writer-layouts",
                "Compare controlled writer layouts",
                "Separate the effect of a changed layout from a changed table or query.",
                "Use the complete scan and its costs.",
            ),
            Lesson(
                "choose-writer-settings",
                "Choose settings for a workload",
                "Justify a layout choice and its tradeoff for a new query mix.",
                "Use the controlled comparison before selecting settings.",
            ),
            Lesson(
                "inspect-writer-settings",
                "Inspect writer settings and reader costs",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "what_a_query_engine_does": (
            Lesson(
                "separate-scan-and-filter",
                "Separate scanning from filtering",
                "Explain which work belongs to the file scan and which to later query stages.",
                "Use projection, pruning and complete scan traces.",
            ),
            Lesson(
                "answer-from-metadata",
                "Answer a query from metadata",
                "State when row counts or bounds suffice without reading column data.",
                "Distinguish candidate row groups from filtered rows.",
            ),
            Lesson(
                "group-dictionary-values",
                "Group values across local dictionaries",
                "Explain why dictionary indices cannot be treated as global identities.",
                "Use dictionary pages and grouping after a scan.",
            ),
            Lesson(
                "limit-a-sorted-query",
                "Decide when a sorted limit can stop",
                "Distinguish bounded sort memory from evidence that scanning may stop.",
                "Use row-group ranges and trustworthy sort information.",
            ),
            Lesson(
                "use-join-derived-filters",
                "Use filters learned from a join input",
                "Explain how known build-side keys can prune the probe-side scan.",
                "Use a filtered scan and the distinction between pruning and matching.",
            ),
        ),
        "modular_encryption": (
            Lesson(
                "read-encryption-modes",
                "Recognise encryption modes",
                "Predict which metadata remains visible in the two footer modes.",
                "Use file signatures and the footer map.",
            ),
            Lesson(
                "distinguish-key-names-and-keys",
                "Distinguish key metadata from keys",
                "Explain why a key reference is not possession of decryption material.",
                "Use encrypted columns and the two footer modes.",
            ),
            Lesson(
                "inspect-protected-modules",
                "Inspect module boundaries and leakage",
                "Separate visible sizes and framing from protected values and verified authenticity.",
                "Use footer modes and key references.",
            ),
            Lesson(
                "build-encryption-inspector",
                "Build the encryption inspector",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "lakehouse_and_beyond": (
            Lesson(
                "read-partition-paths",
                "Read partition values from paths",
                "Explain how a dataset can supply a partition column absent from individual files.",
                "Use a query’s requested columns and predicates.",
            ),
            Lesson(
                "prune-files-before-footers",
                "Prune files before reading their footers",
                "Use table-level statistics to avoid opening ruled-out files.",
                "Use partition paths and file-level bounds.",
            ),
            Lesson(
                "resolve-table-membership",
                "Resolve table membership from a log",
                "Distinguish files present in storage from files active in a table version.",
                "Use partition paths and file statistics to decide which files might match a query.",
            ),
            Lesson(
                "build-table-reader",
                "Build the table reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "changing_a_table": (
            Lesson(
                "follow-snapshots-and-deletes",
                "Follow a snapshot and its deletes",
                "Explain how a snapshot changes visible rows while older data can remain stored.",
                "Use table membership and immutable Parquet files.",
            ),
            Lesson(
                "trace-a-table-lookup",
                "Trace a complete table lookup",
                "Follow the full metadata-to-row lookup chain and explain its cost.",
                "Use snapshots, file membership and page reads.",
            ),
            Lesson(
                "compare-update-costs",
                "Compare copy-on-write and merge-on-read",
                "Explain where update work is paid and how it changes later scans.",
                "Use the snapshot/delete example and a complete read path.",
            ),
            Lesson(
                "decide-when-to-compact",
                "Decide when compaction repays its cost",
                "Compare immediate rewriting with expected future scan savings.",
                "Use the read/write costs and small-file trade-offs from the previous lesson.",
            ),
            Lesson(
                "build-snapshot-reader",
                "Build the snapshot reader",
                "Connect the worked evidence to the implementation and try the coding problems.",
                "Optional lab after this module’s core lessons.",
                optional=True,
            ),
        ),
        "what_iceberg_adds": (
            Lesson(
                "follow-iceberg-metadata",
                "Follow Iceberg metadata to data files",
                "Explain how snapshot, manifest-list and manifest layers locate candidate files.",
                "Use table membership, statistics and snapshots.",
            ),
            Lesson(
                "keep-column-identity",
                "Keep column identity across schema changes",
                "Use field IDs to distinguish a rename from a different field reusing a name.",
                "Use physical/logical schema fields and table snapshots.",
            ),
            Lesson(
                "evolve-partition-specs",
                "Evolve partitioning without renaming fields",
                "Explain why files written under different partition specs can coexist.",
                "Use stable field IDs and partition-derived pruning.",
            ),
            Lesson(
                "commit-a-table-change",
                "Commit a table change safely",
                "Explain how an atomic metadata commit detects concurrent changes.",
                "Use immutable snapshots and metadata versions.",
            ),
        ),
    }
)


def module_href(chapter) -> str:
    """Existing chapter URLs now name the module, never a combined reading page."""
    return f"{chapter.anchor}.html"


def resources(chapter) -> tuple[Lesson, ...]:
    items = [
        Lesson(
            f"{chapter.anchor}-notes",
            "Limits and further reading",
            "Check this module’s scope, review its conclusions and find primary sources.",
            "Supporting material for this module’s lessons.",
            optional=True,
            kind="notes",
        )
    ]
    if chapter.explainer:
        items.append(
            Lesson(
                f"{chapter.anchor}-practice",
                "More practice",
                "Apply the module’s ideas to further questions and your own data.",
                "Try these after the core lessons; no code is required.",
                optional=True,
                kind="practice",
            )
        )
    if chapter.slug in ("what_a_query_engine_does", "what_iceberg_adds"):
        title = (
            "Compare query costs"
            if chapter.slug == "what_a_query_engine_does"
            else "Compare table-format features"
        )
        items.append(
            Lesson(
                f"{chapter.anchor}-comparison",
                title,
                "Use the comparison as a reference after learning the individual mechanisms.",
                "Optional comparison; follow the core lessons first.",
                optional=True,
                kind="comparison",
            )
        )
    return tuple(items)


def reading_pages(canonical: list[dict]) -> list[dict]:
    """The core route visits every module and lesson, skipping optional labs/resources."""
    pages = []
    for page in canonical:
        if page["source"].startswith("appendices/"):
            continue
        chapter = page.get("chapter")
        if not chapter:
            pages.append(page)
            continue
        pages.append({**page, "module": True})
        pages.extend(lesson_page(page, lesson) for lesson in MODULES[chapter.slug] if not lesson.optional)
    return pages


def lesson_page(page: dict, lesson: Lesson) -> dict:
    return {**page, "href": lesson.href, "title": lesson.title, "lesson": lesson}


def lesson_nodes(mdast: dict, chapter_slug: str) -> dict[str, dict]:
    """Partition canonical block wrappers; keep examples, tables and code pairs whole."""

    def blocks(node):
        for child in node.get("children", []):
            if child["type"] == "block":
                yield from blocks(child)
            else:
                yield copy.deepcopy(child)

    expected = [lesson.slug for lesson in MODULES[chapter_slug]] + ["reference"]
    found = []
    groups = {"overview": {"type": "root", "children": []}}
    current = "overview"
    for node in blocks(mdast):
        if node["type"] == "code" and node.get("lang") == "lesson":
            current = node["value"].strip()
            found.append(current)
            groups[current] = {"type": "root", "children": []}
        else:
            groups[current]["children"].append(node)
    if found != expected:
        raise ValueError(f"{chapter_slug}: lesson markers {found!r}, expected {expected!r}")
    if any(not group["children"] for name, group in groups.items() if name != "overview"):
        raise ValueError(f"{chapter_slug}: empty lesson")
    return groups


def supporting_nodes(groups: dict, chapter) -> dict[str, dict]:
    """Give problems, comparisons and limitations actual destinations, without a full page."""
    notes, problems, comparison = [], [], []
    destination = notes
    extra = chapter.slug in ("what_a_query_engine_does", "what_iceberg_adds")
    if extra:
        destination = comparison
    for node in groups["reference"]["children"]:
        if node.get("type") == "heading" and node.get("depth") == 2:
            title = node_text(node)
            destination = problems if title == "Problems" else notes
        destination.append(node)
    result = {
        "notes": {"type": "root", "children": notes},
        "practice": {"type": "root", "children": problems},
        "comparison": {"type": "root", "children": comparison},
    }
    build = next((lesson for lesson in MODULES[chapter.slug] if lesson.optional), None)
    if build:
        groups[build.slug]["children"].extend(problems)
    return result


def node_text(node) -> str:
    if "value" in node:
        return str(node["value"])
    return "".join(node_text(child) for child in node.get("children", []))


def module_card(chapter) -> str:
    lessons = MODULES[chapter.slug]
    core = [lesson for lesson in lessons if not lesson.optional]
    items = "".join(
        f'<li data-lesson="{lesson.slug}"><a href="{lesson.href}">{html.escape(lesson.title)}</a>'
        f"<p>{html.escape(lesson.outcome)}</p></li>"
        for lesson in core
    )
    optional = tuple(lesson for lesson in lessons if lesson.optional) + resources(chapter)
    links = "".join(
        f'<li data-lesson="{lesson.slug}"><a href="{lesson.href}">{html.escape(lesson.title)}</a></li>'
        for lesson in optional
    )
    return (
        '<section class="module-card" aria-label="Lessons in this module">'
        '<p class="eyebrow">Choose a lesson</p>'
        "<p>Follow these lessons in order. Each ends with a fresh case you can reason through without running code.</p>"
        f'<ol class="lesson-list">{items}</ol><div class="module-resources">'
        f"<p>Optional labs and supporting material</p><ul>{links}</ul></div></section>"
    )


def lesson_intro(chapter, lesson: Lesson) -> str:
    core = [item for item in MODULES[chapter.slug] if not item.optional]
    position = (
        {"notes": "Module notes", "practice": "Further practice", "comparison": "Optional comparison"}.get(
            lesson.kind, "Optional build lab"
        )
        if lesson.optional
        else f"Lesson {core.index(lesson) + 1} of {len(core)}"
    )
    return (
        '<div class="lesson-intro reading-guide">'
        f'<p class="eyebrow">{position} · <a href="{module_href(chapter)}">{html.escape(chapter.title)}</a></p>'
        f"<p><strong>Your goal:</strong> {html.escape(lesson.outcome)}</p>"
        f"<p><strong>Before you start:</strong> {html.escape(lesson.preparation)}</p>"
        "<p>Opening or running the code is optional.</p></div>"
    )


def reference_links(body: str, canonical_href: str) -> str:
    """Resolve local fragment links against the canonical source for the ownership pass."""
    ids = set(re.findall(r'\bid="([^"]+)"', body))
    return re.sub(
        r'href="#([^"]+)"',
        lambda match: match[0] if match[1] in ids else f'href="{canonical_href}#{match[1]}"',
        body,
    )


def migrate_links(body: str, anchors: dict[str, str]) -> str:
    return re.sub(r'href="([^"]+)"', lambda match: f'href="{anchors.get(match[1], match[1])}"', body)


def legacy_navigation(body: str, chapter, anchors: dict[str, str]) -> str:
    """Old deep links open the owning lesson; without JS they land on its module entry."""
    prefix = module_href(chapter) + "#"
    mapping = {key[len(prefix) :]: value for key, value in anchors.items() if key.startswith(prefix)}
    present = set(re.findall(r'\bid="([^"]+)"', body))
    for lesson in (*MODULES[chapter.slug], *resources(chapter)):
        old_ids = [
            key
            for key, value in mapping.items()
            if (value.startswith(lesson.href + "#") or value == lesson.href) and key not in present
        ]
        targets = "".join(
            f'<span id="{html.escape(key, quote=True)}" class="legacy-anchor"></span>' for key in old_ids
        )
        body = body.replace(f'<li data-lesson="{lesson.slug}">', f'<li data-lesson="{lesson.slug}">{targets}')
    encoded = json.dumps(mapping).replace("</", "<\\/")
    return (
        body
        + f"""<script>(() => {{
const targets = {encoded};
let fragment = location.hash.slice(1);
try {{ fragment = decodeURIComponent(fragment); }} catch (e) {{}}
const target = targets[fragment];
if (target && target.split("#")[0] !== location.pathname.split("/").pop()) location.replace(target);
}})();</script>"""
    )
