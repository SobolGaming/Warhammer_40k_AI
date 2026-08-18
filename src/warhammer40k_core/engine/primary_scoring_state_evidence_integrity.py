from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import mission_logical_terrain_areas
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryConsecrationDesignationState,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
)
from warhammer40k_core.engine.primary_scoring_action_policy import (
    PrimaryScoringActionPolicy,
    primary_scoring_action_policies_by_id,
)
from warhammer40k_core.engine.primary_scoring_history_evidence import (
    validate_primary_scoring_destruction_history_authority,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.actions import MissionActionState
    from warhammer40k_core.engine.battlefield_state import ModelPlacement
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_scoring_state_evidence import (
        PrimaryScoringStateEvidence,
    )
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex


_OBJECTIVE_CONTROL_TIMING_ORDER = {
    ObjectiveControlTiming.TURN_START: 0,
    ObjectiveControlTiming.PHASE_END: 1,
    ObjectiveControlTiming.TURN_END: 2,
}


def validate_primary_scoring_boundary_context(
    *,
    mission_setup: MissionSetup,
    turn_order: tuple[str, ...],
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> None:
    """Derive whether a record is the actual configured end-of-battle boundary."""
    if not end_of_battle:
        return
    from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
    from warhammer40k_core.engine.phase import BattlePhase

    policies = mission_scoring_policies_from_setup(mission_setup)
    if (
        record.battle_round != policies.game_length_battle_rounds
        or record.active_player_id != turn_order[-1]
        or record.phase != BattlePhase.FIGHT.value
        or record.timing is not ObjectiveControlTiming.TURN_END
    ):
        raise GameLifecycleError(
            "End-of-battle Primary scoring requires the last player's turn-end record "
            "at the final Fight-phase TURN_END boundary."
        )


def validate_primary_scoring_action_boundary(
    *,
    action: MissionActionState,
    policy: PrimaryScoringActionPolicy,
    record: ObjectiveControlRecord,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> None:
    """Reject Action states that could not exist at the scoring boundary."""
    from warhammer40k_core.engine.actions import MissionActionStatus

    start_key = _event_boundary_key(
        label="Primary scoring state Action start",
        battle_round=action.battle_round_started,
        active_player_id=action.player_id,
        phase=action.phase_started,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )
    record_key = _record_boundary_key(
        record=record,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )
    if start_key > record_key:
        raise GameLifecycleError(
            "Primary scoring state Action start cannot come from a future boundary."
        )

    if action.status is MissionActionStatus.COMPLETED:
        if action.completed_battle_round is None or action.completed_phase is None:
            raise GameLifecycleError(
                "Primary scoring completed Action requires completion context."
            )
        completion_key = _action_completion_key(
            action=action,
            policy=policy,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        if completion_key < start_key:
            raise GameLifecycleError(
                "Primary scoring state Action completion cannot precede its start."
            )
        if completion_key > record_key:
            raise GameLifecycleError(
                "Primary scoring state Action completion cannot come from a future boundary."
            )
        return

    if action.status is not MissionActionStatus.STARTED:
        return
    if policy.completion_timing == "immediate":
        raise GameLifecycleError("Primary scoring state cannot retain a started immediate Action.")
    if policy.completion_timing != "turn_end":
        raise GameLifecycleError("Primary scoring state Action completion timing is unsupported.")
    expiry_key = _boundary_key(
        label="Primary scoring state Action expiry",
        battle_round=action.battle_round_started,
        active_player_id=action.player_id,
        phase=battle_phase_sequence[-1],
        timing=ObjectiveControlTiming.TURN_END,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )
    if record_key >= expiry_key:
        raise GameLifecycleError("Primary scoring state cannot retain an expired started Action.")


def validate_primary_scoring_progress_boundary(
    *,
    progress: PrimaryMissionProgressState,
    record: ObjectiveControlRecord,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> None:
    """Reject persistent mission progress created or mutated after the boundary."""
    for marker in progress.markers:
        created_key = _optional_event_boundary_key(
            label="Primary scoring mission marker creation",
            battle_round=marker.created_battle_round,
            active_player_id=marker.created_active_player_id,
            phase=marker.created_phase,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        _reject_future_key(
            label="Primary scoring mission marker creation",
            key=created_key,
            record=record,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        removed_key = _optional_event_boundary_key(
            label="Primary scoring mission marker removal",
            battle_round=marker.removed_battle_round,
            active_player_id=marker.removed_active_player_id,
            phase=marker.removed_phase,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        _reject_future_key(
            label="Primary scoring mission marker removal",
            key=removed_key,
            record=record,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        if created_key is not None and removed_key is not None and removed_key < created_key:
            raise GameLifecycleError(
                "Primary scoring mission marker removal cannot precede creation."
            )

    for selection in progress.condemned_selections:
        selection_key = _turn_key(
            label="Primary scoring condemned selection",
            battle_round=selection.battle_round,
            active_player_id=selection.active_player_id,
            turn_order=turn_order,
        )
        record_turn_key = _turn_key(
            label="Primary scoring ObjectiveControlRecord",
            battle_round=record.battle_round,
            active_player_id=record.active_player_id,
            turn_order=turn_order,
        )
        if selection_key > record_turn_key:
            raise GameLifecycleError(
                "Primary scoring condemned selection cannot come from a future turn."
            )

    for designation in progress.consecration_designations:
        created_key = _event_boundary_key(
            label="Primary scoring consecration creation",
            battle_round=designation.created_battle_round,
            active_player_id=designation.created_active_player_id,
            phase=designation.created_phase,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        _reject_future_key(
            label="Primary scoring consecration creation",
            key=created_key,
            record=record,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        consumed_key = _optional_event_boundary_key(
            label="Primary scoring consecration consumption",
            battle_round=designation.consumed_battle_round,
            active_player_id=designation.consumed_active_player_id,
            phase=designation.consumed_phase,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        _reject_future_key(
            label="Primary scoring consecration consumption",
            key=consumed_key,
            record=record,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        if consumed_key is not None and consumed_key < created_key:
            raise GameLifecycleError(
                "Primary scoring consecration consumption cannot precede creation."
            )
        if designation.last_resolved_battle_round is not None:
            if designation.last_resolved_active_player_id is None:
                raise GameLifecycleError(
                    "Primary scoring consecration resolution requires an active player."
                )
            resolution_key = _boundary_key(
                label="Primary scoring consecration resolution",
                battle_round=designation.last_resolved_battle_round,
                active_player_id=designation.last_resolved_active_player_id,
                phase=battle_phase_sequence[-1],
                timing=ObjectiveControlTiming.TURN_END,
                turn_order=turn_order,
                battle_phase_sequence=battle_phase_sequence,
            )
            record_key = _record_boundary_key(
                record=record,
                turn_order=turn_order,
                battle_phase_sequence=battle_phase_sequence,
            )
            if resolution_key > record_key:
                raise GameLifecycleError(
                    "Primary scoring consecration resolution cannot come from a future turn."
                )
            if resolution_key < created_key:
                raise GameLifecycleError(
                    "Primary scoring consecration resolution cannot precede creation."
                )


def validate_primary_scoring_state_evidence_restore_authority(
    *,
    evidence: PrimaryScoringStateEvidence,
    state: GameState,
    record: ObjectiveControlRecord,
) -> None:
    """Bind a restored snapshot to append-only state history and static identities."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring restore authority requires GameState.")
    phase_sequence = tuple(phase.value for phase in state.battle_phase_sequence)
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Primary scoring restore authority requires MissionSetup.")
    policies_by_id = primary_scoring_action_policies_by_id(mission_setup)
    validate_primary_scoring_progress_boundary(
        progress=evidence.primary_mission_progress_state,
        record=record,
        turn_order=state.turn_order,
        battle_phase_sequence=phase_sequence,
    )
    for action in evidence.primary_mission_action_states:
        policy = policies_by_id.get(action.mission_action_id)
        if policy is None:
            raise GameLifecycleError("Primary scoring state Action policy is not registered.")
        validate_primary_scoring_action_boundary(
            action=action,
            policy=policy,
            record=record,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
    _validate_authoritative_actions(
        evidence=evidence,
        state=state,
        record=record,
        policies_by_id=policies_by_id,
        battle_phase_sequence=phase_sequence,
    )
    _validate_authoritative_departures(evidence=evidence, state=state, record=record)
    validate_primary_scoring_destruction_history_authority(
        state=state,
        record=record,
        destruction_state_ids=evidence.primary_unit_destruction_state_ids,
        end_of_battle=evidence.scoring_boundary_kind.value == "end_of_battle",
    )
    _validate_authoritative_progress(evidence=evidence, state=state, record=record)
    _validate_authoritative_position_identities(evidence=evidence, state=state)


def validate_primary_scoring_position_event_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    """Bind persisted position witnesses to the exact historical scoring boundary."""
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        primary_mission_model_placements_from_checkpoint,
    )
    from warhammer40k_core.engine.primary_position_membership import (
        build_primary_rules_unit_membership_from_model_placements,
    )
    from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
        PRIMARY_SCORING_COMMIT_BOUNDARY_KIND,
        primary_scoring_commit_checkpoint_from_events,
    )
    from warhammer40k_core.engine.primary_scoring_commit_checkpoint_authority import (
        authenticate_primary_scoring_commit_checkpoint,
        validate_primary_scoring_spatial_rows_from_checkpoint,
    )
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring position event authority requires GameState.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError(
            "Primary scoring position event authority requires typed event records."
        )
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError(
            "Primary scoring position event authority requires typed decision records."
        )
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Primary scoring position event authority requires RuntimeModifierRegistry."
        )
    boundary_events_by_record_id: dict[str, list[EventRecord]] = {}
    for event in event_records:
        if event.event_type != "end_boundary_objective_control_determined":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError(
                "Primary scoring objective-control boundary event payload is invalid."
            )
        raw_record_ids = event.payload.get("record_ids")
        if type(raw_record_ids) is not list or any(
            type(record_id) is not str for record_id in raw_record_ids
        ):
            raise GameLifecycleError(
                "Primary scoring objective-control boundary record_ids are invalid."
            )
        for record_id in cast(list[str], raw_record_ids):
            boundary_events_by_record_id.setdefault(record_id, []).append(event)

    authorities_by_record_id = {
        authority.objective_control_record_id: authority
        for authority in state.objective_control_record_authorities
    }
    if len(authorities_by_record_id) != len(state.objective_control_record_authorities):
        raise GameLifecycleError(
            "Primary scoring position authority contains duplicate Objective Control records."
        )

    placements_by_record_id: dict[str, tuple[ModelPlacement, ...]] = {}
    for evidence in state.primary_scoring_state_evidence_records:
        matches = boundary_events_by_record_id.get(
            evidence.objective_control_record_id,
            [],
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Primary scoring position evidence requires exactly one append-only "
                "objective-control boundary event."
            )
        event = matches[0]
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError(
                "Primary scoring objective-control boundary event payload is invalid."
            )
        if (
            payload.get("game_id") != evidence.game_id
            or payload.get("battle_round") != evidence.battle_round
            or payload.get("phase") != evidence.phase
            or payload.get("record_ids") != [evidence.objective_control_record_id]
        ):
            raise GameLifecycleError(
                "Primary scoring position evidence boundary event context drifted."
            )
        authority = authorities_by_record_id.get(evidence.objective_control_record_id)
        if authority is None:
            raise GameLifecycleError(
                "Primary scoring position evidence lacks Objective Control authority."
            )
        oc_checkpoint = authority.boundary_checkpoint
        if (
            authority.objective_control_record_hash != evidence.objective_control_record_hash
            or oc_checkpoint.boundary_kind != "objective_control"
            or oc_checkpoint.game_id != evidence.game_id
            or oc_checkpoint.battlefield_id != evidence.battlefield_id
            or oc_checkpoint.active_player_id != evidence.active_player_id
            or oc_checkpoint.battle_round != evidence.battle_round
            or oc_checkpoint.phase != evidence.phase
        ):
            raise GameLifecycleError(
                "Primary scoring position evidence Objective Control authority drifted."
            )
        commit_event_index, commit_checkpoint = primary_scoring_commit_checkpoint_from_events(
            event_records=event_records,
            objective_control_record_id=evidence.objective_control_record_id,
            scoring_boundary_kind=evidence.scoring_boundary_kind.value,
        )
        oc_event_index = event_records.index(event)
        if commit_event_index <= oc_event_index:
            raise GameLifecycleError(
                "Primary scoring-commit checkpoint must follow Objective Control capture."
            )
        authenticate_primary_scoring_commit_checkpoint(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            checkpoint_index=commit_event_index,
            checkpoint=commit_checkpoint,
            runtime_modifier_registry=runtime_modifier_registry,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        if (
            commit_checkpoint.checkpoint_id != evidence.scoring_commit_checkpoint_id
            or commit_checkpoint.checkpoint_hash != evidence.scoring_commit_checkpoint_hash
            or commit_checkpoint.boundary_kind != PRIMARY_SCORING_COMMIT_BOUNDARY_KIND
            or commit_checkpoint.game_id != evidence.game_id
            or commit_checkpoint.battlefield_id != evidence.battlefield_id
            or commit_checkpoint.active_player_id != evidence.active_player_id
            or commit_checkpoint.battle_round != evidence.battle_round
            or commit_checkpoint.phase != evidence.phase
        ):
            raise GameLifecycleError(
                "Primary scoring position evidence scoring-commit checkpoint drifted."
            )
        model_placements = placements_by_record_id.get(evidence.scoring_commit_checkpoint_id)
        if model_placements is None:
            model_placements = primary_mission_model_placements_from_checkpoint(
                state=state,
                checkpoint=commit_checkpoint,
            )
            placements_by_record_id[evidence.scoring_commit_checkpoint_id] = model_placements
        for witness in evidence.current_rules_unit_position_witnesses:
            expected = build_primary_rules_unit_membership_from_model_placements(
                state=state,
                rules_unit_instance_id=witness.rules_unit_instance_id,
                owner_player_id=witness.owner_player_id,
                component_unit_instance_ids=(
                    witness.rules_unit_membership.component_unit_instance_ids
                ),
                model_placements=model_placements,
            )
            if witness.rules_unit_membership != expected:
                raise GameLifecycleError(
                    "Primary scoring position witness drifted from authoritative boundary history."
                )
        validate_primary_scoring_spatial_rows_from_checkpoint(
            state=state,
            evidence=evidence,
            model_placements=model_placements,
        )


def _validate_authoritative_actions(
    *,
    evidence: PrimaryScoringStateEvidence,
    state: GameState,
    record: ObjectiveControlRecord,
    policies_by_id: dict[str, PrimaryScoringActionPolicy],
    battle_phase_sequence: tuple[str, ...],
) -> None:
    from warhammer40k_core.engine.actions import MissionActionStatus

    if state.mission_setup is None:
        raise GameLifecycleError("Primary scoring Action authority requires MissionSetup.")
    assignment_by_player = {
        assignment.player_id: assignment.primary_mission_id
        for assignment in state.mission_setup.primary_mission_assignments
    }
    authoritative = tuple(
        sorted(
            (
                action
                for action in state.mission_action_states
                if action.mission_action_id in policies_by_id
                or action.mission_id == assignment_by_player.get(action.player_id)
            ),
            key=lambda action: action.action_id,
        )
    )
    expected = tuple(
        action
        for action in authoritative
        if _event_boundary_key(
            label="Primary scoring authoritative Action start",
            battle_round=action.battle_round_started,
            active_player_id=action.player_id,
            phase=action.phase_started,
            turn_order=state.turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
        <= _record_boundary_key(
            record=record,
            turn_order=state.turn_order,
            battle_phase_sequence=battle_phase_sequence,
        )
    )
    evidence_by_id = {action.action_id: action for action in evidence.primary_mission_action_states}
    if set(evidence_by_id) != {action.action_id for action in expected}:
        raise GameLifecycleError(
            "Primary scoring state Action history is incomplete for authoritative GameState."
        )
    for current in expected:
        frozen = evidence_by_id[current.action_id]
        if _action_immutable_identity(frozen) != _action_immutable_identity(current):
            raise GameLifecycleError(
                "Primary scoring state Action history drifted from authoritative GameState."
            )
        if current.status is MissionActionStatus.STARTED:
            if frozen != current:
                raise GameLifecycleError(
                    "Primary scoring state Action history drifted from authoritative GameState."
                )
            continue
        if current.status is MissionActionStatus.COMPLETED:
            policy = policies_by_id[current.mission_action_id]
            completion_key = _action_completion_key(
                action=current,
                policy=policy,
                turn_order=state.turn_order,
                battle_phase_sequence=battle_phase_sequence,
            )
            record_key = _record_boundary_key(
                record=record,
                turn_order=state.turn_order,
                battle_phase_sequence=battle_phase_sequence,
            )
            if completion_key <= record_key and frozen != current:
                raise GameLifecycleError(
                    "Primary scoring state completed Action is missing authoritative state."
                )
            if completion_key > record_key and frozen.status is not MissionActionStatus.STARTED:
                raise GameLifecycleError(
                    "Primary scoring state Action terminal status predates its completion."
                )
            continue
        if frozen not in {
            current,
            replace(
                current,
                status=MissionActionStatus.STARTED,
                interrupted_reason=None,
            ),
        }:
            raise GameLifecycleError(
                "Primary scoring state interrupted Action drifted from authoritative GameState."
            )


def _validate_authoritative_departures(
    *,
    evidence: PrimaryScoringStateEvidence,
    state: GameState,
    record: ObjectiveControlRecord,
) -> None:
    phase_sequence = tuple(phase.value for phase in state.battle_phase_sequence)
    record_key = _record_boundary_key(
        record=record,
        turn_order=state.turn_order,
        battle_phase_sequence=phase_sequence,
    )
    expected = tuple(
        departure
        for departure in state.primary_battlefield_departure_states
        if _event_boundary_key(
            label="Primary scoring authoritative battlefield departure",
            battle_round=departure.battle_round,
            active_player_id=departure.active_player_id,
            phase=departure.phase,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
        <= record_key
    )
    if evidence.primary_battlefield_departure_states != expected:
        raise GameLifecycleError(
            "Primary scoring battlefield departure history is incomplete for "
            "authoritative GameState."
        )


def _validate_authoritative_progress(
    *,
    evidence: PrimaryScoringStateEvidence,
    state: GameState,
    record: ObjectiveControlRecord,
) -> None:
    phase_sequence = tuple(phase.value for phase in state.battle_phase_sequence)
    record_key = _record_boundary_key(
        record=record,
        turn_order=state.turn_order,
        battle_phase_sequence=phase_sequence,
    )
    record_turn_key = _turn_key(
        label="Primary scoring ObjectiveControlRecord",
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        turn_order=state.turn_order,
    )
    markers: list[PrimaryMissionMarkerState] = []
    for marker in state.primary_mission_progress_state.markers:
        created_key = _optional_event_boundary_key(
            label="Primary scoring authoritative marker creation",
            battle_round=marker.created_battle_round,
            active_player_id=marker.created_active_player_id,
            phase=marker.created_phase,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
        if created_key is not None and created_key > record_key:
            continue
        removed_key = _optional_event_boundary_key(
            label="Primary scoring authoritative marker removal",
            battle_round=marker.removed_battle_round,
            active_player_id=marker.removed_active_player_id,
            phase=marker.removed_phase,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
        if removed_key is not None and removed_key > record_key:
            marker = replace(
                marker,
                status=PrimaryMissionMarkerStatus.ACTIVE,
                removed_battle_round=None,
                removed_phase=None,
                removed_active_player_id=None,
                removal_source_id=None,
                removal_event_id=None,
                removal_result_id=None,
                removal_action_id=None,
            )
        markers.append(marker)

    selections = tuple(
        selection
        for selection in state.primary_mission_progress_state.condemned_selections
        if _turn_key(
            label="Primary scoring authoritative condemned selection",
            battle_round=selection.battle_round,
            active_player_id=selection.active_player_id,
            turn_order=state.turn_order,
        )
        <= record_turn_key
    )
    designation_expectations: list[tuple[PrimaryConsecrationDesignationState, bool]] = []
    for designation in state.primary_mission_progress_state.consecration_designations:
        created_key = _event_boundary_key(
            label="Primary scoring authoritative consecration creation",
            battle_round=designation.created_battle_round,
            active_player_id=designation.created_active_player_id,
            phase=designation.created_phase,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
        if created_key > record_key:
            continue
        consumed_key = _optional_event_boundary_key(
            label="Primary scoring authoritative consecration consumption",
            battle_round=designation.consumed_battle_round,
            active_player_id=designation.consumed_active_player_id,
            phase=designation.consumed_phase,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
        resolution_is_future = (
            designation.last_resolved_battle_round is not None
            and designation.last_resolved_active_player_id is not None
            and _boundary_key(
                label="Primary scoring authoritative consecration resolution",
                battle_round=designation.last_resolved_battle_round,
                active_player_id=designation.last_resolved_active_player_id,
                phase=phase_sequence[-1],
                timing=ObjectiveControlTiming.TURN_END,
                turn_order=state.turn_order,
                battle_phase_sequence=phase_sequence,
            )
            > record_key
        )
        if consumed_key is not None and consumed_key > record_key:
            designation = replace(
                designation,
                status=PrimaryConsecrationStatus.ACTIVE,
                consumed_marker_id=None,
                consumed_battle_round=None,
                consumed_phase=None,
                consumed_active_player_id=None,
                consumption_source_id=None,
                consumption_event_id=None,
                consumption_result_id=None,
            )
        if resolution_is_future:
            designation = replace(
                designation,
                last_resolved_battle_round=None,
                last_resolved_active_player_id=None,
                last_resolution_event_id=None,
                last_resolution_result_id=None,
            )
        designation_expectations.append((designation, resolution_is_future))
    expected = PrimaryMissionProgressState(
        markers=tuple(markers),
        condemned_selections=selections,
        consecration_designations=tuple(
            designation for designation, _resolution_is_future in designation_expectations
        ),
    )
    frozen_progress = evidence.primary_mission_progress_state
    if (
        frozen_progress.markers != expected.markers
        or frozen_progress.condemned_selections != expected.condemned_selections
        or tuple(
            designation.designation_id for designation in frozen_progress.consecration_designations
        )
        != tuple(designation.designation_id for designation in expected.consecration_designations)
    ):
        raise GameLifecycleError(
            "Primary scoring mission progress is incomplete for authoritative GameState."
        )
    frozen_designations = {
        designation.designation_id: designation
        for designation in frozen_progress.consecration_designations
    }
    for expected_designation, resolution_is_future in designation_expectations:
        frozen = frozen_designations[expected_designation.designation_id]
        if resolution_is_future:
            frozen = replace(
                frozen,
                last_resolved_battle_round=None,
                last_resolved_active_player_id=None,
                last_resolution_event_id=None,
                last_resolution_result_id=None,
            )
        if frozen != expected_designation:
            raise GameLifecycleError(
                "Primary scoring mission progress drifted from authoritative GameState."
            )


def _validate_authoritative_position_identities(
    *,
    evidence: PrimaryScoringStateEvidence,
    state: GameState,
) -> None:
    if state.mission_setup is None:
        raise GameLifecycleError("Primary scoring position authority requires MissionSetup.")
    unit_owner: dict[str, str] = {}
    model_ids_by_unit: dict[str, frozenset[str]] = {}
    group_components: dict[str, tuple[str, ...]] = {}
    for army in state.army_definitions:
        for unit in army.units:
            unit_owner[unit.unit_instance_id] = army.player_id
            model_ids_by_unit[unit.unit_instance_id] = frozenset(
                model.model_instance_id for model in unit.own_models
            )
            group_components[unit.unit_instance_id] = (unit.unit_instance_id,)
        for formation in army.attached_units:
            group_components[formation.attached_unit_instance_id] = (
                formation.component_unit_instance_ids
            )
            unit_owner[formation.attached_unit_instance_id] = army.player_id
    for starting_formation in state.starting_attached_unit_records:
        group_components[starting_formation.attached_unit_instance_id] = (
            starting_formation.component_unit_instance_ids
        )
        unit_owner[starting_formation.attached_unit_instance_id] = starting_formation.player_id

    witnessed_components: list[str] = []
    objective_ids = {marker.objective_marker_id for marker in state.mission_setup.objective_markers}
    terrain_area_ids = {
        area.logical_terrain_area_id for area in mission_logical_terrain_areas(state.mission_setup)
    }
    for witness in evidence.current_rules_unit_position_witnesses:
        rules_unit_id = witness.rules_unit_instance_id
        components = witness.rules_unit_membership.component_unit_instance_ids
        if (
            group_components.get(rules_unit_id) != components
            or unit_owner.get(rules_unit_id) != witness.owner_player_id
        ):
            raise GameLifecycleError(
                "Primary scoring position witness drifted from authoritative rules-unit identity."
            )
        witnessed_components.extend(components)
        for component in witness.rules_unit_membership.component_memberships:
            known_models = model_ids_by_unit.get(component.unit_instance_id)
            if (
                known_models is None
                or not set(component.evaluated_model_instance_ids) <= known_models
            ):
                raise GameLifecycleError(
                    "Primary scoring position witness references an unknown authoritative model."
                )
            if not set(component.logical_terrain_area_ids) <= terrain_area_ids:
                raise GameLifecycleError(
                    "Primary scoring position witness references an unknown terrain area."
                )
            if not set(component.objective_marker_ids) <= objective_ids:
                raise GameLifecycleError(
                    "Primary scoring position witness references an unknown objective marker."
                )
    if sorted(witnessed_components) != sorted(unit_owner_id for unit_owner_id in model_ids_by_unit):
        raise GameLifecycleError(
            "Primary scoring position witnesses must cover every authoritative component "
            "exactly once."
        )


def _action_completion_key(
    *,
    action: MissionActionState,
    policy: PrimaryScoringActionPolicy,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int, int]:
    if action.completed_battle_round is None or action.completed_phase is None:
        raise GameLifecycleError("Primary scoring completed Action requires completion context.")
    if policy.completion_timing == "immediate":
        if (
            action.completed_battle_round != action.battle_round_started
            or action.completed_phase != action.phase_started
        ):
            raise GameLifecycleError("Immediate Primary scoring Action completion drifted.")
        timing = ObjectiveControlTiming.TURN_START
    elif policy.completion_timing == "turn_end":
        if (
            action.completed_battle_round != action.battle_round_started
            or action.completed_phase != battle_phase_sequence[-1]
        ):
            raise GameLifecycleError("Turn-end Primary scoring Action completion drifted.")
        timing = ObjectiveControlTiming.TURN_END
    else:
        raise GameLifecycleError("Primary scoring Action completion timing is unsupported.")
    return _boundary_key(
        label="Primary scoring state Action completion",
        battle_round=action.completed_battle_round,
        active_player_id=action.player_id,
        phase=action.completed_phase,
        timing=timing,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )


def _action_immutable_identity(action: MissionActionState) -> tuple[object, ...]:
    return (
        action.action_id,
        action.mission_action_id,
        action.player_id,
        action.unit_instance_id,
        action.target_id,
        action.condition_target_id,
        action.mission_id,
        action.battle_round_started,
        action.phase_started,
        action.start_timing,
        action.completion_timing,
        action.eligible_unit_instance_ids,
        action.interruption_conditions,
        action.scoring_source_id,
        action.victory_points,
    )


def _reject_future_key(
    *,
    label: str,
    key: tuple[int, int, int, int] | None,
    record: ObjectiveControlRecord,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> None:
    if key is not None and key > _record_boundary_key(
        record=record,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    ):
        raise GameLifecycleError(f"{label} cannot come from a future boundary.")


def _record_boundary_key(
    *,
    record: ObjectiveControlRecord,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int, int]:
    return _boundary_key(
        label="Primary scoring ObjectiveControlRecord",
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        timing=record.timing,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )


def _event_boundary_key(
    *,
    label: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int, int]:
    return _boundary_key(
        label=label,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=phase,
        timing=ObjectiveControlTiming.TURN_START,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )


def _optional_event_boundary_key(
    *,
    label: str,
    battle_round: int | None,
    active_player_id: str | None,
    phase: str | None,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int, int] | None:
    values = (battle_round, active_player_id, phase)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise GameLifecycleError(f"{label} requires complete battle context.")
    if type(battle_round) is not int or type(active_player_id) is not str or type(phase) is not str:
        raise GameLifecycleError(f"{label} battle context is invalid.")
    return _event_boundary_key(
        label=label,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=phase,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )


def _boundary_key(
    *,
    label: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
    timing: ObjectiveControlTiming,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int, int]:
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError(f"{label} battle_round must be a positive integer.")
    if active_player_id not in turn_order:
        raise GameLifecycleError(f"{label} references an unknown active player.")
    if phase not in battle_phase_sequence:
        raise GameLifecycleError(f"{label} references an unknown battle phase.")
    if type(timing) is not ObjectiveControlTiming:
        raise GameLifecycleError(f"{label} timing must be ObjectiveControlTiming.")
    return (
        battle_round,
        turn_order.index(active_player_id),
        battle_phase_sequence.index(phase),
        _OBJECTIVE_CONTROL_TIMING_ORDER[timing],
    )


def _turn_key(
    *,
    label: str,
    battle_round: int,
    active_player_id: str,
    turn_order: tuple[str, ...],
) -> tuple[int, int]:
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError(f"{label} battle_round must be a positive integer.")
    if active_player_id not in turn_order:
        raise GameLifecycleError(f"{label} references an unknown active player.")
    return battle_round, turn_order.index(active_player_id)


__all__ = (
    "validate_primary_scoring_action_boundary",
    "validate_primary_scoring_boundary_context",
    "validate_primary_scoring_position_event_authority",
    "validate_primary_scoring_progress_boundary",
    "validate_primary_scoring_state_evidence_restore_authority",
)
