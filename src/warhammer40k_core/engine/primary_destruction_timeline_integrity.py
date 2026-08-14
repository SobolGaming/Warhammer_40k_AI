from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, cast

from warhammer40k_core.core.ruleset_descriptor import ReserveDestructionTimingKind
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
)
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState
from warhammer40k_core.engine.unit_destroyed_hooks import (
    model_restoration_events_for_event_log_interval,
    unit_destruction_completion_events_from_starting_presence,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class _DestroyedDepartureSource(Protocol):
    @property
    def completion_key(self) -> str: ...

    @property
    def event_order(self) -> int: ...


class _ScoringRulesUnitIdentity(Protocol):
    @property
    def rules_unit_instance_id(self) -> str: ...

    @property
    def owner_player_id(self) -> str: ...

    @property
    def component_unit_instance_ids(self) -> tuple[str, ...]: ...

    @property
    def starting_model_instance_ids_by_component(
        self,
    ) -> tuple[tuple[str, tuple[str, ...]], ...]: ...

    @property
    def starting_model_instance_ids(self) -> tuple[str, ...]: ...


type _TimelineOrder = tuple[int, int]
type _TransitionRow = tuple[_TimelineOrder, str, dict[str, JsonValue], str]
type _RestorationRow = tuple[_TimelineOrder, str, tuple[str, ...]]


def validate_full_destruction_transition_timeline(
    *,
    state: GameState,
    destructions: tuple[PrimaryUnitDestructionState, ...],
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    departure_sources: Mapping[str, _DestroyedDepartureSource],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    identities_by_id: Mapping[str, _ScoringRulesUnitIdentity],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Replay every historical death/restoration from battle-start presence."""
    event_log = EventLog.from_payload([record.to_payload() for record in event_records])
    raw_restorations = model_restoration_events_for_event_log_interval(
        state=state,
        event_log=event_log,
        start_order_exclusive=-1,
        decision_records=decision_records,
    )
    restorations = _restorations_with_transition_order(
        raw_restorations=raw_restorations,
    )
    transition_rows: list[_TransitionRow] = []
    rows_by_event_order: dict[int, list[tuple[PrimaryBattlefieldDepartureState, str]]] = {}
    for departure in departures:
        if departure.removal_kind is not BattlefieldRemovalKind.DESTROYED:
            continue
        source = departure_sources.get(departure.departure_id)
        if source is None:
            raise GameLifecycleError(
                "Primary destroyed departure lacks validated source provenance."
            )
        for model_id in departure.removed_model_instance_ids:
            rows_by_event_order.setdefault(source.event_order, []).append((departure, model_id))
    for event_order, rows in rows_by_event_order.items():
        for offset, (departure, model_id) in enumerate(
            sorted(rows, key=lambda value: (value[0].departure_id, value[1])),
            start=1,
        ):
            transition_id = f"primary-transition:{departure.departure_id}:{model_id}"
            transition_rows.append(
                (
                    (event_order, offset),
                    transition_id,
                    {
                        "game_id": state.game_id,
                        "model_instance_id": model_id,
                        "target_unit_instance_id": departure.rules_unit_instance_id,
                    },
                    departure_sources[departure.departure_id].completion_key,
                )
            )

    reserve_rows = _validated_reserve_deadline_transition_rows(
        state=state,
        destructions=destructions,
        identities_by_id=identities_by_id,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        prior_transition_rows=tuple(transition_rows),
        restorations=restorations,
    )
    transition_rows.extend(reserve_rows)
    transition_rows.sort(key=lambda value: value[0])
    if len({row[0] for row in transition_rows}) != len(transition_rows):
        raise GameLifecycleError("Primary destruction transition ordering is ambiguous.")
    completion_key_by_transition_id = {row[1]: row[3] for row in transition_rows}
    if len(completion_key_by_transition_id) != len(transition_rows):
        raise GameLifecycleError("Primary destruction transition IDs must be unique.")
    model_destroyed_events, model_restoration_events = _completion_timeline_inputs(
        transition_rows=tuple(transition_rows),
        restorations=restorations,
    )
    completions = unit_destruction_completion_events_from_starting_presence(
        state=state,
        model_destroyed_events=model_destroyed_events,
        model_restoration_events=model_restoration_events,
    )
    observed = tuple(
        sorted(
            (
                cast(str, payload["target_unit_instance_id"]),
                completion_key_by_transition_id[transition_id],
            )
            for _order, transition_id, payload in completions
        )
    )
    expected = tuple(
        sorted(
            (
                destruction.destroyed_unit_instance_id,
                _destruction_completion_key(destruction),
            )
            for destruction in destructions
        )
    )
    if observed != expected:
        raise GameLifecycleError(
            "Primary destruction occurrences drifted from the authoritative transition timeline."
        )


def _validated_reserve_deadline_transition_rows(
    *,
    state: GameState,
    destructions: tuple[PrimaryUnitDestructionState, ...],
    identities_by_id: Mapping[str, _ScoringRulesUnitIdentity],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    prior_transition_rows: tuple[_TransitionRow, ...],
    restorations: tuple[_RestorationRow, ...],
) -> list[_TransitionRow]:
    from warhammer40k_core.engine.reserves import ReserveState, ReserveStatus

    destruction_event_order_by_id = _recorded_destruction_event_order_by_id(
        event_records=event_records
    )
    component_by_model_id = {
        model.model_instance_id: unit.unit_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    reserve_rows: list[_TransitionRow] = []
    for destruction in destructions:
        if destruction.unattributed_cause is not (
            PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
        ):
            continue
        identity = identities_by_id[destruction.destroyed_unit_instance_id]
        mutation_id = destruction.source_mutation_id
        if mutation_id is None or destruction.source_id != (
            f"{mutation_id}:{identity.rules_unit_instance_id}"
        ):
            raise GameLifecycleError("Reserve-deadline Primary destruction source drift.")
        candidates: list[ReserveState] = []
        for reserve_state in state.reserve_states:
            policy = reserve_state.destruction_deadline_policy
            boundary_kind = (
                "end-of-battle"
                if policy.timing_kind is ReserveDestructionTimingKind.END_OF_BATTLE
                else "round-boundary"
            )
            expected_mutation_id = (
                f"{policy.source_id}:round-{destruction.battle_round:02d}:{boundary_kind}"
            )
            route_components = set(
                _reserve_route_component_ids(
                    unit_instance_id=reserve_state.unit_instance_id,
                    embarked_unit_instance_ids=reserve_state.embarked_unit_instance_ids,
                    identities_by_id=identities_by_id,
                )
            )
            if (
                expected_mutation_id == mutation_id
                and reserve_state.status is ReserveStatus.DESTROYED
                and reserve_state.destroyed_battle_round == destruction.battle_round
                and reserve_state.player_id == destruction.destroyed_player_id
                and set(identity.component_unit_instance_ids) <= route_components
                and (
                    policy.timing_kind is ReserveDestructionTimingKind.END_OF_BATTLE
                    or policy.battle_round == destruction.battle_round
                )
            ):
                candidates.append(reserve_state)
        if len(candidates) != 1:
            raise GameLifecycleError(
                "Reserve-deadline Primary destruction requires one destroyed ReserveState route."
            )
        event_order = destruction_event_order_by_id.get(destruction.destruction_id)
        if event_order is None:
            raise GameLifecycleError(
                "Reserve-deadline Primary destruction lacks a recorded boundary event."
            )
        # Only models still present in the logical lineage can transition at the
        # reserve deadline. Earlier exact departures remain historical casualties.
        alive_model_ids = _alive_model_ids_before_order(
            starting_model_ids=identity.starting_model_instance_ids,
            transition_rows=prior_transition_rows,
            restorations=restorations,
            before_order=(event_order, 0),
        )
        if not alive_model_ids:
            raise GameLifecycleError(
                "Reserve-deadline Primary destruction has no living starting models."
            )
        for offset, model_id in enumerate(sorted(alive_model_ids), start=1):
            component_id = component_by_model_id.get(model_id)
            if component_id is None or component_id not in identity.component_unit_instance_ids:
                raise GameLifecycleError(
                    "Reserve-deadline Primary destruction model lineage drift."
                )
            transition_id = f"primary-reserve-transition:{destruction.destruction_id}:{model_id}"
            reserve_rows.append(
                (
                    (event_order, offset),
                    transition_id,
                    {
                        "game_id": state.game_id,
                        "model_instance_id": model_id,
                        "target_unit_instance_id": identity.rules_unit_instance_id,
                    },
                    f"reserve-deadline:{mutation_id}",
                )
            )
    return reserve_rows


def _restorations_with_transition_order(
    *,
    raw_restorations: tuple[tuple[int, str, tuple[str, ...]], ...],
) -> tuple[_RestorationRow, ...]:
    """Represent restoration records in the shared structured timeline order."""
    return tuple(
        ((event_order, 0), event_id, model_ids)
        for event_order, event_id, model_ids in raw_restorations
    )


def _completion_timeline_inputs(
    *,
    transition_rows: tuple[_TransitionRow, ...],
    restorations: tuple[_RestorationRow, ...],
) -> tuple[
    tuple[tuple[int, str, dict[str, JsonValue]], ...],
    tuple[tuple[int, str, tuple[str, ...]], ...],
]:
    """Assign dense integer ranks only at the completion-helper boundary."""
    timeline_orders = tuple(row[0] for row in transition_rows) + tuple(
        restoration[0] for restoration in restorations
    )
    if len(set(timeline_orders)) != len(timeline_orders):
        raise GameLifecycleError("Primary destruction transition ordering is ambiguous.")
    rank_by_order = {
        timeline_order: rank for rank, timeline_order in enumerate(sorted(timeline_orders))
    }
    return (
        tuple(
            (rank_by_order[order], transition_id, payload)
            for order, transition_id, payload, _completion_key in sorted(
                transition_rows,
                key=lambda row: row[0],
            )
        ),
        tuple(
            (rank_by_order[order], event_id, model_ids)
            for order, event_id, model_ids in sorted(
                restorations,
                key=lambda row: row[0],
            )
        ),
    )


def _alive_model_ids_before_order(
    *,
    starting_model_ids: tuple[str, ...],
    transition_rows: tuple[_TransitionRow, ...],
    restorations: tuple[_RestorationRow, ...],
    before_order: _TimelineOrder,
) -> tuple[str, ...]:
    alive = dict.fromkeys(starting_model_ids, True)
    timeline: list[tuple[_TimelineOrder, str, tuple[str, ...]]] = [
        (
            order,
            "destroyed",
            (cast(str, payload["model_instance_id"]),),
        )
        for order, _transition_id, payload, _completion_key in transition_rows
        if order < before_order
    ]
    timeline.extend(
        (event_order, "restored", model_ids)
        for event_order, _event_id, model_ids in restorations
        if event_order < before_order
    )
    for _order, kind, model_ids in sorted(timeline, key=lambda value: value[0]):
        for model_id in model_ids:
            if model_id not in alive:
                continue
            if kind == "destroyed":
                if not alive[model_id]:
                    raise GameLifecycleError(
                        "Primary destruction transition repeats an absent model."
                    )
                alive[model_id] = False
            else:
                if alive[model_id]:
                    raise GameLifecycleError(
                        "Primary restoration transition repeats a present model."
                    )
                alive[model_id] = True
    return tuple(model_id for model_id, is_alive in alive.items() if is_alive)


def _reserve_route_component_ids(
    *,
    unit_instance_id: str,
    embarked_unit_instance_ids: tuple[str, ...],
    identities_by_id: Mapping[str, _ScoringRulesUnitIdentity],
) -> tuple[str, ...]:
    route_ids: set[str] = set()
    for unit_id in (unit_instance_id, *embarked_unit_instance_ids):
        identity = identities_by_id.get(unit_id)
        if identity is None:
            route_ids.add(unit_id)
        else:
            route_ids.update(identity.component_unit_instance_ids)
    return tuple(sorted(route_ids))


def _recorded_destruction_event_order_by_id(
    *,
    event_records: tuple[EventRecord, ...],
) -> dict[str, int]:
    orders: dict[str, int] = {}
    for index, record in enumerate(event_records):
        if record.event_type != PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT:
            continue
        payload = _event_payload(record, event_name="primary_unit_destruction_recorded")
        raw_state = payload.get("primary_unit_destruction_state")
        if not isinstance(raw_state, dict):
            raise GameLifecycleError("Primary destruction recorded event state is malformed.")
        destruction_id = raw_state.get("destruction_id")
        if type(destruction_id) is not str or destruction_id in orders:
            raise GameLifecycleError("Primary destruction recorded event identity is ambiguous.")
        orders[destruction_id] = index
    return orders


def _destruction_completion_key(destruction: PrimaryUnitDestructionState) -> str:
    if destruction.destruction_attribution is not None:
        event_id = destruction.source_model_destroyed_event_id
        if event_id is None:
            raise GameLifecycleError("Attributed Primary destruction lacks a completion event ID.")
        return f"model-destroyed:{event_id}"
    mutation_id = destruction.source_mutation_id
    cause = destruction.unattributed_cause
    if mutation_id is None or cause is None:
        raise GameLifecycleError("Unattributed Primary destruction lacks mutation provenance.")
    if cause is PrimaryUnattributedDestructionCause.DESPERATE_ESCAPE:
        expected_source = f"core-rules:desperate-escape:{mutation_id}"
        completion_key = f"desperate-escape:{mutation_id}"
    elif cause is PrimaryUnattributedDestructionCause.EMERGENCY_DISEMBARK:
        expected_source = f"core-rules:emergency-disembark:{mutation_id}"
        completion_key = f"emergency-disembark:{mutation_id}"
    elif cause is PrimaryUnattributedDestructionCause.UNIT_COHERENCY:
        expected_source = mutation_id
        completion_key = f"unit-coherency:{mutation_id}"
    else:
        expected_source = mutation_id
        completion_key = f"reserve-deadline:{mutation_id}"
    if destruction.source_id != (f"{expected_source}:{destruction.destroyed_unit_instance_id}"):
        raise GameLifecycleError("Unattributed Primary destruction source identity drift.")
    return completion_key


def _event_payload(record: EventRecord, *, event_name: str) -> dict[str, JsonValue]:
    if not isinstance(record.payload, dict):
        raise GameLifecycleError(f"{event_name} event payload must be an object.")
    return record.payload


__all__ = ("validate_full_destruction_transition_timeline",)
