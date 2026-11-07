# Learning progression pilots

Historical record of the initial pilots. The subsequent whole-course rollout removes combined
chapter pages; see `notes/course-learning-design.md` for the current structure and decisions.

## Decision and scope

Keep the sixteen chapters as modules, with shorter independently navigable lessons where the
chapter contains several useful outcomes. Pilot anatomy and nested data before changing the
remaining chapters. Preserve complete reference pages, old anchors, generated evidence,
Python/Rust walkthroughs and coherent implementation labs. All views use one canonical source.

This applies Assembly Lab's learning-design workflow, including separate learner and technical
reviews. Its skill is at
https://github.com/snowch/assembly-lab/blob/c52703d58e14f2783e7cb785ff1e757ba36ccd42/.agents/skills/learning-design/SKILL.md.
The rubric distinguishes naming a prerequisite, demonstrating it and practising it before
composition. A short page alone does not establish learning.

## Brief before interface

Each lesson's observable outcome and prerequisites are recorded in `tools/lessons.py`. The
sequence is a worked example, supported interpretation and a fresh application with reasoning.
Native disclosures provide the fresh task's explanation with JavaScript off. Coding is optional.

Anatomy prepares byte notation before length arithmetic, keeps the complete footer calculation
together, introduces metadata as a map, preserves the complete dependent-request trace, then
compares tail strategies. Existing inline widgets are supported practice. Fresh footer/range
cases use a different fixture; prediction prompts distinguish signature recognition from file
validation, an excluded boundary from an inclusive HTTP endpoint, and known size from known
footer length. Request strategies are traces from the real reader, not browser estimates.

Nested data begins with a complete nullable scalar case from the real fixture in both languages.
Then readers distinguish a null list, empty list and null element before tracing lists inside
lists. Only after interpreting decoded levels do they examine packing and framing. Fresh slots
use the fixture's schema with new values/order, explicitly labelled as schematic; the reader
reconstructs the answer. The packing check contrasts a new RLE run with the demonstrated
bit-packed run. It does not pretend schematic bytes came from a production writer.

Predicted misconceptions: nulls remove records; every missing stored value means the same thing;
any non-zero repetition level starts a record; physical packing changes logical shape. The
fresh cases ask for reconstruction and an explanation that distinguishes those rules.

These boundaries are hypotheses, not a fixed word-count target. The reader-request capstone and
writer comparison in later chapters should remain complete investigations rather than being
split into one page per request or setting.

## Review decisions

- Accepted: preserve the full chapter URLs while making the short route the default Next path.
- Accepted: introduce scalar meaning before binary nested streams.
- Accepted: define the deeper schema path locally before composing its definition levels.
- Accepted: explain bits, run-length encoding and the single-byte header examples before the
  physical-stream task; defer the complete variable-length integer decoder to the build lab.
- Accepted: replace references to steps “above” where the evidence is on an earlier lesson.
- Rejected: hiding code alone solves the progression problem; the conceptual outcomes still
  require distinct completion boundaries.
- Rejected: a completion tick or revealing an answer demonstrates understanding. Resume state
  records a reading position, not a grade.

## Validation and uncertainty

Independent learner and technical reviews found no remaining blockers after the corrections
above. The learner pass also requested a complete RLE example before the fresh RLE task;
the page now shows a separate schematic example decoded by the reader. The technical pass
qualified the all-present RLE explanation to optional flat columns: required paths omit the
stream, and nested empty-list placeholders can still have levels below the maximum.

Browser review covered all nine core lessons and both module pages at desktop/light and
phone/dark, plus representative pages in the opposite theme/width combinations. Native
keyboard answer reveals, code closed on arrival, the core Next route and no document overflow
passed. A no-JavaScript pass checked the essential route. A technical check confirmed lesson
resume, reference links, no duplicate article IDs and numeric cases against the reader.
Final rendered spot-checks confirmed the deeper-path and binary/RLE bridges after rebuilding.
The sentence and teaching-sequence editing passes were completed separately.

`make check` passed: Rust format/lint/tests, reproducible fixtures and figures, current saved
walkthrough answers, generated-number checks, strict MyST parsing, all built links, Python
tests and the full browser suite. The Python run passed all 744 tests with 43 intentionally
skipped exercise tests. New browser checks cover every core route without JavaScript and the
new scalar walkthrough's code controls in both languages. One initial run had an unchanged
pyarrow example subprocess abort; its targeted rerun and the complete retry passed without
changing that example. The cause of the initial abort was not established.

Review agents used separate sessions of the available inherited model, not evidence from a
model comparison. Agent learner role-play is not a novice study. No assistive-technology study
or complete accessibility audit is claimed.

Next evidence: a reader new to Parquet, with the stated prerequisites, uses the pilot without
coaching and attempts a fresh case. Record first attempts, help and post-help responses
separately. Test the lesson boundaries before extending the structure to other modules.
