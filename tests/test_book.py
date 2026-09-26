"""The book's structure and its rules, held by tests rather than by habit.

Each test here enforces something CLAUDE.md or AUTHORING_GUIDE.md says. If one fails, the page
is wrong or the rule is, and the rule's documentation says which to suspect.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

from tools.outline import APPENDICES, CHAPTER_SHAPE, CHAPTERS, EXPERIMENTS, PARTS, UNWRITTEN
from tools.render import LabBlockError, parse_lab_block

ROOT = Path(__file__).resolve().parent.parent
BOOK_PAGES = sorted(
    [ROOT / "index.md"]
    + list((ROOT / "parts").glob("*.md"))
    + list((ROOT / "chapters").glob("*.md"))
    + list((ROOT / "appendices").glob("*.md"))
)
DOCS = [
    ROOT / n for n in ("README.md", "CLAUDE.md", "PLAN.md", "AUTHORING_GUIDE.md", "STYLE.md", "NEXT_STEPS.md")
]
WRITTEN = [c for c in CHAPTERS if UNWRITTEN not in (ROOT / c.path).read_text()]
#: Chapters the Python reader covers: their problems exist in Python as well as Rust.
PORTED = [c for c in WRITTEN if (ROOT / "exercises" / "python" / f"{c.slug}.py").exists()]


def fences(text: str):
    """Yield (language, body) for every fenced block."""
    for m in re.finditer(r"^```([^\n]*)\n(.*?)^```\s*$", text, re.M | re.S):
        yield m.group(1).strip(), m.group(2)


def prose(text: str) -> str:
    """The page with its fenced blocks and inline code removed."""
    text = re.sub(r"^```.*?^```\s*$", "", text, flags=re.M | re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def headings(text: str, level: int) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(rf"^{'#' * level} (.+)$", prose(text), re.M)]


def test_the_table_of_contents_is_the_outline():
    toc = yaml.safe_load((ROOT / "myst.yml").read_text())["project"]["toc"]
    files = [toc[0]["file"]]
    for entry in toc[1:]:
        if "file" in entry:
            files.append(entry["file"])
        files += [c["file"] for c in entry.get("children", [])]
    expected = ["index.md"]
    for part in PARTS:
        expected.append(part.path)
        expected += [c.path for c in CHAPTERS if c.part == part.title]
    expected += [a.path for a in APPENDICES]
    assert files == expected


@pytest.mark.parametrize("chapter", CHAPTERS, ids=lambda c: c.slug)
def test_every_chapter_has_the_seven_part_shape(chapter):
    text = (ROOT / chapter.path).read_text()
    assert headings(text, 2) == list(CHAPTER_SHAPE)
    assert f"({chapter.anchor})=" in text, "the chapter's label is its slug"
    assert f"\ntitle: {chapter.title}\n" in text
    assert f"\n# {chapter.title}\n" in text, "the heading repeats the title, so MyST drops it"


def test_no_identifier_carries_a_chapter_number():
    """A chapter's number is derived from its position. Labels and slugs never contain one."""
    for c in CHAPTERS:
        assert not re.search(r"\d", c.slug), c.slug


@pytest.mark.parametrize("page", BOOK_PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_code_is_quoted_by_text_anchor_never_by_line_number(page):
    assert ":lines:" not in page.read_text(), "line numbers rot on the first edit above them"


@pytest.mark.parametrize("page", BOOK_PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_rust_is_pasted_into_a_page(page):
    """Rust in a page is quoted from the crate with {literalinclude}, never pasted."""
    for lang, _ in fences(page.read_text()):
        assert lang not in ("rust", "rs"), "quote the implementation with {literalinclude}"


@pytest.mark.parametrize("page", BOOK_PAGES + DOCS, ids=lambda p: p.name)
def test_no_em_dashes(page):
    if not page.exists():
        pytest.skip("not written")
    assert chr(0x2014) not in page.read_text(), "STYLE.md: no em dashes"


BANNED = [r"\bIn this chapter\b", r"\bsimply\b", r"\bobviously\b", r"\bjust\b", r"\bbasically\b"]


@pytest.mark.parametrize("page", BOOK_PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_prose_avoids_the_words_style_md_bans(page):
    text = prose(page.read_text())
    found = [p for p in BANNED if re.search(p, text, re.I)]
    assert not found, f"STYLE.md rule 19: {found}"


def lab_blocks(text: str) -> list[dict]:
    return [parse_lab_block(body) for lang, body in fences(text) if lang == "lab"]


@pytest.mark.parametrize("chapter", CHAPTERS, ids=lambda c: c.slug)
def test_experiments_are_the_ones_the_outline_declares(chapter):
    text = (ROOT / chapter.path).read_text()
    used = {b["experiment"] for b in lab_blocks(text)}
    if chapter in WRITTEN:
        assert used == set(chapter.experiments)
    else:
        assert used <= set(chapter.experiments)


def test_every_experiment_is_used_by_some_chapter():
    used = {e for c in CHAPTERS for e in c.experiments}
    assert used == set(EXPERIMENTS)


def test_a_lab_block_naming_an_unknown_experiment_or_fixture_is_refused():
    with pytest.raises(LabBlockError):
        parse_lab_block("experiment: nonsense")
    with pytest.raises(LabBlockError):
        parse_lab_block("experiment: footer\nfixture: missing.parquet")


def test_every_mounted_experiment_has_a_module():
    js = (ROOT / "web" / "lab" / "lab.js").read_text()
    for e in EXPERIMENTS:
        assert re.search(rf"\b{e}: mount", js), f"web/lab/lab.js does not mount {e}"


@pytest.mark.parametrize("chapter", WRITTEN, ids=lambda c: c.slug)
def test_a_written_chapters_problems_are_tests(chapter):
    """Problems are stubs in the exercises crate, graded by tests marked #[ignore]."""
    stubs = ROOT / "exercises" / "src" / f"{chapter.slug}.rs"
    tests = ROOT / "exercises" / "tests" / f"{chapter.slug}.rs"
    assert stubs.exists() and tests.exists()
    assert f"pub mod {chapter.slug};" in (ROOT / "exercises" / "src" / "lib.rs").read_text()
    assert "todo!(" in stubs.read_text(), "ship the stubs unsolved"
    test_src = tests.read_text()
    assert "#[ignore" in test_src
    text = (ROOT / chapter.path).read_text()
    section = text.split("\n## Problems\n", 1)[1].split("\n## Where to go next\n", 1)[0]
    commands = [body.strip() for lang, body in fences(section) if lang == "bash"]
    assert commands, "each tested problem shows the command that runs it"
    python_tests = ROOT / "exercises" / "python" / "tests" / f"test_{chapter.slug}.py"
    rust, python = [], []
    for cmd in commands:
        m = re.fullmatch(r"cargo test -p exercises --test (\w+)(?: (\w+))? -- --ignored", cmd)
        if m:
            assert m.group(1) == chapter.slug
            if m.group(2):
                assert f"fn {m.group(2)}" in test_src, f"no test named {m.group(2)}*"
            rust.append(m.group(2))
            continue
        m = re.fullmatch(
            r"python3 -m pytest exercises/python/tests/test_(\w+)\.py --problems(?: -k (\w+))?", cmd
        )
        assert m, f"unexpected command: {cmd}"
        assert m.group(1) == chapter.slug
        if m.group(2):
            assert f"def test_{m.group(2)}" in python_tests.read_text(), f"no test named {m.group(2)}*"
        python.append(m.group(2))
    if chapter in PORTED:
        assert python == rust, "a ported chapter shows each problem's command in both languages"
    else:
        assert not python, "Python problem commands belong to chapters the Python reader covers"
    assert "No test" in section, "every chapter has a problem about the reader's own system"


@pytest.mark.parametrize("chapter", WRITTEN, ids=lambda c: c.slug)
def test_a_written_chapter_includes_only_generated_fragments_that_exist(chapter):
    text = (ROOT / chapter.path).read_text()
    for m in re.finditer(r"```\{include\} (\S+)", text):
        assert (ROOT / "chapters" / m.group(1)).exists(), m.group(1)


def test_the_renderer_and_the_outline_know_the_same_pages():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build-site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sources = [p["source"] for p in module.page_list()]
    assert sources[0] == "index.md"
    assert sorted(sources) == sorted(str(p.relative_to(ROOT)) for p in BOOK_PAGES)


def test_the_number_check_catches_a_typed_number(tmp_path):
    spec = importlib.util.spec_from_file_location("verify_numbers", ROOT / "scripts" / "verify-numbers.py")
    vn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vn)
    page = ROOT / "chapters" / "_scratch_test_page.md"
    try:
        page.write_text("---\ntitle: x\n---\n\nThe footer is 380 bytes.\n\n```\n637 bytes\n```\n")
        found = vn.problems(page)
        assert len(found) == 1 and "380 bytes" in found[0]
        page.write_text("% number-ok: a definition\nA power of 256.\n\nA power of 256.\n")
        assert len(vn.problems(page)) == 1
    finally:
        page.unlink()


def test_every_chapter_is_in_both_readers():
    """The book is written in Python and in Rust throughout; a chapter in one only is unfinished."""
    assert [c.slug for c in PORTED] == [c.slug for c in WRITTEN]


@pytest.mark.parametrize("chapter", PORTED, ids=lambda c: c.slug)
def test_a_ported_chapter_quotes_both_readers(chapter):
    """Every excerpt of the Rust reader has its Python counterpart beside it, in a tab set."""
    text = (ROOT / chapter.path).read_text()
    rust = re.findall(r"^```\{literalinclude\} \.\./crates/parquet-lab/", text, re.M)
    python = re.findall(r"^```\{literalinclude\} \.\./python/", text, re.M)
    assert len(rust) == len(python), "quote each step in Python and in Rust"
    assert text.count("::::{tab-set}") >= len(rust)
    stubs = (ROOT / "exercises" / "python" / f"{chapter.slug}.py").read_text()
    assert "raise NotImplementedError(" in stubs, "ship the stubs unsolved"
    tests = (ROOT / "exercises" / "python" / "tests" / f"test_{chapter.slug}.py").read_text()
    assert "@pytest.mark.problem(" in tests


def test_the_python_engine_runs_exactly_the_ported_chapters_labs():
    """The labs offer the Python engine for a chapter once its reader is ported, and not before."""
    import ast

    tree = ast.parse((ROOT / "python" / "parquet_lab" / "browser.py").read_text())
    engine = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "EXPERIMENTS"
    )
    assert set(engine) == {e for c in PORTED for e in c.experiments}
