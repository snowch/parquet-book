// A plain text area for editing Python in the page: no framework, no build step.
//
// Tab indents by four spaces, and Enter keeps the line's indentation (one level more after a
// colon), since Python's blocks are its indentation. Tab would otherwise trap the keyboard in the
// editor, so Escape then Tab leaves it. Ctrl+Enter (Cmd+Enter on a Mac) runs.

export const KEYS = "Tab indents · Esc then Tab leaves the editor · Ctrl+Enter runs";

export function codeArea(text, { label, onRun, onInput }) {
  const area = document.createElement("textarea");
  area.className = "code-area";
  area.spellcheck = false;
  area.setAttribute("autocapitalize", "off");
  area.setAttribute("autocomplete", "off");
  area.setAttribute("wrap", "off");
  area.setAttribute("aria-label", label);
  area.value = text;
  let leaving = false;
  const edit = (insert, start = area.selectionStart, end = area.selectionEnd) => {
    area.setRangeText(insert, start, end, "end");
    onInput?.(area.value);
  };
  area.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      onRun?.();
    } else if (e.key === "Escape") {
      leaving = true;
    } else if (e.key === "Tab" && !leaving && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      edit("    ");
    } else if (e.key === "Enter" && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      const before = area.value.slice(0, area.selectionStart);
      const line = before.slice(before.lastIndexOf("\n") + 1);
      const indent = line.match(/^ */)[0] + (/:\s*$/.test(line) ? "    " : "");
      edit(`\n${indent}`);
    }
    if (e.key !== "Escape") leaving = false;
  });
  area.addEventListener("input", () => onInput?.(area.value));
  return area;
}
