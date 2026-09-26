"""Changing a table: finding one row, deleting rows, and compacting (ch15).

Parquet files are written once. A table made of them still changes, and a table format such as
Apache Iceberg or Delta Lake records each version as a *snapshot*: the list of files that make it
up. This module reads a table through its snapshots, and measures what each way of changing it
costs:

- **Finding one row.** A reader opens the files whose statistics could hold the key, then their
  footers, indexes and pages: a chain of requests, each waiting for the last.
- **Deleting a row by copy-on-write.** The file that holds the row is rewritten without it. Reads
  stay as cheap as before; the write costs a whole file.
- **Deleting a row by merge-on-read.** A small *position delete file* names the row's file and
  position. The write is cheap; every later read of that file must fetch the delete file and
  take the row out.
- **Compaction.** Small files and files with deletes are rewritten into a few whole ones, which
  costs a read and a write of everything they hold, and makes later reads cheap again.

The snapshots are a JSON file, ``_snapshots.json``, under the table's prefix. It records for each
data file its row count, its size and the range of its ``order_id`` column, and for each delete
file the data file it names: what an Iceberg manifest records, in the plainest form.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import engine
from .object_store import All, MemoryStore, NetworkModel, Request, TracingStore
from .prune import Mechanisms, Op
from .reader import FooterOptions, Known
from .scan import Query, Strategy, scan_in
from .schema import build, leaves

SNAPSHOTS = "_snapshots.json"
"""Where the snapshots are, under the table's prefix."""

KEY = "order_id"
"""The column the table is keyed on: a lookup finds one value of it."""


class ChangesError(ValueError):
    """A table this module cannot read, with the reader's own message."""


@dataclass
class DataFile:
    path: str
    record_count: int
    file_size: int
    min_key: int
    """The smallest and largest ``order_id`` in the file."""
    max_key: int


@dataclass
class DeleteFile:
    path: str
    record_count: int
    file_size: int
    data_file: str
    """The one data file whose rows it deletes."""


@dataclass
class Snapshot:
    id: str
    summary: str
    data_files: list[DataFile]
    delete_files: list[DeleteFile]

    def deletes_for(self, data_file: str) -> list[DeleteFile]:
        """The delete files that name ``data_file``."""
        return [d for d in self.delete_files if d.data_file == data_file]

    def live_rows(self, f: DataFile) -> int:
        """The rows a data file still holds, by the snapshot's own counts: its records, less the
        positions its delete files name."""
        return f.record_count - sum(d.record_count for d in self.deletes_for(f.path))


def read_snapshots(text: str) -> list[Snapshot]:
    """Every snapshot in a ``_snapshots.json``, oldest first."""
    try:
        j = json.loads(text)
    except ValueError as e:
        raise ChangesError(f"{SNAPSHOTS}: {e}") from e

    def need(v: dict, k: str, kind: type):
        x = v.get(k) if isinstance(v, dict) else None
        if not isinstance(x, kind) or isinstance(x, bool):
            raise ChangesError(f"{SNAPSHOTS}: no {k}")
        return x

    def data_file(f: dict) -> DataFile:
        bounds = f.get(KEY) if isinstance(f.get(KEY), list) else []
        if len(bounds) < 2 or not all(isinstance(b, int) for b in bounds[:2]):
            raise ChangesError(f"{SNAPSHOTS}: a data file with no {KEY} range")
        return DataFile(
            need(f, "path", str),
            need(f, "record_count", int),
            need(f, "file_size", int),
            bounds[0],
            bounds[1],
        )

    def delete_file(f: dict) -> DeleteFile:
        return DeleteFile(
            need(f, "path", str),
            need(f, "record_count", int),
            need(f, "file_size", int),
            need(f, "data_file", str),
        )

    if not isinstance(j, dict) or not isinstance(j.get("snapshots"), list):
        raise ChangesError(f"{SNAPSHOTS}: no snapshots")
    return [
        Snapshot(
            need(s, "id", str),
            need(s, "summary", str),
            [data_file(f) for f in s.get("data_files") or []],
            [delete_file(f) for f in s.get("delete_files") or []],
        )
        for s in j["snapshots"]
    ]


def read_position_deletes(data: bytes) -> list[tuple[str, int]]:
    """The rows of a position delete file: which data file, and which position in it, counting
    from 0. Its columns are ``file_path`` and ``pos``, as Iceberg defines them."""
    out = []
    for row in engine.run(data, "SELECT file_path, pos FROM deletes").rows:
        match row:
            case [str(path), int(pos)] if not isinstance(pos, bool):
                out.append((path, pos))
            case _:
                raise ChangesError("a position delete file holds a path and a position")
    return out


def _find(snapshots: list[Snapshot], id: str) -> Snapshot:
    """The snapshot a table's snapshots file names ``id``."""
    for s in snapshots:
        if s.id == id:
            return s
    raise ChangesError(f"no snapshot {id}")


def open_table(s: TracingStore, prefix: str, id: str) -> Snapshot:
    """Read the snapshots file: the first request of every operation on the table."""
    got = s.get(f"{prefix}{SNAPSHOTS}", All(), "read the table's snapshots")
    return _find(read_snapshots(got.data.decode("utf-8", "replace")), id)


# ---- Reading every row ------------------------------------------------------------------------


@dataclass
class TableScan:
    """A scan of the whole table: ``SELECT count(*), sum(amount_cents)`` over its live rows."""

    snapshot: Snapshot
    rows_decoded: int
    """Rows decoded from the data files, deleted ones included."""
    live_rows: int
    sum_amount_cents: int
    requests: list[Request]
    elapsed_us: int
    bytes_fetched: int


def scan_table(store: MemoryStore, prefix: str, id: str, connections: int, model: NetworkModel) -> TableScan:
    """Read every row of snapshot ``id`` of the table under ``prefix``: the snapshots, then every
    data file and every delete file, whole and all at once, since none depends on another. A data
    file's rows are decoded in order, and the positions its delete files name are left out."""
    s = TracingStore(store, model, connections)
    snapshot = open_table(s, prefix, id)
    s.next_phase()

    def fetch(key: str, why: str) -> bytes:
        return s.get(f"{prefix}{key}", All(), why).data

    deleted: set[tuple[str, int]] = set()
    for d in snapshot.delete_files:
        deleted.update(read_position_deletes(fetch(d.path, "read a delete file")))
    rows_decoded = live_rows = total = 0
    for f in snapshot.data_files:
        amounts = engine.run(fetch(f.path, "read a data file"), "SELECT amount_cents FROM orders").rows
        for pos, row in enumerate(amounts):
            rows_decoded += 1
            if (f.path, pos) in deleted:
                continue  # a delete file names this row: it is no longer in the table
            live_rows += 1
            if isinstance(row[0], int):
                total += row[0]
    return TableScan(snapshot, rows_decoded, live_rows, total, s.requests, s.elapsed_us(), s.bytes_returned())


# ---- Finding one row --------------------------------------------------------------------------


@dataclass
class Lookup:
    """A lookup of one ``order_id``, and what it cost."""

    snapshot: Snapshot
    key: int
    data_files: list[str]
    """The data files whose ``order_id`` range holds the key, and the delete files naming them."""
    delete_files: list[str]
    found: tuple[str, int] | None
    """Where the key was found: the file and the position in it."""
    deleted_by: str | None
    """The delete file that removes the row found, if one does."""
    row: list[tuple[str, object]] = field(default_factory=list)
    """The row, column by column, when it is found and not deleted."""
    rows_decoded: int = 0
    requests: list[Request] = field(default_factory=list)
    elapsed_us: int = 0
    bytes_fetched: int = 0


def files_to_open(snapshot: Snapshot, key: int) -> tuple[list[DataFile], list[DeleteFile]]:
    """The files a lookup of ``key`` must open: every data file whose ``order_id`` range holds
    it, and every delete file that names one of those."""
    data = [f for f in snapshot.data_files if f.min_key <= key <= f.max_key]
    deletes = [d for d in snapshot.delete_files if any(f.path == d.data_file for f in data)]
    return data, deletes


def lookup(
    store: MemoryStore, prefix: str, id: str, key: int, prefetch: int, connections: int, model: NetworkModel
) -> Lookup:
    """Find the row whose ``order_id`` is ``key`` in snapshot ``id``. After the snapshots, the
    delete files that could remove it are fetched while the data file is opened, since neither
    depends on the other; then the data file is read as ch10's scan reads any file, with
    statistics and the page index, ``prefetch`` bytes of its tail in the first request."""
    from .report import open_bytes

    s = TracingStore(store, model, connections)
    snapshot = open_table(s, prefix, id)
    data, deletes = files_to_open(snapshot, key)
    s.next_phase()
    deleted: list[tuple[str, int, str]] = []
    for d in deletes:
        got = s.get(f"{prefix}{d.path}", All(), "read a delete file that names a file the key may be in")
        deleted += [(path, pos, d.path) for path, pos in read_position_deletes(got.data)]
    found = deleted_by = None
    row: list[tuple[str, object]] = []
    rows_decoded = 0
    for f in data:
        key_path = f"{prefix}{f.path}"
        data_bytes = store.get(key_path, All(), "").data
        flat = leaves(build(open_bytes(data_bytes).schema))
        column = next((leaf.column for leaf in flat if leaf.dotted_path() == KEY), None)
        if column is None:
            raise ChangesError(f"{f.path}: no column {KEY}")
        query = Query([leaf.column for leaf in flat], (column, Op.EQ, str(key)))
        strategy = Strategy(
            footer=FooterOptions(Known(f.file_size), prefetch),
            connections=connections,
            coalesce_gap=0,
            whole_chunks=False,
            mechanisms=Mechanisms(statistics=True, bloom=False, page_index=True),
        )
        r = scan_in(s, data_bytes, key_path, query, strategy)
        rows_decoded += r.rows_decoded
        if r.matches:
            pos = r.matches[0]
            found = (f.path, pos)
            deleted_by = next((by for p, n, by in deleted if p == f.path and n == pos), None)
            if deleted_by is None:
                row = list(zip(r.column_names, r.rows[0], strict=True))
            break
        s.next_phase()
    return Lookup(
        snapshot,
        key,
        [f.path for f in data],
        [d.path for d in deletes],
        found,
        deleted_by,
        row,
        rows_decoded,
        s.requests,
        s.elapsed_us(),
        s.bytes_returned(),
    )


# ---- Compaction -------------------------------------------------------------------------------


@dataclass
class Group:
    """Data files rewritten together into one, with the delete files they no longer need."""

    data_files: list[str]
    delete_files: list[str]
    rows_in: int
    rows_out: int
    bytes_in: int
    """What the rewrite must read: every data file and delete file in the group."""


def plan_compaction(snapshot: Snapshot, target_rows: int, small_rows: int) -> list[Group]:
    """Plan a compaction of ``snapshot``. A data file is rewritten if it has deletes, or if it
    holds fewer than ``small_rows`` live rows. In order of their smallest ``order_id``, those
    files are packed into groups: a file joins the current group if the group's live rows stay
    within ``target_rows``, and starts a new group otherwise. A group of one file with no deletes
    would be rewritten unchanged, so it is dropped. Files that are neither small nor deleted from
    are left as they are."""
    candidates = [
        f for f in snapshot.data_files if snapshot.deletes_for(f.path) or snapshot.live_rows(f) < small_rows
    ]
    candidates.sort(key=lambda f: f.min_key)
    groups: list[list[DataFile]] = []
    rows = 0
    for f in candidates:
        live = snapshot.live_rows(f)
        if groups and rows + live <= target_rows:
            groups[-1].append(f)
            rows += live
        else:
            groups.append([f])
            rows = live
    out = []
    for g in groups:
        if len(g) == 1 and not snapshot.deletes_for(g[0].path):
            continue
        deletes = [d for f in g for d in snapshot.deletes_for(f.path)]
        out.append(
            Group(
                [f.path for f in g],
                [d.path for d in deletes],
                sum(f.record_count for f in g),
                sum(snapshot.live_rows(f) for f in g),
                sum(f.file_size for f in g) + sum(d.file_size for d in deletes),
            )
        )
    return out


@dataclass
class CompactionCost:
    """What a compaction cost, from the snapshot before it and the snapshot it wrote."""

    outputs: list[tuple[str, int]]
    """The files the compaction wrote: in ``after`` and not in ``before``."""
    bytes_read: int
    bytes_written: int
    elapsed_us: int
    """Every input read, then every output written, one request each over one connection, a write
    priced as a read of the same size."""


def compaction_cost(
    before: Snapshot, after: Snapshot, plan: list[Group], model: NetworkModel
) -> CompactionCost:
    """The cost of carrying out ``plan``, which turned ``before`` into ``after``. Fails if the
    files ``after`` dropped are not the ones the plan rewrites, or if the rows do not add up."""
    kept = {a.path for a in after.data_files}
    dropped = sorted(f.path for f in before.data_files if f.path not in kept)
    planned = sorted(p for g in plan for p in g.data_files)
    if dropped != planned:
        raise ChangesError(
            f"snapshot {after.id} replaced {', '.join(dropped)}, but the plan rewrites {', '.join(planned)}"
        )
    old = {f.path for f in before.data_files}
    outputs = [(a.path, a.file_size) for a in after.data_files if a.path not in old]
    rows_out = sum(a.record_count for a in after.data_files if a.path not in old)
    if rows_out != sum(g.rows_out for g in plan):
        raise ChangesError(
            f"the plan keeps {sum(g.rows_out for g in plan)} rows, but snapshot {after.id} wrote {rows_out}"
        )
    sizes = {f.path: f.file_size for f in before.data_files} | {
        d.path: d.file_size for d in before.delete_files
    }
    reads = [sizes.get(p, 0) for g in plan for p in g.data_files + g.delete_files]
    elapsed = sum(model.cost_us(b) for b in reads) + sum(model.cost_us(b) for _, b in outputs)
    return CompactionCost(outputs, sum(reads), sum(b for _, b in outputs), elapsed)
