"""Syntax colouring at build time, for the languages the book quotes.

A page carries coloured code as plain HTML spans, so it reads correctly with scripts off and
costs the reader nothing to download. The colouring is a lexer, not a parser: comments, strings,
numbers, keywords and type names, which is what the eye uses to find its way around a block.
A language this module does not know is shown uncoloured, never guessed at.
"""

from __future__ import annotations

import html
import re

_RUST_KEYWORDS = (
    "as break const continue crate else enum extern false fn for if impl in let loop match mod "
    "move mut pub ref return self Self static struct super trait true type unsafe use where while "
    "dyn"
)
_PY_KEYWORDS = (
    "and as assert async await break class continue def del elif else except False finally for "
    "from global if import in is lambda None nonlocal not or pass raise return True try while "
    "with yield"
)
_JS_KEYWORDS = (
    "async await break case catch class const continue default delete do else export extends "
    "false finally for from function if import in instanceof let new null of return static super "
    "switch this throw true try typeof undefined var void while yield"
)
_SQL_KEYWORDS = (
    "select from where group by order having count sum min max avg and or not as limit join on "
    "inner left right outer distinct asc desc between in is null"
)

_LANGS = {
    "rust": (_RUST_KEYWORDS, r"//[^\n]*", r'b?"(?:\\.|[^"\\])*"' + r"|b'(?:\\.|[^'\\])'"),
    "python": (
        _PY_KEYWORDS,
        r"#[^\n]*",
        r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|[rbf]?"(?:\\.|[^"\\\n])*"|[rbf]?\'(?:\\.|[^\'\\\n])*\'',
    ),
    "javascript": (
        _JS_KEYWORDS,
        r"//[^\n]*",
        r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`',
    ),
    "sql": (_SQL_KEYWORDS, r"--[^\n]*", r"'(?:''|[^'])*'"),
    "bash": (
        "if then else fi for do done case esac in function export",
        r"#[^\n]*",
        r'"(?:\\.|[^"\\])*"|\'[^\']*\'',
    ),
    "yaml": ("true false null", r"#[^\n]*", r'"(?:\\.|[^"\\])*"|\'[^\']*\''),
    "json": ("true false null", r"(?!x)x", r'"(?:\\.|[^"\\])*"'),
}
_ALIASES = {
    "rs": "rust",
    "py": "python",
    "js": "javascript",
    "sh": "bash",
    "shell": "bash",
    "console": "bash",
    "yml": "yaml",
}


def _pattern(lang: str) -> re.Pattern:
    keywords, comment, string = _LANGS[lang]
    kw = "|".join(re.escape(k) for k in keywords.split())
    flags = re.IGNORECASE if lang == "sql" else 0
    parts = [
        rf"(?P<comment>{comment})",
        rf"(?P<string>{string})",
        r"(?P<number>\b(?:0x[0-9a-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)(?:u8|u16|u32|u64|usize|i8|i16|i32|i64|f32|f64)?\b)",
        rf"(?P<keyword>\b(?:{kw})\b)",
    ]
    if lang == "rust":
        parts.append(r"(?P<attr>#!?\[[^\]\n]*\])")
        parts.append(r"(?P<macro>\b[a-z_][a-z0-9_]*!)")
        parts.append(r"(?P<type>\b[A-Z][A-Za-z0-9_]*\b)")
    if lang == "python":
        parts.append(r"(?P<attr>@[\w.]+)")
        parts.append(r"(?P<type>\b[A-Z][A-Za-z0-9_]*\b)")
    if lang == "yaml":
        parts.append(r"(?P<type>^[ \t-]*[\w.-]+(?=:))")
    return re.compile("|".join(parts), flags | re.MULTILINE)


_COMPILED: dict[str, re.Pattern] = {}


def highlight(code: str, lang: str | None) -> str:
    """HTML for ``code``, with spans classed ``tok-<kind>`` where the language is known."""
    lang = _ALIASES.get((lang or "").lower(), (lang or "").lower())
    if lang not in _LANGS:
        return html.escape(code)
    pattern = _COMPILED.setdefault(lang, _pattern(lang))
    out, at = [], 0
    for m in pattern.finditer(code):
        out.append(html.escape(code[at : m.start()]))
        kind = m.lastgroup
        out.append(f'<span class="tok-{kind}">{html.escape(m.group(0))}</span>')
        at = m.end()
    out.append(html.escape(code[at:]))
    return "".join(out)
