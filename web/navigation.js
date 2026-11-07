// The complete course map is native HTML. Search only filters its titles; it never fetches
// content, changes the reading order, or treats an opened lesson as completed learning.
const nav = document.getElementById("nav");
const menu = document.getElementById("menu");
const search = document.getElementById("contents-search");
const status = nav.querySelector(".nav-search-status");
const disclosures = [...nav.querySelectorAll("details")];
let savedOpen = null;

nav.querySelector(".nav-search").hidden = false;
search.addEventListener("input", () => {
  const words = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matches = (text) => words.every((word) => text.toLocaleLowerCase().includes(word));
  if (words.length && !savedOpen) savedOpen = disclosures.map((item) => item.open);
  let count = 0;
  for (const part of nav.querySelectorAll(".nav-part")) {
    const partMatches = matches(part.querySelector("summary").textContent);
    for (const module of part.querySelectorAll(".nav-module")) {
      const moduleMatches = partMatches || matches(module.querySelector("summary").textContent);
      let found = false;
      for (const item of module.querySelectorAll(".module-lessons li, .nav-optional li")) {
        const show = moduleMatches || matches(item.textContent);
        item.hidden = !show;
        found ||= show;
        if (show) count++;
      }
      module.hidden = !found;
      module.querySelector(".nav-optional").hidden = ![...module.querySelectorAll(".nav-optional li")].some((item) => !item.hidden);
      if (words.length) module.querySelector("details").open = found;
    }
    const appendix = part.classList.contains("nav-appendices");
    if (appendix) {
      for (const item of part.querySelectorAll("li")) item.hidden = !(partMatches || matches(item.textContent));
    }
    const found = [...part.querySelectorAll(appendix ? "li" : ".nav-module")].some((item) => !item.hidden);
    part.hidden = !found;
    if (words.length) part.querySelector("details").open = found;
  }
  for (const item of nav.querySelectorAll(".nav-front")) item.hidden = !matches(item.textContent);
  if (!words.length && savedOpen) {
    disclosures.forEach((item, index) => { item.open = savedOpen[index]; });
    savedOpen = null;
  }
  const any = [...nav.querySelectorAll("#contents-list > li")].some((item) => !item.hidden);
  status.textContent = !words.length ? "" : !any ? "No matches. Try a topic such as footer or encoding."
    : count ? `${count} matching ${count === 1 ? "lesson or resource" : "lessons and resources"}` : "Matching pages below";
});

const close = nav.querySelector(".nav-close");
close.hidden = false;
close.addEventListener("click", () => menu.click());
const mobile = matchMedia("(max-width: 57.99rem)");
let wasOpen = false;
const reflect = () => {
  const open = mobile.matches && document.body.classList.contains("nav-open");
  document.getElementById("main").inert = open;
  document.getElementById("toc").inert = open;
  for (const item of document.querySelectorAll(".top > :not(#menu)")) item.inert = open;
  if (open && !wasOpen) close.focus({ preventScroll: true });
  if (!open && wasOpen) menu.focus({ preventScroll: true });
  wasOpen = open;
};
new MutationObserver(reflect).observe(document.body, { attributes: true, attributeFilter: ["class"] });
mobile.addEventListener("change", reflect);
document.addEventListener("keydown", (event) => {
  if (!wasOpen) return;
  if (event.key === "Escape") {
    event.preventDefault();
    menu.click();
  }
  if (event.key === "Tab") {
    const items = [menu, ...nav.querySelectorAll("button, input, summary, a[href]")]
      .filter((item) => item.checkVisibility());
    const first = items[0], last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  }
});
reflect();
