# STYLE.md: how to make the writing clear

Every page is edited against this list. CLAUDE.md sets the voice; this is the checklist that gets a
page there. The rules are adapted from `snowch/sizing-and-tco`'s STYLE.md, which earned them by
reviewing a finished book, and trimmed to the habits a byte-level book is most prone to.

The goal: an experienced engineer understands each paragraph on the first reading.

## 1. Short sentences, one idea each

About twenty words. Split a sentence that carries two ideas. Three shapes hide a second sentence
inside a first: a clause after *which*, *rather than* or a second *and*; a colon followed by a list
of clauses; a parenthesis holding a thought of its own.

## 2. One idea per paragraph

A paragraph answers one question. If it moves from what the trailer is to why the footer is at the
end, it is two paragraphs.

## 3. The point first

> A reader starts at the end.

before the reasons, not after them. Do not set a small puzzle and make the reader wait for the
answer (*the second byte is the one that matters*). Say which byte and why.

## 4. Show the bytes

An abstract statement about an encoding is weaker than the bytes it produces. Where a sentence
describes bytes, the page should have an experiment or a generated table that shows them, and the
sentence should point at it.

## 5. Ordinary words

*use*, not *utilise*; *start*, not *commence*; *show*, not *demonstrate*; *to*, not *in order to*.
Keep technical terms that do work (*little-endian*, *varint*, *row group*), and define each in plain
words where it first appears.

## 6. Define a term before it carries an argument

A term used in an argument must be defined earlier on the same page, in plain words. The glossary
(Appendix C) is a reference, not a substitute.

## 7. Headings name what a section contains

A few words, not a sentence, not a question unless the section answers it: *The trailer*, not
*What are the last eight bytes for?*.

## 8. Lists for three or more parallel things

And every item in a list takes the same shape: all sentences or all phrases.

## 9. Cause and effect, said

*The footer is written last.* Then: *so a writer can stream data in one pass*, and *so a reader
must start at the end*. Do not leave the reader to infer why a fact matters.

## 10. Precision is not negotiable

Clarity never removes a caveat, turns a simulated number into a measured one, or rounds a
specification's *must* into *usually*. Say what the simulation is. Say what the code does not
handle. Do not hide uncertainty.

## 11. You, and the active voice

*You select the byte; the reader decodes it.* Use the passive only when the actor is obvious and
uninteresting.

## 12. No em dashes

Use a full stop, a colon, a comma or parentheses. `tests/test_book.py` checks every page and every
document.

## 13. No filler, no performance

Banned outright, and checked: *In this chapter*, *simply*, *just*, *obviously*, *basically*. Also
cut on sight: *it is worth noting that*, *actually*, *really*, *genuinely*, *quite*, *very*, fake
enthusiasm, and rhetorical questions the next sentence answers.

## 14. A short sentence lands a point; it does not label one

*Nothing is ever rewritten.* lands the point before it. *Three requests.* as the opening of a
paragraph is a heading in disguise: write the sentence that says what the three requests are.

## 15. A demonstrative needs its noun

If *this*, *that* or *it* points more than one sentence back, name the thing.

## 16. An evaluation gives its grounds

*The suffix range is better* is incomplete. *The suffix range saves the `HEAD` request, because
the response reports the size* is a claim.

## 17. Numbers are generated

Never type a measured number, even to make a sentence clearer. Point at the table or the panel
that shows it. See AUTHORING_GUIDE.md.

## Before you finish: two passes

**First pass, the sentences.** Rules 1, 5, 11, 12, 13, 14, 15. A scan: minutes per page.

**Second pass, the idea.** Rules 2, 3, 4, 6, 9, 10, 16. Read the page as a reader arriving from the
previous chapter. At each paragraph ask: what does this paragraph claim, and could I point at the
bytes or the request that shows it? A page can pass the first pass and fail the second: clean
sentences, nothing to hold on to.
