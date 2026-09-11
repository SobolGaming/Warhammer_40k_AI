from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    fight_rules_unit_movement_endpoint_from_completed_event,
    rules_unit_views_for_completed_move_event,
)
from warhammer40k_core.engine.mission_action_policies import (
    primary_mission_state_rule_for_id,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    RulesUnitObjectiveProximityWitness,
    rules_unit_objective_proximity_witness,
    rules_unit_objective_proximity_witness_from_placements,
)
from warhammer40k_core.engine.primary_mission_marker_integrity import (
    SURVEIL_MOVE_COMPLETION_EVENT_TYPES,
    SURVEIL_MOVE_PROCESSED_EVENT,
    surveil_move_event_unit_id,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryConsecrationDesignationState,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    primary_consecration_designation_id,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    current_rules_unit_views_for_identity,
    rules_unit_identities_share_lineage,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState
from warhammer40k_core.engine.sequencing import (
    SequencingParticipant,
    SequencingRequirement,
    SequencingRuleOrigin,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_CONSECRATION_STATE_RULE_ID = "consecrate-destroyer-becomes-consecration-unit"
_SURVEIL_STATE_RULE_ID = "surveil-remove-operation-markers-after-move"


def record_consecration_designation_for_destruction(
    *, state: GameState, destruction: PrimaryUnitDestructionState
) -> PrimaryConsecrationDesignationState | None:
    if type(destruction) is not PrimaryUnitDestructionState:
        raise GameLifecycleError("Consecration designation requires destruction evidence.")
    mission_setup = state.mission_setup
    attribution = destruction.destruction_attribution
    if (
        mission_setup is None
        or attribution is None
        or attribution.source_rules_unit_instance_id is None
        or destruction.source_model_destroyed_event_id is None
    ):
        return None
    player_id = attribution.destroying_player_id
    descriptor = primary_mission_state_rule_for_id(_CONSECRATION_STATE_RULE_ID)
    if mission_setup.primary_mission_id_for_player(player_id) != descriptor.primary_mission_id:
        return None
    source_rules_unit_id = attribution.source_rules_unit_instance_id
    if any(
        designation.owner_player_id == player_id
        and designation.status is PrimaryConsecrationStatus.ACTIVE
        and rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=designation.rules_unit_instance_id,
            second_unit_instance_id=source_rules_unit_id,
        )
        for designation in state.primary_mission_progress_state.consecration_designations
    ):
        return None
    current_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=source_rules_unit_id,
    )
    if len(current_views) != 1:
        raise GameLifecycleError("Consecration destroyer identity is ambiguous.")
    source_event_id = destruction.source_model_destroyed_event_id
    designation_id = primary_consecration_designation_id(
        game_id=state.game_id,
        owner_player_id=player_id,
        mission_id=descriptor.primary_mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.state_rule_id,
        rules_unit_instance_id=current_views[0].unit_instance_id,
        component_unit_instance_ids=current_views[0].component_unit_instance_ids,
        source_destruction_id=destruction.destruction_id,
        created_battle_round=destruction.battle_round,
        created_phase=destruction.phase,
        created_active_player_id=destruction.active_player_id,
        source_event_id=source_event_id,
    )
    designation = PrimaryConsecrationDesignationState(
        designation_id=designation_id,
        game_id=state.game_id,
        owner_player_id=player_id,
        mission_id=descriptor.primary_mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.state_rule_id,
        rules_unit_instance_id=current_views[0].unit_instance_id,
        component_unit_instance_ids=current_views[0].component_unit_instance_ids,
        source_destruction_id=destruction.destruction_id,
        created_battle_round=destruction.battle_round,
        created_phase=destruction.phase,
        created_active_player_id=destruction.active_player_id,
        source_event_id=source_event_id,
    )
    state.replace_primary_mission_progress_state(
        state.primary_mission_progress_state.add_consecration_designation(designation)
    )
    return designation


def surveil_move_marker_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
    trigger_event_id: str,
) -> tuple[TimingRuleCandidate, ...]:
    mission_setup = state.mission_setup
    if mission_setup is None or state.battlefield_state is None:
        return ()
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Surveil marker removal requires RuntimeModifierRegistry.")
    trigger_records = tuple(
        record
        for record in decisions.event_log.records
        if record.event_id == trigger_event_id
        and record.event_type in SURVEIL_MOVE_COMPLETION_EVENT_TYPES
        and not _surveil_move_already_processed(
            decisions=decisions,
            trigger_event_id=record.event_id,
        )
    )
    if not trigger_records:
        return ()
    candidates: list[TimingRuleCandidate] = []
    descriptor = primary_mission_state_rule_for_id(_SURVEIL_STATE_RULE_ID)
    for trigger in trigger_records:
        payload = trigger.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Move completion event payload must be an object.")
        if (
            payload.get("game_id") != state.game_id
            or payload.get("battle_round") != state.battle_round
            or payload.get("phase") != completed_phase.value
        ):
            continue
        if (
            trigger.event_type == "movement_activation_completed"
            and payload.get("movement_phase_action") == "remain_stationary"
        ):
            continue
        unit_id = surveil_move_event_unit_id(payload)
        if unit_id is None:
            continue
        mover_views = rules_unit_views_for_completed_move_event(
            state=state,
            event_type=trigger.event_type,
            unit_instance_id=unit_id,
        )
        mover_id = _canonical_move_event_rules_unit_id(
            event_type=trigger.event_type,
            event_unit_instance_id=unit_id,
            mover_views=mover_views,
        )
        mover_owner_ids = {view.owner_player_id for view in mover_views}
        if len(mover_owner_ids) != 1:
            raise GameLifecycleError("Surveil mover owner identity is ambiguous.")
        mover_owner_id = next(iter(mover_owner_ids))
        if (
            mission_setup.primary_mission_id_for_player(mover_owner_id)
            != descriptor.primary_mission_id
        ):
            continue
        component_ids = tuple(
            sorted(
                {
                    component_id
                    for view in mover_views
                    for component_id in view.component_unit_instance_ids
                }
            )
        )
        endpoint = (
            fight_rules_unit_movement_endpoint_from_completed_event(
                payload=payload,
                component_unit_instance_ids=component_ids,
            )
            if trigger.event_type == "fight_movement_completed"
            else None
        )
        objective_proximity_witness = (
            rules_unit_objective_proximity_witness(
                state=state,
                rules_unit_instance_id=mover_id,
            )
            if endpoint is None
            else rules_unit_objective_proximity_witness_from_placements(
                state=state,
                rules_unit_instance_id=mover_id,
                model_placements=endpoint.model_placements,
            )
        )
        objective_ids = objective_proximity_witness.objective_marker_ids
        marker_ids = tuple(
            marker.marker_id
            for marker in state.primary_mission_progress_state.markers
            if marker.status is PrimaryMissionMarkerStatus.ACTIVE
            and marker.owner_player_id != mover_owner_id
            and marker.marker_kind == "operation"
            and marker.objective_marker_id in objective_ids
        )
        if not marker_ids:
            continue
        candidate_payload = {
            "trigger_event_id": trigger.event_id,
            "moving_rules_unit_instance_id": mover_id,
            "objective_marker_ids": list(objective_ids),
            "objective_proximity_witness": objective_proximity_witness.to_payload(),
            "marker_ids": list(marker_ids),
        }
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=f"surveil-marker-removal:{trigger.event_id}:{mover_id}",
                    player_id=mover_owner_id,
                    source_rule_id=descriptor.source_id,
                    requirement=SequencingRequirement.MANDATORY,
                    origin=SequencingRuleOrigin.MISSION,
                    payload=validate_json_value(candidate_payload),
                ),
                activate=partial(
                    _remove_surveil_markers,
                    state=state,
                    decisions=decisions,
                    completed_phase=completed_phase,
                    trigger=trigger,
                    mover_id=mover_id,
                    mover_owner_id=mover_owner_id,
                    objective_proximity_witness=objective_proximity_witness,
                    marker_ids=marker_ids,
                ),
            )
        )
    return tuple(candidates)


def resume_surveil_marker_candidate(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    trigger_event_id: str,
    participant: SequencingParticipant,
) -> TimingRuleCandidate | None:
    descriptor = primary_mission_state_rule_for_id(_SURVEIL_STATE_RULE_ID)
    payload = participant.payload
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "trigger_event_id",
            "moving_rules_unit_instance_id",
            "objective_marker_ids",
            "objective_proximity_witness",
            "marker_ids",
        }
        or payload["trigger_event_id"] != trigger_event_id
        or type(payload["moving_rules_unit_instance_id"]) is not str
        or not isinstance(payload["marker_ids"], list)
        or not payload["marker_ids"]
        or any(type(identifier) is not str for identifier in payload["marker_ids"])
        or participant.source_rule_id != descriptor.source_id
        or participant.requirement is not SequencingRequirement.MANDATORY
        or participant.origin is not SequencingRuleOrigin.MISSION
        or participant.player_id not in state.player_ids
        or participant.participant_id
        != f"surveil-marker-removal:{trigger_event_id}:{payload['moving_rules_unit_instance_id']}"
    ):
        raise GameLifecycleError("Captured Surveil marker rule source identity drift.")
    if participant != SequencingParticipant(
        participant_id=participant.participant_id,
        player_id=participant.player_id,
        source_rule_id=descriptor.source_id,
        requirement=SequencingRequirement.MANDATORY,
        origin=SequencingRuleOrigin.MISSION,
        payload=payload,
    ):
        raise GameLifecycleError("Captured Surveil participant classification drift.")
    witness = RulesUnitObjectiveProximityWitness.from_payload(
        payload["objective_proximity_witness"]
    )
    if (
        witness.rules_unit_instance_id != payload["moving_rules_unit_instance_id"]
        or list(witness.objective_marker_ids) != payload["objective_marker_ids"]
    ):
        raise GameLifecycleError("Captured Surveil mover witness drift.")
    events = tuple(
        event for event in decisions.event_log.records if event.event_id == trigger_event_id
    )
    if len(events) != 1 or events[0].event_type not in SURVEIL_MOVE_COMPLETION_EVENT_TYPES:
        raise GameLifecycleError("Captured Surveil rule lacks its source move.")
    if _surveil_move_already_processed(decisions=decisions, trigger_event_id=trigger_event_id):
        return None
    return TimingRuleCandidate(
        participant=participant,
        activate=partial(
            _remove_surveil_markers,
            state=state,
            decisions=decisions,
            completed_phase=completed_phase,
            trigger=events[0],
            mover_id=payload["moving_rules_unit_instance_id"],
            mover_owner_id=participant.player_id,
            objective_proximity_witness=witness,
            marker_ids=tuple(cast(list[str], payload["marker_ids"])),
        ),
    )


def _remove_surveil_markers(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    trigger: EventRecord,
    mover_id: str,
    mover_owner_id: str,
    objective_proximity_witness: RulesUnitObjectiveProximityWitness,
    marker_ids: tuple[str, ...],
) -> None:
    descriptor = primary_mission_state_rule_for_id(_SURVEIL_STATE_RULE_ID)
    objective_ids = objective_proximity_witness.objective_marker_ids
    removed: list[PrimaryMissionMarkerState] = []
    for marker in state.primary_mission_progress_state.markers:
        if (
            marker.marker_id not in marker_ids
            or marker.status is not PrimaryMissionMarkerStatus.ACTIVE
            or marker.owner_player_id == mover_owner_id
            or marker.marker_kind != "operation"
            or marker.objective_marker_id not in objective_ids
        ):
            continue
        removed_marker = marker.removed(
            battle_round=state.battle_round,
            phase=completed_phase.value,
            active_player_id=_active_player_id(state),
            source_id=descriptor.source_id,
            event_id=trigger.event_id,
        )
        state.replace_primary_mission_progress_state(
            state.primary_mission_progress_state.replace_marker(removed_marker)
        )
        removed.append(removed_marker)
    decisions.event_log.append(
        SURVEIL_MOVE_PROCESSED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": completed_phase.value,
            "player_id": mover_owner_id,
            "moving_rules_unit_instance_id": mover_id,
            "moving_rules_unit_objective_proximity_witness": (
                objective_proximity_witness.to_payload()
            ),
            "objective_marker_ids": list(objective_ids),
            "removed_primary_mission_markers": [marker.to_payload() for marker in removed],
            "trigger_event_id": trigger.event_id,
            "trigger_event_type": trigger.event_type,
            "source_id": descriptor.source_id,
        },
    )


def _surveil_move_already_processed(
    *, decisions: DecisionController, trigger_event_id: str
) -> bool:
    return any(
        record.event_type == SURVEIL_MOVE_PROCESSED_EVENT
        and isinstance(record.payload, dict)
        and record.payload.get("trigger_event_id") == trigger_event_id
        for record in decisions.event_log.records
    )


def _canonical_move_event_rules_unit_id(
    *,
    event_type: str,
    event_unit_instance_id: str,
    mover_views: tuple[RulesUnitView, ...],
) -> str:
    if event_type == "fight_movement_completed" or len(mover_views) != 1:
        return event_unit_instance_id
    return mover_views[0].unit_instance_id


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Primary mission state runtime requires active player.")
    return state.active_player_id


__all__ = (
    "record_consecration_designation_for_destruction",
    "surveil_move_marker_candidates",
)
