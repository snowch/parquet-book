"""Compression: turning a page's compressed bytes back into its encoded bytes (ch07).

A writer encodes a page's values first, then hands the encoded bytes to a general-purpose
compressor. The column chunk's metadata names the codec, and every page header gives both sizes,
so a reader knows how large the output will be before it starts.

Three codecs are decoded here, each small enough to read in full:

- **SNAPPY**, raw Snappy: literals and back-references, byte-aligned.
- **LZ4_RAW**, an LZ4 block: the same idea with a different layout.
- **GZIP**, a gzip member around a DEFLATE stream: back-references too, but written with Huffman
  codes, so the tokens are bit-aligned.

ZSTD and BROTLI are not decoded. Each needs a decoder several times the size of all three above
together, and neither would teach more than DEFLATE does. A file that uses them still opens, its
sizes are still read from the footer, and a page that needs decompressing is reported as one this
reader cannot decompress.

Every decoder records what it did as :class:`Token`\\ s: which compressed bytes it read, which
output bytes it wrote, and, for a back-reference, where in the output it copied them from. The
laboratory steps through them. Python's ``zlib`` could inflate GZIP in one call; this module does
it by hand, because the point is to see how.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bytes import Span, crc32

HEADER, LITERAL, COPY = "header", "literal", "copy"


class CompressError(ValueError):
    pass


@dataclass
class Token:
    """What one step of a decompressor did."""

    kind: str
    """``header`` for bytes that describe the stream rather than hold data; ``literal`` for
    output bytes copied from the input as they are; ``copy`` for output bytes copied from
    ``distance`` bytes back in the output."""
    label: str
    input: Span
    """The compressed bytes it read. For GZIP, whose codes are bit-aligned, the bytes that hold
    those bits."""
    output: Span
    """The output bytes it wrote, as offsets into the decompressed page."""
    detail: str
    distance: int | None = None


@dataclass
class Decompressed:
    data: bytes
    tokens: list[Token]


def supported(codec: str) -> bool:
    """Whether :func:`decompress` can decode a codec."""
    return codec in ("UNCOMPRESSED", "SNAPPY", "LZ4_RAW", "GZIP")


def decompress(codec: str, data: bytes, base: int, size: int) -> Decompressed:
    """Decompress ``data``, which starts at file offset ``base``, into exactly ``size`` bytes."""
    if codec == "UNCOMPRESSED":
        out = Decompressed(
            bytes(data),
            [Token(LITERAL, "stored", Span(base, base + len(data)), Span(0, len(data)), "not compressed")],
        )
    elif codec == "SNAPPY":
        out = snappy(data, base)
    elif codec == "LZ4_RAW":
        out = lz4_raw(data, base, size)
    elif codec == "GZIP":
        out = gzip(data, base)
    else:
        raise CompressError(
            f"this reader does not decompress {codec}; it reads {codec} files' sizes from the "
            "footer, but not their pages"
        )
    if len(out.data) != size:
        raise CompressError(
            f"{codec}: the page header says {size} bytes, and decompressing gave {len(out.data)}"
        )
    return out


def copy_back(out: bytearray, distance: int, length: int) -> None:
    """Copy ``length`` bytes from ``distance`` bytes back in ``out``. The source may overlap the
    bytes being written: a distance of one repeats the last byte ``length`` times. So the copy is
    byte by byte."""
    if distance == 0 or distance > len(out):
        raise CompressError(
            f"a copy reaches {distance} bytes back, and only {len(out)} bytes have been written"
        )
    start = len(out) - distance
    for i in range(length):
        out.append(out[start + i])


def n_bytes(n: int) -> str:
    """ "1 byte", "2 bytes"."""
    return "1 byte" if n == 1 else f"{n} bytes"


def _span(base: int, start: int, end: int) -> Span:
    return Span(base + start, base + end)


def _get(data: bytes, at: int) -> int:
    if at >= len(data):
        raise CompressError(f"the compressed bytes end at offset {at}, mid-token")
    return data[at]


def _le(data: bytes, at: int, n: int) -> int:
    """Little-endian, ``n`` bytes."""
    return sum(_get(data, at + i) << (8 * i) for i in range(n))


def snappy(data: bytes, base: int) -> Decompressed:
    """Raw Snappy: a varint giving the output length, then elements. Each element starts with a
    tag byte whose low two bits say what it is::

        00  literal             length - 1 in the tag's top six bits; 60..63 mean "in the next 1..4 bytes"
        01  copy, 1-byte offset length 4..11 in three bits, offset in three bits and the next byte
        10  copy, 2-byte offset length 1..64 in the top six bits, offset in the next two bytes
        11  copy, 4-byte offset length 1..64 in the top six bits, offset in the next four bytes
    """
    tokens = []
    size, shift, i = 0, 0, 0
    while True:
        b = _get(data, i)
        i += 1
        size |= (b & 0x7F) << shift
        shift += 7
        if b & 0x80 == 0:
            break
    tokens.append(
        Token(HEADER, "length", _span(base, 0, i), Span(0, 0), f"varint: the output is {size} bytes")
    )
    out = bytearray()
    while i < len(data):
        start, tag = i, data[i]
        i += 1
        at = len(out)
        if tag & 0b11 == 0b00:
            length = tag >> 2
            if length >= 60:
                extra = length - 59
                length = _le(data, i, extra)
                i += extra
            length += 1
            if i + length > len(data):
                raise CompressError("a literal runs past the end of the compressed bytes")
            out += data[i : i + length]
            i += length
            tokens.append(
                Token(LITERAL, "literal", _span(base, start, i), Span(at, len(out)),
                      f"tag {tag:02x}: a literal, the next {n_bytes(length)}")
            )  # fmt: skip
            continue
        if tag & 0b11 == 0b01:
            length = 4 + ((tag >> 2) & 0b111)
            distance = ((tag >> 5) << 8) | _get(data, i)
            i += 1
        elif tag & 0b11 == 0b10:
            length, distance = 1 + (tag >> 2), _le(data, i, 2)
            i += 2
        else:
            length, distance = 1 + (tag >> 2), _le(data, i, 4)
            i += 4
        copy_back(out, distance, length)
        tokens.append(
            Token(COPY, "copy", _span(base, start, i), Span(at, len(out)),
                  f"tag {tag:02x}: copy {n_bytes(length)} from {distance} back", distance)
        )  # fmt: skip
    if len(out) != size:
        raise CompressError(f"Snappy promised {size} bytes and its elements wrote {len(out)}")
    return Decompressed(bytes(out), tokens)


def lz4_raw(data: bytes, base: int, size: int) -> Decompressed:
    """An LZ4 block: a run of sequences, each some literals and then one match. ::

        token      literal length in the high four bits, match length - 4 in the low four;
                   15 in either means "add the bytes that follow, until one is not 255"
        literals
        offset     two bytes, little-endian: how far back the match starts

    The last sequence has literals and no match: the block ends after them.
    """
    tokens = []
    out = bytearray()
    i = 0

    def more(n: int) -> int:
        # A length of 15 continues in the bytes that follow, each added until one is not 255.
        nonlocal i
        if n == 15:
            while True:
                b = _get(data, i)
                i += 1
                n += b
                if b != 255:
                    break
        return n

    while i < len(data):
        start, token = i, data[i]
        i += 1
        literals = more(token >> 4)
        at = len(out)
        if i + literals > len(data):
            raise CompressError("literals run past the end of the compressed bytes")
        out += data[i : i + literals]
        i += literals
        tokens.append(
            Token(LITERAL, "literals", _span(base, start, i), Span(at, len(out)),
                  f"token {token:02x}: a literal, the next {n_bytes(literals)}")
        )  # fmt: skip
        if i == len(data):
            break  # the last sequence: no match
        match_start = i
        distance = _le(data, i, 2)
        i += 2
        length = more(token & 0x0F) + 4
        at = len(out)
        copy_back(out, distance, length)
        tokens.append(
            Token(COPY, "match", _span(base, match_start, i), Span(at, len(out)),
                  f"copy {n_bytes(length)} from {distance} back", distance)
        )  # fmt: skip
    return Decompressed(bytes(out), tokens)


def gzip(data: bytes, base: int) -> Decompressed:
    """A gzip member: a header, a DEFLATE stream, and a trailer holding the output's CRC-32 and
    length. The reader checks both."""
    if len(data) < 18 or data[0] != 0x1F or data[1] != 0x8B or data[2] != 8:
        raise CompressError("not a gzip member: it should start 1f 8b 08")
    flags = data[3]
    i = 10
    if flags & 0x04:
        i += 2 + _le(data, i, 2)  # FEXTRA
    for flag in (0x08, 0x10):  # FNAME, FCOMMENT: zero-terminated strings
        if flags & flag:
            while _get(data, i) != 0:
                i += 1
            i += 1
    if flags & 0x02:
        i += 2  # FHCRC
    tokens = [Token(HEADER, "gzip header", _span(base, 0, i), Span(0, 0), "1f 8b: gzip; 08: DEFLATE")]
    out, end = inflate(data[i:], base + i, tokens)
    i += end
    crc, length = _le(data, i, 4), _le(data, i + 4, 4)
    actual = crc32(out)
    tokens.append(
        Token(HEADER, "gzip trailer", _span(base, i, i + 8), Span(len(out), len(out)),
              f"CRC-32 {crc:08x} ({'matches' if crc == actual else 'does not match'}), length {length}")
    )  # fmt: skip
    if crc != actual or length != len(out) & 0xFFFF_FFFF:
        raise CompressError(
            f"the gzip trailer does not match the output: CRC-32 {crc:08x} against {actual:08x}"
        )
    return Decompressed(out, tokens)


class Bits:
    """DEFLATE reads bits least significant first, and Huffman codes most significant first."""

    def __init__(self, data: bytes) -> None:
        self.data, self.pos = data, 0
        """``pos`` is the position in bits from the start of ``data``."""

    def bit(self) -> int:
        b = (_get(self.data, self.pos // 8) >> (self.pos % 8)) & 1
        self.pos += 1
        return b

    def bits(self, n: int) -> int:
        return sum(self.bit() << i for i in range(n))

    def span(self, base: int, start: int) -> Span:
        """The bytes holding bits ``start..self.pos``, as file offsets."""
        return Span(base + start // 8, base + (self.pos + 7) // 8)


class Huffman:
    """A canonical Huffman code, described the way DEFLATE describes it: by each symbol's code
    length alone. ``count[n]`` is how many codes are ``n`` bits long, and ``symbols`` lists the
    symbols in code order."""

    def __init__(self, lengths: list[int]) -> None:
        self.count = [0] * 16
        for n in lengths:
            self.count[n] += 1
        self.count[0] = 0
        self.symbols = [s for n in range(1, 16) for s, m in enumerate(lengths) if m == n]

    def decode(self, bits: Bits) -> int:
        """Read one code a bit at a time. The codes of each length are consecutive integers, so
        after ``n`` bits the code is either among the ``count[n]`` codes of that length or
        longer."""
        code = first = index = 0
        for n in range(1, 16):
            code |= bits.bit()
            count = self.count[n]
            if code - first < count:
                return self.symbols[index + code - first]
            index += count
            first = (first + count) << 1
            code <<= 1
        raise CompressError("a Huffman code longer than fifteen bits")


# Lengths 3..258 and distances 1..32768 are each a base plus some extra bits.
LENGTH_BASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258]  # fmt: skip
LENGTH_EXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0]
DIST_BASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577]  # fmt: skip
DIST_EXTRA = [
    0,
    0,
    0,
    0,
    1,
    1,
    2,
    2,
    3,
    3,
    4,
    4,
    5,
    5,
    6,
    6,
    7,
    7,
    8,
    8,
    9,
    9,
    10,
    10,
    11,
    11,
    12,
    12,
    13,
    13,
]
CODE_LENGTH_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]
"""The order a dynamic block lists the code-length code's own lengths in."""


def inflate(data: bytes, base: int, tokens: list[Token]) -> tuple[bytes, int]:
    """Inflate a DEFLATE stream. Returns the output and how many bytes of ``data`` it used."""
    bits = Bits(data)
    out = bytearray()
    while True:
        start = bits.pos
        last = bits.bit() == 1
        kind = bits.bits(2)
        final_note = ", the last" if last else ""
        if kind == 0:
            # Stored: skip to a byte boundary, then a length, its complement, and the bytes.
            at = (bits.pos + 7) // 8
            length, nlength = _le(data, at, 2), _le(data, at + 2, 2)
            if length != ~nlength & 0xFFFF:
                raise CompressError("a stored block's length and its complement disagree")
            if at + 4 + length > len(data):
                raise CompressError("a stored block runs past the end")
            before = len(out)
            out += data[at + 4 : at + 4 + length]
            bits.pos = (at + 4 + length) * 8
            tokens.append(
                Token(LITERAL, "stored block", bits.span(base, start), Span(before, len(out)),
                      f"{n_bytes(length)}, not compressed{final_note}")
            )  # fmt: skip
            if last:
                break
            continue
        if kind == 1:
            # Fixed codes: lengths the specification lists, the same in every stream.
            lit = Huffman([8] * 144 + [9] * 112 + [7] * 24 + [8] * 8)
            dist, what = Huffman([5] * 30), "fixed Huffman codes"
        elif kind == 2:
            lit, dist = dynamic_codes(bits)
            what = "its own Huffman codes"
        else:
            raise CompressError("block type 3 is reserved")
        tokens.append(
            Token(HEADER, "block", bits.span(base, start), Span(len(out), len(out)),
                  f"a compressed block with {what}{final_note}")
        )  # fmt: skip
        while True:
            start = bits.pos
            symbol = lit.decode(bits)
            at = len(out)
            if symbol < 256:
                out.append(symbol)
                # Consecutive literals are one token, so the list stays readable.
                t = tokens[-1] if tokens else None
                if t is not None and t.kind == LITERAL and t.output.end == at:
                    t.input = Span(t.input.start, bits.span(base, start).end)
                    t.output = Span(t.output.start, at + 1)
                    t.detail = f"{n_bytes(t.output.length)}, each its own Huffman code"
                else:
                    tokens.append(
                        Token(LITERAL, "literals", bits.span(base, start), Span(at, at + 1),
                              "1 byte, its own Huffman code")
                    )  # fmt: skip
                continue
            if symbol == 256:
                break  # end of block
            s = symbol - 257
            if s >= 29:
                raise CompressError(f"length symbol {symbol} does not exist")
            length = LENGTH_BASE[s] + bits.bits(LENGTH_EXTRA[s])
            d = dist.decode(bits)
            if d >= 30:
                raise CompressError(f"distance symbol {d} does not exist")
            distance = DIST_BASE[d] + bits.bits(DIST_EXTRA[d])
            copy_back(out, distance, length)
            tokens.append(
                Token(COPY, "copy", bits.span(base, start), Span(at, len(out)),
                      f"copy {n_bytes(length)} from {distance} back", distance)
            )  # fmt: skip
        if last:
            break
    return bytes(out), (bits.pos + 7) // 8


def dynamic_codes(bits: Bits) -> tuple[Huffman, Huffman]:
    """A dynamic block's codes, which it describes before its data: how many codes of each kind,
    then the code lengths of a small code, then every literal and distance code's length written
    in that small code, with run lengths for repeats and zeros."""
    hlit = bits.bits(5) + 257
    hdist = bits.bits(5) + 1
    hclen = bits.bits(4) + 4
    cl = [0] * 19
    for i in CODE_LENGTH_ORDER[:hclen]:
        cl[i] = bits.bits(3)
    code_lengths = Huffman(cl)
    lengths: list[int] = []
    while len(lengths) < hlit + hdist:
        n = code_lengths.decode(bits)
        if n <= 15:
            value, repeat = n, 1
        elif n == 16:
            if not lengths:
                raise CompressError("a repeat with nothing before it")
            value, repeat = lengths[-1], 3 + bits.bits(2)
        elif n == 17:
            value, repeat = 0, 3 + bits.bits(3)
        else:
            value, repeat = 0, 11 + bits.bits(7)
        lengths += [value] * repeat
    if len(lengths) != hlit + hdist:
        raise CompressError("the code lengths overrun their count")
    return Huffman(lengths[:hlit]), Huffman(lengths[hlit:])
