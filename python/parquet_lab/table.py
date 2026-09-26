"""A table of many files: finding them, ruling them out, and querying them together (ch14).

A table is a directory of Parquet files in an object store. Before a query engine can read any
of them it must know which files there are, and it would rather not open the ones that cannot
hold an answer. There are two ways to find out:

- **List the directory.** One ``LIST`` request returns every key under the table's prefix. Files
  laid out in Hive-style partitions carry values in their paths, ``country=UK/part-0.parquet``,
  so a condition on ``country`` rules files out by name. Anything else about a file is in its
  footer, which costs requests to read.
- **Read the table's log.** Table formats such as Delta Lake and Apache Iceberg keep a list of
  the table's files, and with each file its partition values and statistics. One request for the
  log tells the reader which files exist and what each holds, before it opens any.

This module does both, then fetches the files that survive, whole, and runs
:mod:`parquet_lab.engine` over them. It reads only what the log format needs here: ``add`` and
``remove`` actions in one log file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from . import engine
from .encoding import json_text
from .engine import Answer, Source
from .object_store import All, MemoryStore, NetworkModel, Request, TracingStore
from .prune import Op

LOG = "_delta_log/00000000000000000000.json"
"""Where the log is, under the table's prefix. A real log has many versions; this reads one."""


class Discovery(Enum):
    LIST = "list"
    """``LIST``, and read every file."""
    LIST_AND_PRUNE = "list and prune"
    """``LIST``, and rule out files by the partition values in their paths."""
    LOG = "log"
    """Read the log, and rule out files by partition values and by the statistics it records."""


@dataclass
class FileStats:
    """A file's statistics as a log records them: values as JSON, by column."""

    num_records: int
    min: dict[str, object]
    max: dict[str, object]
    null_count: dict[str, int]


@dataclass
class TableFile:
    """One file of the table, and what the plan decided about it."""

    key: str
    partition: list[tuple[str, str]]
    size: int
    stats: FileStats | None
    read: bool = True
    why: str = ""


@dataclass
class TableAnswer:
    answer: Answer
    files: list[TableFile]
    requests: list[Request]
    elapsed_us: int
    bytes_fetched: int


class TableError(ValueError):
    pass


def partition_values(path: str) -> list[tuple[str, str]]:
    """The partition values in a Hive-style path: every ``name=value`` directory, in order.
    Values are percent-encoded when they hold characters a path cannot, such as ``/`` or ``=``."""
    dirs = path.split("/")[:-1]
    return [(unescape(k), unescape(v)) for k, _, v in (d.partition("=") for d in dirs if "=" in d)]


def unescape(s: str) -> str:
    """Percent-decoding by hand: ``%`` and two hex digits is one byte, and anything else is
    kept as it is."""
    b = s.encode()
    out = bytearray()
    i = 0
    while i < len(b):
        pair = b[i + 1 : i + 3]
        if b[i] == ord("%") and len(pair) == 2 and all(chr(x) in "0123456789abcdefABCDEF" for x in pair):
            out.append(int(pair, 16))
            i += 3
        else:
            out.append(b[i])
            i += 1
    return out.decode("utf-8", "replace")


def _json_line(line: str, n: int) -> object:
    try:
        return json.loads(line)
    except ValueError as e:
        raise TableError(f"log line {n}: {e}") from e


def read_log(text: str) -> tuple[list[TableFile], list[str]]:
    """The files a log says the table holds, with their partition values, sizes and statistics,
    and the table's columns from its schema. Each line is one action; ``remove`` undoes an
    ``add``."""
    files: list[TableFile] = []
    columns: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        action = _json_line(line, n)
        if not isinstance(action, dict):
            continue
        meta = action.get("metaData")
        if isinstance(meta, dict):
            schema = meta.get("schemaString")
            try:
                parsed = json.loads(schema if isinstance(schema, str) else "{}")
            except ValueError as e:
                raise TableError(f"the log's schema: {e}") from e
            fields = parsed.get("fields") if isinstance(parsed, dict) else None
            columns = (
                [f["name"] for f in fields if isinstance(f, dict) and isinstance(f.get("name"), str)]
                if isinstance(fields, list)
                else []
            )
        remove = action.get("remove")
        if isinstance(remove, dict):
            path = remove.get("path") if isinstance(remove.get("path"), str) else ""
            files = [f for f in files if f.key != path]
        add = action.get("add")
        if not isinstance(add, dict):
            continue
        key = add.get("path")
        if not isinstance(key, str):
            raise TableError(f"log line {n}: an add with no path")
        values = add.get("partitionValues")
        partition = (
            [(k, v if isinstance(v, str) else "") for k, v in values.items()]
            if isinstance(values, dict)
            else []
        )
        # The statistics are themselves JSON, stored as a string.
        stats = None
        raw = add.get("stats")
        if isinstance(raw, str):
            try:
                stats = _stats(json.loads(raw))
            except ValueError:
                stats = None
        size = add.get("size")
        files.append(TableFile(key, partition, size if type(size) is int and size >= 0 else 0, stats))
    return files, columns


def _stats(s: object) -> FileStats:
    def pairs(k: str) -> dict:
        v = s.get(k) if isinstance(s, dict) else None
        return v if isinstance(v, dict) else {}

    records = s.get("numRecords") if isinstance(s, dict) else None
    return FileStats(
        num_records=records if type(records) is int else 0,
        min=pairs("minValues"),
        max=pairs("maxValues"),
        null_count={k: v if type(v) is int else 0 for k, v in pairs("nullCount").items()},
    )


_INTEGER = re.compile(r"[+-]?[0-9]+")
_FLOAT = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[+-]?(?:inf|infinity|nan)", re.I)


def literal(text: str) -> object:
    """A literal as the engine's value: a number if it reads as one, text otherwise."""
    if _INTEGER.fullmatch(text) and -(2**63) <= int(text) < 2**63:
        return int(text)
    if _FLOAT.fullmatch(text):
        return float(text)
    return text


def _json_value(j: object) -> object:
    if isinstance(j, (list, dict)):
        return None
    return engine.from_json(j)


def _comparable(a: object, b: object) -> bool:
    """Whether a value of one kind can be compared with another: numbers with numbers, text with
    text. A log's statistics are JSON, and a comparison across kinds proves nothing."""

    def number(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    return (number(a) and number(b)) or (isinstance(a, str) and isinstance(b, str))


def rules_out(file: TableFile, c: engine.Condition, use_stats: bool) -> str | None:
    """Why a condition rules a file out, if it does: from its partition values, then from the
    statistics a log records for it."""
    v = literal(c.value)
    p = next((value for k, value in file.partition if k == c.column), None)
    if p is not None:
        if c.op is Op.IS_NULL:
            ok = False
        elif c.op is Op.IS_NOT_NULL:
            ok = True
        else:
            ok = c.op.matches((p.encode() > c.value.encode()) - (p.encode() < c.value.encode()))
        return None if ok else f"its partition is {c.column}={p}"
    s = file.stats
    if not use_stats or s is None:
        return None
    nulls = s.null_count.get(c.column)
    if c.op is Op.IS_NULL:
        return f"the log counts no nulls in {c.column}" if nulls == 0 else None
    if c.op is Op.IS_NOT_NULL:
        return f"the log says {c.column} is always null" if nulls == s.num_records else None
    if c.column not in s.min or c.column not in s.max:
        return None
    low, high = _json_value(s.min[c.column]), _json_value(s.max[c.column])
    if not _comparable(v, low) or not _comparable(v, high):
        return None
    lo, hi = engine.order(v, low), engine.order(v, high)
    out = {
        Op.EQ: lo == -1 or hi == 1,
        Op.NOT_EQ: lo == 0 and hi == 0,
        Op.LT: lo != 1,
        Op.LT_EQ: lo == -1,
        Op.GT: hi != -1,
        Op.GT_EQ: hi == 1,
    }[c.op]
    return f"the log says {c.column} runs from {json_text(low)} to {json_text(high)}" if out else None


def query(
    store: MemoryStore, prefix: str, sql: str, discovery: Discovery, connections: int, model: NetworkModel
) -> TableAnswer:
    """Answer ``sql`` from the table under ``prefix`` in ``store``."""
    q = engine.parse(sql)
    s = TracingStore(store, model, connections)
    if discovery is Discovery.LOG:
        got = s.get(f"{prefix}{LOG}", All(), "read the table's log")
        files, log_columns = read_log(got.data.decode("utf-8", "replace"))
    else:
        keys = s.list(prefix, "list the table's files")
        files = [
            TableFile(k[len(prefix) :], partition_values(k[len(prefix) :]), size, None)
            for k, size in keys
            if k.endswith(".parquet")
        ]
        log_columns = []
    # Rule files out before reading any: by path, and with a log by its statistics too.
    for f in files:
        if discovery is Discovery.LIST:
            f.why = "read: listing gives no reason to skip"
            continue
        found = next(
            ((c, w) for c in q.conditions if (w := rules_out(f, c, discovery is Discovery.LOG)) is not None),
            None,
        )
        if found is not None:
            c, why = found
            f.read = False
            f.why = f"skipped: {c.column} {c.op.symbol} {c.value}, and {why}"
        else:
            f.why = "read: nothing rules it out"
    # Fetch the survivors, whole: they are small, and ch10 found one request best for small files.
    s.next_phase()
    fetched = []
    for f in files:
        if f.read:
            got = s.get(f"{prefix}{f.key}", All(), "read a file the plan kept")
            fetched.append(Source(f.key, got.data, f.partition))
    if not fetched:
        columns = log_columns
        if not columns:
            columns = (
                [i.arg for i in q.items if i.arg is not None] + [c.column for c in q.conditions] + q.group_by
            )
        answer = engine.run_empty(sql, columns, "every file was ruled out before reading")
    else:
        answer = engine.run_sources(fetched, sql)
    return TableAnswer(answer, files, s.requests, s.elapsed_us(), s.bytes_returned())
