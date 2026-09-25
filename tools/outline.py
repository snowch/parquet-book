"""The book's shape, in one machine-readable place.

PLAN.md holds the argument: what each chapter is for, and why the book is in this order. This
module holds only what a script or a test needs: the order, the titles, the question each
chapter answers, what each chapter adds to the reader, and which fixtures and experiments it
uses.

A chapter's number is derived from its position here and never typed anywhere else. Its identity
is its slug: the file name, the anchor a cross-reference uses, and the name of its module in the
exercises crate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The headings every chapter carries, in order. ``tests/test_book.py`` holds every chapter to
#: them. A section a chapter needs and this list lacks is a subsection of one of these.
#:
#: The order is the book's method. A chapter opens on a question, answers it by experiment on
#: real bytes, then builds the piece of the reader that the experiment needed. The reader sees
#: the behaviour before the code that produces it.
CHAPTER_SHAPE = (
    "The question",
    "The experiment",
    "Building it",
    "What this cannot tell you",
    "Key takeaways",
    "Problems",
    "Where to go next",
)

#: What a page carries until it is written. Everything that reports progress keys off it.
UNWRITTEN = "[To write"


@dataclass(frozen=True)
class Part:
    slug: str
    title: str
    question: str

    @property
    def path(self) -> str:
        return f"parts/{self.slug}.md"


@dataclass(frozen=True)
class Chapter:
    number: int
    slug: str
    title: str
    part: str
    #: The one question the chapter answers. Its opening paragraph expands it.
    question: str
    #: What the reader has, working, at the end of the chapter: the piece of the reader it adds.
    builds: str
    #: The experiments (``lab`` blocks) the chapter embeds.
    experiments: tuple[str, ...] = ()
    #: The fixtures those experiments and the chapter's figures read.
    fixtures: tuple[str, ...] = ()
    needs: tuple[str, ...] = field(default=())

    @property
    def anchor(self) -> str:
        return self.slug.replace("_", "-")

    @property
    def label(self) -> str:
        return f"ch{self.number:02d}"

    @property
    def path(self) -> str:
        return f"chapters/{self.slug}.md"


@dataclass(frozen=True)
class Appendix:
    letter: str
    slug: str
    title: str

    @property
    def anchor(self) -> str:
        return self.slug.replace("_", "-")

    @property
    def label(self) -> str:
        return f"Appendix {self.letter}"

    @property
    def path(self) -> str:
        return f"appendices/{self.slug}.md"


PARTS = (
    Part("the_file", "Part I: The file", "What is a Parquet file, byte by byte?"),
    Part("the_values", "Part II: The values", "How do values become bytes, and back?"),
    Part("reading_less", "Part III: Reading less", "How does a reader avoid reading most of a file?"),
    Part(
        "writing_and_querying",
        "Part IV: Writing and querying",
        "What makes a file good to read, and what reads it?",
    ),
    Part("beyond_one_file", "Part V: Beyond one file", "What changes when files are protected, or many?"),
)

_P = {p.slug: p.title for p in PARTS}

_CHAPTERS = (
    (
        "why_parquet_exists",
        "Why Parquet exists",
        "the_file",
        "Why store a table one column at a time, when every program thinks in rows?",
        "A tiny table stored both ways, and a count of the bytes each query must touch.",
        ("layouts",),
        (),
    ),
    (
        "anatomy_of_a_parquet_file",
        "Anatomy of a Parquet file",
        "the_file",
        "Given only a file's bytes, how does a reader find anything in it?",
        "Footer discovery over a simulated object store: size, trailer, footer range, FileMetaData.",
        ("footer", "anatomy"),
        ("tiny.parquet", "multiple-row-groups.parquet"),
    ),
    (
        "the_type_system",
        "The type system",
        "the_file",
        "How do a handful of storage types carry strings, dates, decimals and timestamps?",
        "The schema tree rebuilt from the footer, with maximum levels, and logical types applied to values.",
        ("schema",),
        ("types.parquet",),
    ),
    (
        "nested_data",
        "Nested data",
        "the_file",
        "How can nested, nullable records live in flat columns without losing their shape?",
        "The RLE/bit-packing hybrid for levels, a column read into triples, and records rebuilt from them.",
        ("levels",),
        ("nested.parquet",),
    ),
    (
        "encodings",
        "Encodings",
        "the_values",
        "How do values become compact bytes before any compressor sees them?",
        "Decoders for dictionary pages and indices, the delta encodings and BYTE_STREAM_SPLIT, each with a trace.",
        ("encodings",),
        ("encodings.parquet", "dictionary.parquet"),
    ),
    (
        "pages",
        "Pages",
        "the_values",
        "What is inside a column chunk, and how does a reader walk it?",
        "A page walker for dictionary pages and data pages v1 and v2, with row boundaries and checksums.",
        ("pages",),
        ("pages.parquet", "pages-v2.parquet"),
    ),
    (
        "compression",
        "Compression",
        "the_values",
        "What does compression add on top of encoding, and what does it cost?",
        "Decompression in the read path, and measured ratios for comparable datasets.",
        (),
        (),
    ),
    (
        "metadata_and_statistics",
        "Metadata and statistics",
        "reading_less",
        "What does the footer know that lets a reader avoid reading the data?",
        "Column statistics decoded and compared, with their sort-order pitfalls.",
        (),
        (),
    ),
    (
        "skipping_data",
        "Skipping data",
        "reading_less",
        "Given a predicate, which bytes can a reader prove it does not need?",
        "Row-group pruning, page indexes and Bloom filters, each deciding which ranges to skip.",
        (),
        (),
    ),
    (
        "how_readers_read",
        "How readers read",
        "reading_less",
        "Why does a reader issue exactly the requests it does?",
        "The complete read path over the object store: projection, pruning, coalescing, prefetching, caching.",
        (),
        (),
    ),
    (
        "writing_parquet_well",
        "Writing Parquet well",
        "writing_and_querying",
        "Which writer settings decide how cheap a file is to read?",
        "Generated files with different row-group sizes, sort orders and codecs, compared by what reading them costs.",
        (),
        (),
    ),
    (
        "a_tiny_query_engine",
        "A tiny query engine",
        "writing_and_querying",
        "What does it take to answer SQL from Parquet bytes?",
        "A minimal query engine: scan, filter, project, aggregate and group, with every stage shown.",
        (),
        (),
    ),
    (
        "modular_encryption",
        "Modular encryption",
        "beyond_one_file",
        "What can a reader still see in an encrypted file, and what changes for it?",
        "A reader that recognises encrypted modules and reports what stays visible.",
        (),
        (),
    ),
    (
        "lakehouse_and_beyond",
        "Lakehouse and beyond",
        "beyond_one_file",
        "How does one Parquet file become one part of a larger analytical system?",
        "Many files, partitions, manifests and file pruning over the same object store.",
        (),
        (),
    ),
)

CHAPTERS = tuple(
    Chapter(
        number=i + 1,
        slug=slug,
        title=title,
        part=_P[part],
        question=question,
        builds=builds,
        experiments=experiments,
        fixtures=fixtures,
    )
    for i, (slug, title, part, question, builds, experiments, fixtures) in enumerate(_CHAPTERS)
)

APPENDICES = (
    Appendix("A", "running_the_lab", "Running the lab"),
    Appendix("B", "the_fixtures", "The fixtures"),
    Appendix("C", "glossary", "Glossary"),
)

BY_SLUG = {c.slug: c for c in CHAPTERS}
BY_ANCHOR = {x.anchor: x for x in (*CHAPTERS, *APPENDICES)}

#: The experiments ``web/lab/lab.js`` knows how to mount. A ``lab`` block naming anything else
#: fails the build, rather than rendering an empty box.
EXPERIMENTS = ("layouts", "footer", "anatomy", "schema", "levels", "encodings", "pages")
