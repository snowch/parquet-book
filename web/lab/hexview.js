// The byte view: every byte of a file, sixteen to a row, as hex and as ASCII.
//
// It draws what it is given and remembers nothing about Parquet. Colours come from regions the
// reader reported (a span and a kind each), dimming from the spans the reader actually fetched,
// and highlights from whichever panel the reader last pointed at. So when a byte is coloured as
// the footer length, that is because the Rust reader said those are the footer-length bytes.

const ROW = 16;

export class HexView {
  constructor(container, { onSelect } = {}) {
    this.el = document.createElement("div");
    this.el.className = "hex";
    this.el.setAttribute("role", "grid");
    this.el.setAttribute("aria-label", "File bytes");
    container.append(this.el);
    this.onSelect = onSelect || (() => {});
    this.bytes = new Uint8Array();
    this.cells = [];
    this.chars = [];
    this.selection = null;
    this.el.addEventListener("click", (e) => this.#click(e));
    this.el.addEventListener("keydown", (e) => this.#key(e));
  }

  // Draw `bytes`, coloured by `regions`: [{ span: [start, end], kind, cls }], innermost last.
  render(bytes, regions = []) {
    this.bytes = bytes;
    const kinds = new Array(bytes.length).fill("");
    const titles = new Array(bytes.length).fill("");
    for (const r of regions) {
      for (let i = r.span[0]; i < Math.min(r.span[1], bytes.length); i++) {
        kinds[i] = r.cls;
        titles[i] = r.title;
      }
    }
    const rows = [];
    for (let row = 0; row < bytes.length; row += ROW) {
      let hex = "", ascii = "";
      for (let i = row; i < row + ROW; i++) {
        if (i >= bytes.length) {
          hex += '<span class="pad">  </span>';
          continue;
        }
        const b = bytes[i];
        const cls = kinds[i] ? ` ${kinds[i]}` : "";
        const t = titles[i] ? ` title="${titles[i]} · offset ${i}"` : ` title="offset ${i}"`;
        hex += `<span class="b${cls}" data-o="${i}"${t}>${b.toString(16).padStart(2, "0")}</span>`;
        const ch = b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : "·";
        ascii += `<span class="a${cls}" data-o="${i}">${escapeHtml(ch)}</span>`;
        if ((i - row) === 7) hex += '<span class="gap"></span>';
      }
      rows.push(
        `<div class="row"><span class="off" title="0x${row.toString(16)}">${String(row).padStart(6, " ")}</span>` +
        `<span class="hexcol">${hex}</span><span class="asc">${ascii}</span></div>`);
    }
    this.el.innerHTML = rows.join("");
    this.cells = Array.from(this.el.querySelectorAll(".b"));
    this.chars = Array.from(this.el.querySelectorAll(".a"));
    this.el.tabIndex = 0;
    if (this.selection) this.#paintSelection();
  }

  // Dim every byte outside `spans`: the bytes the reader never asked the store for.
  dimOutside(spans) {
    const inside = (i) => spans.some(([a, b]) => i >= a && i < b);
    this.cells.forEach((c, i) => c.classList.toggle("unfetched", !inside(i)));
    this.chars.forEach((c, i) => c.classList.toggle("unfetched", !inside(i)));
  }

  clearDim() {
    this.dimOutside([[0, this.bytes.length]]);
  }

  // Outline `span` as the thing currently being explained, and bring it into view.
  highlight(span, { scroll = true } = {}) {
    for (const c of this.el.querySelectorAll(".hl")) c.classList.remove("hl");
    if (!span) return;
    const [a, b] = span;
    for (let i = a; i < Math.min(b, this.cells.length); i++) {
      this.cells[i].classList.add("hl");
      this.chars[i].classList.add("hl");
    }
    if (scroll && this.cells[a]) {
      const row = this.cells[a].parentElement.parentElement;
      const top = row.offsetTop - this.el.offsetTop;
      if (top < this.el.scrollTop || top > this.el.scrollTop + this.el.clientHeight - 40) {
        this.el.scrollTo({ top: Math.max(0, top - 40), behavior: "smooth" });
      }
    }
  }

  select(start, end = start + 1) {
    this.selection = [start, end];
    this.#paintSelection();
    this.onSelect(this.selection);
  }

  #paintSelection() {
    for (const c of this.el.querySelectorAll(".sel")) c.classList.remove("sel");
    if (!this.selection) return;
    const [a, b] = this.selection;
    for (let i = a; i < Math.min(b, this.cells.length); i++) {
      this.cells[i].classList.add("sel");
      this.chars[i].classList.add("sel");
    }
  }

  #click(e) {
    const t = e.target.closest("[data-o]");
    if (!t) return;
    const o = Number(t.dataset.o);
    if (e.shiftKey && this.selection) {
      const a = Math.min(this.selection[0], o);
      const b = Math.max(this.selection[1] - 1, o) + 1;
      this.select(a, b);
    } else {
      this.select(o);
    }
  }

  #key(e) {
    if (!this.selection) return;
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -ROW, ArrowDown: ROW }[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const o = Math.max(0, Math.min(this.bytes.length - 1, this.selection[0] + step));
    this.select(o);
    this.highlight(null);
    const cell = this.cells[o];
    if (cell) cell.scrollIntoView({ block: "nearest" });
  }
}

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
