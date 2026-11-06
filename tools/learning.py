"""Chapter-two practice, derived from the real reader and its traced object store."""

import html
import json
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
from parquet_lab.object_store import MemoryStore, NetworkModel, TracingStore  # noqa: E402
from parquet_lab.reader import FooterOptions, Head, Known, SuffixRange, read_footer  # noqa: E402


def esc(value):
    return html.escape(str(value))


@lru_cache(maxsize=1)
def evidence():
    data = (ROOT / "fixtures/tiny.parquet").read_bytes()
    files = MemoryStore()
    files.put("tiny.parquet", data)
    store = TracingStore(files, NetworkModel())
    opened = read_footer(store, "tiny.parquet", FooterOptions())
    chunk = next(c for c in opened.metadata.row_groups[0].columns if c.path == ["country"])
    span = chunk.byte_range()
    cases = []
    sizes = sorted({8, 128, 256, opened.trailer.footer_length + 8, min(512, len(data))})
    for mode, source in [("head", Head()), ("known", Known(len(data))), ("suffix", SuffixRange())]:
        for size in sizes:
            traced = TracingStore(files, NetworkModel())
            read_footer(traced, "tiny.parquet", FooterOptions(size=source, prefetch=size))
            requests = [
                {"method": r.method, "range": r.range or "—", "bytes": r.bytes_returned, "why": r.why}
                for r in traced.requests
            ]
            cases.append(
                {
                    "mode": mode,
                    "prefetch": size,
                    "requests": requests,
                    "bytes": sum(r["bytes"] for r in requests),
                }
            )
    return {
        "size": len(data),
        "length": opened.trailer.footer_length,
        "start": opened.footer.start,
        "end": opened.footer.end,
        "magic": data[:4].decode("ascii"),
        "byte": data[0],
        "terms": opened.trailer.length_terms(),
        "chunk": {"start": span.start, "end": span.end},
        "sizes": sizes,
        "cases": cases,
    }


def trace_table(case):
    rows = "".join(
        f"<tr><td>{esc(r['method'])}</td><td><code>{esc(r['range'])}</code></td>"
        f"<td>{r['bytes']}</td><td>{esc(r['why'])}</td></tr>"
        for r in case["requests"]
    )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Request</th><th>Range</th>'
        "<th>File bytes returned</th><th>Why</th></tr></thead><tbody>" + rows + "</tbody></table></div>"
        f"<p>{len(case['requests'])} requests · {case['bytes']} file bytes returned.</p>"
    )


def render_learning(name):
    d = evidence()
    if name == "requests":
        modes = '<label>Size source <select name="mode"><option value="head">Ask with HEAD</option><option value="known">Size already known</option><option value="suffix">Use a suffix range</option></select></label>'
        sizes = (
            '<label>First GET size <select name="prefetch">'
            + "".join(f'<option value="{n}">{n} bytes</option>' for n in d["sizes"])
            + "</select></label>"
        )
        body = (
            "<p>Change the size source or the first read. Every displayed request is a trace from the book’s reader.</p>"
            f'<div class="learning-controls" hidden>{modes}{sizes}</div>'
            f'<div class="learning-trace">{trace_table(d["cases"][0])}</div>'
            "<details><summary>Compare all strategies without JavaScript</summary>"
            + "".join(
                f"<p><strong>{esc(c['mode'])} · {c['prefetch']} bytes prefetched</strong></p>{trace_table(c)}"
                for c in d["cases"]
            )
            + '</details><p class="learning-note">Byte totals count file data, excluding HTTP headers. Request costs use a simulated store, not a real network measurement.</p>'
        )
        payload = {"cases": d["cases"]}
        title = "Explore the reader’s requests"
    else:
        if name == "byte":
            title = "Read a byte in another notation"
            question = (
                f"The opening byte is written {d['byte']:02x} in hexadecimal. What is its decimal value?"
            )
            answer = d["byte"]
            explanation = f"Hexadecimal {answer:02x} means {answer // 16} × 16 + {answer % 16} = {answer}. ASCII interprets that value as {d['magic'][0]}. A representation is not the same as a meaning."
            before = "<p>Hexadecimal uses the digits 0–9, then a–f for ten through fifteen. Each position is worth sixteen times the position to its right.</p>"
        elif name == "length":
            title = "Decode the footer length"
            question = "Add the byte contributions. How many bytes long is the footer?"
            answer = d["length"]
            terms = d["terms"]
            before = (
                '<div class="table-wrap"><table><thead><tr><th>Hex byte</th><th>Decimal value</th><th>Place value</th><th>Contribution</th></tr></thead><tbody>'
                + "".join(
                    f"<tr><td><code>{b:02x}</code></td><td>{b}</td><td>{w:,}</td><td>{b * w:,}</td></tr>"
                    for b, w in terms
                )
                + "</tbody></table></div>"
            )
            explanation = (
                " + ".join(str(b * w) for b, w in terms)
                + f" = {answer}. Little-endian puts the smallest-weight byte first; it does not reverse the digits inside a byte."
            )
        elif name == "start":
            title = "Locate the footer"
            question = f"The file has {d['size']} bytes, the trailer has eight, and the footer has {d['length']}. At which offset does the footer start?"
            answer = d["start"]
            before = "<p>Subtract the trailer from the file size, then subtract the footer length.</p>"
            explanation = f"{d['size']} − 8 − {d['length']} = {answer}. The footer occupies [{answer}, {d['end']}): it includes {answer} and ends before {d['end']}. Its last included byte is {d['end'] - 1}."
        elif name == "chunk":
            title = "Turn the map into a request"
            answer = d["chunk"]["end"] - 1
            before = f"<p>The footer places <code>country</code> at [{d['chunk']['start']}, {d['chunk']['end']}). HTTP includes both endpoints.</p>"
            question = f"Complete the HTTP range: bytes={d['chunk']['start']}–?"
            explanation = f"Use bytes={d['chunk']['start']}-{answer}. That is {d['chunk']['end'] - d['chunk']['start']} bytes. Including offset {answer + 1} would fetch a byte of the next chunk."
        else:
            raise ValueError(f"unknown learning check {name!r}")
        title_id = f"learning-{name}"
        body = (
            before + f'<p id="{title_id}-question">{esc(question)}</p>'
            f'<form class="learning-controls" hidden><label for="{title_id}-input">Your answer</label>'
            f'<input id="{title_id}-input" type="number" step="1" required aria-describedby="{title_id}-question">'
            '<button type="submit">Check answer</button><p class="learning-feedback" role="status"></p></form>'
            f"<details><summary>Reveal the explanation</summary><p>{esc(explanation)}</p></details>"
        )
        hints = {
            "byte": "Hexadecimal uses base sixteen. Multiply the first digit by sixteen, then add the second.",
            "length": "Multiply each decimal byte value by its place value, then add the contributions.",
            "start": "Subtract both the trailer length and the footer length from the file size.",
            "chunk": "The table excludes its end. HTTP includes its end, so request the preceding byte.",
        }
        payload = {"answer": answer, "explanation": explanation, "hint": hints[name]}
    encoded = json.dumps(payload).replace("</", "<\\/")
    return (
        f'<section class="learning-check" data-learning="{name}" aria-label="{esc(title)}">'
        f'<p class="learning-title">{esc(title)}</p>{body}'
        f'<script type="application/json" class="learning-data">{encoded}</script></section>'
    )
