from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from inspect import signature
from typing import cast

import pytest

from tests.phase11c_command_phase_helpers import battle_state, with_model_offsets
from tests.phase17n_primary_mission_helpers import (
    phase17n_action_turn_end_record,
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    phase17n_state_with_setup,
)
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.game_state_payloads import GameStatePayload
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.objective_control_record_authority import (
    ObjectiveControlRecordAuthority,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryCondemnedSelectionState,
    PrimaryConsecrationDesignationState,
    PrimaryMissionProgressState,
    primary_condemned_selection_id,
    primary_consecration_designation_id,
)
from warhammer40k_core.engine.primary_scoring_action_policy import (
    primary_scoring_action_policies_by_id,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PrimaryScoringBoundaryLifecycle,
    resolve_primary_scoring_boundary_lifecycle,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PrimaryScoringSpatialEvidence,
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA,
    PrimaryScoringBoundaryKind,
    PrimaryScoringRulesUnitPositionWitness,
    PrimaryScoringStateEvidence,
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
    validate_primary_scoring_state_evidence_authority,
    validate_primary_scoring_state_evidence_context,
    validate_primary_scoring_state_evidence_records,
)
from warhammer40k_core.engine.primary_scoring_state_evidence_integrity import (
    validate_primary_scoring_action_boundary,
    validate_primary_scoring_state_evidence_restore_authority,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    build_primary_rules_unit_turn_start_snapshot,
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState, ReserveStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord
from warhammer40k_core.engine.sticky_objective_control import (
    StickyObjectiveControlState,
    apply_sticky_objective_control,
)
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source,
)


@pytest.fixture(scope="module")
def completed_primary_scoring_boundary() -> tuple[
    GameState,
    ObjectiveControlRecord,
    PrimaryScoringStateEvidence,
    str,
]:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id="decoy-objective",
        current_phase=BattlePhase.FIGHT,
        player_unit_count=2,
    )
    if state.mission_setup is None:
        raise AssertionError("Step 5A fixture requires mission setup.")
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=state.mission_setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Step 5A fixture requires battlefield state.")
    departed_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    placement = battlefield.unit_placement_by_id(departed_unit.unit_instance_id)
    removed_model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    battlefield = battlefield.with_removed_models(removed_model_ids)
    state.battlefield_state = battlefield
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=departed_unit.unit_instance_id,
        affected_component_unit_instance_ids=(departed_unit.unit_instance_id,),
        departed_component_unit_instance_ids=(departed_unit.unit_instance_id,),
        removed_model_instance_ids=removed_model_ids,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id="phase17n-step5a-departure",
        source_id="phase17n-step5a-departure-source",
    )
    if departure is None:
        raise AssertionError("Step 5A fixture requires battlefield-departure evidence.")
    record = phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    if len(resolved) != 1:
        raise AssertionError("Step 5A fixture requires one resolved Primary Action.")
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    evidence = next(
        candidate
        for candidate in state.primary_scoring_state_evidence_records
        if candidate.objective_control_record_id == record.record_id
        and candidate.scoring_boundary_kind is PrimaryScoringBoundaryKind.ORDINARY
    )
    return (
        state,
        record,
        evidence,
        departed_unit.unit_instance_id,
    )


@pytest.fixture(scope="module")
def persisted_primary_scoring_boundary() -> tuple[
    GameState,
    PrimaryScoringStateEvidence,
]:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    if mission_setup is None or battlefield is None:
        raise AssertionError("Step 5A persisted fixture requires mission battlefield state.")
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=mission_setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    if target_id != action.target_id:
        raise AssertionError("Step 5A persisted fixture Action target drifted.")
    action_record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=action_record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    if len(resolved) != 1 or len(state.primary_mission_progress_state.markers) != 1:
        raise AssertionError("Step 5A persisted fixture requires Action-created progress.")
    score_primary_objective_control_boundary(
        state=state,
        record=action_record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )

    state.battle_round = 2
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    departed_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    placement = battlefield.unit_placement_by_id(departed_unit.unit_instance_id)
    removed_model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    battlefield = battlefield.with_removed_models(removed_model_ids)
    state.battlefield_state = battlefield
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=departed_unit.unit_instance_id,
        affected_component_unit_instance_ids=(departed_unit.unit_instance_id,),
        departed_component_unit_instance_ids=(departed_unit.unit_instance_id,),
        removed_model_instance_ids=removed_model_ids,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id="phase17n-step5a-persisted-departure",
        source_id="phase17n-step5a-persisted-departure-source",
    )
    if departure is None:
        raise AssertionError("Step 5A persisted fixture requires departure evidence.")

    scoring_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    state.record_objective_control_record(scoring_record)
    evidence = build_primary_scoring_state_evidence(
        scoring_player_id=scoring_record.active_player_id,
        state=state,
        record=scoring_record,
        end_of_battle=False,
    )
    policies = mission_scoring_policies_from_setup(mission_setup)
    awards = policies.primary_awards_from_objective_control(
        record=scoring_record,
        authoritative_state=state,
        end_of_battle=False,
    )
    if not awards:
        raise AssertionError("Step 5A persisted fixture requires a Primary VP award.")
    record_primary_scoring_state_evidence(state=state, evidence=evidence)
    for award in awards:
        state.award_victory_points(award)
    resolve_primary_scoring_boundary_lifecycle(
        scoring_player_id=scoring_record.active_player_id,
        state=state,
        record=scoring_record,
        scoring_boundary_kind=evidence.scoring_boundary_kind,
        scoring_commit_checkpoint_id=evidence.scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=evidence.scoring_commit_checkpoint_hash,
        evidence_id=evidence.evidence_id,
    )
    GameState.from_payload(state.to_payload())
    return state, evidence


@pytest.fixture(scope="module")
def retained_objective_control_authority() -> tuple[
    GameState,
    ObjectiveControlRecord,
    ObjectiveControlRecordAuthority,
]:
    setup = phase17n_event_setup(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-b",
        phase=BattlePhase.FIGHT,
        battle_round=1,
    )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Step 5A sticky fixture requires battlefield state.")
    target_marker = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    player_b_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    placement = battlefield.unit_placement_by_id(player_b_unit.unit_instance_id)
    state.battlefield_state = battlefield.with_unit_placement(
        with_model_offsets(
            placement,
            target_marker,
            offsets=((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
        )
    )
    base_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=BattlePhase.FIGHT,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    retained_objective = next(
        result
        for result in base_record.results
        if result.status is ObjectiveControlStatus.UNCONTROLLED
    )
    player_a_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    sticky_state = StickyObjectiveControlState(
        state_id="phase17n-step5a-retained-control-state",
        game_id=state.game_id,
        player_id="player-a",
        objective_id=retained_objective.objective_id,
        source_rule_id="phase17n-step5a-retained-control-source",
        source_event_id="phase17n-step5a-retained-control-event",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        active_player_id="player-b",
        originating_unit_instance_id=player_a_unit.unit_instance_id,
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        replay_payload={"source": "phase17n-step5a-retained-control"},
    )
    state.record_sticky_objective_control_state(sticky_state)
    retained_record = apply_sticky_objective_control(
        record=base_record,
        states=(sticky_state,),
    )
    state.record_objective_control_record(retained_record)
    score_primary_objective_control_boundary(
        state=state,
        record=retained_record,
        end_of_battle=False,
    )
    return state, retained_record, state.objective_control_record_authorities[-1]


def _coordinated_objective_control_forgery_payload(
    *,
    state: GameState,
    evidence: PrimaryScoringStateEvidence,
    forged_record: ObjectiveControlRecord,
) -> GameStatePayload:
    forged_state = GameState.from_payload(state.to_payload())
    forged_state.objective_control_records = [
        forged_record if record.record_id == forged_record.record_id else record
        for record in forged_state.objective_control_records
    ]
    forged_state.primary_scoring_state_evidence_records = [
        row
        for row in forged_state.primary_scoring_state_evidence_records
        if row.evidence_id != evidence.evidence_id
    ]
    forged_evidence = build_primary_scoring_state_evidence(
        scoring_player_id=forged_record.active_player_id,
        state=forged_state,
        record=forged_record,
        end_of_battle=False,
    )
    forged_state.primary_scoring_state_evidence_records = [
        forged_evidence if row.evidence_id == evidence.evidence_id else row
        for row in state.primary_scoring_state_evidence_records
    ]
    payload = deepcopy(forged_state.to_payload())
    updated_transactions = 0
    for ledger_payload in payload["victory_point_ledgers"]:
        for transaction_payload in ledger_payload["transactions"]:
            if transaction_payload["source_kind"] != "primary":
                continue
            metadata = cast(dict[str, object], transaction_payload["metadata"])
            if metadata.get("objective_control_record_id") != evidence.objective_control_record_id:
                continue
            metadata["primary_scoring_state_evidence_id"] = forged_evidence.evidence_id
            metadata["primary_scoring_state_evidence_hash"] = forged_evidence.evidence_hash
            updated_transactions += 1
    if updated_transactions == 0:
        raise AssertionError("Step 5A forgery fixture requires Primary VP transactions.")
    return payload


def _coordinated_objective_control_authority_payload(
    *,
    state: GameState,
    forged_record: ObjectiveControlRecord,
    authority: ObjectiveControlRecordAuthority,
    retained_sticky_objective_control_states: tuple[StickyObjectiveControlState, ...] | None = None,
    boundary_checkpoint: PrimaryMissionBoundaryCheckpoint | None = None,
) -> GameStatePayload:
    forged_authority = ObjectiveControlRecordAuthority.create(
        record=forged_record,
        boundary_checkpoint=(
            authority.boundary_checkpoint if boundary_checkpoint is None else boundary_checkpoint
        ),
        retained_sticky_objective_control_states=(
            authority.retained_sticky_objective_control_states
            if retained_sticky_objective_control_states is None
            else retained_sticky_objective_control_states
        ),
    )
    rebuilt_evidence = tuple(
        _rebuild_state_evidence(evidence, record=forged_record)
        if evidence.objective_control_record_id == forged_record.record_id
        else evidence
        for evidence in state.primary_scoring_state_evidence_records
    )
    evidence_id_by_previous_id = {
        previous.evidence_id: rebuilt.evidence_id
        for previous, rebuilt in zip(
            state.primary_scoring_state_evidence_records,
            rebuilt_evidence,
            strict=True,
        )
    }
    rebuilt_lifecycles = tuple(
        PrimaryScoringBoundaryLifecycle.create(
            objective_control_record_id=row.objective_control_record_id,
            scoring_player_id=row.scoring_player_id,
            objective_control_record_hash=objective_control_record_hash(forged_record),
            scoring_boundary_kind=row.scoring_boundary_kind,
            status=row.status,
            pending_window=row.pending_window,
            pending_decision_request_id=row.pending_decision_request_id,
            scoring_commit_checkpoint_id=row.scoring_commit_checkpoint_id,
            scoring_commit_checkpoint_hash=row.scoring_commit_checkpoint_hash,
            evidence_id=(
                None
                if row.evidence_id is None
                else evidence_id_by_previous_id.get(row.evidence_id, row.evidence_id)
            ),
            primary_transaction_ids=row.primary_transaction_ids,
        )
        if row.objective_control_record_id == forged_record.record_id
        else row
        for row in state.primary_scoring_boundary_lifecycles
    )
    payload = deepcopy(state.to_payload())
    payload["objective_control_records"] = [
        forged_record.to_payload() if record["record_id"] == forged_record.record_id else record
        for record in payload["objective_control_records"]
    ]
    payload["objective_control_record_authorities"] = [
        forged_authority.to_payload()
        if stored["objective_control_record_id"] == forged_record.record_id
        else stored
        for stored in payload["objective_control_record_authorities"]
    ]
    payload["primary_scoring_state_evidence_records"] = [
        evidence.to_payload() for evidence in rebuilt_evidence
    ]
    payload["primary_scoring_boundary_lifecycles"] = [
        row.to_payload() for row in rebuilt_lifecycles
    ]
    return payload


def _rebuild_objective_control_checkpoint(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    *,
    battle_shocked_unit_instance_ids: tuple[str, ...] | None = None,
) -> PrimaryMissionBoundaryCheckpoint:
    return PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=checkpoint.active_player_id,
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=checkpoint.model_states,
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=(
            checkpoint.battle_shocked_unit_instance_ids
            if battle_shocked_unit_instance_ids is None
            else battle_shocked_unit_instance_ids
        ),
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=checkpoint.objective_control_modifier_sources,
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_card_jsons=checkpoint.active_secondary_mission_card_jsons,
        completed_mission_action_state_jsons=checkpoint.completed_mission_action_state_jsons,
        primary_unit_destruction_state_jsons=checkpoint.primary_unit_destruction_state_jsons,
        starting_strength_record_jsons=checkpoint.starting_strength_record_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )


def _rebuild_state_evidence(
    evidence: PrimaryScoringStateEvidence,
    *,
    record: ObjectiveControlRecord | None = None,
    scoring_boundary_kind: PrimaryScoringBoundaryKind | None = None,
    primary_mission_progress_state: PrimaryMissionProgressState | None = None,
    primary_mission_action_states: tuple[MissionActionState, ...] | None = None,
    primary_battlefield_departure_states: tuple[PrimaryBattlefieldDepartureState, ...]
    | None = None,
    primary_unit_destruction_state_ids: tuple[str, ...] | None = None,
    current_rules_unit_position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...]
    | None = None,
    primary_scoring_spatial_evidence_by_player_id: tuple[PrimaryScoringSpatialEvidence, ...]
    | None = None,
) -> PrimaryScoringStateEvidence:
    return PrimaryScoringStateEvidence.create(
        scoring_player_id=evidence.active_player_id if record is None else record.active_player_id,
        game_id=evidence.game_id,
        battlefield_id=evidence.battlefield_id,
        battle_round=evidence.battle_round if record is None else record.battle_round,
        active_player_id=(evidence.active_player_id if record is None else record.active_player_id),
        phase=evidence.phase if record is None else record.phase,
        timing=evidence.timing if record is None else record.timing,
        scoring_boundary_kind=(
            evidence.scoring_boundary_kind
            if scoring_boundary_kind is None
            else scoring_boundary_kind
        ),
        objective_control_record_id=(
            evidence.objective_control_record_id if record is None else record.record_id
        ),
        objective_control_record_hash=(
            evidence.objective_control_record_hash
            if record is None
            else objective_control_record_hash(record)
        ),
        scoring_commit_checkpoint_id=evidence.scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=evidence.scoring_commit_checkpoint_hash,
        primary_mission_progress_state=(
            evidence.primary_mission_progress_state
            if primary_mission_progress_state is None
            else primary_mission_progress_state
        ),
        primary_mission_action_states=(
            evidence.primary_mission_action_states
            if primary_mission_action_states is None
            else primary_mission_action_states
        ),
        primary_battlefield_departure_states=(
            evidence.primary_battlefield_departure_states
            if primary_battlefield_departure_states is None
            else primary_battlefield_departure_states
        ),
        primary_unit_destruction_state_ids=(
            evidence.primary_unit_destruction_state_ids
            if primary_unit_destruction_state_ids is None
            else primary_unit_destruction_state_ids
        ),
        current_rules_unit_position_witnesses=(
            evidence.current_rules_unit_position_witnesses
            if current_rules_unit_position_witnesses is None
            else current_rules_unit_position_witnesses
        ),
        primary_scoring_spatial_evidence_by_player_id=(
            evidence.primary_scoring_spatial_evidence_by_player_id
            if primary_scoring_spatial_evidence_by_player_id is None
            else primary_scoring_spatial_evidence_by_player_id
        ),
    )


def _condemned_selection(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    battle_round: int,
) -> PrimaryCondemnedSelectionState:
    source_rule_id = "phase17n-step5a-future-selection-source"
    source_descriptor_id = "phase17n-step5a-future-selection-descriptor"
    candidate_policy_id = "phase17n-step5a-future-selection-policy"
    source_event_id = "phase17n-step5a-future-selection-event"
    selection_id = primary_condemned_selection_id(
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        battle_round=battle_round,
        active_player_id=owner_player_id,
        candidate_policy_id=candidate_policy_id,
        candidate_rules_unit_instance_ids=(),
        candidate_evidence_ids=(),
        selected_rules_unit_instance_ids=(),
        minimum_selection_count=0,
        maximum_selection_count=0,
        used_fallback_candidates=False,
        selection_request_id=None,
        selection_result_id=None,
        source_event_id=source_event_id,
    )
    return PrimaryCondemnedSelectionState(
        selection_id=selection_id,
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        battle_round=battle_round,
        active_player_id=owner_player_id,
        candidate_policy_id=candidate_policy_id,
        candidate_rules_unit_instance_ids=(),
        candidate_evidence_ids=(),
        selected_rules_unit_instance_ids=(),
        minimum_selection_count=0,
        maximum_selection_count=0,
        used_fallback_candidates=False,
        selection_request_id=None,
        selection_result_id=None,
        source_event_id=source_event_id,
    )


def _consecration_designation(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
    created_active_player_id: str,
    created_phase: str,
) -> PrimaryConsecrationDesignationState:
    source_rule_id = "phase17n-step5a-future-designation-source"
    source_descriptor_id = "phase17n-step5a-future-designation-descriptor"
    source_destruction_id = "phase17n-step5a-future-designation-destruction"
    source_event_id = "phase17n-step5a-future-designation-event"
    designation_id = primary_consecration_designation_id(
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
        source_destruction_id=source_destruction_id,
        created_battle_round=1,
        created_phase=created_phase,
        created_active_player_id=created_active_player_id,
        source_event_id=source_event_id,
    )
    return PrimaryConsecrationDesignationState(
        designation_id=designation_id,
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
        source_destruction_id=source_destruction_id,
        created_battle_round=1,
        created_phase=created_phase,
        created_active_player_id=created_active_player_id,
        source_event_id=source_event_id,
    )


__all__: list[str] = []
__all__ += ["AttachedUnitFormation", "BattlePhase", "BattleShockedUnitState"]
__all__ += ["BattlefieldRemovalKind", "GameLifecycleError", "GameLifecycleStage", "GameState"]
__all__ += ["GameStatePayload", "MissionActionState", "MissionActionStatus"]
__all__ += ["MissionScoringPolicies", "ObjectiveControlContext", "ObjectiveControlRecord"]
__all__ += ["ObjectiveControlRecordAuthority", "ObjectiveControlResult", "ObjectiveControlScore"]
__all__ += ["ObjectiveControlStatus", "ObjectiveControlTiming", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA", "PrimaryBattlefieldDepartureState"]
__all__ += ["PrimaryCondemnedSelectionState", "PrimaryConsecrationDesignationState"]
__all__ += ["PrimaryMissionBoundaryCheckpoint", "PrimaryMissionProgressState"]
__all__ += ["PrimaryScoringBoundaryKind", "PrimaryScoringBoundaryLifecycle"]
__all__ += ["PrimaryScoringRulesUnitPositionWitness", "PrimaryScoringSpatialEvidence"]
__all__ += ["PrimaryScoringStateEvidence", "ReserveKind", "ReserveState", "ReserveStatus"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS", "RuntimeModifierRegistry"]
__all__ += ["StartingAttachedUnitRecord", "StickyObjectiveControlState", "_condemned_selection"]
__all__ += ["_consecration_designation", "_coordinated_objective_control_authority_payload"]
__all__ += ["_coordinated_objective_control_forgery_payload"]
__all__ += ["_rebuild_objective_control_checkpoint", "_rebuild_state_evidence"]
__all__ += ["apply_sticky_objective_control", "battle_state"]
__all__ += ["build_primary_rules_unit_turn_start_snapshot"]
__all__ += ["build_primary_scoring_state_evidence", "cast", "completed_primary_scoring_boundary"]
__all__ += ["deepcopy", "event_source", "mission_scoring_policies_from_setup"]
__all__ += ["objective_control_record_hash", "persisted_primary_scoring_boundary"]
__all__ += ["phase17n_action_turn_end_record", "phase17n_event_setup"]
__all__ += ["phase17n_started_primary_action_fixture", "phase17n_state_with_setup"]
__all__ += ["primary_condemned_selection_id", "primary_consecration_designation_id"]
__all__ += ["primary_scoring_action_policies_by_id", "primary_scoring_rules_from_definition"]
__all__ += ["pytest", "record_primary_battlefield_departure"]
__all__ += ["record_primary_scoring_state_evidence", "record_primary_turn_start_evidence"]
__all__ += ["replace", "reserve_destruction_policy_from_scoring_policy"]
__all__ += ["resolve_objective_control", "resolve_primary_mission_actions_at_turn_end"]
__all__ += ["resolve_primary_scoring_boundary_lifecycle", "retained_objective_control_authority"]
__all__ += ["score_primary_objective_control_boundary", "signature"]
__all__ += ["validate_primary_scoring_action_boundary"]
__all__ += ["validate_primary_scoring_state_evidence_authority"]
__all__ += ["validate_primary_scoring_state_evidence_context"]
__all__ += ["validate_primary_scoring_state_evidence_records"]
__all__ += ["validate_primary_scoring_state_evidence_restore_authority"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack", "with_model_offsets"]
