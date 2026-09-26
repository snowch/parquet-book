"""A simulated object store: the subset of S3's semantics a Parquet reader depends on.

Three operations, because a Parquet reader needs no more:

- ``HEAD`` returns an object's size.
- ``GET`` with ``Range: bytes=a-b`` returns bytes ``a`` to ``b`` inclusive.
- ``GET`` with ``Range: bytes=-n`` returns the last ``n`` bytes, and the response says how large
  the whole object is. A reader can find a footer with no ``HEAD`` at all.

:class:`MemoryStore` holds the objects. :class:`TracingStore` wraps any store, logs every
request, and charges each one a simulated cost from a :class:`NetworkModel`. The trace the
browser shows is this log. Nothing is drawn that a request did not do.

The costs are simulated on purpose. A real network would make every run of the book give
different numbers, and the book's rule is that every number it shows can be reproduced. The
model is deliberately simple: a fixed cost per request plus bytes over bandwidth. That captures
the property that shapes Parquet readers (a request is expensive, a byte is cheap) and nothing
else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .bytes import Span


@dataclass(frozen=True)
class Bounded:
    """``bytes=start-(end-1)``: a span of absolute offsets."""

    span: Span

    def header(self) -> str:
        return self.span.http_range()


@dataclass(frozen=True)
class Suffix:
    """``bytes=-n``: the last ``n`` bytes, whatever the object's size."""

    n: int

    def header(self) -> str:
        return f"bytes=-{self.n}"


@dataclass(frozen=True)
class All:
    """No ``Range`` header: the whole object (ch14)."""

    def header(self) -> str:
        return "the whole object"


GetRange = Bounded | Suffix | All
"""Which bytes a ``GET`` asks for."""


class StoreError(Exception):
    status = 0


class NotFound(StoreError):
    status = 404

    def __init__(self, key: str) -> None:
        super().__init__(f"404: no object named {key}")


class RangeNotSatisfiable(StoreError):
    """HTTP 416: the range starts at or after the end of the object."""

    status = 416

    def __init__(self, key: str, range: str, size: int) -> None:
        super().__init__(f"416: {range} is outside {key}, which is {size} bytes")


@dataclass
class GetResult:
    """The body of a successful ``GET``."""

    data: bytes
    span: Span
    """Which bytes of the object these are: the response's ``Content-Range``."""
    object_size: int
    """The object's total size, which ``Content-Range`` also carries."""


class ObjectStore(Protocol):
    """What a Parquet reader needs from storage.

    ``why`` is not part of any storage protocol. It is instrumentation: the reader says what it
    wants the bytes for, the trace records it, and the browser can then answer "why did the
    reader request these bytes?" from the reader's own words rather than from a caption.
    """

    def head(self, key: str, why: str) -> int: ...

    def get(self, key: str, range: GetRange, why: str) -> GetResult: ...

    def list(self, prefix: str, why: str) -> list[tuple[str, int]]:
        """The keys that start with ``prefix``, in order, with each object's size: S3's
        ``LIST`` (ch14)."""
        ...

    def next_phase(self) -> None:
        """Say that the next request depends on the answers to earlier ones, so it cannot start
        until they have finished. A store that does not model time ignores it."""


class MemoryStore:
    """Objects held in memory: the book's fixtures, embedded in the page or read from disk."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = bytes(data)

    def _object(self, key: str) -> bytes:
        if key not in self.objects:
            raise NotFound(key)
        return self.objects[key]

    def list(self, prefix: str, why: str) -> list[tuple[str, int]]:
        return [(k, len(v)) for k, v in sorted(self.objects.items()) if k.startswith(prefix)]

    def head(self, key: str, why: str) -> int:
        return len(self._object(key))

    def get(self, key: str, range: GetRange, why: str) -> GetResult:
        """Serve a range the way S3 does: a range that runs past the end is cut short rather than
        refused, a suffix longer than the object returns the whole object, and only a range that
        starts at or beyond the end is an error."""
        data = self._object(key)
        size = len(data)
        if isinstance(range, Bounded):
            s = range.span
            if s.start >= size or s.length == 0:
                raise RangeNotSatisfiable(key, range.header(), size)
            span = Span(s.start, min(s.end, size))
        elif isinstance(range, Suffix):
            span = Span(max(size - range.n, 0), size)
        else:
            span = Span(0, size)
        return GetResult(data[span.start : span.end], span, size)

    def next_phase(self) -> None:
        pass


@dataclass(frozen=True)
class NetworkModel:
    """What a request costs: a fixed latency, and the time to move its bytes.

    The defaults are a request that takes a while to start and then moves bytes quickly: the
    shape of object storage over a network. The two numbers are a scenario, not a measurement;
    the browser lets the reader change both.
    """

    latency_us: int = 20_000
    """Time from sending a request to the first byte of the response, in microseconds."""
    bandwidth_bytes_per_sec: int = 100_000_000
    """Bytes per second once the response is flowing. Zero means unlimited."""

    def cost_us(self, nbytes: int) -> int:
        """Microseconds to complete one request that returns ``nbytes`` bytes."""
        bw = self.bandwidth_bytes_per_sec
        transfer = 0 if bw == 0 else -(-nbytes * 1_000_000 // bw)
        return self.latency_us + transfer


@dataclass
class Request:
    """One entry in the trace: a request, what came back, and what it cost."""

    seq: int
    method: str
    key: str
    range: str | None
    """The ``Range`` header, if the request had one."""
    why: str
    status: int
    """200 for a ``HEAD``, 206 for a satisfied range, or the error status."""
    returned: Span | None
    """The bytes that came back, as offsets into the object."""
    bytes_returned: int
    start_us: int
    end_us: int
    connection: int
    """Which connection carried it, from 0."""
    phase: int
    """Which phase it belonged to, from 0."""


class TracingStore:
    """Wraps a store, and records and prices every request that passes through it.

    The store has ``connections`` connections, one by default. A request goes on whichever
    connection is free first, and starts when that connection is free and the current phase has
    begun. With one connection every request starts when the previous one ended. With several,
    requests in the same phase overlap in time (ch10).

    A **phase** is a set of requests that do not depend on each other. A request that needs the
    answer to an earlier one, such as a data read that needs the footer, belongs to a later
    phase: :meth:`next_phase` makes every later request wait for all earlier ones.
    """

    def __init__(self, inner: ObjectStore, model: NetworkModel, connections: int = 1) -> None:
        self.inner, self.model = inner, model
        self.requests: list[Request] = []
        self.free_at = [0] * max(connections, 1)
        """When each connection is next free."""
        self.phase_start = 0
        """No request starts before this: the end of the previous phase."""
        self.phase = 0

    def elapsed_us(self) -> int:
        """Total simulated time: when the last request finished."""
        return max((r.end_us for r in self.requests), default=0)

    def bytes_returned(self) -> int:
        return sum(r.bytes_returned for r in self.requests)

    def _record(self, method, key, range, why, status, returned) -> None:
        nbytes = returned.length if returned else 0
        # The connection that is free first; ties go to the lowest number.
        free, connection = min((t, i) for i, t in enumerate(self.free_at))
        start_us = max(free, self.phase_start)
        end_us = start_us + self.model.cost_us(nbytes)
        self.free_at[connection] = end_us
        self.requests.append(
            Request(
                seq=len(self.requests) + 1,
                method=method,
                key=key,
                range=range,
                why=why,
                status=status,
                returned=returned,
                bytes_returned=nbytes,
                start_us=start_us,
                end_us=end_us,
                connection=connection,
                phase=self.phase,
            )
        )

    def next_phase(self) -> None:
        """Start a new phase: later requests wait until every request so far has finished."""
        self.phase_start = self.elapsed_us()
        self.phase += 1

    def list(self, prefix: str, why: str) -> list[tuple[str, int]]:
        """A ``LIST`` is one request. Its response, a page of keys, is not counted in bytes: the
        model prices the request, not the listing's size."""
        out = self.inner.list(prefix, why)
        self._record("LIST", prefix, None, why, 200, None)
        return out

    def head(self, key: str, why: str) -> int:
        try:
            size = self.inner.head(key, why)
        except StoreError as e:
            self._record("HEAD", key, None, why, e.status, None)
            raise
        self._record("HEAD", key, None, why, 200, None)
        return size

    def get(self, key: str, range: GetRange, why: str) -> GetResult:
        header = None if isinstance(range, All) else range.header()
        try:
            result = self.inner.get(key, range, why)
        except StoreError as e:
            self._record("GET", key, header, why, e.status, None)
            raise
        self._record("GET", key, header, why, 206, result.span)
        return result
