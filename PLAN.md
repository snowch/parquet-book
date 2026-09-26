# PLAN.md: the argument

`tools/outline.py` holds the book's shape as data. This file holds the reasoning: what the book is
for, why it is in this order, which decisions are settled, and what the reader implementation adds
in each phase. When the two disagree, the outline is right about *what* and this file is right
about *why*.

## 1. The premise

**The book should not explain how Parquet works. The reader should build a working Parquet reader
while reading it.**

A prose explanation of a file format is easy to nod along to and hard to use. The questions an
engineer brings to Parquet are concrete: *why did my engine make forty requests to open one
file?*, *which bytes does this predicate let it skip?*, *why is this file slow to open?* They are
answered by looking at bytes and requests, so the book shows bytes and requests, and makes the
reader write the code that produces them.

The method in every chapter is the same:

```
question -> experiment -> observe bytes -> implement a piece -> run its test
         -> inspect the result -> explain why it works -> extend
```

The implementation is the teaching instrument. A chapter should leave the reader with something
concrete that works.

## 2. The reader, built in phases

The reader (`crates/parquet-lab`) grows with the book. Each phase is the set of chapters that
needs it, and each is finished, tested and quoted before the chapters that use it are written.

| Phase | Adds | Chapters | State |
|---|---|---|---|
| 1 | magic, trailer, footer discovery over an object store, Thrift compact decoding, `FileMetaData`, schema, row groups, column chunks, page headers | ch01, ch02, ch03 | done |
| 2 | PLAIN, dictionary, RLE/bit-packing hybrid, delta encodings, BYTE_STREAM_SPLIT; levels | ch04, ch05 | done |
| 3 | page walking with values, data page v1 and v2, decompression | ch06, ch07 | done; ZSTD and Brotli sizes only |
| 4 | statistics decoding with sort orders, pruning, page indexes, Bloom filters | ch08, ch09 | done |
| 5 | projection, request coalescing, concurrency, prefetching, caching; a query engine | ch10, ch11, ch12 | done; caching not modelled |
| 6 | encrypted modules, multi-file datasets, manifests | ch13, ch14 | done; decryption not implemented; one log file, no checkpoints |

**Deliberately unsupported**, and reported as unsupported rather than guessed at: decryption,
legacy two-level list layouts, INT96 conversion beyond display, the deprecated LZ4 framing,
column chunks stored in other files (`file_path`), and writing Parquet. The reader never writes a
fixture; see §4.

Where a production implementation does something the teaching reader does not, the book says so
and names the implementation: arrow-rs, parquet-java, and Arrow C++ (through pyarrow) are the
comparisons.

## 3. Why this order

Part I is about finding things; Part II about decoding them; Part III about not decoding them. That
is the order a reader's work is done in, and it is the order the implementation can be built in:
each phase depends only on earlier ones.

**ch01 comes before any Parquet.** Its experiment stores a toy table two ways, because the reason
for Parquet's shape is the cost of reading the wrong layout, and that is clearest before the
format's detail arrives. It uses the same traced object store as everything after it.

**The footer is the first real experiment.** It is the one part of the format a reader cannot
avoid, it is small enough to decode by hand, and its discovery is a chain of dependent requests
that shows at once why object storage shapes readers. Every later chapter's experiment starts
from an opened footer.

**Object storage runs through the whole book, not one chapter.** The request trace introduced in
ch02 is the unit of cost for ch08 to ch12. ch10 is where it becomes the subject.

**The query engine comes last in Part IV** because it is a consumer of everything before it:
projection, pruning, decoding. **Encryption is late** so its complexity cannot distort the earlier
architecture: the reader recognises `PARE` from ch02 and does nothing else with it until ch13.

The chapter progression follows the source tutorial the book was planned from, *The Apache Parquet
File Format: A Detailed Tutorial*, with one change: that tutorial's hands-on inspection chapter
(PyArrow, DuckDB and the CLI) is replaced by a query engine, because inspection is what every
chapter here already does, and a query engine is what shows the pieces working together.

## 4. Settled decisions

**Rust for the core, compiled to WebAssembly for the browser.** The browser must run the
implementation, not a second teaching implementation in JavaScript: two implementations would
disagree, and a book whose pictures disagree with its tests teaches nothing. Rust compiles to
small, import-free WASM, is fast enough to recompute every panel on every slider movement, and
reads clearly when quoted.

**No dependencies in the reader.** Not for Thrift, not for JSON, not for WASM bindings. Each is
small enough to write in the open, which is the point of the book, and `cargo build --offline`
works on a fresh clone. The WASM interface is a hand-written C ABI of numbers and byte buffers,
because a generated binding would be the one part of the system the reader could not read.

**MyST parses, the repository renders.** As in `sizing-and-tco`: `myst build --strict` resolves
every reference and fails on a broken one, and `tools/render.py` renders the parse, raising on any
node it does not know. The page is not somebody else's application, so the lab's script owns its
mount points, and nothing hydrates over it. The site is static, relative-linked, and cached by a
service worker for offline reading.

**A simulated object store, not S3.** `HEAD`, `GET`, bounded ranges and suffix ranges with S3's
semantics, over objects in memory, with a deterministic cost model. The book must work offline and
give the same numbers every time. A real S3-compatible backend could implement the same trait; it
would be a demonstration, never the source of a figure.

**Fixtures are written by pyarrow, pinned.** A reader tested against its own output proves only
consistency. pyarrow also writes a manifest describing each fixture, which is the tests' oracle.
Writes are deterministic for a fixed pyarrow version, and `fixtures/generate.py --check` enforces
that the committed bytes are what the generator writes.

**Teaching decompressors for three codecs; none for ZSTD or Brotli.** The reader decodes SNAPPY,
LZ4_RAW and GZIP (DEFLATE) itself, each short enough to quote whole and each recording its tokens
for the laboratory. ZSTD and Brotli decoders would each be several times the size of all three
together and would teach nothing DEFLATE does not; adding a crate for them would break the
no-dependency rule. Their fixtures are still written and measured, from footers, and a page that
needs them is refused with a message naming the codec. Decompressed output is checked against
`codec-none.parquet`, pyarrow's own uncompressed pages, not against the reader.

**Encryption is read, not decrypted, and its fixtures are written once.** The reader recognises
both footer modes, walks encrypted modules by their lengths, and refuses encrypted columns by
name; it does not implement AES, GCM or a key service. pyarrow draws fresh data keys and nonces
on every write, so the encrypted fixtures cannot be reproduced byte for byte: the generator keeps
the committed bytes while they decrypt, with test keys published in the generator, to exactly the
intended rows, and the tests hold the keyless reader to pyarrow's keyed description of them.

**Problems are Rust tests, run at a desk.** `sizing-and-tco` runs its Python problems in the page
under Pyodide. A Rust problem cannot be compiled in a browser page at reasonable cost, so here the
problems run with `cargo test -- --ignored`, and the page shows the command. The experiments carry
the in-browser interactivity instead.

## 5. The chapter shape

Every chapter has seven sections, in `tools/outline.CHAPTER_SHAPE`, enforced by
`tests/test_book.py`:

1. **The question**: one question, and why the previous chapter leaves it open.
2. **The experiment**: a `lab` panel on a real fixture, a numbered list of things to try, and
   generated tables that record what the experiment shows.
3. **Building it**: the code the experiment ran, quoted from the crate, in the order it ran, and
   the command that tests it.
4. **What this cannot tell you**: the limits of the experiment, of the simulation, and of the code.
5. **Key takeaways**: claims already made and shown above, each in bold with its reason.
6. **Problems**: stubs with tests, and one problem about the reader's own files.
7. **Where to go next**: primary sources, and the next chapter.

The experiment comes before the code on purpose. A reader who has watched the requests happen
reads the function that made them as an explanation, not as an abstraction.

## 6. Conventions

- British English, active voice, short sentences, no em dashes. STYLE.md.
- Every number from the reader. Every code block from the working tree.
- Spans are half-open `[start, end)`. HTTP ranges are inclusive; the conversion lives in one
  function, `Span::http_range`.
- Identity is the slug. A chapter's number is derived from its position in the outline.
