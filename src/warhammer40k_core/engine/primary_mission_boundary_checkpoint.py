from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attached_unit_formation import (
    AttachedUnitFormation,
    AttachedUnitFormationPayload,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    PersistingEffect,
    PersistingEffectPayload,
)
from warhammer40k_core.engine.event_log import (
    EventLog,
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PRIMARY_MISSION_ACTION_VANGUARD_EFFECT,
    MissionActionPriorUseEvidence,
    MissionActionTerrainModelInventoryEvidence,
    PrimaryMissionActionCompletionEvidence,
    PrimaryMissionActionStartEvidence,
    canonical_mission_action_prior_uses,
    canonical_terrain_model_inventory,
)
from warhammer40k_core.engine.primary_mission_action_start_authority import (
    capture_primary_mission_action_terrain_model_inventory,
    terrain_intersections_from_model_inventory,
    validate_primary_mission_action_terrain_model_inventory,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryCheckpointReference,
    PrimaryMissionBoundaryModelState,
    PrimaryMissionObjectiveControlModifierSource,
)
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    primary_mission_boundary_physical_event_model_ids,
    validate_primary_mission_boundary_physical_authority,
)
from warhammer40k_core.engine.primary_mission_boundary_unit_history_authority import (
    validate_primary_mission_boundary_unit_history_authority,
)
from warhammer40k_core.engine.primary_mission_objective_control_authority import (
    resolve_checkpoint_objective_control,
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    validate_primary_mission_oc_effect_event_authority,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex


def record_primary_mission_boundary_checkpoint(
    *,
    state: GameState,
    event_log: EventLog,
    boundary_kind: str,
    player_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> PrimaryMissionBoundaryCheckpointReference:
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Primary mission boundary checkpoint requires EventLog.")
    checkpoint = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind=boundary_kind,
        player_id=player_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    event = event_log.append(PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT, checkpoint.to_payload())
    return checkpoint.reference(event_id=event.event_id)


def capture_primary_mission_boundary_checkpoint(
    *,
    state: GameState,
    boundary_kind: str,
    player_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> PrimaryMissionBoundaryCheckpoint:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary mission boundary checkpoint requires GameState.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Primary mission boundary checkpoint requires RuntimeModifierRegistry."
        )
    if state.active_player_id is None or state.current_battle_phase is None:
        raise GameLifecycleError("Primary mission boundary checkpoint requires battle context.")
    if player_id != state.active_player_id or player_id not in state.player_ids:
        raise GameLifecycleError("Primary mission boundary checkpoint player drifted.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary mission boundary checkpoint requires battlefield state.")
    inventory = capture_primary_mission_action_terrain_model_inventory(
        state=state,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    modifier_sources = _objective_control_modifier_sources(
        state=state,
        runtime_modifier_registry=runtime_modifier_registry,
        applied_modifier_ids=_inventory_applied_oc_modifier_ids(inventory),
    )
    model_states = tuple(_boundary_model_state(state=state, row=row) for row in inventory)
    checkpoint = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=boundary_kind,
        game_id=state.game_id,
        player_id=player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=state.current_battle_phase.value,
        battlefield_id=battlefield.battlefield_id,
        model_states=model_states,
        attached_unit_formation_jsons=tuple(
            canonical_json(formation.to_payload())
            for army in state.army_definitions
            for formation in army.attached_units
        ),
        battle_shocked_unit_instance_ids=tuple(state.battle_shocked_unit_ids),
        advanced_unit_state_jsons=tuple(
            canonical_json(row.to_payload())
            for row in state.advanced_unit_states
            if row.player_id == player_id and row.battle_round == state.battle_round
        ),
        fell_back_unit_state_jsons=tuple(
            canonical_json(row.to_payload())
            for row in state.fell_back_unit_states
            if row.player_id == player_id and row.battle_round == state.battle_round
        ),
        shot_unit_instance_ids=(
            ()
            if state.current_battle_phase is not BattlePhase.SHOOTING
            or state.shooting_phase_state is None
            else state.shooting_phase_state.shot_unit_ids
        ),
        objective_control_modifier_sources=modifier_sources,
        active_primary_marker_jsons=tuple(
            canonical_json(marker.to_payload())
            for marker in state.primary_mission_progress_state.markers
            if marker.status is PrimaryMissionMarkerStatus.ACTIVE
        ),
        active_secondary_mission_ids=tuple(
            card.secondary_mission_id
            for card in state.secondary_mission_card_states
            if card.player_id == player_id and card.status is SecondaryMissionCardStatus.ACTIVE
        ),
        mission_action_prior_use_jsons=tuple(
            canonical_json(row.to_payload()) for row in _mission_action_prior_uses(state=state)
        ),
    )
    validate_primary_mission_boundary_checkpoint_modifier_sources(
        state=state,
        checkpoint=checkpoint,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    validate_primary_mission_boundary_checkpoint(
        state=state,
        checkpoint=checkpoint,
        validate_retained_same_turn_state=True,
    )
    return checkpoint


def validate_primary_mission_boundary_checkpoint_modifier_sources(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    expected = _objective_control_modifier_sources(
        state=state,
        runtime_modifier_registry=runtime_modifier_registry,
        applied_modifier_ids=_checkpoint_applied_oc_modifier_ids(checkpoint),
    )
    if checkpoint.objective_control_modifier_sources != expected:
        raise GameLifecycleError(
            "Primary mission boundary Objective Control modifier source drifted."
        )


def validate_primary_mission_boundary_checkpoint_runtime_source_registry(
    *,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    """Bind a persisted checkpoint's applied OC sources to the loaded registry."""
    if type(checkpoint) is not PrimaryMissionBoundaryCheckpoint:
        raise GameLifecycleError(
            "Primary mission boundary source validation requires a checkpoint."
        )
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Primary mission boundary source validation requires a RuntimeModifierRegistry."
        )
    _validate_checkpoint_modifier_source_registry(
        checkpoint=checkpoint,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def validate_primary_mission_boundary_checkpoint_source_registry(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    checkpoint_rows: list[tuple[int, EventRecord, PrimaryMissionBoundaryCheckpoint]] = []
    for checkpoint_index, event in enumerate(event_records):
        if event.event_type != PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT:
            continue
        checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(event.payload)
        checkpoint_rows.append((checkpoint_index, event, checkpoint))
        validate_primary_mission_oc_effect_event_authority(
            state=state,
            event_records=event_records,
            checkpoint_index=checkpoint_index,
            checkpoint=checkpoint,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        _validate_checkpoint_modifier_source_registry(
            checkpoint=checkpoint,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if (
            checkpoint.boundary_kind not in {"primary_scoring_commit", "objective_control"}
            and state.battle_round == checkpoint.battle_round
            and state.active_player_id == checkpoint.active_player_id
        ):
            validate_primary_mission_boundary_checkpoint_modifier_sources(
                state=state,
                checkpoint=checkpoint,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            _validate_current_checkpoint_oc_resolutions(
                state=state,
                checkpoint=checkpoint,
                runtime_modifier_registry=runtime_modifier_registry,
            )
    if checkpoint_rows:
        checkpoint_index, _event, checkpoint = checkpoint_rows[-1]
        validate_primary_mission_boundary_physical_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            checkpoint_index=checkpoint_index,
            checkpoint=checkpoint,
        )
    _validate_checkpoint_ownership(
        event_records=event_records,
        checkpoint_rows=tuple(checkpoint_rows),
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
    )


def _validate_checkpoint_ownership(
    *,
    event_records: tuple[EventRecord, ...],
    checkpoint_rows: tuple[tuple[int, EventRecord, PrimaryMissionBoundaryCheckpoint], ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    from warhammer40k_core.engine.mission_decisions import (
        START_MISSION_ACTION_DECISION_TYPE,
    )

    checkpoints_by_event_id = {
        event.event_id: (index, checkpoint) for index, event, checkpoint in checkpoint_rows
    }
    if len(checkpoints_by_event_id) != len(checkpoint_rows):
        raise GameLifecycleError("Primary mission checkpoint event identities are duplicated.")
    next_checkpoint_index_by_event_id = {
        event.event_id: (
            checkpoint_rows[position + 1][0]
            if position + 1 < len(checkpoint_rows)
            else len(event_records)
        )
        for position, (_index, event, _checkpoint) in enumerate(checkpoint_rows)
    }

    action_request_checkpoint_ids: set[str] = set()
    turn_end_checkpoint_ids: set[str] = set()
    for checkpoint_index, checkpoint_event, checkpoint in checkpoint_rows:
        if checkpoint.boundary_kind in {"turn_end", "objective_control", "primary_scoring_commit"}:
            if checkpoint.boundary_kind == "turn_end":
                turn_end_checkpoint_ids.add(checkpoint_event.event_id)
            continue
        if checkpoint_index + 1 >= len(event_records):
            raise GameLifecycleError("Primary mission Action checkpoint is orphaned.")
        request_event = event_records[checkpoint_index + 1]
        request = _checkpoint_owned_action_request(event=request_event)
        payload = request.payload
        if not isinstance(payload, dict) or (
            request.decision_type != START_MISSION_ACTION_DECISION_TYPE
            or request.actor_id != checkpoint.player_id
            or checkpoint.active_player_id != checkpoint.player_id
            or payload.get("game_id") != checkpoint.game_id
            or payload.get("player_id") != checkpoint.player_id
            or payload.get("battle_round") != checkpoint.battle_round
            or payload.get("phase") != checkpoint.phase
        ):
            raise GameLifecycleError("Primary mission Action checkpoint ownership drifted.")
        _validate_checkpoint_request_decision_authority(
            request=request,
            decision_records=decision_records,
            pending_decision_requests=pending_decision_requests,
        )
        action_request_checkpoint_ids.add(checkpoint_event.event_id)

    for request_index, event in enumerate(event_records):
        if event.event_type != "decision_requested" or not isinstance(event.payload, dict):
            continue
        if event.payload.get("decision_type") != START_MISSION_ACTION_DECISION_TYPE:
            continue
        if request_index == 0:
            raise GameLifecycleError("Primary mission Action request checkpoint is missing.")
        checkpoint_event = event_records[request_index - 1]
        owned = checkpoints_by_event_id.get(checkpoint_event.event_id)
        if owned is None or owned[1].boundary_kind != "action_request":
            raise GameLifecycleError("Primary mission Action request checkpoint is missing.")
        action_request_checkpoint_ids.add(checkpoint_event.event_id)

    vanguard_checkpoint_consumer_counts: dict[str, int] = {}
    for terminal_index, event in enumerate(event_records):
        if event.event_type not in {
            "mission_action_completed",
            "mission_action_completion_failed",
        } or not isinstance(event.payload, dict):
            continue
        raw_evidence = event.payload.get(PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY)
        if raw_evidence is None:
            continue
        evidence = PrimaryMissionActionCompletionEvidence.from_payload(raw_evidence)
        reference = evidence.boundary_checkpoint
        if reference is None:
            continue
        owned = checkpoints_by_event_id.get(reference.checkpoint_event_id)
        if owned is None:
            raise GameLifecycleError("Vanguard checkpoint consumer references a missing event.")
        checkpoint_index, checkpoint = owned
        if (
            evidence.effect_descriptor != PRIMARY_MISSION_ACTION_VANGUARD_EFFECT
            or checkpoint.boundary_kind != "turn_end"
            or checkpoint.reference(event_id=reference.checkpoint_event_id) != reference
            or checkpoint_index >= terminal_index
            or terminal_index >= next_checkpoint_index_by_event_id[reference.checkpoint_event_id]
            or checkpoint.game_id != evidence.game_id
            or checkpoint.player_id != evidence.player_id
            or checkpoint.active_player_id != evidence.active_player_id
            or checkpoint.battle_round != evidence.battle_round
            or checkpoint.phase != evidence.phase
        ):
            raise GameLifecycleError("Vanguard checkpoint consumer ownership drifted.")
        vanguard_checkpoint_consumer_counts[reference.checkpoint_event_id] = (
            vanguard_checkpoint_consumer_counts.get(reference.checkpoint_event_id, 0) + 1
        )

    if any(count != 1 for count in vanguard_checkpoint_consumer_counts.values()):
        raise GameLifecycleError("Vanguard checkpoint consumer inventory is duplicated.")
    vanguard_checkpoint_ids = set(vanguard_checkpoint_consumer_counts)
    owned_checkpoint_ids = action_request_checkpoint_ids | vanguard_checkpoint_ids
    all_checkpoint_ids = set(checkpoints_by_event_id)
    if owned_checkpoint_ids != all_checkpoint_ids:
        orphaned = all_checkpoint_ids.difference(owned_checkpoint_ids)
        if orphaned <= turn_end_checkpoint_ids:
            raise GameLifecycleError("Primary mission turn-end checkpoint is orphaned.")
        raise GameLifecycleError("Primary mission Action checkpoint is orphaned.")


def _checkpoint_owned_action_request(*, event: EventRecord) -> DecisionRequest:
    if event.event_type != "decision_requested" or not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission Action checkpoint is orphaned.")
    try:
        return DecisionRequest.from_payload(cast(DecisionRequestPayload, event.payload))
    except (DecisionError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Primary mission Action checkpoint request is invalid.") from exc


def _validate_checkpoint_request_decision_authority(
    *,
    request: DecisionRequest,
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    authoritative = tuple(
        record.request
        for record in decision_records
        if record.request.request_id == request.request_id
    ) + tuple(
        pending for pending in pending_decision_requests if pending.request_id == request.request_id
    )
    if len(authoritative) != 1 or authoritative[0] != request:
        raise GameLifecycleError(
            "Primary mission Action checkpoint request lacks exact decision authority."
        )


def primary_mission_boundary_checkpoint_for_reference(
    *,
    event_records: tuple[EventRecord, ...],
    reference: PrimaryMissionBoundaryCheckpointReference,
) -> tuple[PrimaryMissionBoundaryCheckpoint, int]:
    if type(reference) is not PrimaryMissionBoundaryCheckpointReference:
        raise GameLifecycleError("Primary mission boundary checkpoint reference is invalid.")
    matches = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_id == reference.checkpoint_event_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Primary mission boundary checkpoint event is missing.")
    index, event = matches[0]
    if event.event_type != PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT:
        raise GameLifecycleError("Primary mission boundary checkpoint event type drifted.")
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(event.payload)
    if (
        checkpoint.checkpoint_id != reference.checkpoint_id
        or checkpoint.checkpoint_hash != reference.checkpoint_hash
    ):
        raise GameLifecycleError("Primary mission boundary checkpoint reference drifted.")
    return checkpoint, index


def primary_mission_boundary_checkpoint_for_request(
    *,
    event_records: tuple[EventRecord, ...],
    request_id: str,
) -> tuple[PrimaryMissionBoundaryCheckpointReference, PrimaryMissionBoundaryCheckpoint, int]:
    request_matches = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "decision_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == request_id
    )
    if len(request_matches) != 1:
        raise GameLifecycleError(
            "Primary mission Action request lacks one decision_requested event."
        )
    request_index, _request_event = request_matches[0]
    if request_index == 0:
        raise GameLifecycleError(
            "Primary mission Action request lacks its boundary checkpoint event."
        )
    checkpoint_event = event_records[request_index - 1]
    if checkpoint_event.event_type != PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT:
        raise GameLifecycleError(
            "Primary mission Action request lacks its boundary checkpoint event."
        )
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(checkpoint_event.payload)
    reference = checkpoint.reference(event_id=checkpoint_event.event_id)
    return reference, checkpoint, request_index - 1


def validate_primary_mission_action_request_checkpoint(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_id: str,
    reference: PrimaryMissionBoundaryCheckpointReference,
    player_id: str,
    battle_round: int,
    phase: str,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> PrimaryMissionBoundaryCheckpoint:
    expected_reference, checkpoint, checkpoint_index = (
        primary_mission_boundary_checkpoint_for_request(
            event_records=event_records,
            request_id=request_id,
        )
    )
    if reference != expected_reference:
        raise GameLifecycleError("Primary mission Action request checkpoint drifted.")
    if (
        checkpoint.boundary_kind != "action_request"
        or checkpoint.game_id != state.game_id
        or checkpoint.player_id != player_id
        or checkpoint.active_player_id != player_id
        or checkpoint.battle_round != battle_round
        or checkpoint.phase != phase
    ):
        raise GameLifecycleError("Primary mission Action request checkpoint context drifted.")
    validate_primary_mission_boundary_checkpoint(
        state=state,
        checkpoint=checkpoint,
        validate_retained_same_turn_state=True,
    )
    validate_primary_mission_boundary_physical_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )
    validate_primary_mission_boundary_unit_history_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )
    validate_primary_mission_oc_effect_event_authority(
        state=state,
        event_records=event_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    request_event = event_records[checkpoint_index + 1]
    if not isinstance(request_event.payload, dict) or (
        request_event.payload.get("actor_id") != player_id
        or request_event.payload.get("decision_type") != "start_mission_action"
    ):
        raise GameLifecycleError("Primary mission Action request checkpoint closure drifted.")
    return checkpoint


def validate_primary_mission_vanguard_checkpoint(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    reference: PrimaryMissionBoundaryCheckpointReference,
    player_id: str,
    battle_round: int,
    phase: str,
    terminal_event_id: str,
    objective_control_record_id: str,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> PrimaryMissionBoundaryCheckpoint:
    checkpoint, checkpoint_index = primary_mission_boundary_checkpoint_for_reference(
        event_records=event_records,
        reference=reference,
    )
    event_index_by_id = {event.event_id: index for index, event in enumerate(event_records)}
    terminal_index = event_index_by_id.get(terminal_event_id)
    if terminal_index is None or checkpoint_index >= terminal_index:
        raise GameLifecycleError("Vanguard boundary checkpoint ordering drifted.")
    objective_boundaries = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "end_boundary_objective_control_determined"
        and isinstance(event.payload, dict)
        and event.payload.get("game_id") == checkpoint.game_id
        and event.payload.get("battle_round") == battle_round
        and event.payload.get("phase") == phase
        and event.payload.get("record_ids") == [objective_control_record_id]
    )
    if len(objective_boundaries) != 1 or objective_boundaries[0] >= checkpoint_index:
        raise GameLifecycleError("Vanguard boundary checkpoint ordering drifted.")
    if (
        checkpoint.boundary_kind != "turn_end"
        or checkpoint.game_id != state.game_id
        or checkpoint.player_id != player_id
        or checkpoint.active_player_id != player_id
        or checkpoint.battle_round != battle_round
        or checkpoint.phase != phase
    ):
        raise GameLifecycleError("Vanguard boundary checkpoint context drifted.")
    validate_primary_mission_boundary_checkpoint(
        state=state,
        checkpoint=checkpoint,
        validate_retained_same_turn_state=True,
    )
    validate_primary_mission_boundary_physical_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )
    validate_primary_mission_boundary_unit_history_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )
    validate_primary_mission_oc_effect_event_authority(
        state=state,
        event_records=event_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    if any(
        primary_mission_boundary_physical_event_model_ids(event)
        for event in event_records[checkpoint_index + 1 : terminal_index]
    ):
        raise GameLifecycleError("Vanguard boundary has an intervening physical mutation.")
    return checkpoint


def validate_primary_mission_action_start_checkpoint_evidence(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_id: str,
    evidence: PrimaryMissionActionStartEvidence,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> PrimaryMissionBoundaryCheckpoint:
    checkpoint = validate_primary_mission_action_request_checkpoint(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_id=request_id,
        reference=evidence.boundary_checkpoint,
        player_id=evidence.player_id,
        battle_round=evidence.battle_round,
        phase=evidence.phase,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    expected_advanced = _unit_ids_from_state_jsons(checkpoint.advanced_unit_state_jsons)
    expected_fell_back = _unit_ids_from_state_jsons(checkpoint.fell_back_unit_state_jsons)
    action_identity_ids = set(evidence.unit_identity_ids)
    authority = evidence.start_authority
    checkpoint_intersections = terrain_model_inventory_from_checkpoint(checkpoint)
    expected_selected_terrain = tuple(
        row
        for row in terrain_intersections_from_model_inventory(checkpoint_intersections)
        if row.owner_player_id == evidence.player_id
        and row.rules_unit_instance_id == evidence.unit_instance_id
        and row.component_unit_instance_id in evidence.component_unit_instance_ids
    )
    if (
        authority.candidate_units
        or authority.terrain_model_inventory
        or authority.battle_shocked_unit_instance_ids
        or authority.advanced_unit_instance_ids
        or authority.fell_back_unit_instance_ids
        or authority.shot_unit_instance_ids
        or authority.active_secondary_mission_ids
        or evidence.battle_shocked
        is not bool(action_identity_ids.intersection(checkpoint.battle_shocked_unit_instance_ids))
        or evidence.advanced_unit_instance_ids
        != tuple(sorted(action_identity_ids.intersection(expected_advanced)))
        or evidence.fell_back_unit_instance_ids
        != tuple(sorted(action_identity_ids.intersection(expected_fell_back)))
        or evidence.shot_unit_instance_ids
        != tuple(sorted(action_identity_ids.intersection(checkpoint.shot_unit_instance_ids)))
        or evidence.active_primary_mission_marker_ids
        != active_primary_marker_ids_from_checkpoint(checkpoint)
        or evidence.prior_uses != mission_action_prior_uses_from_checkpoint(checkpoint)
        or (
            evidence.target_policy == "terrain_area_in_enemy_territory"
            and evidence.terrain_intersections != expected_selected_terrain
        )
    ):
        raise GameLifecycleError(
            "Primary Mission Action start evidence drifted from its boundary checkpoint."
        )
    return checkpoint


def validate_primary_mission_vanguard_checkpoint_evidence(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    terminal_event_id: str,
    evidence: PrimaryMissionActionCompletionEvidence,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> PrimaryMissionBoundaryCheckpoint:
    reference = evidence.boundary_checkpoint
    if reference is None:
        raise GameLifecycleError("Vanguard completion lacks its boundary checkpoint.")
    objective_control_record_id = evidence.objective_control_record_id
    if objective_control_record_id is None:
        raise GameLifecycleError("Vanguard completion lacks Objective Control authority.")
    checkpoint = validate_primary_mission_vanguard_checkpoint(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        reference=reference,
        player_id=evidence.player_id,
        battle_round=evidence.battle_round,
        phase=evidence.phase,
        terminal_event_id=terminal_event_id,
        objective_control_record_id=objective_control_record_id,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    if evidence.terrain_model_inventory != terrain_model_inventory_from_checkpoint(
        checkpoint
    ) or evidence.action_unit_battle_shocked is not bool(
        set(evidence.action_unit_identity_ids).intersection(
            checkpoint.battle_shocked_unit_instance_ids
        )
    ):
        raise GameLifecycleError(
            "Vanguard completion evidence drifted from its end-turn checkpoint."
        )
    return checkpoint


def validate_primary_mission_boundary_checkpoint(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    validate_retained_same_turn_state: bool,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None or checkpoint.battlefield_id != battlefield.battlefield_id:
        raise GameLifecycleError("Primary mission boundary checkpoint battlefield drifted.")
    inventory = terrain_model_inventory_from_checkpoint(checkpoint)
    validate_primary_mission_action_terrain_model_inventory(state=state, values=inventory)
    _validate_attached_unit_inventory(state=state, checkpoint=checkpoint)
    _validate_marker_inventory(state=state, checkpoint=checkpoint)
    _validate_action_opportunity_history(state=state, checkpoint=checkpoint)
    if validate_retained_same_turn_state:
        _validate_retained_same_turn_state(state=state, checkpoint=checkpoint)


def terrain_model_inventory_from_checkpoint(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[MissionActionTerrainModelInventoryEvidence, ...]:
    return canonical_terrain_model_inventory(
        tuple(
            MissionActionTerrainModelInventoryEvidence(
                owner_player_id=row.owner_player_id,
                rules_unit_instance_id=row.rules_unit_instance_id,
                component_unit_instance_id=row.component_unit_instance_id,
                model_instance_id=row.model_instance_id,
                wounds_remaining_at_boundary=row.wounds_remaining,
                model_placement_json=row.model_placement_json,
                source_objective_control_json=row.source_objective_control_json,
                resolved_objective_control_json=row.resolved_objective_control_json,
                logical_terrain_area_ids=row.logical_terrain_area_ids,
            )
            for row in checkpoint.model_states
        )
    )


def active_primary_marker_ids_from_checkpoint(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            PrimaryMissionMarkerState.from_payload(_json_object(value)).marker_id
            for value in checkpoint.active_primary_marker_jsons
        )
    )


def mission_action_prior_uses_from_checkpoint(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[MissionActionPriorUseEvidence, ...]:
    return canonical_mission_action_prior_uses(
        tuple(
            MissionActionPriorUseEvidence.from_payload(_json_object(value))
            for value in checkpoint.mission_action_prior_use_jsons
        )
    )


def _mission_action_prior_uses(*, state: GameState) -> tuple[MissionActionPriorUseEvidence, ...]:
    from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
        primary_mission_action_prior_use_evidence,
    )

    return primary_mission_action_prior_use_evidence(
        state=state,
        actions=tuple(state.mission_action_states),
    )


def _boundary_model_state(
    *,
    state: GameState,
    row: MissionActionTerrainModelInventoryEvidence,
) -> PrimaryMissionBoundaryModelState:
    alive = row.wounds_remaining_at_boundary > 0
    placement = row.model_placement_json
    reserve_model_ids = set(state.unarrived_reserve_model_ids())
    embarked_model_ids = set(state.embarked_model_ids())
    if placement is not None:
        presence = "battlefield"
    elif not alive:
        presence = "destroyed"
    elif row.model_instance_id in embarked_model_ids:
        presence = "embarked"
    elif row.model_instance_id in reserve_model_ids:
        presence = "reserves"
    else:
        presence = "off_battlefield"
    return PrimaryMissionBoundaryModelState(
        owner_player_id=row.owner_player_id,
        rules_unit_instance_id=row.rules_unit_instance_id,
        component_unit_instance_id=row.component_unit_instance_id,
        model_instance_id=row.model_instance_id,
        alive=alive,
        wounds_remaining=row.wounds_remaining_at_boundary,
        presence=presence,
        model_placement_json=placement,
        source_objective_control_json=row.source_objective_control_json,
        resolved_objective_control_json=row.resolved_objective_control_json,
        logical_terrain_area_ids=row.logical_terrain_area_ids,
    )


def _objective_control_modifier_sources(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry,
    applied_modifier_ids: tuple[str, ...],
) -> tuple[PrimaryMissionObjectiveControlModifierSource, ...]:
    bindings_by_id = {
        binding.modifier_id: binding
        for binding in runtime_modifier_registry.all_objective_control_bindings()
    }
    effects_by_id = {
        effect.effect_id: effect
        for effect in state.persisting_effects
        if _is_generic_objective_control_effect(effect)
    }
    duplicate_source_ids = set(bindings_by_id).intersection(effects_by_id)
    if duplicate_source_ids:
        raise GameLifecycleError(
            "Primary mission Objective Control source identities are duplicated."
        )
    unknown_ids = set(applied_modifier_ids).difference(bindings_by_id, effects_by_id)
    if unknown_ids:
        raise GameLifecycleError(
            "Primary mission boundary Objective Control modifier source is unregistered."
        )
    rows: list[PrimaryMissionObjectiveControlModifierSource] = []
    for modifier_id in applied_modifier_ids:
        binding = bindings_by_id.get(modifier_id)
        if binding is not None:
            rows.append(
                PrimaryMissionObjectiveControlModifierSource(
                    modifier_id=binding.modifier_id,
                    source_id=binding.source_id,
                    source_effect_id=None,
                    source_effect_json=None,
                )
            )
            continue
        effect = effects_by_id[modifier_id]
        rows.append(
            PrimaryMissionObjectiveControlModifierSource(
                modifier_id=effect.effect_id,
                source_id=effect.source_rule_id,
                source_effect_id=effect.effect_id,
                source_effect_json=canonical_json(effect.to_payload()),
            )
        )
    return tuple(rows)


def _inventory_applied_oc_modifier_ids(
    inventory: tuple[MissionActionTerrainModelInventoryEvidence, ...],
) -> tuple[str, ...]:
    return _applied_oc_modifier_ids(
        tuple(
            (row.source_objective_control_json, row.resolved_objective_control_json)
            for row in inventory
        )
    )


def _checkpoint_applied_oc_modifier_ids(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[str, ...]:
    return _applied_oc_modifier_ids(
        tuple(
            (row.source_objective_control_json, row.resolved_objective_control_json)
            for row in checkpoint.model_states
        )
    )


def _applied_oc_modifier_ids(values: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    applied: set[str] = set()
    for source_json, resolved_json in values:
        source_ids = _json_string_list(
            _json_object(source_json),
            key="applied_modifier_ids",
        )
        resolved_ids = _json_string_list(
            _json_object(resolved_json),
            key="applied_modifier_ids",
        )
        applied.update(set(resolved_ids).difference(source_ids))
    return tuple(sorted(applied))


def _validate_checkpoint_modifier_source_registry(
    *,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    applied_ids = _checkpoint_applied_oc_modifier_ids(checkpoint)
    if tuple(row.modifier_id for row in checkpoint.objective_control_modifier_sources) != (
        applied_ids
    ):
        raise GameLifecycleError(
            "Primary mission boundary Objective Control applied-source inventory drifted."
        )
    bindings_by_id = {
        binding.modifier_id: binding
        for binding in runtime_modifier_registry.all_objective_control_bindings()
    }
    for source in checkpoint.objective_control_modifier_sources:
        if source.source_effect_id is None:
            binding = bindings_by_id.get(source.modifier_id)
            if binding is None or source.source_id != binding.source_id:
                raise GameLifecycleError(
                    "Primary mission boundary Objective Control modifier is unregistered."
                )
            continue
        effect_json = source.source_effect_json
        if effect_json is None:
            raise GameLifecycleError(
                "Primary mission boundary Objective Control effect source is incomplete."
            )
        effect = PersistingEffect.from_payload(
            cast(PersistingEffectPayload, _json_object(effect_json))
        )
        if (
            source.modifier_id != effect.effect_id
            or source.source_effect_id != effect.effect_id
            or source.source_id != effect.source_rule_id
            or not _is_generic_objective_control_effect(effect)
        ):
            raise GameLifecycleError(
                "Primary mission boundary Objective Control effect source drifted."
            )


def _validate_current_checkpoint_oc_resolutions(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    models_by_id = {
        model.model_instance_id: (unit.unit_instance_id, model)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    for row in checkpoint.model_states:
        unit_id, model = models_by_id[row.model_instance_id]
        resolved = resolve_checkpoint_objective_control(
            state=state,
            unit_instance_id=unit_id,
            model=model,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if canonical_json(resolved.to_payload()) != row.resolved_objective_control_json:
            raise GameLifecycleError(
                "Primary mission boundary Objective Control resolution drifted."
            )


def _is_generic_objective_control_effect(effect: PersistingEffect) -> bool:
    if not isinstance(effect.effect_payload, dict):
        return False
    payload = effect.effect_payload
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return False
    raw_effect = payload.get("effect")
    if not isinstance(raw_effect, dict) or raw_effect.get("kind") != "modify_characteristic":
        return False
    parameters = raw_effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Generic Objective Control effect parameters are invalid.")
    return any(
        isinstance(parameter, dict)
        and parameter.get("key") == "characteristic"
        and parameter.get("value") == "objective_control"
        for parameter in parameters
    )


def _validate_attached_unit_inventory(
    *, state: GameState, checkpoint: PrimaryMissionBoundaryCheckpoint
) -> None:
    formations = tuple(
        AttachedUnitFormation.from_payload(cast(AttachedUnitFormationPayload, _json_object(value)))
        for value in checkpoint.attached_unit_formation_jsons
    )
    starting = {
        (
            row.player_id,
            row.attached_unit_instance_id,
            row.component_unit_instance_ids,
        )
        for row in state.starting_attached_unit_records
    }
    owners = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for formation in formations:
        component_owners = {
            owners.get(unit_id) for unit_id in formation.component_unit_instance_ids
        }
        if len(component_owners) != 1 or None in component_owners:
            raise GameLifecycleError("Primary mission boundary attached-unit inventory drifted.")
        owner = next(iter(component_owners))
        if (
            owner,
            formation.attached_unit_instance_id,
            formation.component_unit_instance_ids,
        ) not in starting:
            raise GameLifecycleError("Primary mission boundary attached-unit inventory drifted.")
    rules_unit_ids = {row.rules_unit_instance_id for row in checkpoint.model_states}
    formation_ids = {row.attached_unit_instance_id for row in formations}
    if not formation_ids <= rules_unit_ids:
        raise GameLifecycleError("Primary mission boundary attached-unit identity drifted.")


def _validate_marker_inventory(
    *, state: GameState, checkpoint: PrimaryMissionBoundaryCheckpoint
) -> None:
    current_by_id = {
        marker.marker_id: marker for marker in state.primary_mission_progress_state.markers
    }
    for value in checkpoint.active_primary_marker_jsons:
        marker = PrimaryMissionMarkerState.from_payload(_json_object(value))
        current = current_by_id.get(marker.marker_id)
        if marker.status is not PrimaryMissionMarkerStatus.ACTIVE or current is None:
            raise GameLifecycleError("Primary mission boundary marker inventory drifted.")
        restored_current = replace(
            current,
            status=PrimaryMissionMarkerStatus.ACTIVE,
            removed_battle_round=None,
            removed_phase=None,
            removed_active_player_id=None,
            removal_source_id=None,
            removal_event_id=None,
            removal_result_id=None,
            removal_action_id=None,
        )
        if marker != restored_current:
            raise GameLifecycleError("Primary mission boundary marker inventory drifted.")


def _validate_action_opportunity_history(
    *, state: GameState, checkpoint: PrimaryMissionBoundaryCheckpoint
) -> None:
    for secondary_id in checkpoint.active_secondary_mission_ids:
        matches = tuple(
            card
            for card in state.secondary_mission_card_states
            if card.player_id == checkpoint.player_id
            and card.secondary_mission_id == secondary_id
            and (
                card.mode is SecondaryMissionCardMode.FIXED
                or card.battle_round == checkpoint.battle_round
            )
        )
        if len(matches) != 1:
            raise GameLifecycleError("Primary mission boundary secondary inventory drifted.")
    current_action_by_id = {action.action_id: action for action in state.mission_action_states}
    for row in mission_action_prior_uses_from_checkpoint(checkpoint):
        action = current_action_by_id.get(row.action_id)
        if action is None or (
            action.mission_action_id,
            action.player_id,
            action.battle_round_started,
            action.phase_started,
            action.unit_instance_id,
            action.target_id,
        ) != (
            row.mission_action_id,
            row.player_id,
            row.battle_round_started,
            row.phase_started,
            row.unit_instance_id,
            row.target_id,
        ):
            raise GameLifecycleError("Primary mission boundary prior Action inventory drifted.")


def _validate_retained_same_turn_state(
    *, state: GameState, checkpoint: PrimaryMissionBoundaryCheckpoint
) -> None:
    if (
        state.battle_round != checkpoint.battle_round
        or state.active_player_id != checkpoint.active_player_id
    ):
        return
    expected_advanced = tuple(
        sorted(
            canonical_json(row.to_payload())
            for row in state.advanced_unit_states
            if row.player_id == checkpoint.player_id and row.battle_round == checkpoint.battle_round
        )
    )
    expected_fell_back = tuple(
        sorted(
            canonical_json(row.to_payload())
            for row in state.fell_back_unit_states
            if row.player_id == checkpoint.player_id and row.battle_round == checkpoint.battle_round
        )
    )
    if not set(checkpoint.advanced_unit_state_jsons) <= set(expected_advanced) or not set(
        checkpoint.fell_back_unit_state_jsons
    ) <= set(expected_fell_back):
        raise GameLifecycleError("Primary mission boundary retained unit history drifted.")
    if (
        state.battle_round == checkpoint.battle_round
        and state.active_player_id == checkpoint.active_player_id
        and state.current_battle_phase is BattlePhase.SHOOTING
        and state.shooting_phase_state is not None
        and not set(checkpoint.shot_unit_instance_ids)
        <= set(state.shooting_phase_state.shot_unit_ids)
    ):
        raise GameLifecycleError("Primary mission boundary retained shot history drifted.")
    if (
        checkpoint.boundary_kind == "turn_end"
        and state.current_battle_phase is not None
        and state.current_battle_phase.value == checkpoint.phase
    ):
        _validate_retained_turn_end_model_state(state=state, checkpoint=checkpoint)


def _validate_retained_turn_end_model_state(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary mission turn-end checkpoint battlefield drifted.")
    current_models = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if set(current_models) != {row.model_instance_id for row in checkpoint.model_states}:
        raise GameLifecycleError("Primary mission turn-end checkpoint model inventory drifted.")
    reserve_ids = set(state.unarrived_reserve_model_ids())
    embarked_ids = set(state.embarked_model_ids())
    for row in checkpoint.model_states:
        model = current_models[row.model_instance_id]
        placement = battlefield.model_placement_or_none(row.model_instance_id)
        alive = model.wounds_remaining > 0
        if placement is not None:
            presence = "battlefield"
            placement_json = canonical_json(placement.to_payload())
        elif not alive:
            presence = "destroyed"
            placement_json = None
        elif row.model_instance_id in embarked_ids:
            presence = "embarked"
            placement_json = None
        elif row.model_instance_id in reserve_ids:
            presence = "reserves"
            placement_json = None
        else:
            presence = "off_battlefield"
            placement_json = None
        if (
            row.alive is not alive
            or row.wounds_remaining != model.wounds_remaining
            or row.presence != presence
            or row.model_placement_json != placement_json
        ):
            raise GameLifecycleError(
                "Primary mission turn-end checkpoint retained model state drifted."
            )


def _json_object(value: str) -> dict[str, JsonValue]:
    try:
        decoded: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise GameLifecycleError("Primary mission boundary JSON is invalid.") from exc
    if not isinstance(decoded, dict):
        raise GameLifecycleError("Primary mission boundary JSON must encode an object.")
    decoded_object = cast(dict[object, object], decoded)
    return cast(dict[str, JsonValue], validate_json_value(decoded_object))


def _json_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list) or any(type(value) is not str for value in values):
        raise GameLifecycleError("Primary mission Objective Control source list is invalid.")
    return tuple(cast(list[str], values))


def _unit_ids_from_state_jsons(values: tuple[str, ...]) -> tuple[str, ...]:
    ids: list[str] = []
    for value in values:
        unit_id = _json_object(value).get("unit_instance_id")
        if type(unit_id) is not str:
            raise GameLifecycleError("Primary mission boundary movement state identity is invalid.")
        ids.append(unit_id)
    return tuple(sorted(ids))


__all__ = (
    "active_primary_marker_ids_from_checkpoint",
    "capture_primary_mission_boundary_checkpoint",
    "primary_mission_boundary_checkpoint_for_reference",
    "primary_mission_boundary_checkpoint_for_request",
    "record_primary_mission_boundary_checkpoint",
    "terrain_model_inventory_from_checkpoint",
    "validate_primary_mission_action_request_checkpoint",
    "validate_primary_mission_action_start_checkpoint_evidence",
    "validate_primary_mission_boundary_checkpoint",
    "validate_primary_mission_boundary_checkpoint_modifier_sources",
    "validate_primary_mission_boundary_checkpoint_runtime_source_registry",
    "validate_primary_mission_vanguard_checkpoint",
    "validate_primary_mission_vanguard_checkpoint_evidence",
)
