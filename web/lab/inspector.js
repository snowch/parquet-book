// The byte inspector: what the selected bytes could mean, and what the reader says they mean.
//
// A byte is a value only once you decide how many bytes belong to it and in which order. The
// inspector lists the choices side by side, every one computed by `report::interpret` in Rust,
// under the name of the structure the reader says the byte belongs to.
//
// It also lets you change a byte. The change is made to the file inside the WebAssembly module,
// and every panel is recomputed from the damaged file, so what the reader then does is what
// this reader does with a damaged file.

import { escapeHtml } from "./hexview.js";

// Integers beyond 2^53 arrive as strings (see json.rs), and are grouped the same way.
const fmt = (n) => (typeof n === "number"
  ? n.toLocaleString("en-GB")
  : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","));

export class Inspector {
  constructor(container, { onEdit, onRestore } = {}) {
    this.el = document.createElement("div");
    this.el.className = "inspector";
    container.append(this.el);
    this.onEdit = onEdit || (() => {});
    this.onRestore = onRestore || (() => {});
    this.el.innerHTML = '<p class="hint">Select a byte in the byte view. Shift-click to select a range.</p>';
    this.el.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = this.el.querySelector("input[name=byte]");
      const value = parseInt(input.value, 16);
      if (Number.isNaN(value) || value < 0 || value > 255) {
        input.setCustomValidity("Two hex digits, 00 to ff");
        input.reportValidity();
        return;
      }
      this.onEdit(this.offset, value);
    });
    this.el.addEventListener("click", (e) => {
      if (e.target.closest(".restore")) this.onRestore();
    });
  }

  show({ selection, info, path, bytes, edited }) {
    this.offset = selection[0];
    const [a, b] = selection;
    const where = path && path.length
      ? path.slice(1).map((n) => escapeHtml(n.label)).join(" › ")
      : "";
    const rows = [];
    const row = (k, v, note = "") => rows.push(
      `<tr><th>${k}</th><td>${v}</td><td class="note">${note}</td></tr>`);
    if (b - a > 1) {
      const hex = Array.from(bytes.slice(a, Math.min(b, a + 64)), (x) => x.toString(16).padStart(2, "0")).join(" ");
      row("Range", `[${a}, ${b})`, `${fmt(b - a)} bytes`);
      row("HTTP range", `<code>bytes=${a}-${b - 1}</code>`, "inclusive at both ends");
      row("Hex", `<code>${hex}${b - a > 64 ? " …" : ""}</code>`);
    }
    if (info && info.ok) {
      row("Offset", `${fmt(info.offset)}`, `0x${info.offset.toString(16)}`);
      row("Byte", `<code>${info.hex}</code> · ${info.byte}`, `bits ${info.binary}${info.ascii ? ` · ASCII “${escapeHtml(info.ascii)}”` : ""}`);
      if (info.u32_le !== undefined) {
        const terms = info.u32_le_terms.map((t) => `<code>${t.byte.toString(16).padStart(2, "0")}</code>×${fmt(t.weight)}`).join(" + ");
        row("u32, little-endian", fmt(info.u32_le), terms);
        row("i32, little-endian", fmt(info.i32_le));
      }
      if (info.u64_le !== undefined) row("i64, little-endian", fmt(info.i64_le));
      if (info.f64_le !== undefined) row("f64, little-endian", escapeHtml(String(info.f64_le)));
      if (info.uleb128) {
        row("ULEB128 varint", fmt(info.uleb128.value), `${info.uleb128.length} byte(s); zigzag ${fmt(info.uleb128.zigzag)}`);
      }
      const h = info.thrift_field_header;
      row("As a Thrift field header", `delta ${h.delta}, type ${h.type_nibble}`, h.type ? `a ${h.type} field` : "not a valid type");
    }
    this.el.innerHTML =
      (where ? `<p class="where">${where}</p>` : "") +
      `<table>${rows.join("")}</table>` +
      `<form class="edit"><label>Change byte ${fmt(a)} to <input name="byte" size="2" maxlength="2" ` +
      `value="${info && info.ok ? info.hex : ""}" spellcheck="false" autocomplete="off"></label> ` +
      `<button type="submit">Apply</button>` +
      (edited ? ` <button type="button" class="restore">Restore the original file</button>` : "") +
      `</form>`;
  }
}
