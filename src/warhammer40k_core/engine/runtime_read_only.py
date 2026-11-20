from __future__ import annotations

import marshal
import pickle
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from io import BytesIO
from operator import attrgetter
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


type _ReducerResult = tuple[Callable[..., object], tuple[object, ...], object]
type _Reducer = Callable[[object], _ReducerResult]


class _SnapshotReducers(dict[type[object], _Reducer]):
    def __missing__(self, kind: type[object]) -> _Reducer:
        if issubclass(kind, str):
            # Ordinary strings take pickle's fast path. String subclasses
            # carry their live Python type even when declared in a function.
            def reduce_string(value: object) -> _ReducerResult:
                assert isinstance(value, str)
                return tuple, ((id(kind), str.__str__(value)),), None

            self[kind] = reduce_string
            return reduce_string

        if not is_dataclass(kind) or "__slots__" not in vars(kind):
            raise KeyError(kind)
        names = tuple(member.name for member in fields(kind))
        if not names:
            raise KeyError(kind)
        read_fields = attrgetter(*names)

        def reduce_slots(value: object) -> _ReducerResult:
            return kind, (), read_fields(value)

        self[kind] = reduce_slots
        return reduce_slots


def _typed_snapshot(value: object, reducers: _SnapshotReducers) -> bytes:
    output = BytesIO()
    encoder = pickle.Pickler(output, protocol=pickle.HIGHEST_PROTOCOL)
    encoder.dispatch_table = reducers
    encoder.dump(value)
    return output.getvalue()


@dataclass(frozen=True, slots=True, eq=False)
class RuntimeReadOnlySnapshot:
    runtime_values: bytes
    event_values: tuple[bool, bytes]
    occurrences: tuple[tuple[object, ...], ...]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RuntimeReadOnlySnapshot):
            return NotImplemented
        return (
            self.runtime_values == other.runtime_values
            and self.event_values == other.event_values
            and all(
                len(before) == len(after)
                and all(left is right for left, right in zip(before, after, strict=True))
                for before, after in zip(self.occurrences, other.occurrences, strict=True)
            )
        )


def runtime_read_only_snapshot(
    state: GameState, decisions: DecisionController, *additional_inputs: object
) -> RuntimeReadOnlySnapshot:
    """Capture exact runtime values and retain the authoritative ledger occurrences.

    The byte snapshots are only compared in memory and are never loaded. Pickle
    preserves runtime types such as enums and list/tuple distinctions. Encoding
    the flat event values separately avoids pickling the large JSON history.
    """
    queue = decisions.queue
    log = decisions.event_log
    # Keep the actual containers, so changing a private ledger list into an
    # equal-looking tuple also changes the snapshot.
    records = decisions._records  # pyright: ignore[reportPrivateUsage]
    event_records = log._records  # pyright: ignore[reportPrivateUsage]
    if any(type(event) is not EventRecord for event in event_records):
        raise GameLifecycleError("Read-only runtime history requires typed events.")
    reducers = _SnapshotReducers()
    runtime_values = _typed_snapshot(
        (state, type(decisions), queue, records, type(log), additional_inputs),
        reducers,
    )
    flat_events = (
        type(event_records) is list,
        tuple((event.event_id, event.event_type, event.payload) for event in event_records),
    )
    try:
        # Version 2 omits reference tracking for these JSON values.
        event_values = (False, marshal.dumps(flat_events, 2, allow_code=False))
    except ValueError:
        # Marshal accepts builtin values. A valid JSON string subclass still
        # has an exact representation via the typed runtime encoder.
        event_values = (True, _typed_snapshot(flat_events, reducers))
    return RuntimeReadOnlySnapshot(
        runtime_values,
        event_values,
        (
            (state, decisions, queue, log, *additional_inputs),
            queue.pending_requests,
            tuple(records),
            tuple(event_records),
            tuple(reducers),
        ),
    )
