from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.cult_ambush import (
    CULT_AMBUSH_MARKER_REMOVAL_DISTANCE_INCHES,
    SOURCE_RULE_ID,
    CultAmbushMarker,
    CultAmbushMarkerPayload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    FightMovementCompletedEndpoint,
    FightRulesUnitPlacement,
    fight_rules_unit_movement_endpoint_from_completed_event,
    rules_unit_views_for_completed_move_event,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_PROCESSED_MARKER_REMOVAL_MOVE_EVENTS = frozenset(
    {
        "movement_activation_completed",
        "charge_move_completed",
        "fight_movement_completed",
        "unit_disembarked",
        "reinforcement_unit_arrived",
        "triggered_movement_resolved",
        "heroic_intervention_charge_move_completed",
        "catalog_setup_reactive_charge_move_completed",
    }
)
_CULT_AMBUSH_MARKER_PLACED_EVENT_TYPE = "genestealer_cults_cult_ambush_marker_placed"
_CULT_AMBUSH_MARKER_PLACED_EVENT_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "player_id",
        "request_id",
        "result_id",
        "marker",
        "source_rule_id",
    }
)
_CULT_AMBUSH_MARKER_PAYLOAD_KEYS = frozenset(
    {
        "marker_id",
        "player_id",
        "replacement_unit_instance_id",
        "source_destroyed_unit_instance_id",
        "created_battle_round",
        "created_phase",
        "created_active_player_id",
        "x_inches",
        "y_inches",
        "marker_diameter_inches",
        "ingress_window_closed",
    }
)


def cult_ambush_marker_removal_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    trigger_event_id: str,
) -> tuple[TimingRuleCandidate, ...]:
    if not state.cult_ambush_markers or state.battlefield_state is None:
        return ()
    candidates: list[TimingRuleCandidate] = []
    marker_placement_evidence = _marker_placement_event_evidence(
        state=state,
        decisions=decisions,
    )
    for record_index, record in enumerate(tuple(decisions.event_log.records)):
        if (
            record.event_id != trigger_event_id
            or record.event_type not in _PROCESSED_MARKER_REMOVAL_MOVE_EVENTS
        ):
            continue
        if _marker_removal_already_processed(decisions, trigger_event_id=record.event_id):
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Move completion event payload must be an object.")
        if (
            payload.get("game_id") != state.game_id
            or payload.get("battle_round") != state.battle_round
            or payload.get("active_player_id") != state.active_player_id
            or payload.get("phase") != completed_phase.value
        ):
            continue
        unit_id = _event_unit_instance_id(payload)
        if unit_id is None:
            continue
        rules_units = rules_unit_views_for_completed_move_event(
            state=state,
            event_type=record.event_type,
            unit_instance_id=unit_id,
        )
        owner_id = _rules_unit_owner(rules_units)
        if all(marker.player_id == owner_id for marker in state.cult_ambush_markers):
            continue
        component_ids = _rules_unit_component_ids(rules_units)
        endpoint = (
            fight_rules_unit_movement_endpoint_from_completed_event(
                payload=payload,
                component_unit_instance_ids=component_ids,
            )
            if record.event_type == "fight_movement_completed"
            else None
        )
        if _rules_unit_has_aircraft_keyword(rules_units=rules_units, endpoint=endpoint):
            continue
        eligible: dict[str, list[CultAmbushMarker]] = {}
        for marker in tuple(state.cult_ambush_markers):
            if marker.player_id == owner_id:
                continue
            if (
                _marker_placement_event_index(
                    marker=marker,
                    evidence_by_marker_id=marker_placement_evidence,
                )
                >= record_index
            ):
                continue
            if _rules_unit_is_within_marker_removal_distance(
                state=state,
                marker=marker,
                rules_units=rules_units,
                placements=(
                    _current_rules_unit_model_placements(state=state, rules_units=rules_units)
                    if endpoint is None
                    else endpoint.model_placements
                ),
            ):
                eligible.setdefault(marker.player_id, []).append(marker)
        for player_id, markers in sorted(eligible.items()):
            candidates.append(
                TimingRuleCandidate(
                    participant=SequencingParticipant(
                        participant_id=f"cult-marker-removal:{record.event_id}:{player_id}",
                        player_id=player_id,
                        source_rule_id=SOURCE_RULE_ID,
                        requirement=SequencingRequirement.MANDATORY,
                        payload=validate_json_value(
                            {
                                "trigger_event_id": record.event_id,
                                "trigger_event_type": record.event_type,
                                "moving_unit_instance_id": unit_id,
                                "markers": [marker.to_payload() for marker in markers],
                            }
                        ),
                    ),
                    activate=partial(
                        _remove_markers,
                        state=state,
                        decisions=decisions,
                        completed_phase=completed_phase,
                        markers=tuple(markers),
                        trigger_event_id=record.event_id,
                        trigger_event_type=record.event_type,
                        unit_id=unit_id,
                    ),
                )
            )
    return tuple(candidates)


def resume_cult_marker_candidate(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    trigger_event_id: str,
    participant: SequencingParticipant,
) -> TimingRuleCandidate | None:
    payload = participant.payload
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {"trigger_event_id", "trigger_event_type", "moving_unit_instance_id", "markers"}
        or payload["trigger_event_id"] != trigger_event_id
        or type(payload["trigger_event_type"]) is not str
        or type(payload["moving_unit_instance_id"]) is not str
        or not isinstance(payload["markers"], list)
        or not payload["markers"]
        or participant.source_rule_id != SOURCE_RULE_ID
        or participant.requirement is not SequencingRequirement.MANDATORY
        or participant.participant_id
        != f"cult-marker-removal:{trigger_event_id}:{participant.player_id}"
    ):
        raise GameLifecycleError("Captured Cult marker rule source identity drift.")
    if participant != SequencingParticipant(
        participant_id=participant.participant_id,
        player_id=participant.player_id,
        source_rule_id=SOURCE_RULE_ID,
        requirement=SequencingRequirement.MANDATORY,
        payload=payload,
    ):
        raise GameLifecycleError("Captured Cult participant classification drift.")
    evidence = _marker_placement_event_evidence(state=state, decisions=decisions)
    sources = tuple(
        (index, event)
        for index, event in enumerate(decisions.event_log.records)
        if event.event_id == trigger_event_id
    )
    if len(sources) != 1 or sources[0][1].event_type != payload["trigger_event_type"]:
        raise GameLifecycleError("Captured Cult marker move source drift.")
    markers: list[CultAmbushMarker] = []
    for raw in payload["markers"]:
        if not isinstance(raw, dict):
            raise GameLifecycleError("Captured Cult marker must be an object.")
        marker = CultAmbushMarker.from_payload(cast(CultAmbushMarkerPayload, raw))
        if marker.player_id != participant.player_id:
            raise GameLifecycleError("Captured Cult marker owner drift.")
        placed = evidence.get(marker.marker_id)
        if (
            placed is None
            or placed[0] >= sources[0][0]
            or placed[1] != replace(marker, ingress_window_closed=False)
        ):
            raise GameLifecycleError("Captured Cult marker creation authority drift.")
        current = tuple(
            item for item in state.cult_ambush_markers if item.marker_id == marker.marker_id
        )
        if current:
            if len(current) != 1 or replace(current[0], ingress_window_closed=False) != replace(
                marker, ingress_window_closed=False
            ):
                raise GameLifecycleError("Captured Cult marker state drift.")
            markers.append(current[0])
    if not markers or _marker_removal_already_processed(
        decisions, trigger_event_id=trigger_event_id
    ):
        return None
    return TimingRuleCandidate(
        participant=participant,
        activate=partial(
            _remove_markers,
            state=state,
            decisions=decisions,
            completed_phase=completed_phase,
            markers=tuple(markers),
            trigger_event_id=trigger_event_id,
            trigger_event_type=payload["trigger_event_type"],
            unit_id=payload["moving_unit_instance_id"],
        ),
    )


def _remove_markers(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    markers: tuple[CultAmbushMarker, ...],
    trigger_event_id: str,
    trigger_event_type: str,
    unit_id: str,
) -> None:
    for marker in markers:
        _remove_marker(
            state=state,
            decisions=decisions,
            completed_phase=completed_phase,
            marker=marker,
            trigger_event_id=trigger_event_id,
            trigger_event_type=trigger_event_type,
            unit_id=unit_id,
        )


def _remove_marker(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    marker: CultAmbushMarker,
    trigger_event_id: str,
    trigger_event_type: str,
    unit_id: str,
) -> None:
    state.remove_cult_ambush_marker(marker.marker_id)
    decisions.event_log.append(
        "genestealer_cults_cult_ambush_marker_removed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": completed_phase.value,
            "player_id": marker.player_id,
            "marker": marker.to_payload(),
            "trigger_event_id": trigger_event_id,
            "trigger_event_type": trigger_event_type,
            "enemy_unit_instance_id": unit_id,
            "source_rule_id": SOURCE_RULE_ID,
        },
    )


def _marker_placement_event_evidence(
    *,
    state: GameState,
    decisions: DecisionController,
) -> dict[str, tuple[int, CultAmbushMarker]]:
    evidence_by_marker_id: dict[str, tuple[int, CultAmbushMarker]] = {}
    for record_index, record in enumerate(decisions.event_log.records):
        if record.event_type != _CULT_AMBUSH_MARKER_PLACED_EVENT_TYPE:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError(
                "Cult Ambush marker placement event payload must be an object."
            )
        if frozenset(payload) != _CULT_AMBUSH_MARKER_PLACED_EVENT_KEYS:
            raise GameLifecycleError("Cult Ambush marker placement event payload shape drifted.")
        raw_marker = payload.get("marker")
        if not isinstance(raw_marker, dict):
            raise GameLifecycleError("Cult Ambush marker placement evidence must be an object.")
        if frozenset(raw_marker) != _CULT_AMBUSH_MARKER_PAYLOAD_KEYS:
            raise GameLifecycleError("Cult Ambush marker placement evidence shape drifted.")
        marker = CultAmbushMarker.from_payload(cast(CultAmbushMarkerPayload, raw_marker))
        if marker.ingress_window_closed:
            raise GameLifecycleError("Cult Ambush marker placement evidence is already closed.")
        if (
            payload.get("game_id") != state.game_id
            or payload.get("battle_round") != marker.created_battle_round
            or payload.get("active_player_id") != marker.created_active_player_id
            or payload.get("phase") != marker.created_phase.value
            or payload.get("player_id") != marker.player_id
            or payload.get("source_rule_id") != SOURCE_RULE_ID
        ):
            raise GameLifecycleError("Cult Ambush marker placement event context drifted.")
        for field_name in ("request_id", "result_id"):
            value = payload.get(field_name)
            if type(value) is not str or not value.strip():
                raise GameLifecycleError(
                    f"Cult Ambush marker placement event {field_name} must be an identifier."
                )
        if marker.marker_id in evidence_by_marker_id:
            raise GameLifecycleError("Cult Ambush marker placement event identity is duplicated.")
        evidence_by_marker_id[marker.marker_id] = (record_index, marker)
    return evidence_by_marker_id


def _marker_placement_event_index(
    *,
    marker: CultAmbushMarker,
    evidence_by_marker_id: dict[str, tuple[int, CultAmbushMarker]],
) -> int:
    evidence = evidence_by_marker_id.get(marker.marker_id)
    if evidence is None:
        raise GameLifecycleError("Cult Ambush marker state lacks placement event evidence.")
    record_index, placed_marker = evidence
    if replace(marker, ingress_window_closed=False) != placed_marker:
        raise GameLifecycleError("Cult Ambush marker placement evidence drifted from state.")
    return record_index


def _rules_unit_owner(rules_units: tuple[RulesUnitView, ...]) -> str:
    owner_ids = {rules_unit.owner_player_id for rules_unit in rules_units}
    if len(owner_ids) != 1:
        raise GameLifecycleError("Cult Ambush moving rules-unit owner is ambiguous.")
    return next(iter(owner_ids))


def _rules_unit_component_ids(rules_units: tuple[RulesUnitView, ...]) -> tuple[str, ...]:
    component_ids = tuple(
        sorted(
            component.unit.unit_instance_id
            for rules_unit in rules_units
            for component in rules_unit.components
        )
    )
    if not component_ids or len(component_ids) != len(set(component_ids)):
        raise GameLifecycleError("Cult Ambush moving rules-unit component inventory is invalid.")
    return component_ids


def _rules_unit_has_aircraft_keyword(
    *,
    rules_units: tuple[RulesUnitView, ...],
    endpoint: FightMovementCompletedEndpoint | None,
) -> bool:
    if endpoint is None:
        return any(
            keyword == "AIRCRAFT"
            for rules_unit in rules_units
            for keyword in (*rules_unit.keywords, *rules_unit.faction_keywords)
        )
    endpoint_component_ids = set(
        endpoint.component_unit_instance_ids
        if isinstance(endpoint, FightRulesUnitPlacement)
        else (endpoint.unit_instance_id,)
    )
    return any(
        keyword == "AIRCRAFT"
        for rules_unit in rules_units
        for component in rules_unit.components
        if component.unit.unit_instance_id in endpoint_component_ids
        for keyword in (*component.unit.keywords, *component.unit.faction_keywords)
    )


def _rules_unit_is_within_marker_removal_distance(
    *,
    state: GameState,
    marker: CultAmbushMarker,
    rules_units: tuple[RulesUnitView, ...],
    placements: tuple[ModelPlacement, ...],
) -> bool:
    model_by_id, component_by_model_id = _rules_unit_model_inventory(rules_units)
    for placement in placements:
        model = model_by_id.get(placement.model_instance_id)
        if (
            model is None
            or component_by_model_id[model.model_instance_id] != placement.unit_instance_id
        ):
            raise GameLifecycleError("Cult Ambush move endpoint model identity drift.")
        geometry_model = geometry_model_for_placement(model=model, placement=placement)
        context = DistanceMeasurementContext.from_objective_marker_to_model(
            marker_id=marker.marker_id,
            marker_pose=marker.pose,
            model=geometry_model,
            marker_diameter_inches=marker.marker_diameter_inches,
        )
        if context.horizontal_distance_inches() <= CULT_AMBUSH_MARKER_REMOVAL_DISTANCE_INCHES:
            return True
    return False


def _current_rules_unit_model_placements(
    *,
    state: GameState,
    rules_units: tuple[RulesUnitView, ...],
) -> tuple[ModelPlacement, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Cult Ambush marker removal requires battlefield_state.")
    placements = tuple(
        model_placement
        for rules_unit in rules_units
        for component in rules_unit.components
        if (unit_placement := battlefield.unit_placement_or_none(component.unit.unit_instance_id))
        is not None
        for model_placement in unit_placement.model_placements
    )
    if not placements:
        raise GameLifecycleError("Cult Ambush move event has no placed rules-unit models.")
    return placements


def _rules_unit_model_inventory(
    rules_units: tuple[RulesUnitView, ...],
) -> tuple[dict[str, ModelInstance], dict[str, str]]:
    model_by_id = {
        model.model_instance_id: model
        for rules_unit in rules_units
        for component in rules_unit.components
        for model in component.unit.own_models
    }
    component_by_model_id = {
        model.model_instance_id: component.unit.unit_instance_id
        for rules_unit in rules_units
        for component in rules_unit.components
        for model in component.unit.own_models
    }
    expected_model_count = sum(
        len(component.unit.own_models)
        for rules_unit in rules_units
        for component in rules_unit.components
    )
    if len(model_by_id) != expected_model_count:
        raise GameLifecycleError("Cult Ambush moving rules-unit model inventory is duplicated.")
    return model_by_id, component_by_model_id


def _marker_removal_already_processed(
    decisions: DecisionController,
    *,
    trigger_event_id: str,
) -> bool:
    return any(
        record.event_type == "genestealer_cults_cult_ambush_marker_removed"
        and isinstance(record.payload, dict)
        and record.payload.get("trigger_event_id") == trigger_event_id
        for record in decisions.event_log.records
    )


def _event_unit_instance_id(payload: dict[str, JsonValue]) -> str | None:
    for key in ("unit_instance_id", "target_unit_instance_id"):
        value = payload.get(key)
        if type(value) is str:
            return value
    return None


__all__ = ("cult_ambush_marker_removal_candidates",)
