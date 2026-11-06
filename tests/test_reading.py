"""Saved examples remain real, optional code stays optional, and chapters teach without a run."""

import json
from pathlib import Path

import pytest

from tools import render as renderer
from tools.outline import CHAPTERS
from tools.walkthrough_results import RESULTS, edited, source_digest

ROOT = Path(__file__).resolve().parent.parent


def test_every_quoted_walkthrough_has_a_current_saved_answer():
    saved = json.loads(RESULTS.read_text())
    paths = list((ROOT / "walkthroughs/python").glob("*/*.py"))
    assert set(saved) == {p.relative_to(ROOT).as_posix() for p in paths}
    for p in paths:
        result = saved[p.relative_to(ROOT).as_posix()]
        assert result["source_sha256"] == source_digest(p.read_text())
        assert result["stdout"].strip()
        for case in result["comparisons"]:
            assert edited(p.read_text(), case["changes"]) != p.read_text()
            assert case["stdout"] != result["stdout"]
            assert case["explanation"]


@pytest.mark.parametrize("chapter", CHAPTERS, ids=lambda c: c.slug)
def test_every_chapter_has_a_goal_and_a_conceptual_question(chapter):
    text = (ROOT / chapter.path).read_text()
    assert ":class: reading-guide" in text
    assert text.count("```checkpoint\n") == 1
    assert text.index("```checkpoint") > text.index("## Key takeaways")
    assert text.index("```checkpoint") < text.index("## Problems")
    if not chapter.explainer:
        assert "**Optional implementation.**" in text


def test_saved_answers_are_outside_optional_code_and_escaped(monkeypatch):
    path = "walkthroughs/python/anatomy_of_a_parquet_file/first_bytes.py"
    monkeypatch.setattr(
        renderer,
        "_saved_results",
        lambda: {
            path: {
                "source_sha256": source_digest((ROOT / path).read_text()),
                "stdout": "<script> & bytes\n",
                "comparisons": [],
            }
        },
    )
    node = {
        "type": "tabSet",
        "children": [
            {
                "type": "tabItem",
                "sync": lang,
                "children": [
                    {
                        "type": "include",
                        "literal": True,
                        "file": "../" + source,
                        "children": [{"type": "code", "lang": lang, "value": "pass"}],
                    }
                ],
            }
            for lang, source in [("python", path), ("rust", "walkthroughs/src/bin/first_bytes.rs")]
        ],
    }
    output = renderer.render(node)
    assert "&lt;script&gt; &amp; bytes" in output
    assert output.index("example-result") < output.index('<details class="code-disclosure">')
    assert output.startswith('<section class="worked-example">') and output.endswith("</details></section>")
    assert "Read or run the code" in output
    assert "<details open" not in output


def test_a_stale_result_fails_the_build(monkeypatch):
    path = "walkthroughs/python/anatomy_of_a_parquet_file/first_bytes.py"
    monkeypatch.setattr(renderer, "_saved_results", lambda: {path: {"source_sha256": "stale"}})
    with pytest.raises(ValueError, match="stale walkthrough"):
        renderer._worked_result(path)


def test_comparison_edits_cannot_silently_stop_matching():
    with pytest.raises(ValueError, match="match once"):
        edited("name = 'x'\nname = 'x'", [("name = 'x'", "name = 'y'")])


def test_a_checkpoint_hides_only_the_answer():
    output = renderer.render(
        {"type": "code", "lang": "checkpoint", "value": "question: Can x < y?\nanswer: Only if x < y."}
    )
    assert output.index("Can x &lt; y?") < output.index("<details>")
    assert output.index("Only if x &lt; y.") > output.index("<details>")
    with pytest.raises(ValueError):
        renderer.render({"type": "code", "lang": "checkpoint", "value": "question: Missing answer"})
