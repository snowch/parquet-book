# Reading a page directly from the contents

## Brief

The reader opened the first module's notes from the contents and could not identify what
"the two layouts above" or "the counting files" referred to. The screenshot is direct evidence
of disorientation. Other likely failures from detached chapter sections are hypotheses until
checked in their published destinations.

Outcome: a reader arriving at any published destination can identify its subject, locate the
example behind a claim, and choose the relevant preparation or the next useful action.
This audit preserves the short lessons, worked evidence, optional code and fresh applications.
It does not require every advanced page to reteach the whole course.

Inspect the canonical sources and the rendered partitions, including notes, builds, practice,
comparisons, module indexes, part pages and appendices. Search for positional and unnamed
references, then read their context: a genuine same-page "above" is not automatically wrong.
Check the linked lesson actually contains the named evidence. Check newly qualified claims
against the examples and model rather than changing labels alone.

The first module provides a worked audit case: the real CSV/Parquet byte-read comparison and
the schematic row/column layout are separate examples. The notes must identify both and scope
their conclusions. The remaining modules are independent applications of the same entry test.

## UX direction

Keep the established book palette and typography: white #ffffff, ink #243447, muted blue
#526577, link blue #285e83, pale blue #f1f5f8 and dark-mode equivalents from the stylesheet.
Serif reading prose and headings retain their roles; interface guidance remains sans serif.
Use the existing left-aligned reading measure and a compact introduction, not another dashboard.

Page title names the subject. The introduction states the page's purpose and links to meaningful
preparation. Supporting pages name the evidence they discuss. Link text names a topic or example
rather than an internal chapter code. Preserve ordinary keyboard-operable anchors and reflow.

Compared with adding a generic "read earlier lessons" banner, this plan gives the missing subject
and destination at the point where the reader needs them. Avoid repeating all prerequisites or
adding navigation that has no teaching job.

## Review and evidence

Separate drafting passes covered modules one to eight, modules nine to sixteen, and navigation
plus front/reference pages. Independent learner reviews then examined the early and late
destinations without the authors' explanations. A separate technical reviewer checked the
claims, examples and implementation scope. All used the configured parent model with no override.

Final reports: [early destinations](page-entry-reviews/early.md),
[late destinations](page-entry-reviews/late.md), and
[technical and UX checks](page-entry-reviews/technical.md). All accepted findings are closed;
the reports retain the initial evidence, rejected concerns and final verification details.

The source audit covers all 116 published destinations: 56 core lessons, thirteen build labs,
sixteen notes, three practice pages, two comparisons, sixteen module indexes and ten
front/reference pages. Each reviewer read the actual partition boundaries, not only matches for
words such as "above". The early and late browser sweeps each visited 53 destinations in phone
and desktop widths in both themes. Reports distinguish those automated visits from inspected
screenshots and semantic reading of link destinations.

### Changes

- All supporting titles identify a subject. Notes state which examples they qualify and link
  to those examples. Core/build preparation links name the needed mechanisms, including earlier
  modules where appropriate. Three independent entry lessons explain their simple assumptions
  instead of inventing a prerequisite.
- Detached references in every module now identify the fixture, query, walkthrough or schematic.
  Local reminders supply the subject; links provide the route to its evidence. Notes do not
  pretend that an absent computation happened "here".
- Chapter shorthand such as `ch05` renders as the chapter title, preserving explicit descriptive
  labels. Existing lesson URLs and heading destinations remain available.
- Qualify conclusions from the controlled examples: CSV/Parquet byte counts versus the layout
  schematic; row-group bounds rather than sortedness as a necessary condition; this scheduler's
  phase barriers; visibility in each encryption mode; uncached footer costs; table-format and
  default-value scope; retryable commit conflicts; and the simplified single-log fixture.
- Preserve the short reading sequence, worked results, code disclosures and fresh applications.
  Preparation replaces generic header boilerplate. It does not add another navigation panel.

### Findings resolved during integration

Explicit labels initially replaced implicit heading IDs, breaking existing glossary references.
The strict build rejected these; labels now preserve the original heading IDs. A newly labelled
walkthrough paragraph did not render its anchor, so it now has a meaningful heading.

Semantic browser review also found three valid-looking library links that reached the wrong
lab: MyST resolved the repeated "Ask a library" heading to the footer chapter. Direct public
lab/fragment links now reach the nested-data, page-checksum and compression comparisons. New
regression checks protect these destinations. The string-prefix lesson's preparation now reaches
the actual byte-array length explanation rather than an unrelated dictionary introduction.

Rejected findings are retained in the independent reports. A genuine reference to a figure on
the same page is valid; notes need not duplicate whole lessons; an optional comparison with a
properly scoped caption is useful. Link checks alone cannot establish that the destination
teaches what its label promises.

### Validation record

The final focused checks passed: 42 renderer/lesson tests, all built links, and browser checks
for all 34 optional module destinations at phone/light and desktop/dark widths. Keyboard
contents-to-notes-to-example navigation passes. The reviewer sweeps additionally cover both
themes at both widths, target semantics, retained legacy anchors and no page overflow.

Earlier attempts are not silently counted as passes: the first integration build rejected
replaced heading anchors; the first complete check stopped at formatting; a focused browser
test initially included appendices that do not use lesson introductions. These were corrected.
A subsequent full run was deliberately interrupted when independent review found wrong-lab
links, then restarted against the corrected source.

Final `make check` passed: Rust formatting, lint and tests; regenerated fixture/evidence checks;
strict MyST parsing; all 119 built HTML pages' links; 772 Python tests with 43 intentional exercise
skips; and the complete browser suite, including the new optional-page entry checks. The only
Python warning is the pre-existing pytest plugin deprecation. Documentation checks were rerun
after adding the final audit records: 197 passed.

Decision: keep the short lessons, specific preparation and compact example context. The
reported entry failure is resolved and the same criterion is now in the authoring guidance.
Agent review and browser tests are not evidence from a new human learner. No novice study or
complete assistive-technology audit was performed.
