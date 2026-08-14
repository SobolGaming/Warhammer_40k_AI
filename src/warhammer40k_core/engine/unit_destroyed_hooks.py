from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.healing import HealingStep


type UnitDestroyedHandler = Callable[["UnitDestroyedContext"], None]
type ModelDestroyedEvent = tuple[int, str, dict[str, JsonValue]]
type ModelRestorationEvent = tuple[int, str, tuple[str, ...]]


ATTACHED_UNIT_DESTRUCTION_SOURCE_RULE_ID = (
    "gw-11e-core-rules:eng-01-06-new40k-core-rules:19.02-attached-units"
)
ATTACHED_UNIT_DESTRUCTION_SOURCE_SHA256 = (
    "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833"
)


@dataclass(frozen=True, slots=True)
class UnitDestroyedContext:
    state: GameState
    decisions: DecisionController
    completed_phase: BattlePhase
    model_destroyed_event_id: str
    model_destroyed_payload: dict[str, JsonValue]
    destroying_player_id: str
    destroyed_unit_instance_id: str
    destroyed_player_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("UnitDestroyedContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("UnitDestroyedContext decisions must be DecisionController.")
        object.__setattr__(self, "completed_phase", _battle_phase_from_token(self.completed_phase))
        object.__setattr__(
            self,
            "model_destroyed_event_id",
            _validate_identifier("model_destroyed_event_id", self.model_destroyed_event_id),
        )
        payload = validate_json_value(self.model_destroyed_payload)
        if not isinstance(payload, dict):
            raise GameLifecycleError("UnitDestroyedContext model_destroyed_payload must be object.")
        object.__setattr__(self, "model_destroyed_payload", payload)
        object.__setattr__(
            self,
            "destroying_player_id",
            _validate_identifier("destroying_player_id", self.destroying_player_id),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier("destroyed_unit_instance_id", self.destroyed_unit_instance_id),
        )
        object.__setattr__(
            self,
            "destroyed_player_id",
            _validate_identifier("destroyed_player_id", self.destroyed_player_id),
        )
        if self.destroying_player_id == self.destroyed_player_id:
            raise GameLifecycleError("UnitDestroyedContext requires enemy destruction.")


@dataclass(frozen=True, slots=True)
class UnitDestroyedHookBinding:
    hook_id: str
    source_id: str
    handler: UnitDestroyedHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("UnitDestroyedHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class UnitDestroyedHookRegistry:
    bindings: tuple[UnitDestroyedHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[UnitDestroyedHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[UnitDestroyedHookBinding, ...]:
        return self.bindings

    def resolve(self, context: UnitDestroyedContext) -> None:
        if type(context) is not UnitDestroyedContext:
            raise GameLifecycleError("Unit-destroyed hooks require context.")
        for binding in self.bindings:
            binding.handler(context)


def unit_destruction_completion_events_for_phase(
    *,
    state: GameState,
    event_log: EventLog,
    completed_phase: BattlePhase,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    """Return canonical rules-unit completions for unit-destroyed rules.

    Component completions remain available through
    ``component_destruction_completion_events_for_phase`` for exact departure
    evidence.  A unit that started the battle Attached completes only when its
    final frozen starting model is destroyed (Core Rules 19.02, official source
    identified by ``ATTACHED_UNIT_DESTRUCTION_SOURCE_SHA256``).
    """
    phase_events = model_destroyed_events_for_lifecycle_phase(
        state=state,
        event_log=event_log,
        completed_phase=completed_phase,
    )
    phase_restorations = model_restoration_events_for_event_log_interval(
        state=state,
        event_log=event_log,
        start_order_exclusive=_last_completed_phase_event_order(event_log),
    )
    return tuple(
        (event_id, payload)
        for _order, event_id, payload in unit_destruction_completion_events_for_interval(
            state=state,
            model_destroyed_events=phase_events,
            model_restoration_events=phase_restorations,
        )
    )


def unit_destruction_completion_events_for_interval(
    *,
    state: GameState,
    model_destroyed_events: tuple[ModelDestroyedEvent, ...],
    model_restoration_events: tuple[ModelRestorationEvent, ...] = (),
) -> tuple[ModelDestroyedEvent, ...]:
    """Return every chronological alive-to-destroyed logical transition.

    Restoration evidence is part of the interval grammar: a unit destroyed, set
    back up, and destroyed again produces two occurrences, while a model revived
    before the rest of its unit dies prevents a false completion.
    """
    events = _validate_model_destroyed_event_interval(
        state=state,
        model_destroyed_events=model_destroyed_events,
    )
    restorations = _validate_model_restoration_event_interval(
        state=state,
        model_restoration_events=model_restoration_events,
    )
    return _destruction_completion_records_by_identity(
        state=state,
        model_destroyed_events=events,
        model_restoration_events=restorations,
        completion_model_ids_by_identity=_logical_completion_model_ids_by_unit(state),
    )


def unit_destruction_completion_events_from_starting_presence(
    *,
    state: GameState,
    model_destroyed_events: tuple[ModelDestroyedEvent, ...],
    model_restoration_events: tuple[ModelRestorationEvent, ...] = (),
) -> tuple[ModelDestroyedEvent, ...]:
    """Return full-game logical completions from frozen battle-start presence.

    Historical restore validation has the whole authoritative transition stream,
    so it must not infer the stream's initial state from the final battlefield.
    Every frozen starting model begins present; destruction transitions require a
    present model and restoration transitions require an absent model.
    """
    events = _validate_model_destroyed_event_interval(
        state=state,
        model_destroyed_events=model_destroyed_events,
    )
    restorations = _validate_model_restoration_event_interval(
        state=state,
        model_restoration_events=model_restoration_events,
    )
    return _destruction_completion_records_by_identity(
        state=state,
        model_destroyed_events=events,
        model_restoration_events=restorations,
        completion_model_ids_by_identity=_logical_completion_model_ids_by_unit(state),
        starts_with_all_models_alive=True,
    )


def component_destruction_completion_events_for_phase(
    *,
    state: GameState,
    event_log: EventLog,
    completed_phase: BattlePhase,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    """Return exact component completions used by battlefield-departure evidence.

    Starting Attached components use their frozen battle-start model IDs.  This
    deliberately ignores later materialized models without claiming that the
    surviving current component left the battlefield.
    """
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Unit-destruction completion lookup requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Unit-destruction completion lookup requires EventLog.")
    phase = _battle_phase_from_token(completed_phase)
    if state.battlefield_state is None:
        return ()
    phase_events = model_destroyed_events_for_lifecycle_phase(
        state=state,
        event_log=event_log,
        completed_phase=phase,
    )
    phase_restorations = model_restoration_events_for_event_log_interval(
        state=state,
        event_log=event_log,
        start_order_exclusive=_last_completed_phase_event_order(event_log),
    )
    completion_records = _component_destruction_completion_records(
        state=state,
        model_destroyed_events=phase_events,
        model_restoration_events=phase_restorations,
    )
    return tuple((event_id, payload) for _order, event_id, payload in completion_records)


def physical_component_destruction_completion_events_for_phase(
    *,
    state: GameState,
    event_log: EventLog,
    completed_phase: BattlePhase,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    """Return each transition on which a current physical component is empty."""
    phase = _battle_phase_from_token(completed_phase)
    phase_events = model_destroyed_events_for_lifecycle_phase(
        state=state,
        event_log=event_log,
        completed_phase=phase,
    )
    phase_restorations = model_restoration_events_for_event_log_interval(
        state=state,
        event_log=event_log,
        start_order_exclusive=_last_completed_phase_event_order(event_log),
    )
    completion_records = _destruction_completion_records_by_identity(
        state=state,
        model_destroyed_events=phase_events,
        model_restoration_events=phase_restorations,
        completion_model_ids_by_identity={
            unit.unit_instance_id: unit.own_model_ids()
            for army in state.army_definitions
            for unit in army.units
        },
    )
    return tuple((event_id, payload) for _order, event_id, payload in completion_records)


def _component_destruction_completion_records(
    *,
    state: GameState,
    model_destroyed_events: tuple[ModelDestroyedEvent, ...],
    model_restoration_events: tuple[ModelRestorationEvent, ...] = (),
) -> tuple[ModelDestroyedEvent, ...]:
    return _destruction_completion_records_by_identity(
        state=state,
        model_destroyed_events=model_destroyed_events,
        model_restoration_events=model_restoration_events,
        completion_model_ids_by_identity=_component_completion_model_ids_by_unit(state),
    )


def _logical_completion_model_ids_by_unit(state: GameState) -> dict[str, tuple[str, ...]]:
    historical_by_component = {
        component_id: record
        for record in state.starting_attached_unit_records
        for component_id in record.component_unit_instance_ids
    }
    completion_ids = {
        record.attached_unit_instance_id: record.starting_model_instance_ids()
        for record in state.starting_attached_unit_records
    }
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id in historical_by_component:
                continue
            completion_ids[unit.unit_instance_id] = unit.own_model_ids()
    return completion_ids


def _component_completion_model_ids_by_unit(state: GameState) -> dict[str, tuple[str, ...]]:
    historical_by_component = {
        component_id: record
        for record in state.starting_attached_unit_records
        for component_id in record.component_unit_instance_ids
    }
    completion_ids: dict[str, tuple[str, ...]] = {}
    for army in state.army_definitions:
        for unit in army.units:
            historical = historical_by_component.get(unit.unit_instance_id)
            completion_ids[unit.unit_instance_id] = (
                unit.own_model_ids()
                if historical is None
                else historical.starting_model_instance_ids_for_component(unit.unit_instance_id)
            )
    return completion_ids


def _destruction_completion_records_by_identity(
    *,
    state: GameState,
    model_destroyed_events: tuple[ModelDestroyedEvent, ...],
    model_restoration_events: tuple[ModelRestorationEvent, ...],
    completion_model_ids_by_identity: dict[str, tuple[str, ...]],
    starts_with_all_models_alive: bool = False,
) -> tuple[ModelDestroyedEvent, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        return ()
    models_by_id = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if type(starts_with_all_models_alive) is not bool:
        raise GameLifecycleError("Unit-destruction initial-presence mode must be bool.")
    identity_by_model_id: dict[str, str] = {}
    for identity_id, model_ids in completion_model_ids_by_identity.items():
        for model_id in model_ids:
            if model_id not in models_by_id and not starts_with_all_models_alive:
                raise GameLifecycleError(
                    "Unit-destruction completion lost a frozen starting model."
                )
            if model_id in identity_by_model_id:
                raise GameLifecycleError(
                    "Unit-destruction completion model belongs to multiple identities."
                )
            identity_by_model_id[model_id] = identity_id
    removed_model_ids = set(battlefield.removed_model_ids)
    alive_by_model_id = (
        dict.fromkeys(identity_by_model_id, True)
        if starts_with_all_models_alive
        else {
            model_id: models_by_id[model_id].is_alive and model_id not in removed_model_ids
            for model_id in identity_by_model_id
        }
    )
    timeline: list[tuple[int, str, str, object]] = [
        (order, "destroyed", event_id, payload)
        for order, event_id, payload in model_destroyed_events
    ]
    timeline.extend(
        (order, "restored", event_id, model_ids)
        for order, event_id, model_ids in model_restoration_events
    )
    timeline.sort(key=lambda item: item[0])
    if len({item[0] for item in timeline}) != len(timeline):
        raise GameLifecycleError("Unit-destruction and restoration event orders must be unique.")
    if not starts_with_all_models_alive:
        for _order, event_kind, _event_id, event_value in reversed(timeline):
            if event_kind == "destroyed":
                payload = cast(dict[str, JsonValue], event_value)
                model_id = _payload_identifier(payload, key="model_instance_id")
                if model_id in alive_by_model_id:
                    alive_by_model_id[model_id] = True
                continue
            for model_id in cast(tuple[str, ...], event_value):
                if model_id in alive_by_model_id:
                    alive_by_model_id[model_id] = False
    completions: list[ModelDestroyedEvent] = []
    for event_order, event_kind, event_id, event_value in timeline:
        if event_kind == "restored":
            for model_id in cast(tuple[str, ...], event_value):
                if model_id in alive_by_model_id:
                    if alive_by_model_id[model_id]:
                        raise GameLifecycleError(
                            "Model-restoration event requires a destroyed model transition."
                        )
                    alive_by_model_id[model_id] = True
            continue
        payload = cast(dict[str, JsonValue], event_value)
        model_id = _payload_identifier(payload, key="model_instance_id")
        completion_identity_id = identity_by_model_id.get(model_id)
        if completion_identity_id is None:
            continue
        if not alive_by_model_id[model_id]:
            raise GameLifecycleError("Model-destruction event requires a living model transition.")
        alive_by_model_id[model_id] = False
        if any(
            alive_by_model_id[candidate_id]
            for candidate_id in completion_model_ids_by_identity[completion_identity_id]
        ):
            continue
        completion_payload = dict(payload)
        completion_payload["target_unit_instance_id"] = completion_identity_id
        completions.append((event_order, event_id, completion_payload))
    return tuple(completions)


def model_destroyed_events_for_lifecycle_phase(
    *,
    state: GameState,
    event_log: EventLog,
    completed_phase: BattlePhase,
) -> tuple[tuple[int, str, dict[str, JsonValue]], ...]:
    """Return destruction events that occurred inside the current lifecycle phase.

    An out-of-phase attack retains its attack phase in ``payload["phase"]``.  Event
    occurrence therefore comes from the lifecycle event boundary, not from that
    attack-semantic field.
    """
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Model-destruction phase lookup requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Model-destruction phase lookup requires EventLog.")
    phase = _battle_phase_from_token(completed_phase)
    if state.current_battle_phase is not phase:
        raise GameLifecycleError(
            "Model-destruction phase lookup must match the current lifecycle phase."
        )
    boundary_order = _last_completed_phase_event_order(event_log)
    events: list[tuple[int, str, dict[str, JsonValue]]] = []
    for event_order, record in enumerate(event_log.records):
        if event_order <= boundary_order or record.event_type != "model_destroyed":
            continue
        event_payload = validate_json_value(record.payload)
        if not isinstance(event_payload, dict):
            raise GameLifecycleError("model_destroyed event payload must be an object.")
        if event_payload.get("game_id") != state.game_id:
            continue
        if event_payload.get("battle_round") != state.battle_round:
            continue
        if event_payload.get("active_player_id") != state.active_player_id:
            continue
        events.append((event_order, record.event_id, dict(event_payload)))
    return tuple(events)


def model_restoration_events_for_event_log_interval(
    *,
    state: GameState,
    event_log: EventLog,
    start_order_exclusive: int,
    decision_records: tuple[DecisionRecord, ...] | None = None,
) -> tuple[ModelRestorationEvent, ...]:
    """Return authenticated model-restoration evidence after an event boundary.

    Live resolution authenticates against the engine-owned ``decision_recorded``
    event.  Replay restoration additionally supplies the authoritative controller
    records, which must match that event exactly.  A restoration-shaped event is
    never evidence by itself.
    """
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Model-restoration lookup requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Model-restoration lookup requires EventLog.")
    if type(start_order_exclusive) is not int or start_order_exclusive < -1:
        raise GameLifecycleError("Model-restoration event boundary is invalid.")
    authoritative_records = _validate_optional_restoration_decision_records(decision_records)
    decision_events_by_result_id = _decision_events_by_result_id(event_log)
    used_result_ids: set[str] = set()
    events: list[ModelRestorationEvent] = []
    for event_order, record in enumerate(event_log.records):
        if event_order <= start_order_exclusive:
            continue
        payload = validate_json_value(record.payload)
        if not isinstance(payload, dict):
            if record.event_type in {
                "healing_step_resolved",
                "return_on_death_set_back_up_completed",
            }:
                raise GameLifecycleError("Model-restoration event payload must be an object.")
            continue
        if record.event_type == "healing_step_resolved":
            model_ids = _healing_restored_model_ids(payload)
            if model_ids:
                result_id = _authenticate_healing_restoration_event(
                    state=state,
                    event_order=event_order,
                    payload=payload,
                    decision_events_by_result_id=decision_events_by_result_id,
                    authoritative_records=authoritative_records,
                )
                _claim_restoration_result_id(result_id, used_result_ids=used_result_ids)
        elif record.event_type == "return_on_death_set_back_up_completed":
            if payload.get("game_id") != state.game_id:
                continue
            model_ids = _return_on_death_restored_model_ids(payload)
            result_id = _authenticate_return_on_death_restoration_event(
                state=state,
                event_log=event_log,
                event_order=event_order,
                payload=payload,
                decision_events_by_result_id=decision_events_by_result_id,
                authoritative_records=authoritative_records,
            )
            _claim_restoration_result_id(result_id, used_result_ids=used_result_ids)
        else:
            continue
        if model_ids:
            events.append((event_order, record.event_id, model_ids))
    return tuple(events)


def _healing_restored_model_ids(payload: dict[str, JsonValue]) -> tuple[str, ...]:
    raw_step = payload.get("step")
    if not isinstance(raw_step, dict):
        raise GameLifecycleError("healing_step_resolved step must be an object.")
    step_kind = raw_step.get("step_kind")
    if step_kind not in {"revive_model", "revive_model_embarked"}:
        return ()
    return (_validate_identifier("restored_model_instance_id", raw_step.get("model_instance_id")),)


@dataclass(frozen=True, slots=True)
class _RestorationDecisionEvent:
    event_order: int
    record: DecisionRecord


def _validate_optional_restoration_decision_records(
    decision_records: object,
) -> tuple[DecisionRecord, ...] | None:
    if decision_records is None:
        return None
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in cast(tuple[object, ...], decision_records)
    ):
        raise GameLifecycleError(
            "Model-restoration replay provenance requires typed decision records."
        )
    return cast(tuple[DecisionRecord, ...], decision_records)


def _decision_events_by_result_id(
    event_log: EventLog,
) -> dict[str, tuple[_RestorationDecisionEvent, ...]]:
    from warhammer40k_core.engine.decision_record import DecisionRecordPayload
    from warhammer40k_core.engine.decision_request import DecisionError

    grouped: dict[str, list[_RestorationDecisionEvent]] = {}
    for event_order, event in enumerate(event_log.records):
        if event.event_type != "decision_recorded":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("decision_recorded event payload must be an object.")
        try:
            record = DecisionRecord.from_payload(cast(DecisionRecordPayload, event.payload))
        except (DecisionError, KeyError, TypeError) as exc:
            raise GameLifecycleError(
                "Model-restoration decision event payload is invalid."
            ) from exc
        grouped.setdefault(record.result.result_id, []).append(
            _RestorationDecisionEvent(event_order=event_order, record=record)
        )
    return {result_id: tuple(records) for result_id, records in grouped.items()}


def _require_restoration_decision(
    *,
    request_id: object,
    result_id: object,
    expected_decision_type: str,
    restoration_event_order: int,
    decision_events_by_result_id: dict[str, tuple[_RestorationDecisionEvent, ...]],
    authoritative_records: tuple[DecisionRecord, ...] | None,
) -> DecisionRecord:
    requested_request_id = _validate_identifier("restoration_request_id", request_id)
    requested_result_id = _validate_identifier("restoration_result_id", result_id)
    candidates = decision_events_by_result_id.get(requested_result_id, ())
    if len(candidates) != 1:
        raise GameLifecycleError(
            "Model-restoration event requires one authoritative decision event."
        )
    evidence = candidates[0]
    record = evidence.record
    if evidence.event_order >= restoration_event_order:
        raise GameLifecycleError("Model-restoration decision must precede its mutation event.")
    if (
        record.request.request_id != requested_request_id
        or record.result.request_id != requested_request_id
        or record.request.decision_type != expected_decision_type
        or record.result.decision_type != expected_decision_type
    ):
        raise GameLifecycleError("Model-restoration decision provenance drift.")
    if authoritative_records is not None:
        replay_candidates = tuple(
            candidate
            for candidate in authoritative_records
            if candidate.result.result_id == requested_result_id
        )
        if len(replay_candidates) != 1 or replay_candidates[0] != record:
            raise GameLifecycleError(
                "Model-restoration decision event drifted from replay decision records."
            )
    return record


def _claim_restoration_result_id(
    result_id: str,
    *,
    used_result_ids: set[str],
) -> None:
    if result_id in used_result_ids:
        raise GameLifecycleError(
            "One decision result cannot authenticate multiple model restorations."
        )
    used_result_ids.add(result_id)


def _authenticate_healing_restoration_event(
    *,
    state: GameState,
    event_order: int,
    payload: dict[str, JsonValue],
    decision_events_by_result_id: dict[str, tuple[_RestorationDecisionEvent, ...]],
    authoritative_records: tuple[DecisionRecord, ...] | None,
) -> str:
    from warhammer40k_core.engine.healing import (
        SELECT_HEALING_MODEL_DECISION_TYPE,
        HealingStep,
        HealingStepKind,
        HealingStepPayload,
    )
    from warhammer40k_core.engine.healing_revival import (
        SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
    )

    raw_step = payload.get("step")
    if not isinstance(raw_step, dict):
        raise GameLifecycleError("healing_step_resolved step must be an object.")
    try:
        step = HealingStep.from_payload(cast(HealingStepPayload, raw_step))
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Healing restoration step payload is invalid.") from exc
    if step.step_kind not in {
        HealingStepKind.REVIVE_MODEL,
        HealingStepKind.REVIVE_MODEL_EMBARKED,
    }:
        raise GameLifecycleError("Healing restoration event has a non-restoration step.")
    if step.request_id is None or step.result_id is None or step.model_instance_id is None:
        raise GameLifecycleError("Healing restoration requires recorded decision provenance.")
    expected_type = (
        SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE
        if step.step_kind is HealingStepKind.REVIVE_MODEL
        else SELECT_HEALING_MODEL_DECISION_TYPE
    )
    record = _require_restoration_decision(
        request_id=step.request_id,
        result_id=step.result_id,
        expected_decision_type=expected_type,
        restoration_event_order=event_order,
        decision_events_by_result_id=decision_events_by_result_id,
        authoritative_records=authoritative_records,
    )
    request_payload = _json_object(
        record.request.payload,
        message="Healing restoration request payload must be an object.",
    )
    effect_payload = _json_object(
        request_payload.get("effect"),
        message="Healing restoration request must include its effect.",
    )
    _validate_healing_effect_event_identity(
        state=state,
        event_payload=payload,
        effect_payload=effect_payload,
        model_instance_id=step.model_instance_id,
    )
    if request_payload.get("step_index") != step.step_index:
        raise GameLifecycleError("Healing restoration step index drift.")
    if step.step_kind is HealingStepKind.REVIVE_MODEL:
        if request_payload.get("model_instance_id") != step.model_instance_id:
            raise GameLifecycleError("Healing restoration request model identity drift.")
        _validate_healing_revival_placement_result(record=record, step=step)
    else:
        _validate_embarked_healing_selection_result(
            record=record,
            step=step,
            event_payload=payload,
        )
    return step.result_id


def _validate_healing_effect_event_identity(
    *,
    state: GameState,
    event_payload: dict[str, JsonValue],
    effect_payload: dict[str, JsonValue],
    model_instance_id: str,
) -> None:
    key_pairs = (
        ("effect_id", "effect_id"),
        ("target_unit_instance_id", "target_unit_instance_id"),
        ("amount", "amount"),
        ("source_rule_id", "source_rule_id"),
        ("source_context", "source_context"),
    )
    if any(
        event_payload.get(event_key) != effect_payload.get(effect_key)
        for event_key, effect_key in key_pairs
    ):
        raise GameLifecycleError("Healing restoration effect provenance drift.")
    target_unit_id = _validate_identifier(
        "healing_restoration_target_unit_instance_id",
        event_payload.get("target_unit_instance_id"),
    )
    component_id = next(
        (
            unit.unit_instance_id
            for army in state.army_definitions
            for unit in army.units
            if model_instance_id in unit.own_model_ids()
        ),
        None,
    )
    if component_id is None:
        raise GameLifecycleError("Healing restoration references an unknown model.")
    valid_target_ids = {component_id}
    valid_target_ids.update(
        record.attached_unit_instance_id
        for record in state.starting_attached_unit_records
        if component_id in record.component_unit_instance_ids
    )
    if target_unit_id not in valid_target_ids:
        raise GameLifecycleError("Healing restoration target identity drift.")


def _validate_healing_revival_placement_result(
    *,
    record: DecisionRecord,
    step: HealingStep,
) -> None:
    from warhammer40k_core.engine.movement_proposals import (
        PlacementProposalPayload,
        PlacementProposalPayloadPayload,
    )

    if step.transition_batch is None or len(step.transition_batch.placements) != 1:
        raise GameLifecycleError("Healing restoration requires one placement mutation.")
    try:
        submission = PlacementProposalPayload.from_payload(
            cast(PlacementProposalPayloadPayload, record.result.payload)
        )
        unit_placement = submission.require_unit_placement()
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Healing restoration placement decision is invalid.") from exc
    if submission.proposal_request_id != record.request.request_id:
        raise GameLifecycleError("Healing restoration proposal request identity drift.")
    if len(unit_placement.model_placements) != 1:
        raise GameLifecycleError("Healing restoration must place exactly one model.")
    placed_model = unit_placement.model_placements[0]
    transition = step.transition_batch.placements[0]
    if (
        placed_model.model_instance_id != step.model_instance_id
        or transition.model_instance_id != step.model_instance_id
        or transition.pose != placed_model.pose
    ):
        raise GameLifecycleError("Healing restoration placement mutation drift.")


def _validate_embarked_healing_selection_result(
    *,
    record: DecisionRecord,
    step: HealingStep,
    event_payload: dict[str, JsonValue],
) -> None:
    result_payload = _json_object(
        record.result.payload,
        message="Embarked healing restoration result payload must be an object.",
    )
    if (
        result_payload.get("selection_kind") != "revive_model"
        or result_payload.get("model_instance_id") != step.model_instance_id
        or result_payload.get("effect_id") != event_payload.get("effect_id")
        or result_payload.get("target_unit_instance_id")
        != event_payload.get("target_unit_instance_id")
        or result_payload.get("step_index") != step.step_index
        or result_payload.get("source_rule_id") != event_payload.get("source_rule_id")
        or result_payload.get("source_context") != event_payload.get("source_context")
    ):
        raise GameLifecycleError("Embarked healing restoration selection provenance drift.")


def _authenticate_return_on_death_restoration_event(
    *,
    state: GameState,
    event_log: EventLog,
    event_order: int,
    payload: dict[str, JsonValue],
    decision_events_by_result_id: dict[str, tuple[_RestorationDecisionEvent, ...]],
    authoritative_records: tuple[DecisionRecord, ...] | None,
) -> str:
    from dataclasses import replace

    from warhammer40k_core.engine.return_on_death import (
        RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
        RETURN_ON_DEATH_ROLL_RESOLVED_EVENT_TYPE,
        RETURN_ON_DEATH_SET_BACK_UP_REQUESTED_EVENT_TYPE,
        SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
        PendingReturnOnDeath,
        PendingReturnOnDeathPayload,
    )

    raw_pending = _json_object(
        payload.get("pending"),
        message="Return-on-death restoration pending payload must be an object.",
    )
    try:
        pending = PendingReturnOnDeath.from_payload(cast(PendingReturnOnDeathPayload, raw_pending))
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Return-on-death restoration pending payload is invalid.") from exc
    if not pending.resolved:
        raise GameLifecycleError("Return-on-death restoration requires a resolved pending state.")
    stored = state.pending_return_on_death_by_id(pending.pending_id)
    if stored != pending:
        raise GameLifecycleError("Return-on-death restoration pending state drift.")
    record = _require_restoration_decision(
        request_id=payload.get("request_id"),
        result_id=payload.get("result_id"),
        expected_decision_type=SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
        restoration_event_order=event_order,
        decision_events_by_result_id=decision_events_by_result_id,
        authoritative_records=authoritative_records,
    )
    request_payload = _json_object(
        record.request.payload,
        message="Return-on-death restoration request payload must be an object.",
    )
    expected_request_values = {
        "pending_id": pending.pending_id,
        "source_rule_id": pending.source_rule_id,
        "destroyed_unit_instance_id": pending.destroyed_unit_instance_id,
        "destroyed_model_instance_id": pending.destroyed_model_instance_id,
    }
    if any(request_payload.get(key) != value for key, value in expected_request_values.items()):
        raise GameLifecycleError("Return-on-death restoration request provenance drift.")
    placement_payload = _json_object(
        payload.get("placement"),
        message="Return-on-death restoration placement must be an object.",
    )
    result_payload = _json_object(
        record.result.payload,
        message="Return-on-death restoration result payload must be an object.",
    )
    attempted_placement = _json_object(
        result_payload.get("attempted_placement"),
        message="Return-on-death result must include attempted_placement.",
    )
    if attempted_placement != placement_payload:
        raise GameLifecycleError("Return-on-death restoration placement decision drift.")
    unresolved_payload = replace(pending, resolved=False).to_payload()
    created_order = _unique_prior_event_order(
        event_log=event_log,
        before_order=event_order,
        event_type=RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
        predicate=lambda candidate: candidate.get("pending") == unresolved_payload,
        error_message="Return-on-death restoration requires one pending-creation event.",
    )
    roll_order = _unique_prior_event_order(
        event_log=event_log,
        after_order=created_order,
        before_order=event_order,
        event_type=RETURN_ON_DEATH_ROLL_RESOLVED_EVENT_TYPE,
        predicate=lambda candidate: (
            candidate.get("game_id") == state.game_id
            and candidate.get("pending_id") == pending.pending_id
            and candidate.get("success") is True
        ),
        error_message="Return-on-death restoration requires one successful roll event.",
    )
    _unique_prior_event_order(
        event_log=event_log,
        after_order=roll_order,
        before_order=event_order,
        event_type=RETURN_ON_DEATH_SET_BACK_UP_REQUESTED_EVENT_TYPE,
        predicate=lambda candidate: (
            candidate.get("game_id") == state.game_id
            and candidate.get("pending_id") == pending.pending_id
            and candidate.get("request_id") == record.request.request_id
        ),
        error_message="Return-on-death restoration requires one placement-request event.",
    )
    return record.result.result_id


def _unique_prior_event_order(
    *,
    event_log: EventLog,
    before_order: int,
    event_type: str,
    predicate: Callable[[dict[str, JsonValue]], bool],
    error_message: str,
    after_order: int = -1,
) -> int:
    matches: list[int] = []
    for index, record in enumerate(event_log.records):
        if index <= after_order or index >= before_order or record.event_type != event_type:
            continue
        if not isinstance(record.payload, dict):
            raise GameLifecycleError(f"{event_type} event payload must be an object.")
        if predicate(record.payload):
            matches.append(index)
    if len(matches) != 1:
        raise GameLifecycleError(error_message)
    return matches[0]


def _json_object(value: object, *, message: str) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError(message)
    return payload


def _return_on_death_restored_model_ids(
    payload: dict[str, JsonValue],
) -> tuple[str, ...]:
    raw_placement = payload.get("placement")
    if not isinstance(raw_placement, dict):
        raise GameLifecycleError("Return-on-death restoration placement must be an object.")
    raw_model_placements = raw_placement.get("model_placements")
    if not isinstance(raw_model_placements, list) or not raw_model_placements:
        raise GameLifecycleError(
            "Return-on-death restoration model_placements must be a non-empty list."
        )
    model_ids: list[str] = []
    for raw_model_placement in raw_model_placements:
        if not isinstance(raw_model_placement, dict):
            raise GameLifecycleError(
                "Return-on-death restoration model placement must be an object."
            )
        model_ids.append(
            _validate_identifier(
                "restored_model_instance_id",
                raw_model_placement.get("model_instance_id"),
            )
        )
    if len(set(model_ids)) != len(model_ids):
        raise GameLifecycleError("Model-restoration event must not repeat model IDs.")
    return tuple(sorted(model_ids))


def _last_completed_phase_event_order(event_log: EventLog) -> int:
    boundary_order = -1
    for event_order, record in enumerate(event_log.records):
        if record.event_type == "battle_phase_completed":
            boundary_order = event_order
    return boundary_order


def _validate_model_destroyed_event_interval(
    *,
    state: GameState,
    model_destroyed_events: object,
) -> tuple[tuple[int, str, dict[str, JsonValue]], ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Unit-destruction interval lookup requires GameState.")
    if type(model_destroyed_events) is not tuple:
        raise GameLifecycleError("Unit-destruction event interval must be a tuple.")
    component_by_model_id = {
        model.model_instance_id: unit.unit_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    historical_by_component = {
        component_id: record
        for record in state.starting_attached_unit_records
        for component_id in record.component_unit_instance_ids
    }
    validated: list[tuple[int, str, dict[str, JsonValue]]] = []
    seen_event_ids: set[str] = set()
    previous_order = -1
    for raw_event in cast(tuple[object, ...], model_destroyed_events):
        if type(raw_event) is not tuple:
            raise GameLifecycleError("Unit-destruction event interval entry is invalid.")
        event_values = cast(tuple[object, ...], raw_event)
        if len(event_values) != 3:
            raise GameLifecycleError("Unit-destruction event interval entry is invalid.")
        event_order, raw_event_id, raw_payload = event_values
        if type(event_order) is not int or event_order < 0 or event_order <= previous_order:
            raise GameLifecycleError(
                "Unit-destruction event interval must be strictly chronological."
            )
        event_id = _validate_identifier("model_destroyed_event_id", raw_event_id)
        if event_id in seen_event_ids:
            raise GameLifecycleError("Unit-destruction event interval IDs must be unique.")
        payload = validate_json_value(raw_payload)
        if not isinstance(payload, dict):
            raise GameLifecycleError("Unit-destruction event payload must be an object.")
        if payload.get("game_id") != state.game_id:
            raise GameLifecycleError("Unit-destruction event interval game_id drift.")
        model_id = _payload_identifier(payload, key="model_instance_id")
        component_id = component_by_model_id.get(model_id)
        if component_id is None:
            raise GameLifecycleError("Unit-destruction event references an unknown model.")
        target_unit_id = _payload_identifier(payload, key="target_unit_instance_id")
        historical = historical_by_component.get(component_id)
        valid_target_ids = {component_id}
        if historical is not None:
            valid_target_ids.add(historical.attached_unit_instance_id)
        if target_unit_id not in valid_target_ids:
            raise GameLifecycleError("Unit-destruction event target identity drift.")
        validated.append((event_order, event_id, dict(payload)))
        previous_order = event_order
        seen_event_ids.add(event_id)
    return tuple(validated)


def _validate_model_restoration_event_interval(
    *,
    state: GameState,
    model_restoration_events: object,
) -> tuple[ModelRestorationEvent, ...]:
    if type(model_restoration_events) is not tuple:
        raise GameLifecycleError("Model-restoration event interval must be a tuple.")
    known_model_ids = {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    validated: list[ModelRestorationEvent] = []
    seen_event_ids: set[str] = set()
    previous_order = -1
    for raw_event in cast(tuple[object, ...], model_restoration_events):
        if type(raw_event) is not tuple:
            raise GameLifecycleError("Model-restoration event interval entry is invalid.")
        event_values = cast(tuple[object, ...], raw_event)
        if len(event_values) != 3:
            raise GameLifecycleError("Model-restoration event interval entry is invalid.")
        event_order, raw_event_id, raw_model_ids = event_values
        if type(event_order) is not int or event_order < 0 or event_order <= previous_order:
            raise GameLifecycleError(
                "Model-restoration event interval must be strictly chronological."
            )
        event_id = _validate_identifier("model_restoration_event_id", raw_event_id)
        if event_id in seen_event_ids:
            raise GameLifecycleError("Model-restoration event interval IDs must be unique.")
        if type(raw_model_ids) is not tuple:
            raise GameLifecycleError("Model-restoration model IDs must be a tuple.")
        model_ids = tuple(
            _validate_identifier("restored_model_instance_id", model_id)
            for model_id in cast(tuple[object, ...], raw_model_ids)
        )
        if not model_ids or len(set(model_ids)) != len(model_ids):
            raise GameLifecycleError("Model-restoration model IDs must be non-empty and unique.")
        if any(model_id not in known_model_ids for model_id in model_ids):
            raise GameLifecycleError("Model-restoration event references an unknown model.")
        validated.append((event_order, event_id, tuple(sorted(model_ids))))
        previous_order = event_order
        seen_event_ids.add(event_id)
    return tuple(validated)


def _payload_identifier(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Unit-destruction event payload missing {key}.")
    return _validate_identifier(key, payload[key])


def _validate_bindings(value: object) -> tuple[UnitDestroyedHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.UNIT_DESTROYED,
        binding_type=UnitDestroyedHookBinding,
        registry_name="UnitDestroyedHookRegistry",
        invalid_binding_message="UnitDestroyedHookRegistry requires hook bindings.",
    )


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Unit-destroyed hook phase must be BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported unit-destroyed hook phase: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
