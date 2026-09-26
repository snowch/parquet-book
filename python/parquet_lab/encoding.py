"""Encodings: how values become bytes (ch05).

This holds the one-value readers: a single PLAIN-encoded value, which is how the footer stores a
column's minimum and maximum, and bytes as hex. Whole pages are decoded in later chapters.

It also holds the two ways the book writes a value as text, so Python and Rust show the same
characters: a number in its shortest exact form, and a string in quotes.
"""

from __future__ import annotations

import math
import struct
import unicodedata
from decimal import Decimal


def plain_scalar(physical: int, data: bytes) -> str | None:
    """One value in PLAIN form, rendered for display. ``None`` when the bytes do not fit the
    type.

    PLAIN writes fixed-width numbers little-endian and in full. A statistics value for a
    ``BYTE_ARRAY`` column is the bare bytes, without the four-byte length prefix a PLAIN page
    would give it, because the Thrift field already carries a length.
    """
    match physical, len(data):
        case 0, 1:
            return "true" if data[0] != 0 else "false"
        case 1, 4:
            return str(struct.unpack("<i", data)[0])
        case 2, 8:
            return str(struct.unpack("<q", data)[0])
        case 4, 4:
            return show_float(struct.unpack("<f", data)[0], single=True)
        case 5, 8:
            return show_float(struct.unpack("<d", data)[0])
        case 6 | 7, _:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                return hex(data)
            if any(unicodedata.category(c) == "Cc" for c in text):
                return hex(data)
            return quote(text)
    return None


def hex(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def show_float(v: float, single: bool = False) -> str:
    """A float in the fewest digits that read back as the same value, never in exponent form:
    ``1.5``, ``100000000000000000000``, ``0.0000001``. ``single`` rounds to a 32-bit float's
    precision, for ``FLOAT`` columns."""
    if math.isnan(v):
        return "NaN"
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    digits = repr(v)
    if single:
        # The shortest decimal that a 32-bit float reads back as this value.
        exact = struct.pack("<f", v)
        for p in range(1, 10):
            candidate = f"{v:.{p}g}"
            if struct.pack("<f", float(candidate)) == exact:
                digits = candidate
                break
    text = format(Decimal(digits).normalize(), "f")
    return text


_ESCAPES = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\0": "\\0"}
_UNPRINTABLE = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


def quote(text: str) -> str:
    """A string in double quotes, with quotes, backslashes and unprintable characters escaped."""
    out = []
    for c in text:
        if c in _ESCAPES:
            out.append(_ESCAPES[c])
        elif unicodedata.category(c) in _UNPRINTABLE:
            out.append(f"\\u{{{ord(c):x}}}")
        else:
            out.append(c)
    return '"' + "".join(out) + '"'


def debug_float(v: float) -> str:
    """A float as the Rust reader's JSON writes it: the fewest digits that read back as the same
    value, always with a point or an exponent, and an exponent only for very large or very small
    values (``1.0``, ``0.0001``, ``1e16``, ``1.5e-7``)."""
    if math.isnan(v):
        return "NaN"
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    a = abs(v)
    if a != 0 and (a >= 1e16 or a < 1e-4):
        sign, digits, exponent = Decimal(repr(v)).as_tuple()
        d = "".join(map(str, digits)).rstrip("0") or "0"
        power = len("".join(map(str, digits))) - 1 + exponent
        mantissa = d[0] + (f".{d[1:]}" if len(d) > 1 else "")
        return f"{'-' if sign else ''}{mantissa}e{power}"
    text = format(Decimal(repr(v)), "f")
    return text if "." in text else text + ".0"


def _json_str(s: str) -> str:
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 0x20:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


MAX_SAFE = 2**53 - 1


def json_text(value: object) -> str:
    """A JSON value as compact text, character for character as the Rust reader writes it. A
    decode step's detail quotes a value this way, so the two readers' steps read the same."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return _json_str(str(value)) if abs(value) > MAX_SAFE else str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return _json_str("NaN")
        if math.isinf(value):
            return _json_str("Infinity" if value > 0 else "-Infinity")
        return debug_float(value)
    if isinstance(value, str):
        return _json_str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(json_text(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{_json_str(k)}:{json_text(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"cannot write {type(value).__name__} as JSON")
