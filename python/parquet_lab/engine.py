"""A tiny query engine: SQL answered from Parquet bytes (ch12).

Every earlier chapter built a piece of a reader. This module puts them under a query language,
small enough to read in full::

    SELECT *  |  item, item, ...          item: column, count(*), count(c), sum(c), min(c),
    FROM name                                   max(c) or avg(c)
    [WHERE condition AND condition ...]   condition: column op value, column IS [NOT] NULL
    [GROUP BY column, ...]
    [ORDER BY column [ASC|DESC], ...]
    [LIMIT n]

A query runs as a pipeline of stages, each a plain loop over rows:

1. **Scan** reads the columns the query mentions. Row groups the footer's statistics rule out for
   any condition are skipped (:mod:`parquet_lab.prune`); the rest are decoded
   (:mod:`parquet_lab.column`).
2. **Filter** keeps the rows every condition accepts, comparing in each column's own order
   (:mod:`parquet_lab.stats`).
3. **Aggregate** groups rows and folds each group's values, when the query asks for it.
4. **Sort** and **Limit** order and cut the result.

Each stage records how many rows went in and came out, and a few of them, so the laboratory can
show the query at every step.

A value in a result row is ``None``, a ``bool``, an ``int``, a ``float`` or a ``str``.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from functools import cmp_to_key

from . import plain
from .column import read_column
from .encoding import json_text, quote
from .logical import value_json
from .prune import Op, Predicate, against_bounds
from .schema import Leaf, build, leaves
from .stats import bounds


class QueryError(ValueError):
    pass


# ---- The language -------------------------------------------------------------------------

AGGREGATES = ("count", "sum", "min", "max", "avg")


@dataclass(frozen=True)
class Item:
    """``*``, a column, or an aggregate: ``kind`` is ``"star"``, ``"column"`` or an aggregate's
    name; ``arg`` is the column, and ``None`` for ``count(*)``."""

    kind: str
    arg: str | None = None

    def name(self) -> str:
        """The item as a result column is named: ``country``, ``count(*)``,
        ``sum(amount_cents)``."""
        if self.kind == "star":
            return "*"
        if self.kind == "column":
            return self.arg
        return f"{self.kind}({self.arg or '*'})"

    @property
    def is_aggregate(self) -> bool:
        return self.kind in AGGREGATES


@dataclass(frozen=True)
class Condition:
    column: str
    op: Op
    value: str
    """The literal as written, without quotes; empty for ``IS NULL`` and ``IS NOT NULL``."""


@dataclass
class Select:
    items: list[Item]
    table: str
    conditions: list[Condition] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    order_by: list[tuple[str, bool]] = field(default_factory=list)
    """Result column names, each ascending unless ``True``."""
    limit: int | None = None


def _quote_char(c: str) -> str:
    """A character in single quotes, as the Rust engine writes one in an error."""
    escapes = {"'": "\\'", "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\0": "\\0"}
    inner = escapes.get(c) or quote(c)[1:-1].replace('\\"', '"')
    return f"'{inner}'"


def tokens(sql: str) -> list[tuple[str, str]]:
    """Split SQL into ``(kind, text)`` tokens: ``word``, ``number``, ``text`` or ``symbol``."""
    out = []
    i = 0
    while i < len(sql):
        c = sql[i]
        if c.isspace():
            i += 1
        elif (c.isascii() and c.isalpha()) or c == "_":
            start = i
            while i < len(sql) and ((sql[i].isascii() and sql[i].isalnum()) or sql[i] in "_."):
                i += 1
            out.append(("word", sql[start:i]))
        elif c in "0123456789" or (c == "-" and i + 1 < len(sql) and sql[i + 1] in "0123456789"):
            start = i
            i += 1
            while i < len(sql) and sql[i] in "0123456789.":
                i += 1
            out.append(("number", sql[start:i]))
        elif c == "'":
            end = sql.find("'", i + 1)
            if end < 0:
                raise QueryError("a string is missing its closing quote")
            out.append(("text", sql[i + 1 : end]))
            i = end + 1
        else:
            two = sql[i : i + 2]
            if two in ("<=", ">=", "!=", "<>"):
                symbol = two
            elif c in "=<>(),*":
                symbol = c
            else:
                raise QueryError(f"unexpected character {_quote_char(c)}")
            i += len(symbol)
            out.append(("symbol", symbol))
    return out


class Parser:
    def __init__(self, sql: str) -> None:
        self.tokens = tokens(sql)
        self.at = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def keyword(self, k: str) -> bool:
        t = self.peek()
        if t and t[0] == "word" and t[1].lower() == k.lower():
            self.at += 1
            return True
        return False

    def expect_keyword(self, k: str) -> None:
        if not self.keyword(k):
            raise QueryError(f"expected {k}{self.here()}")

    def symbol(self, s: str) -> bool:
        if self.peek() == ("symbol", s):
            self.at += 1
            return True
        return False

    def here(self) -> str:
        t = self.peek()
        if t is None:
            return " at the end"
        return f" at '{t[1]}'" if t[0] == "text" else f" at {quote(t[1])}"

    def name(self) -> str:
        t = self.peek()
        if t is None or t[0] != "word":
            raise QueryError(f"expected a column name{self.here()}")
        self.at += 1
        return t[1]

    def item(self) -> Item:
        if self.symbol("*"):
            return Item("star")
        word = self.name()
        agg = word.lower()
        if agg in AGGREGATES and self.symbol("("):
            arg = None if agg == "count" and self.symbol("*") else self.name()
            if not self.symbol(")"):
                raise QueryError(f"expected ){self.here()}")
            return Item(agg, arg)
        return Item("column", word)

    def condition(self) -> Condition:
        column = self.name()
        if self.keyword("is"):
            negated = self.keyword("not")
            self.expect_keyword("null")
            return Condition(column, Op.IS_NOT_NULL if negated else Op.IS_NULL, "")
        t = self.peek()
        if t is None or t[0] != "symbol":
            raise QueryError(f"expected a comparison{self.here()}")
        self.at += 1
        op = Op.parse("!=" if t[1] == "<>" else t[1])
        v = self.peek()
        if v is None or v[0] not in ("number", "text"):
            raise QueryError(f"expected a value{self.here()}")
        self.at += 1
        return Condition(column, op, v[1])

    def list(self, one):
        out = [one()]
        while self.symbol(","):
            out.append(one())
        return out


def parse(sql: str) -> Select:
    """Parse one ``SELECT``."""
    p = Parser(sql)
    p.expect_keyword("select")
    items = p.list(p.item)
    p.expect_keyword("from")
    q = Select(items, p.name())
    if p.keyword("where"):
        q.conditions.append(p.condition())
        while p.keyword("and"):
            q.conditions.append(p.condition())
    if p.keyword("group"):
        p.expect_keyword("by")
        q.group_by = p.list(p.name)
    if p.keyword("order"):
        p.expect_keyword("by")

        def one():
            c = p.name()
            desc = p.keyword("desc")
            if not desc:
                p.keyword("asc")
            return c, desc

        q.order_by = p.list(one)
    if p.keyword("limit"):
        t = p.peek()
        if t is None or t[0] != "number":
            raise QueryError(f"expected a number{p.here()}")
        p.at += 1
        if not re.fullmatch(r"[0-9]+", t[1]) or int(t[1]) >= 2**64:
            raise QueryError(f"LIMIT {t[1]} is not a count")
        q.limit = int(t[1])
    if p.at != len(p.tokens):
        raise QueryError(f"unexpected{p.here()}")
    return q


# ---- Values -------------------------------------------------------------------------------


def from_json(j: object) -> object:
    """A JSON value as a result value. An integer too large for 64 bits wraps, as it does in the
    Rust engine; anything that is not a scalar becomes its JSON text."""
    if j is None or isinstance(j, (bool, float, str)):
        return j
    if isinstance(j, int):
        return (j + 2**63) % 2**64 - 2**63
    return json_text(j)


def _number(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _number_or_zero(v: object) -> float:
    n = _number(v)
    return 0.0 if n is None else n


def _total(x: float) -> int:
    """A float's position in IEEE 754's total order, as an integer to compare: negative NaN, -inf,
    ..., -0.0, 0.0, ..., inf, NaN."""
    bits = struct.unpack("<q", struct.pack("<d", x))[0]
    return bits ^ 0x7FFF_FFFF_FFFF_FFFF if bits < 0 else bits


def _rank(v: object) -> int:
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1
    return 2 if isinstance(v, (int, float)) else 3


def order(a: object, b: object) -> int:
    """An order over every value, for sorting and grouping: nulls first, then numbers, then
    strings. Values of a column are all one kind, so the mixed cases only need to be fixed."""

    def cmp(x, y):
        return (x > y) - (x < y)

    ra, rb = _rank(a), _rank(b)
    if ra == rb == 2:
        if type(a) is int and type(b) is int:
            return cmp(a, b)
        return cmp(_total(_number(a)), _total(_number(b)))
    if ra == rb == 3:
        return cmp(a.encode(), b.encode())
    if ra == rb == 1:
        return cmp(a, b)
    return cmp(ra, rb)


# ---- Running a query ----------------------------------------------------------------------

SAMPLE = 5


@dataclass
class Stage:
    """One stage of the pipeline, as the laboratory shows it."""

    name: str
    detail: str
    rows_in: int
    rows_out: int
    columns: list[str]
    sample: list[list[object]]
    """The first few rows the stage produced."""


@dataclass
class Answer:
    columns: list[str]
    rows: list[list[object]]
    stages: list[Stage]
    row_groups_read: int
    row_groups: int
    bytes_read: int


def _stage(name: str, detail: str, rows_in: int, columns: list[str], rows: list) -> Stage:
    return Stage(name, detail, rows_in, len(rows), list(columns), [list(r) for r in rows[:SAMPLE]])


class Acc:
    """An aggregate's running state for one group."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.count = 0
        self.value: object = None
        self.total = 0.0

    def add(self, v: object, star: bool = False) -> None:
        """Fold in one value. ``star`` is ``count(*)``'s row, which counts whatever it holds."""
        if star:
            if self.kind == "count":
                self.count += 1
            return
        if v is None:
            return  # aggregates skip nulls
        if self.kind == "count":
            self.count += 1
        elif self.kind == "sum":
            if self.value is None:
                self.value = v
            elif type(self.value) is int and type(v) is int:
                self.value += v
            else:
                self.value = _number_or_zero(self.value) + _number_or_zero(v)
        elif self.kind == "min":
            if self.value is None or order(v, self.value) < 0:
                self.value = v
        elif self.kind == "max":
            if self.value is None or order(v, self.value) > 0:
                self.value = v
        else:  # avg
            self.total += _number_or_zero(v)
            self.count += 1

    def result(self) -> object:
        if self.kind == "count":
            return self.count
        if self.kind == "avg":
            return None if self.count == 0 else self.total / self.count
        return self.value


@dataclass
class Source:
    """One file a query reads, and the partition values its path gives it (ch14). Every source
    must have the same schema; partition columns are not in the files, only in their paths."""

    name: str
    data: bytes
    partition: list[tuple[str, str]] = field(default_factory=list)


def run(file: bytes, sql: str) -> Answer:
    """Answer ``sql`` from ``file``'s bytes."""
    return run_sources([Source("the file", file)], sql)


def run_sources(sources: list[Source], sql: str) -> Answer:
    """Answer ``sql`` from several files at once: a table (ch14)."""
    from .report import open_bytes

    q = parse(sql)
    mds = []
    for s in sources:
        try:
            mds.append(open_bytes(s.data))
        except Exception as e:  # a format or store error, reported with the file's name
            raise QueryError(f"{s.name}: {e}") from e
    if not mds:
        raise QueryError("no files to read")
    md0 = mds[0]
    flat = [leaf for leaf in leaves(build(md0.schema)) if leaf.max_repetition_level == 0]
    partition_names = [k for k, _ in sources[0].partition]

    def find(name: str) -> Leaf | str:
        """A column of the query: a ``Leaf`` the files hold, or the name of a partition."""
        leaf = next((leaf for leaf in flat if leaf.dotted_path() == name), None)
        if leaf is not None:
            return leaf
        if name in partition_names:
            return name
        raise QueryError(f"no column {name}")

    # Every column the query mentions: the files' in schema order, then the partitions'.
    mentioned = []
    for i in q.items:
        if i.kind == "star":
            mentioned += [leaf.dotted_path() for leaf in flat] + partition_names
        elif i.arg is not None:
            mentioned.append(i.arg)
    mentioned += [c.column for c in q.conditions] + q.group_by
    columns: list[Leaf | str] = []
    for name in mentioned:
        col = find(name)
        same = any(
            (isinstance(c, Leaf) and isinstance(col, Leaf) and c.column == col.column) or c == col
            for c in columns
        )
        if not same:
            columns.append(col)
    columns.sort(key=lambda c: (0, c.column, "") if isinstance(c, Leaf) else (1, 0, c))
    names = [c.dotted_path() if isinstance(c, Leaf) else c for c in columns]

    # A condition on a file's column compares PLAIN bytes in the column's order; one on a
    # partition compares the path's text.
    predicates = []
    for c in q.conditions:
        at = names.index(c.column) if c.column in names else 0
        col = find(c.column)
        if isinstance(col, Leaf):
            converted = md0.schema[col.element].converted_type
            predicates.append((at, Predicate.new(col, converted, c.op, c.value)))
        else:
            predicates.append((at, (c.op, c.value)))

    # 1. Scan: skip the row groups any condition rules out, and decode the rest.
    stages = []
    raw: list[list[bytes | None]] = []
    rows: list[list[object]] = []
    read = size = 0
    skipped_why = []
    many = len(sources) > 1
    for source, md in zip(sources, mds, strict=True):
        for g, rg in enumerate(md.row_groups):
            why = None
            # Skip the row group if any condition's comparison with its bounds rules it out.
            for c, (_, t) in zip(q.conditions, predicates, strict=True):
                col = find(c.column)
                if not isinstance(t, Predicate) or not isinstance(col, Leaf):
                    continue
                chunk = rg.columns[col.column]
                s = chunk.statistics
                if s is None:
                    continue
                o = md.column_orders
                type_order = o is not None and col.column < len(o) and o[col.column] == "TYPE_ORDER"
                try:
                    b = bounds(s, t.comparator, type_order)
                    found = (b.min, b.max)
                except ValueError:
                    found = None
                d = against_bounds(t, found, s.null_count, chunk.num_values)
                if d.skip:
                    where = f"{source.name} " if many else ""
                    why = f"{where}row group {g}: {c.column} {c.op.symbol} {c.value}: {d.why}"
                    break
            if why is not None:
                skipped_why.append(why)
                continue
            read += 1
            cols = []
            for col in columns:
                if isinstance(col, Leaf):
                    chunk = rg.columns[col.column]
                    size += chunk.byte_range().length
                    cells = []
                    for tr in read_column(source.data, chunk, col).triples:
                        if tr.value is None:
                            cells.append((None, None))
                        else:
                            shown = value_json(col.physical_type, col.logical_type, tr.value)
                            cells.append(
                                (plain.to_plain_bytes(tr.value, col.physical_type), from_json(shown))
                            )
                else:
                    v = next((v for k, v in source.partition if k == col), None)
                    cells = [(None, v)] * rg.num_rows
                cols.append(cells)
            for r in range(rg.num_rows):
                raw.append([c[r][0] for c in cols])
                rows.append([c[r][1] for c in cols])
    scanned = sum(md.num_rows for md in mds)
    groups = sum(len(md.row_groups) for md in mds)
    detail = f"read {read} of {groups} row groups"
    if many:
        detail += f" in {len(sources)} files"
    detail += f", {size} bytes of column chunks"
    if skipped_why:
        detail += f"; skipped {'; '.join(skipped_why)}"
    stages.append(_stage("Scan", detail, scanned, names, rows))

    # 2. Filter: every condition, in each column's own order.
    if predicates:
        before = len(rows)

        def keep(r: list, v: list) -> bool:
            for i, t in predicates:
                if isinstance(t, Predicate):
                    if not t.row_matches(r[i]):
                        return False
                else:
                    op, text = t
                    if isinstance(v[i], str):
                        ordering = (v[i].encode() > text.encode()) - (v[i].encode() < text.encode())
                        if not op.matches(ordering):
                            return False
                    elif op is not Op.IS_NULL:
                        return False
            return True

        rows = [v for r, v in zip(raw, rows, strict=True) if keep(r, v)]
        text = " and ".join(
            f"{c.column} {c.op.symbol}" if not c.value else f"{c.column} {c.op.symbol} {c.value}"
            for c in q.conditions
        )
        stages.append(_stage("Filter", text, before, names, rows))
    return finish(q, names, rows, stages, read, groups, size)


def run_empty(sql: str, columns: list[str], why: str) -> Answer:
    """Answer a query that reads no files: every file was ruled out before reading (ch14).
    ``columns`` are the table's columns, from its log, for ``SELECT *``."""
    q = parse(sql)
    names = [
        c
        for c in columns
        if any(i.kind == "star" or i.arg == c for i in q.items)
        or c in q.group_by
        or any(x.column == c for x in q.conditions)
    ]
    for i in q.items:
        if i.arg is not None and i.arg not in columns:
            raise QueryError(f"no column {i.arg}")
    return finish(q, names, [], [_stage("Scan", f"read nothing: {why}", 0, names, [])], 0, 0, 0)


def finish(
    q: Select, names: list[str], rows: list, stages: list, read: int, groups: int, size: int
) -> Answer:
    """Aggregate or project, then sort and limit: everything after the rows are read."""

    def position(name: str) -> int | None:
        return names.index(name) if name in names else None

    # 3. Aggregate, or project.
    aggregating = bool(q.group_by) or any(i.is_aggregate for i in q.items)
    out_names = [n for i in q.items for n in (names if i.kind == "star" else [i.name()])]
    before = len(rows)
    if aggregating:
        keys = []
        for c in q.group_by:
            if position(c) is None:
                raise QueryError(f"no column {c}")
            keys.append(position(c))
        for i in q.items:
            if i.kind == "column" and i.arg not in q.group_by:
                raise QueryError(f"{i.arg} is neither grouped by nor aggregated")
            if i.kind == "star":
                raise QueryError("SELECT * cannot be aggregated")
        aggs = [
            (i.kind, position(i.arg) if i.arg is not None else None, i.arg is None)
            for i in q.items
            if i.is_aggregate
        ]
        grouped: list[tuple[list, list[Acc]]] = []
        for r in rows:
            key = [r[k] for k in keys]
            at = next(
                (
                    n
                    for n, (k, _) in enumerate(grouped)
                    if all(order(a, b) == 0 for a, b in zip(k, key, strict=True))
                ),
                None,
            )
            if at is None:
                grouped.append((key, [Acc(kind) for kind, _, _ in aggs]))
                at = len(grouped) - 1
            for acc, (_, arg, star) in zip(grouped[at][1], aggs, strict=True):
                if star or arg is None:
                    acc.add(None, star=True)
                else:
                    acc.add(r[arg])
        if not grouped and not keys:
            grouped.append(([], [Acc(kind) for kind, _, _ in aggs]))
        out = []
        for key, accs in grouped:
            results = iter(accs)
            row = []
            for i in q.items:
                if i.kind == "column":
                    row.append(key[q.group_by.index(i.arg) if i.arg in q.group_by else 0])
                else:
                    acc = next(results, None)
                    row.append(acc.result() if acc else None)
            out.append(row)
        by = "all rows as one group" if not q.group_by else f"by {', '.join(q.group_by)}"
        stages.append(_stage("Aggregate", by, before, out_names, out))
        rows = out
    else:
        idx = []
        for n in out_names:
            if position(n) is None:
                raise QueryError(f"no column {n}")
            idx.append(position(n))
        rows = [[r[i] for i in idx] for r in rows]
        stages.append(_stage("Project", ", ".join(out_names), before, out_names, rows))

    # 4. Sort and limit.
    if q.order_by:
        keys = []
        for c, desc in q.order_by:
            if c not in out_names:
                raise QueryError(f"ORDER BY {c}: only result columns can be sorted by")
            keys.append((out_names.index(c), desc))

        def compare(a: list, b: list) -> int:
            for i, desc in keys:
                o = order(a[i], b[i])
                if o:
                    return -o if desc else o
            return 0

        rows = sorted(rows, key=cmp_to_key(compare))
        text = ", ".join(f"{c} descending" if d else c for c, d in q.order_by)
        stages.append(_stage("Sort", text, len(rows), out_names, rows))
    if q.limit is not None:
        before = len(rows)
        rows = rows[: q.limit]
        stages.append(_stage("Limit", f"{q.limit} rows", before, out_names, rows))
    return Answer(out_names, rows, stages, read, groups, size)
