"""Definitions have one source, valid destinations and an ordinary-link fallback."""

import json
from pathlib import Path

import pytest

from tools import render as renderer
from tools.glossary import entries, render_glossary, targets

ROOT = Path(__file__).resolve().parent.parent


def term(title, text):
    return [
        {"type": "heading", "depth": 2, "children": [{"type": "text", "value": title}]},
        {"type": "paragraph", "children": [{"type": "text", "value": text}]},
    ]


def test_definitions_keep_native_anchors_and_escape_text():
    intro, definitions = entries({"type": "root", "children": term("Projection", "x < y & z")})
    result = render_glossary(intro, definitions)
    assert 'id="term-projection"' in result and 'id="projection"' in result
    assert "x &lt; y &amp; z" in result
    assert 'href="#glossary-p"' in result
    assert '<div class="glossary-search" hidden>' in result


def test_duplicate_or_empty_definitions_fail_the_build():
    with pytest.raises(ValueError, match="duplicate"):
        entries({"type": "root", "children": term("Projection", "a") + term("Projection", "b")})
    with pytest.raises(ValueError, match="explanatory content"):
        entries({"type": "root", "children": term("Projection", "a")[:1]})


def test_only_explicit_term_names_get_lookup_links(monkeypatch):
    _, definitions = entries({"type": "root", "children": term("Projection", "Selecting columns.")})
    monkeypatch.setattr(renderer, "TERMS", targets(definitions))
    bold = {"type": "strong", "children": [{"type": "text", "value": "Column projection"}]}
    assert 'class="term-link" href="glossary.html#term-projection"' in renderer.render(bold)
    assert renderer.render({"type": "text", "value": "Projection"}) == "Projection"
    bold["children"][0]["value"] = "Projection saves some reads"
    assert "term-link" not in renderer.render(bold)
    bold["children"] = [
        {"type": "link", "url": "example.html", "children": [{"type": "text", "value": "Projection"}]}
    ]
    assert renderer.render(bold).count("<a ") == 1


def test_lookup_payload_and_glossary_show_the_same_definitions():
    data = json.loads((ROOT / "_build/html/glossary.json").read_text())
    page = (ROOT / "_build/html/glossary.html").read_text()
    assert data and len(data) == page.count('class="glossary-entry"')
    for key, entry in data.items():
        assert f'id="{key}"' in page
        assert entry["body"] in page
        assert entry["href"] == f"glossary.html#{key}"
        assert "Learn it:" in entry["body"]


def test_first_lesson_teaches_its_reading_cost_vocabulary_before_the_fresh_case():
    page = (ROOT / "_build/html/read-fewer-columns.html").read_text()
    question = page.index('class="lesson-practice"')
    for name in ("projection", "metadata", "footer", "prefetch"):
        assert page.index(f'class="term-link" href="glossary.html#term-{name}"') < question
