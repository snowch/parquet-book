"""Reading a column chunk into levels and values (ch04).

A column chunk's pages hold, for every value slot, a repetition level, a definition level, and,
when the slot is not null, a value. This module reads them out as triples::

    (r, d, value)    r: where in the nesting a new element starts
                     d: how deep along the path the value is defined
                     value: present only when d is the column's maximum

A data page (version 1) body is laid out in three parts, and the levels are only there when the
column can have them::

    [u32 length][repetition levels]   if max repetition level > 0
    [u32 length][definition levels]   if max definition level > 0
    [values, PLAIN]                   one per slot whose d is the maximum

The values may be encoded in any way :mod:`parquet_lab.decode` knows (ch05). A dictionary page,
when there is one, comes first, and the data pages then hold indices into it.

A data page version 2 (ch06) keeps the same three parts, but the level streams' lengths move into
the page header, so the levels have no length prefix, and they are never compressed.

A compressed page (ch07) is decompressed before any of this. Under version 1 the whole body is
one compressed block; under version 2 only the values are, and only when the header says so.
Spans into a decompressed copy would point at bytes that are not in the file, so every span
found inside one is reported as the compressed bytes that hold it: the reader can say which
compressed block a value came from, not which of its bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import compress, decode, plain, rle
from .bytes import ByteReader, Span
from .decode import Dictionary, Step
from .metadata import ColumnChunk
from .pages import Page, read_page, walk_pages
from .plain import PlainValue
from .rle import Run, bit_width
from .schema import Leaf


class ColumnError(ValueError):
    pass


@dataclass
class Triple:
    """One value slot of a column."""

    rep: int
    definition: int
    value: PlainValue | None
    value_span: Span | None
    extra_spans: list[Span]
    """Other bytes the value needed: its dictionary index run, its length, its prefix length."""
    page: int
    """Which page it came from."""


@dataclass
class DataPage:
    """A data page's body, split into its parts."""

    page: Page
    rep_levels: tuple[Span, list[Run]] | None
    """The four-byte length and the repetition-level runs after it."""
    def_levels: tuple[Span, list[Run]] | None
    values: Span
    encoding: str
    steps: list[Step]
    """How the values were decoded, step by step."""


@dataclass
class DictionaryPage:
    """A column chunk's dictionary page, decoded."""

    page: Page
    entries: Dictionary


@dataclass
class ColumnData:
    dictionary: DictionaryPage | None = None
    pages: list[DataPage] = field(default_factory=list)
    triples: list[Triple] = field(default_factory=list)


def level_stream(r: ByteReader, max_level: int, count: int, known_len: int | None):
    """Read one level stream of RLE / bit-packed runs.

    In a version 1 page the stream starts with its own four-byte length (``known_len`` is
    ``None``). In a version 2 page the header already gave the length, and the stream has no
    prefix.
    """
    start = r.offset()
    try:
        n = known_len if known_len is not None else r.read_le_u32()
        data, body = r.read_bytes(n)
    except ValueError as e:
        raise ColumnError(str(e)) from e
    try:
        runs = rle.decode(data, body.start, bit_width(max_level), count)
    except ValueError as e:
        raise ColumnError(f"levels: {e}") from e
    return Span(start, body.end), runs


def read_column(file: bytes, chunk: ColumnChunk, leaf: Leaf) -> ColumnData:
    """Read every data page of a column chunk into triples."""
    refuse_encrypted(chunk)
    r = chunk.byte_range()
    if r.end > len(file):
        raise ColumnError(f"the column chunk claims bytes {r}, past the end of the file")
    try:
        pages = walk_pages(file[r.start : r.end], r.start)
    except ValueError as e:
        raise ColumnError(str(e)) from e
    return decode_pages(file, chunk, leaf, pages)


def read_column_pages(file: bytes, chunk: ColumnChunk, leaf: Leaf, offsets: list[int]) -> ColumnData:
    """Read only some pages of a column chunk: its dictionary page, if it has one, and the data
    pages starting at ``offsets``, each read where the page index says it is (ch10). The bytes
    between them are never looked at, so a reader need not have fetched them."""
    refuse_encrypted(chunk)
    r = chunk.byte_range()

    def one(at: int) -> Page:
        if at > r.end or at > len(file):
            raise ColumnError(f"no page at offset {at} in chunk {r}")
        try:
            return read_page(ByteReader(file[at : r.end], at))
        except ValueError as e:
            raise ColumnError(f"page at offset {at}: {e}") from e

    pages = []
    if chunk.dictionary_page_offset is not None and chunk.dictionary_page_offset > 0:
        pages.append(one(r.start))
    pages += [one(at) for at in offsets]
    return decode_pages(file, chunk, leaf, pages)


def refuse_encrypted(chunk: ColumnChunk) -> None:
    """An encrypted column chunk's pages are encrypted modules (ch13). Without its key they
    cannot be read, and the reader says so rather than decoding ciphertext."""
    if chunk.crypto is not None:
        key = "its own key" if chunk.crypto.with_column_key else "the footer key"
        raise ColumnError(
            f"column {chunk.dotted_path()} is encrypted with {key}, and this reader has no keys"
        )


def decode_pages(file: bytes, chunk: ColumnChunk, leaf: Leaf, pages: list[Page]) -> ColumnData:
    """Decode pages already located: a dictionary page first, if there is one, then data
    pages."""
    out = ColumnData()
    codec = chunk.codec
    for index, page in enumerate(pages):
        if page.body_span.end > len(file):
            raise ColumnError(f"page body {page.body_span} is past the end of the file")
        body = file[page.body_span.start : page.body_span.end]
        if page.page_type == "DICTIONARY_PAGE":
            # The dictionary: every distinct value, PLAIN-encoded, once.
            count = max(page.num_values or 0, 0)
            plain_body = _decompress(codec, body, page, page.uncompressed_page_size)
            try:
                entries = plain.decode(
                    leaf.physical_type, leaf.type_length, plain_body, page.body_span.start, count
                )
            except ValueError as e:
                raise ColumnError(f"dictionary: {e}") from e
            if codec != "UNCOMPRESSED":
                entries = [(v, page.body_span) for v, _ in entries]
            out.dictionary = DictionaryPage(page, entries)
            continue
        if page.page_type not in ("DATA_PAGE", "DATA_PAGE_V2"):
            raise ColumnError(f"unexpected page type {page.page_type}")
        count = max(page.num_values or 0, 0)
        # Version 1 compresses the whole body as one block. Decompress it, and read the levels
        # and values from the copy.
        whole = page.v2 is None and codec != "UNCOMPRESSED"
        levels_bytes = _decompress(codec, body, page, page.uncompressed_page_size) if whole else body
        levels_base = page.body_span.start
        r = ByteReader(levels_bytes, levels_base)
        # Version 2 moves the level lengths into the header and never compresses the levels.
        v2 = page.v2
        rep_len = max(v2.repetition_levels_byte_length, 0) if v2 else None
        def_len = max(v2.definition_levels_byte_length, 0) if v2 else None
        rep_levels = (
            level_stream(r, leaf.max_repetition_level, count, rep_len)
            if leaf.max_repetition_level > 0
            else None
        )
        def_levels = (
            level_stream(r, leaf.max_definition_level, count, def_len)
            if leaf.max_definition_level > 0
            else None
        )
        reps = rle.values(rep_levels[1]) if rep_levels else [0] * count
        defs = rle.values(def_levels[1]) if def_levels else [leaf.max_definition_level] * count
        present = sum(1 for d in defs if d == leaf.max_definition_level)
        values_start = r.offset()
        rest = levels_bytes[values_start - levels_base :]
        # Version 2 compresses only the values, and only when the header says so.
        values_compressed = codec != "UNCOMPRESSED" and v2 is not None and v2.is_compressed
        if values_compressed:
            levels = values_start - page.body_span.start
            rest = _decompress(codec, rest, page, page.uncompressed_page_size - levels)
        encoding = page.encoding or ""
        try:
            decoded = decode.values(
                encoding,
                leaf.physical_type,
                leaf.type_length,
                rest,
                values_start,
                present,
                out.dictionary.entries if out.dictionary else None,
            )
        except ValueError as e:
            raise ColumnError(f"values: {e}") from e
        values = Span(values_start, max(decoded.end, values_start))
        # Spans found in a decompressed copy become the compressed bytes that hold them.
        if whole or values_compressed:
            compressed = Span(page.body_span.start if whole else values_start, page.body_span.end)
            _blur(decoded, compressed)
            values = compressed
            if whole:
                for stream in (rep_levels, def_levels):
                    if stream is None:
                        continue
                    for run in stream[1]:
                        run.header = run.body = compressed
                rep_levels = (compressed, rep_levels[1]) if rep_levels else None
                def_levels = (compressed, def_levels[1]) if def_levels else None
        found = iter(decoded.values)
        for i in range(count):
            if defs[i] == leaf.max_definition_level:
                v = next(found, None)
                if v is None:
                    raise ColumnError("fewer values than definition levels say are present")
                out.triples.append(Triple(reps[i], defs[i], v.value, v.span, v.extra, index))
            else:
                out.triples.append(Triple(reps[i], defs[i], None, None, [], index))
        out.pages.append(DataPage(page, rep_levels, def_levels, values, encoding, decoded.steps))
    return out


def _decompress(codec: str, data: bytes, page: Page, size: int) -> bytes:
    """Decompress a page body, or a version 2 page's values section, into ``size`` bytes."""
    if size < 0:
        raise ColumnError(f"page size {size}")
    try:
        return compress.decompress(codec, data, page.body_span.start, size).data
    except ValueError as e:
        raise ColumnError(f"page at offset {page.header_span.start}: {e}") from e


def _blur(decoded: decode.Decoded, to: Span) -> None:
    """Report every span of a decode as ``to``: the compressed bytes the decoded bytes came
    from."""
    for v in decoded.values:
        v.span = to
        v.extra = []
    for step in decoded.steps:
        step.span = to
    decoded.end = to.end


def first_rows(rep_levels_per_page: list[list[int]]) -> list[int]:
    """The index of the first row each page holds, given each page's repetition levels.

    A row starts wherever the repetition level is 0. Under data page version 1 a row can begin in
    one page and continue in the next, so a page's first slot may not start a row; the page's
    first row is then the one that starts next. Counting the zeros before each page is enough.
    """
    out, started = [], 0
    for page in rep_levels_per_page:
        out.append(started)
        started += sum(1 for r in page if r == 0)
    return out
