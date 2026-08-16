from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.actions import (
    MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
    MISSION_ACTION_UNIT_LEFT_BATTLEFIELD_INTERRUPTION_REASON,
    MissionActionState,
    MissionActionStatus,
    mission_action_interruption_reason_for_displacement,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mission_action_policies import (
    mission_action_policy_descriptors,
    mission_action_policy_for_id,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
)
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_identity,
    rules_unit_identities_share_lineage,
)
from warhammer40k_core.engine.scoring import (
    PrimaryUnitDestructionState,
    PrimaryUnitDestructionStatePayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_MOVE_COMPLETION_EVENTS = frozenset(
    {
        "catalog_setup_reactive_charge_move_completed",
        "charge_move_completed",
        "fight_movement_completed",
        "heroic_intervention_charge_move_completed",
        "movement_activation_completed",
        "triggered_movement_resolved",
    }
)


@dataclass(frozen=True, slots=True)
class _InterruptionEvidence:
    event_order: int
    event: EventRecord
    reason: str
    phase: BattlePhase


def reconcile_primary_mission_action_interruptions(
    *,
    state: GameState,
    decisions: DecisionController,
) -> tuple[MissionActionState, ...]:
    """Interrupt source-backed Primary Actions from post-start authoritative evidence."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or type(decisions) is not DecisionController:
        raise GameLifecycleError(
            "Primary Mission Action interruption reconciliation requires engine state."
        )
    policy_ids = {
        descriptor.mission_action_id for descriptor in mission_action_policy_descriptors()
    }
    candidates = tuple(
        sorted(
            (
                action
                for action in state.mission_action_states
                if action.status is MissionActionStatus.STARTED
                and action.mission_action_id in policy_ids
            ),
            key=lambda action: action.action_id,
        )
    )
    interrupted_states: list[MissionActionState] = []
    for action in candidates:
        evidence = _first_interruption_evidence(
            state=state,
            action=action,
            event_records=decisions.event_log.records,
        )
        if evidence is None:
            continue
        policy = mission_action_policy_for_id(action.mission_action_id)
        interrupted = action.interrupt(reason=evidence.reason)
        event_payload: dict[str, JsonValue] = {
            "game_id": state.game_id,
            "battle_round": action.battle_round_started,
            "active_player_id": state.active_player_id,
            "player_id": action.player_id,
            "phase": evidence.phase.value,
            "action_id": action.action_id,
            "mission_action_id": action.mission_action_id,
            "unit_instance_id": action.unit_instance_id,
            "mission_action_state": validate_json_value(interrupted.to_payload()),
            "interrupted_reason": interrupted.interrupted_reason,
            "source_evidence_event_id": evidence.event.event_id,
            "source_evidence_event_type": evidence.event.event_type,
            "source_id": policy.source_id,
        }
        state.replace_mission_action_state(interrupted)
        decisions.event_log.append("mission_action_interrupted", event_payload)
        interrupted_states.append(interrupted)
    return tuple(interrupted_states)


def validate_primary_mission_action_interruption_evidence(
    *,
    state: GameState,
    action: MissionActionState,
    evidence_event: EventRecord,
) -> None:
    """Fail closed unless one referenced event supports the persisted interruption reason."""

    if action.status is not MissionActionStatus.INTERRUPTED:
        raise GameLifecycleError("Interruption evidence requires an interrupted Action.")
    payload = _event_payload(evidence_event)
    if payload.get("game_id") != state.game_id:
        raise GameLifecycleError("Primary Action interruption evidence game drifted.")
    component_by_model_id = {
        model.model_instance_id: unit.unit_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    supported_reasons: set[str] = set()
    if evidence_event.event_type in _MOVE_COMPLETION_EVENTS:
        raw_batch = payload.get("transition_batch")
        if type(raw_batch) is not dict:
            raise GameLifecycleError("Primary Action movement evidence requires transition_batch.")
        batch = BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, raw_batch)
        )
        supported_reasons.update(
            reason
            for displacement in batch.displacements
            if _model_matches_action(
                state=state,
                action=action,
                model_instance_id=displacement.model_instance_id,
                component_by_model_id=component_by_model_id,
            )
            if (
                reason := mission_action_interruption_reason_for_displacement(
                    displacement.displacement_kind
                )
            )
            is not None
        )
        relevant_removals = tuple(
            removal
            for removal in batch.removals
            if _model_matches_action(
                state=state,
                action=action,
                model_instance_id=removal.model_instance_id,
                component_by_model_id=component_by_model_id,
            )
        )
        removal_kinds = {removal.removal_kind for removal in relevant_removals}
        if relevant_removals:
            reason = (
                MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
                if removal_kinds == {BattlefieldRemovalKind.DESTROYED}
                else MISSION_ACTION_UNIT_LEFT_BATTLEFIELD_INTERRUPTION_REASON
            )
            if reason != MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON or {
                removal.model_instance_id for removal in relevant_removals
            } == _action_lineage_model_ids(state=state, action=action):
                supported_reasons.add(reason)
    elif evidence_event.event_type == PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT:
        departure = PrimaryBattlefieldDepartureState.from_payload(
            payload.get("primary_battlefield_departure_state")
        )
        if _departure_matches_action(state=state, action=action, departure=departure):
            if departure.removal_kind is BattlefieldRemovalKind.DESTROYED:
                if _departure_covers_action_lineage(
                    state=state,
                    action=action,
                    departure=departure,
                ):
                    supported_reasons.add(MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON)
            else:
                supported_reasons.add(MISSION_ACTION_UNIT_LEFT_BATTLEFIELD_INTERRUPTION_REASON)
    elif evidence_event.event_type == PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT:
        destruction = _unit_destruction_from_event(payload)
        if _destruction_matches_action(
            state=state,
            action=action,
            destruction=destruction,
        ):
            supported_reasons.add(MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON)
    elif evidence_event.event_type == "model_destroyed":
        raise GameLifecycleError(
            "Primary Action unit-destroyed interruption requires authoritative "
            "whole-lineage completion evidence."
        )
    else:
        raise GameLifecycleError("Primary Action interruption evidence type is unsupported.")
    if action.interrupted_reason not in supported_reasons:
        raise GameLifecycleError("Primary Action interruption evidence reason drifted.")


def _first_interruption_evidence(
    *,
    state: GameState,
    action: MissionActionState,
    event_records: tuple[EventRecord, ...],
) -> _InterruptionEvidence | None:
    start_order = _start_event_order(action=action, event_records=event_records)
    component_by_model_id = {
        model.model_instance_id: unit.unit_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    candidates: list[_InterruptionEvidence] = []
    destruction_completion_candidates: list[_InterruptionEvidence] = []
    for event_order, event in enumerate(event_records):
        if event_order <= start_order:
            continue
        if event.event_type not in {
            *_MOVE_COMPLETION_EVENTS,
            PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
            PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
        }:
            continue
        payload = _event_payload(event)
        if payload.get("game_id") != state.game_id:
            continue
        if event.event_type in _MOVE_COMPLETION_EVENTS:
            candidates.extend(
                _transition_evidence(
                    state=state,
                    action=action,
                    event=event,
                    event_order=event_order,
                    payload=payload,
                    component_by_model_id=component_by_model_id,
                )
            )
            continue
        if event.event_type == PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT:
            departure = PrimaryBattlefieldDepartureState.from_payload(
                payload.get("primary_battlefield_departure_state")
            )
            if _departure_matches_action(state=state, action=action, departure=departure) and (
                departure.removal_kind is not BattlefieldRemovalKind.DESTROYED
                or _departure_covers_action_lineage(
                    state=state,
                    action=action,
                    departure=departure,
                )
            ):
                candidates.append(
                    _InterruptionEvidence(
                        event_order=event_order,
                        event=event,
                        reason=(
                            MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
                            if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
                            else MISSION_ACTION_UNIT_LEFT_BATTLEFIELD_INTERRUPTION_REASON
                        ),
                        phase=_event_phase(payload),
                    )
                )
            continue
        destruction = _unit_destruction_from_event(payload)
        if _destruction_matches_action(
            state=state,
            action=action,
            destruction=destruction,
        ):
            destruction_completion_candidates.append(
                _InterruptionEvidence(
                    event_order=event_order,
                    event=event,
                    reason=MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
                    phase=_event_phase(payload),
                )
            )
    if destruction_completion_candidates:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.reason != MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
        ]
        candidates.extend(destruction_completion_candidates)
    if not candidates:
        return None
    return min(candidates, key=lambda evidence: evidence.event_order)


def _transition_evidence(
    *,
    state: GameState,
    action: MissionActionState,
    event: EventRecord,
    event_order: int,
    payload: dict[str, JsonValue],
    component_by_model_id: dict[str, str],
) -> tuple[_InterruptionEvidence, ...]:
    if (
        event.event_type == "movement_activation_completed"
        and payload.get("movement_phase_action") == "remain_stationary"
    ):
        return ()
    raw_batch = payload.get("transition_batch")
    if raw_batch is None:
        return ()
    if type(raw_batch) is not dict:
        raise GameLifecycleError("Move completion transition_batch must be an object.")
    batch = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_batch)
    )
    phase = _event_phase(payload)
    evidence: list[_InterruptionEvidence] = []
    displacement_reasons = {
        reason
        for displacement in batch.displacements
        if _model_matches_action(
            state=state,
            action=action,
            model_instance_id=displacement.model_instance_id,
            component_by_model_id=component_by_model_id,
        )
        if (
            reason := mission_action_interruption_reason_for_displacement(
                displacement.displacement_kind
            )
        )
        is not None
    }
    if len(displacement_reasons) > 1:
        raise GameLifecycleError("Move completion has conflicting Action interruption reasons.")
    if displacement_reasons:
        evidence.append(
            _InterruptionEvidence(
                event_order=event_order,
                event=event,
                reason=next(iter(displacement_reasons)),
                phase=phase,
            )
        )
    relevant_removals = tuple(
        removal
        for removal in batch.removals
        if _model_matches_action(
            state=state,
            action=action,
            model_instance_id=removal.model_instance_id,
            component_by_model_id=component_by_model_id,
        )
    )
    if relevant_removals:
        removal_kinds = {removal.removal_kind for removal in relevant_removals}
        reason = (
            MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
            if removal_kinds == {BattlefieldRemovalKind.DESTROYED}
            else MISSION_ACTION_UNIT_LEFT_BATTLEFIELD_INTERRUPTION_REASON
        )
        if reason != MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON or {
            removal.model_instance_id for removal in relevant_removals
        } == _action_lineage_model_ids(state=state, action=action):
            evidence.append(
                _InterruptionEvidence(
                    event_order=event_order,
                    event=event,
                    reason=reason,
                    phase=phase,
                )
            )
    return tuple(evidence)


def _start_event_order(
    *, action: MissionActionState, event_records: tuple[EventRecord, ...]
) -> int:
    matches = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "mission_action_started"
        and _nested_action_id(event) == action.action_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Started Primary Mission Action requires one authoritative start event."
        )
    return matches[0]


def _departure_matches_action(
    *,
    state: GameState,
    action: MissionActionState,
    departure: PrimaryBattlefieldDepartureState,
) -> bool:
    return (
        departure.game_id == state.game_id
        and bool(departure.departed_component_unit_instance_ids)
        and rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=action.unit_instance_id,
            second_unit_instance_id=departure.rules_unit_instance_id,
        )
    )


def _departure_covers_action_lineage(
    *,
    state: GameState,
    action: MissionActionState,
    departure: PrimaryBattlefieldDepartureState,
) -> bool:
    return set(departure.departed_component_unit_instance_ids) == (
        _action_lineage_component_ids(state=state, action=action)
    )


def _unit_destruction_from_event(
    payload: dict[str, JsonValue],
) -> PrimaryUnitDestructionState:
    raw_destruction = payload.get("primary_unit_destruction_state")
    if type(raw_destruction) is not dict:
        raise GameLifecycleError("Primary Action unit-destruction evidence state is malformed.")
    destruction = PrimaryUnitDestructionState.from_payload(
        cast(PrimaryUnitDestructionStatePayload, raw_destruction)
    )
    if (
        payload.get("game_id") != destruction.game_id
        or payload.get("battle_round") != destruction.battle_round
        or payload.get("active_player_id") != destruction.active_player_id
        or payload.get("phase") != destruction.phase
        or payload.get("source_model_destroyed_event_id")
        != destruction.source_model_destroyed_event_id
    ):
        raise GameLifecycleError("Primary Action unit-destruction evidence context drifted.")
    return destruction


def _destruction_matches_action(
    *,
    state: GameState,
    action: MissionActionState,
    destruction: PrimaryUnitDestructionState,
) -> bool:
    if destruction.game_id != state.game_id or destruction not in (
        state.primary_unit_destruction_states
    ):
        return False
    return _rules_unit_lineage_component_ids(
        state=state,
        unit_instance_id=destruction.destroyed_unit_instance_id,
    ) == _action_lineage_component_ids(state=state, action=action)


def _action_lineage_component_ids(
    *,
    state: GameState,
    action: MissionActionState,
) -> set[str]:
    return _rules_unit_lineage_component_ids(
        state=state,
        unit_instance_id=action.unit_instance_id,
    )


def _rules_unit_lineage_component_ids(
    *,
    state: GameState,
    unit_instance_id: str,
) -> set[str]:
    historical = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == unit_instance_id
    )
    if len(historical) > 1:
        raise GameLifecycleError("Primary Action historical rules-unit lineage is ambiguous.")
    if historical:
        return set(historical[0].component_unit_instance_ids)
    return {
        component_id
        for view in current_rules_unit_views_for_identity(
            state=state,
            unit_instance_id=unit_instance_id,
        )
        for component_id in view.component_unit_instance_ids
    }


def _action_lineage_model_ids(
    *,
    state: GameState,
    action: MissionActionState,
) -> set[str]:
    component_ids = _action_lineage_component_ids(state=state, action=action)
    return {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in component_ids
        for model in unit.own_models
    }


def _model_matches_action(
    *,
    state: GameState,
    action: MissionActionState,
    model_instance_id: str,
    component_by_model_id: dict[str, str],
) -> bool:
    component_id = component_by_model_id.get(model_instance_id)
    return component_id is not None and rules_unit_identities_share_lineage(
        state=state,
        first_unit_instance_id=action.unit_instance_id,
        second_unit_instance_id=component_id,
    )


def _nested_action_id(event: EventRecord) -> str | None:
    payload = _event_payload(event)
    nested = payload.get("mission_action_state")
    if type(nested) is not dict:
        return None
    action_id = nested.get("action_id")
    return action_id if type(action_id) is str else None


def _event_payload(event: EventRecord) -> dict[str, JsonValue]:
    if type(event.payload) is not dict:
        raise GameLifecycleError(f"{event.event_type} event payload must be an object.")
    return event.payload


def _event_phase(payload: dict[str, JsonValue]) -> BattlePhase:
    raw_phase = payload.get("phase")
    if type(raw_phase) is not str:
        raise GameLifecycleError("Primary Action interruption evidence phase is missing.")
    try:
        return BattlePhase(raw_phase)
    except ValueError as exc:
        raise GameLifecycleError("Primary Action interruption evidence phase is invalid.") from exc


__all__ = (
    "reconcile_primary_mission_action_interruptions",
    "validate_primary_mission_action_interruption_evidence",
)
