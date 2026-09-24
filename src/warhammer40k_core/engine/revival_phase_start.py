"""Authenticate Core revival anchors at the recorded start of the actual phase."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowError,
    TimingWindowPayload,
)
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_revival_2026_09 import (
    PACKAGE_HASH,
    REVIVAL_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class RevivalPhaseStartPayload(TypedDict):
    rule_source_id: str
    source_package_hash: str
    game_id: str
    battle_round: int
    turn_owner_player_id: str
    phase: str
    phase_start_event_id: str
    phase_start_window_id: str
    target_unit_instance_id: str
    model_ids: list[str]


def validated_revival_phase_start_payload(raw: JsonValue) -> RevivalPhaseStartPayload:
    if not isinstance(raw, dict) or set(raw) != set(RevivalPhaseStartPayload.__annotations__):
        raise GameLifecycleError("Revival phase-start evidence shape is invalid.")
    for key in set(RevivalPhaseStartPayload.__annotations__) - {"battle_round", "model_ids"}:
        value = raw[key]
        if type(value) is not str or not value or value != value.strip():
            raise GameLifecycleError("Revival phase-start identity is invalid.")
    if type(raw["battle_round"]) is not int or raw["battle_round"] < 1:
        raise GameLifecycleError("Revival phase-start round is invalid.")
    models = raw["model_ids"]
    if not isinstance(models, list) or any(
        type(value) is not str or not value or value != value.strip() for value in models
    ):
        raise GameLifecycleError("Revival phase-start model inventory is invalid.")
    identifiers = cast(list[str], models)
    if identifiers != sorted(set(identifiers)):
        raise GameLifecycleError("Revival phase-start models must be sorted and unique.")
    if raw["rule_source_id"] != REVIVAL_SOURCE_ID or raw["source_package_hash"] != PACKAGE_HASH:
        raise GameLifecycleError("Revival phase-start source authority drifted.")
    return cast(RevivalPhaseStartPayload, raw)


def revival_phase_start_evidence(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    target_unit_instance_id: str,
    before_event_index: int | None = None,
) -> RevivalPhaseStartPayload:
    """Use a real phase opening; omission of a history boundary means the live phase."""
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        physical_model_authority_before_event,
    )

    stop = len(event_records) if before_event_index is None else before_event_index
    if type(stop) is not int or not 0 <= stop <= len(event_records):
        raise GameLifecycleError("Revival phase-start history boundary is invalid.")
    openings: list[tuple[int, TimingWindow]] = []
    seen: set[str] = set()
    for index, event in enumerate(event_records[:stop]):
        if event.event_type != "timing_window_opened":
            continue
        payload = event.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("timing_window"), dict):
            raise GameLifecycleError("Revival phase-start timing authority is malformed.")
        try:
            window = TimingWindow.from_payload(cast(TimingWindowPayload, payload["timing_window"]))
        except (TimingWindowError, KeyError, TypeError) as exc:
            raise GameLifecycleError("Revival phase-start timing authority is invalid.") from exc
        if window.descriptor.trigger_kind is not TimingTriggerKind.START_PHASE:
            continue
        if window.phase is None or window.active_player_id not in state.player_ids:
            raise GameLifecycleError("Revival phase-start phase or turn owner is invalid.")
        expected_id = (
            f"timing-window:{state.game_id}:round-{window.battle_round:02d}:"
            f"turn:{window.active_player_id}:phase:{window.phase.value}:start"
        )
        if (
            window.game_id != state.game_id
            or window.window_id != expected_id
            or window.descriptor.descriptor_id != f"{expected_id}:descriptor"
            or window.descriptor.source_rule_id != "core-rules-lifecycle-timing"
            or window.descriptor.source_step != window.phase.value
            or window.descriptor.phase is not window.phase
            or window.trigger_event_id is not None
            or window.window_id in seen
        ):
            raise GameLifecycleError("Revival phase-start occurrence authority drifted.")
        seen.add(window.window_id)
        openings.append((index, window))
    if not openings:
        raise GameLifecycleError("Revival requires a recorded phase-start boundary.")
    index, window = openings[-1]
    if before_event_index is None and (
        state.current_battle_phase is not window.phase
        or state.battle_round != window.battle_round
        or state.active_player_id != window.active_player_id
    ):
        raise GameLifecycleError("Revival phase-start occurrence is stale.")
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    if target.unit_instance_id != target_unit_instance_id:
        raise GameLifecycleError("Revival phase-start target must be a canonical rules unit.")
    target_ids = {model.model_instance_id for model in target.own_models}
    physical = physical_model_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=index,
    )
    assert window.phase is not None
    assert window.active_player_id is not None
    return RevivalPhaseStartPayload(
        rule_source_id=REVIVAL_SOURCE_ID,
        source_package_hash=PACKAGE_HASH,
        game_id=state.game_id,
        battle_round=window.battle_round,
        turn_owner_player_id=window.active_player_id,
        phase=window.phase.value,
        phase_start_event_id=event_records[index].event_id,
        phase_start_window_id=window.window_id,
        target_unit_instance_id=target_unit_instance_id,
        model_ids=sorted(
            row.model_instance_id
            for row in physical
            if row.model_instance_id in target_ids
            and row.presence in {"battlefield", "retained_destroyed"}
        ),
    )


def validate_revival_anchor_coherency(
    *,
    returned: Model,
    present_models: tuple[Model, ...],
    phase_start_model_ids: tuple[str, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    """Measure current poses of other phase-start models, including retained presence."""
    policy = ruleset_descriptor.coherency_policy
    if policy.max_horizontal_inches is None or policy.max_vertical_inches is None:
        raise GameLifecycleError("Revival coherency policy is incomplete.")
    count = len({model.model_id for model in present_models} | {returned.model_id})
    threshold = policy.large_unit_model_count_threshold
    required = (
        policy.required_neighbors_large_unit
        if threshold is not None and count >= threshold
        else policy.required_neighbors_small_unit
    )
    if required is None:
        raise GameLifecycleError("Revival coherency neighbor policy is incomplete.")
    phase_start_ids = set(phase_start_model_ids)
    anchors = tuple(
        model
        for model in present_models
        if model.model_id in phase_start_ids and model.model_id != returned.model_id
    )
    neighbors = sum(
        returned.base_distance_to(anchor) <= policy.max_horizontal_inches
        and returned.volume.vertical_gap_to(returned.pose, anchor.volume, anchor.pose)
        <= policy.max_vertical_inches
        for anchor in anchors
    )
    if neighbors < required:
        raise GameLifecycleError("Revived model is not coherent with phase-start models.")


def revival_phase_start_for_request(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request: DecisionRequest,
    target_unit_instance_id: str,
) -> RevivalPhaseStartPayload:
    indexes = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    if len(indexes) != 1:
        raise GameLifecycleError("Revival phase-start request lacks unique historical authority.")
    return revival_phase_start_evidence(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        target_unit_instance_id=target_unit_instance_id,
        before_event_index=indexes[0],
    )


def validate_revival_selection_phase_start(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request: DecisionRequest,
    target_unit_instance_id: str,
    phase_start_model_ids: tuple[str, ...],
) -> None:
    payload = request.payload
    if not isinstance(payload, dict) or payload.get("selection_kind") != "revive_model":
        return
    model_ids = payload.get("legal_model_ids")
    if not isinstance(model_ids, list) or any(type(model_id) is not str for model_id in model_ids):
        raise GameLifecycleError("Revival selection model inventory is invalid.")
    if all(
        state.transport_cargo_state_for_embarked_unit(state.unit_instance_id_for_model(model_id))
        is not None
        for model_id in cast(list[str], model_ids)
    ):
        return
    expected = revival_phase_start_for_request(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request=request,
        target_unit_instance_id=target_unit_instance_id,
    )
    current = revival_phase_start_evidence(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        target_unit_instance_id=target_unit_instance_id,
    )
    if expected != current or tuple(expected["model_ids"]) != phase_start_model_ids:
        raise GameLifecycleError("Revival selection phase-start authority drifted.")
