# Book visual design

The course is a technical field guide with a visible reading sequence. Its contents should
show where the reader is, how lessons fit into chapters, and which material is optional.

Applied the [Frontend Design skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md).
The design plan was reviewed before implementation: use the actual chapter and lesson sequence
as the organising device, rather than surrounding every item with a card.

## Direction

- White paper, a cool blue-grey rail, dark blue ink and one blue navigation accent. Keep the
  existing semantic colours in experiments and the light/dark theme choice.
- Charter/Georgia for major titles and prose, system sans for controls and section headings,
  monospace for bytes and source. No font download is required.
- Left-aligned, bounded reading columns. Contents opens the current part and chapter. A solid
  accent marks the current page; chapter numbers and lesson positions show the real sequence.
- Chapter indexes use numbered lesson rows with outcomes. Optional resources have a quieter
  grouped area. Lesson introductions use a shared alignment with the prose.
- Mobile contents has its own close control, internal scrolling and a narrower measure on
  tablets. On small phones the header prioritises the book title over the GitHub star shortcut.

## Interaction and preservation

The course map is native HTML. Without JavaScript, mobile readers reach it after the lesson;
part and chapter disclosures still work. Search is progressive enhancement over titles already
in the document, with empty-result feedback and restoration of the previous disclosure state.
Filtered lessons keep their original numbers.

The mobile overlay makes the covered page inert, contains keyboard focus, and closes with
Escape, the close control, the Chapters button or browser Back. Closing returns keyboard focus
to the Chapters button. Desktop rails retain their existing controls and saved preferences.

The reading route, source explanations, saved results, fresh checks, optional code, interactive
experiments and old deep-link migration retain their behaviour. Browser checks cover search,
keyboard navigation and the existing course and laboratory workflows. Visual review uses phone,
tablet and desktop widths in both themes, including expanded code and a page with a byte map.
