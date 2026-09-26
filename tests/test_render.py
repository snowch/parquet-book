"""The renderer refuses what it does not understand, and escapes what it does."""

from __future__ import annotations

import pytest

from tools.highlight import highlight
from tools.render import UnknownNodeError, render, render_page


def test_an_unknown_node_raises_rather_than_vanishing():
    with pytest.raises(UnknownNodeError):
        render({"type": "someNewDirective", "children": []})


def test_text_is_escaped():
    assert render({"type": "text", "value": "<b>&"}) == "&lt;b&gt;&amp;"


def test_a_lab_block_becomes_a_mount_point_with_a_fallback():
    html = render({"type": "code", "lang": "lab", "value": "experiment: footer\nfixture: tiny.parquet"})
    assert 'class="lab"' in html
    assert 'data-experiment="footer"' in html and 'data-fixture="tiny.parquet"' in html
    assert "needs JavaScript" in html


def test_a_literal_include_names_its_source_file():
    node = {
        "type": "include",
        "literal": True,
        "file": "../crates/parquet-lab/src/bytes.rs",
        "children": [{"type": "code", "lang": "rust", "value": "fn f() {}"}],
    }
    html = render(node)
    assert "crates/parquet-lab/src/bytes.rs" in html and "../" not in html.split("<pre>")[0]


def test_footnotes_are_collected_at_the_end():
    tree = {
        "type": "root",
        "children": [
            {"type": "paragraph", "children": [{"type": "footnoteReference", "enumerator": "1"}]},
            {"type": "footnoteDefinition", "enumerator": "1", "children": [{"type": "text", "value": "n"}]},
        ],
    }
    html = render_page(tree)
    assert html.index("fnref-1") < html.index('class="footnotes"')


def test_highlighting_colours_rust_and_escapes_it():
    out = highlight('fn f() -> u32 { let s = "<x>"; 42 } // done', "rust")
    assert '<span class="tok-keyword">fn</span>' in out
    assert '<span class="tok-string">&quot;&lt;x&gt;&quot;</span>' in out
    assert '<span class="tok-comment">// done</span>' in out
    assert '<span class="tok-number">42</span>' in out


def test_an_unknown_language_is_shown_uncoloured():
    assert highlight("a < b", "brainfuck") == "a &lt; b"


def test_code_shows_one_blank_line_at_most():
    out = render({"type": "code", "lang": "", "value": "def a():\n    pass\n\n\ndef b():\n    pass"})
    assert "pass\n\ndef b" in out and "\n\n\n" not in out
