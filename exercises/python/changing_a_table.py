"""ch15's problems. Edit this file; ``tests/test_changing_a_table.py`` grades it."""

from parquet_lab.changes import Snapshot


def files_to_open(snapshot: Snapshot, key: int) -> tuple[list[str], list[str]]:
    """Problem 15.1: which files must a lookup of one ``order_id`` open?

    Return the paths of every data file in ``snapshot`` whose ``order_id`` range, from
    ``min_key`` to ``max_key`` inclusive, holds ``key``, in the snapshot's order; and the paths of
    every delete file that names one of those data files, in the snapshot's order. A data file
    whose range cannot hold the key need not be opened, and neither do the delete files that name
    only such files.
    """
    raise NotImplementedError("problem 15.1")


def plan_compaction(snapshot: Snapshot, target_rows: int, small_rows: int) -> list[list[str]]:
    """Problem 15.2: plan a compaction.

    A data file is rewritten if a delete file names it, or if it holds fewer than ``small_rows``
    live rows: its ``record_count``, less the ``record_count`` of every delete file that names it.
    Take those files in order of their ``min_key``, and pack them into groups: a file joins the
    current group if the group's live rows, with the file's, stay within ``target_rows``, and
    starts a new group otherwise. Drop any group of one file that no delete file names: it would
    be rewritten unchanged. Return each group's data file paths, groups in order.

    ``snapshot.live_rows(f)`` and ``snapshot.deletes_for(path)`` are yours to use.
    """
    raise NotImplementedError("problem 15.2")
