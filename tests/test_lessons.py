"""Lesson boundaries must preserve complete examples, code and a valid reference route."""

import importlib.util
import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tools.lesson_practice import render_transfer
from tools.lessons import MODULES, lesson_nodes, reading_pages, reference_links, resources, supporting_nodes
from tools.outline import CHAPTERS

ROOT = Path(__file__).resolve().parent.parent


def builder():
    spec = importlib.util.spec_from_file_location("lesson_site", ROOT / "scripts/build-site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_reading_route_has_all_core_lessons_and_skips_optional_labs():
    route = reading_pages(builder().page_list())
    hrefs = [page["href"] for page in route]
    assert len(hrefs) == len(set(hrefs))
    assert not any(p["source"].startswith("appendices/") for p in route)
    for lessons in MODULES.values():
        positions = [hrefs.index(lesson.href) for lesson in lessons if not lesson.optional]
        assert positions == list(range(positions[0], positions[0] + len(positions)))
        assert all(lesson.href not in hrefs for lesson in lessons if lesson.optional)
    assert set(MODULES) == {c.slug for c in CHAPTERS}
    assert hrefs[hrefs.index("why-parquet-exists.html") + 1] == "read-fewer-columns.html"
    assert hrefs[hrefs.index("choose-a-table-layout.html") + 1] == "anatomy-of-a-parquet-file.html"
    assert hrefs[hrefs.index("choose-a-tail-read.html") + 1] == "the-type-system.html"
    assert hrefs[hrefs.index("stored-levels.html") + 1] == "the-values.html"


@pytest.mark.parametrize("slug", MODULES)
def test_real_parse_partitions_all_quoted_sources_without_loss_or_duplication(slug):
    content = ROOT / "_build/site/content"
    parsed = next(
        json.loads(path.read_text())
        for path in content.glob("*.json")
        if json.loads(path.read_text()).get("location", "").endswith(f"/{slug}.md")
    )
    groups = lesson_nodes(parsed["mdast"], slug)

    def sources(node):
        found = [node["file"]] if node.get("type") == "include" else []
        for child in node.get("children", []):
            found.extend(sources(child))
        return found

    # Count actual published ownership after splitting support and moving coding problems.
    support = supporting_nodes(groups, next(c for c in CHAPTERS if c.slug == slug))
    assert not sources(groups["overview"]), "module intros must not hide code or generated evidence"
    owned = [*(groups[lesson.slug] for lesson in MODULES[slug]), support["notes"]]
    if next(c for c in CHAPTERS if c.slug == slug).explainer:
        owned.append(support["practice"])
    if slug in ("what_a_query_engine_does", "what_iceberg_adds"):
        owned.append(support["comparison"])
    assert sorted(sources(parsed["mdast"])) == sorted(source for group in owned for source in sources(group))
    for lesson in MODULES[slug]:
        nodes = groups[lesson.slug]
        text = json.dumps(nodes)
        if not lesson.optional:
            assert '"lang": "problems"' not in text
            assert '"lang": "practice"' in text or '"lang": "transfer"' in text
        else:
            assert '"lang": "problems"' in text
            quoted = sources(nodes)
            assert any("../python/parquet_lab/" in source for source in quoted)
            assert any("../crates/parquet-lab/" in source for source in quoted)


@pytest.mark.parametrize("failure", ["missing", "duplicate", "reordered"])
def test_invalid_boundaries_fail_instead_of_swallowing_a_lesson(failure):
    names = [lesson.slug for lesson in MODULES["nested_data"]] + ["reference"]
    if failure == "missing":
        names.pop(1)
    elif failure == "duplicate":
        names.insert(1, names[0])
    else:
        names[0], names[1] = names[1], names[0]
    nodes = [
        item
        for name in names
        for item in (
            {"type": "code", "lang": "lesson", "value": name},
            {"type": "paragraph", "children": []},
        )
    ]
    with pytest.raises(ValueError, match="lesson markers"):
        lesson_nodes({"children": [{"type": "block", "children": nodes}]}, "nested_data")


def test_omitted_sections_link_to_reference_while_local_anchors_stay_local():
    body = '<h2 id="here">Here</h2><a href="#here">Local</a><a href="#limits">Limits</a>'
    repaired = reference_links(body, "complete.html")
    assert 'href="#here"' in repaired
    assert 'href="complete.html#limits"' in repaired


def test_fresh_footer_uses_a_different_writer_fixture():
    manifest = json.loads((ROOT / "fixtures/multiple-row-groups.json").read_text())
    tiny = json.loads((ROOT / "fixtures/tiny.json").read_text())
    assert manifest["footer_length"] != tiny["footer_length"]
    output = render_transfer("footer")
    assert str(manifest["file_size"]) in output
    assert str(manifest["footer_length"]) in output
    assert str(manifest["file_size"] - 8 - manifest["footer_length"]) in output
    assert "<details><summary>Check your reasoning</summary>" in output


@pytest.mark.parametrize("case", ["scalar", "list", "nested"])
def test_schematic_inputs_are_labelled_and_have_native_reasoning(case):
    output = render_transfer(case)
    assert "Schematic input" in output
    assert '<th scope="col">r</th>' in output
    assert "Check your reasoning" in output
    assert "script" not in output


def test_optional_resources_are_bounded_and_not_the_full_chapter():
    for chapter in CHAPTERS:
        kinds = {lesson.kind for lesson in resources(chapter)}
        assert "notes" in kinds
        assert ("practice" in kinds) == chapter.explainer
        assert all(
            lesson.optional and lesson.href != chapter.anchor + ".html" for lesson in resources(chapter)
        )


def test_published_chapter_urls_are_indexes_without_combined_content():
    class Elements(HTMLParser):
        def __init__(self):
            super().__init__()
            self.classes = []

        def handle_starttag(self, tag, attrs):
            self.classes.extend(dict(attrs).get("class", "").split())

    for chapter in CHAPTERS:
        page = ROOT / "_build/html" / f"{chapter.anchor}.html"
        document = Elements()
        document.feed(page.read_text())
        assert "module-card" in document.classes
        assert not {"worked-example", "code-disclosure", "workbench", "lab"} & set(document.classes)
        assert not (ROOT / "_build/html/integration").exists()


def test_component_harness_cannot_be_written_into_the_publish_directory(tmp_path):
    site = tmp_path / "site"
    run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build-site.py"),
            "--out",
            str(site),
            "--integration-out",
            str(site / "private"),
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 2
    assert "outside the published site" in run.stderr
    assert not site.exists()
