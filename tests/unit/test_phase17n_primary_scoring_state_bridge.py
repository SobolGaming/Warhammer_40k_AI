from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from inspect import signature
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import battle_state
from tests.phase17n_primary_mission_helpers import (
    phase17n_action_turn_end_record,
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
)

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
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
)
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
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
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


def test_phase17n_step5a_simple_objective_conditions_are_registered() -> None:
    assert {
        "control_four_or_more_objectives_end_of_battle",
        "control_one_or_more_central_objectives_first_battle_round",
        "control_three_or_more_objectives_from_battle_round_two",
        "one_or_more_controlled_non_home_objectives_is_central_objective",
    } <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS


def test_phase17n_step5a_aggregate_scoring_api_accepts_only_authoritative_state() -> None:
    assert tuple(
        signature(MissionScoringPolicies.primary_awards_from_objective_control).parameters
    ) == ("self", "record", "authoritative_state", "end_of_battle")


def test_phase17n_step5a_persists_applicable_zero_award_boundary() -> None:
    state = battle_state()
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Step 5A zero-award fixture requires battlefield state.")
    state.mission_setup = setup
    state.battlefield_state = replace(
        battlefield,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 2
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    state.record_objective_control_record(record)

    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )

    assert all(not ledger.transactions for ledger in state.victory_point_ledgers)
    assert len(state.primary_scoring_state_evidence_records) == 1
    restored = GameState.from_payload(state.to_payload())
    assert restored.primary_scoring_state_evidence_records == (
        state.primary_scoring_state_evidence_records
    )


def test_phase17n_step5a_ordinary_boundary_excludes_later_reserve_deadline_destruction() -> None:
    state = battle_state()
    if state.mission_setup is None or state.battlefield_state is None:
        raise AssertionError("Step 5A reserve deadline fixture requires mission state.")
    assert state.mission_setup.primary_mission_id_for_player("player-b") == (
        "primary-unstoppable-force"
    )
    reserve_unit_id = "army-alpha:intercessor-unit-1"
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement(reserve_unit_id))
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=reserve_unit_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                policies.policy_for_player("player-a")
            ),
        )
    )
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record_primary_turn_start_evidence(state=state)

    state.advance_to_next_battle_phase()

    reserve_state = state.reserve_state_for_unit(reserve_unit_id)
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.DESTROYED
    (destruction,) = tuple(
        row
        for row in state.primary_unit_destruction_states
        if row.destroyed_unit_instance_id == reserve_unit_id
    )
    ordinary = next(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.battle_round == 3
        and evidence.active_player_id == "player-b"
        and evidence.phase == BattlePhase.FIGHT.value
        and evidence.timing is ObjectiveControlTiming.TURN_END
        and evidence.scoring_boundary_kind is PrimaryScoringBoundaryKind.ORDINARY
    )
    assert destruction.destruction_id not in ordinary.primary_unit_destruction_state_ids
    assert not any(
        isinstance(transaction.metadata, dict)
        and transaction.metadata.get("scoring_rule_condition")
        == "one_or_more_enemy_units_destroyed_this_turn"
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
    )

    restored = GameState.from_payload(state.to_payload())

    assert restored.to_payload() == state.to_payload()

    forged_inclusion = _rebuild_state_evidence(
        ordinary,
        primary_unit_destruction_state_ids=(destruction.destruction_id,),
    )
    forged_payload = deepcopy(state.to_payload())
    forged_payload["primary_scoring_state_evidence_records"] = [
        (forged_inclusion.to_payload() if row["evidence_id"] == ordinary.evidence_id else row)
        for row in forged_payload["primary_scoring_state_evidence_records"]
    ]
    with pytest.raises(GameLifecycleError, match="post-boundary reserve destruction"):
        GameState.from_payload(forged_payload)

    state.advance_to_next_battle_phase()
    later = next(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.battle_round == 4
        and evidence.active_player_id == "player-a"
        and evidence.phase == BattlePhase.COMMAND.value
        and evidence.scoring_boundary_kind is PrimaryScoringBoundaryKind.ORDINARY
    )
    assert destruction.destruction_id in later.primary_unit_destruction_state_ids
    forged_omission = _rebuild_state_evidence(
        later,
        primary_unit_destruction_state_ids=(),
    )
    forged_payload = deepcopy(state.to_payload())
    forged_payload["primary_scoring_state_evidence_records"] = [
        forged_omission.to_payload() if row["evidence_id"] == later.evidence_id else row
        for row in forged_payload["primary_scoring_state_evidence_records"]
    ]
    with pytest.raises(GameLifecycleError, match="destruction history is incomplete"):
        GameState.from_payload(forged_payload)


def test_phase17n_step5a_action_policy_projection_includes_all_source_primary_actions() -> None:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="take-and-hold",
    )

    policies = primary_scoring_action_policies_by_id(setup)

    assert policies["booby-trap-terrain"].primary_mission_id == "primary-death-trap"
    assert policies["booby-trap-terrain"].victory_points == 0
    assert policies["terraform-objective"].primary_mission_id == "terraform"
    assert policies["terraform-objective"].victory_points == 1
    assert policies["decoy-objective"].primary_mission_id == "primary-smoke-and-mirrors"
    assert len({policy.source_id for policy in policies.values()}) == len(policies)
    assert all(
        policy.source_id.endswith(f":action:{policy.mission_action_id}")
        for policy in policies.values()
    )


def test_phase17n_step5a_bridge_accepts_normal_lifecycle_death_trap_action() -> None:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="take-and-hold",
        player_id="player-a",
        mission_action_id="booby-trap-terrain",
        current_phase=BattlePhase.FIGHT,
    )
    assert action.status is MissionActionStatus.COMPLETED
    assert action.victory_points == 0
    record = phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )

    evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=False,
    )

    assert evidence.primary_mission_action_states == (action,)


def test_phase17n_step5a_does_not_promote_condition_pending_primary_missions() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    step5a_mission_ids = {
        "primary-gather-intel",
        "primary-secure-asset",
        "primary-triangulation",
        "primary-vital-link",
    }
    coverage_by_id = {
        row.primary_mission_id: row for row in event_source.primary_mission_scoring_coverage_rows()
    }

    assert (
        sum(
            row.status is event_source.PrimaryMissionScoringCoverageStatus.ENGINE_IMPLEMENTED
            for row in coverage_by_id.values()
        )
        == 13
    )
    assert (
        sum(
            row.status
            is event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING
            for row in coverage_by_id.values()
        )
        == 12
    )
    for mission_id in step5a_mission_ids:
        assert coverage_by_id[mission_id].status is (
            event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING
        )
        assert (
            primary_scoring_rules_from_definition(
                primary_by_id[mission_id],
                require_supported=False,
            )
            == ()
        )
        with pytest.raises(
            GameLifecycleError,
            match="source is known but engine implementation is pending",
        ):
            primary_scoring_rules_from_definition(primary_by_id[mission_id])


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
    return (
        state,
        record,
        build_primary_scoring_state_evidence(
            state=state,
            record=record,
            end_of_battle=False,
        ),
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
    action_record = phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
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

    state.battle_round = 2
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
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
    GameState.from_payload(state.to_payload())
    return state, evidence


def test_phase17n_step5a_bridge_round_trips_complete_authoritative_state(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, departed_unit_id = completed_primary_scoring_boundary

    assert evidence.schema_version == PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA
    assert evidence.objective_control_record_id == record.record_id
    assert evidence.objective_control_record_hash == objective_control_record_hash(record)
    assert evidence.primary_mission_progress_state == state.primary_mission_progress_state
    assert isinstance(evidence.primary_mission_progress_state, PrimaryMissionProgressState)
    assert tuple(action.action_id for action in evidence.primary_mission_action_states) == tuple(
        sorted(action.action_id for action in state.mission_action_states)
    )
    assert tuple(
        departure.departure_id for departure in evidence.primary_battlefield_departure_states
    ) == tuple(
        sorted(departure.departure_id for departure in state.primary_battlefield_departure_states)
    )
    departed_position = evidence.position_witness_for_rules_unit(departed_unit_id)
    assert departed_position.owner_player_id == "player-b"
    assert departed_position.rules_unit_membership.evaluated_model_instance_ids == ()
    assert set(evidence.to_payload()) == {
        "schema_version",
        "game_id",
        "battlefield_id",
        "battle_round",
        "active_player_id",
        "phase",
        "timing",
        "scoring_boundary_kind",
        "objective_control_record_id",
        "objective_control_record_hash",
        "scoring_commit_checkpoint_id",
        "scoring_commit_checkpoint_hash",
        "primary_mission_progress_state",
        "primary_mission_action_states",
        "primary_battlefield_departure_states",
        "primary_unit_destruction_state_ids",
        "current_rules_unit_position_witnesses",
        "primary_scoring_spatial_evidence_by_player_id",
        "evidence_id",
        "evidence_hash",
    }
    assert PrimaryScoringStateEvidence.from_payload(evidence.to_payload()) == evidence

    restored = GameState.from_payload(state.to_payload())
    restored_record = next(
        candidate
        for candidate in restored.objective_control_records
        if candidate.record_id == record.record_id
    )
    assert (
        build_primary_scoring_state_evidence(
            state=restored,
            record=restored_record,
            end_of_battle=False,
        )
        == evidence
    )


def test_phase17n_step5a_registry_distinguishes_final_ordinary_and_end_battle_boundaries(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    source_state, source_record, _source_evidence, _departed_unit_id = (
        completed_primary_scoring_boundary
    )
    state = GameState.from_payload(source_state.to_payload())
    state.battle_round = 5
    state.active_player_id = state.turn_order[-1]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    final_record = replace(
        source_record,
        record_id=(
            f"objective-control:round-05:{state.active_player_id}:"
            f"{BattlePhase.FIGHT.value}:{ObjectiveControlTiming.TURN_END.value}"
        ),
        battle_round=5,
        active_player_id=state.active_player_id,
        phase=BattlePhase.FIGHT.value,
        timing=ObjectiveControlTiming.TURN_END,
    )
    state.record_objective_control_record(final_record)
    ordinary = build_primary_scoring_state_evidence(
        state=state,
        record=final_record,
        end_of_battle=False,
    )
    end_of_battle = build_primary_scoring_state_evidence(
        state=state,
        record=final_record,
        end_of_battle=True,
    )

    assert ordinary.scoring_boundary_kind is PrimaryScoringBoundaryKind.ORDINARY
    assert end_of_battle.scoring_boundary_kind is PrimaryScoringBoundaryKind.END_OF_BATTLE
    assert ordinary.evidence_id != end_of_battle.evidence_id
    record_primary_scoring_state_evidence(state=state, evidence=ordinary)
    record_primary_scoring_state_evidence(state=state, evidence=end_of_battle)
    record_primary_scoring_state_evidence(state=state, evidence=ordinary)

    assert validate_primary_scoring_state_evidence_records(
        [ordinary, end_of_battle],
        game_id=state.game_id,
        mission_setup=state.mission_setup,
        turn_order=state.turn_order,
        objective_control_records=tuple(state.objective_control_records),
    ) == [ordinary, end_of_battle]

    duplicate_boundary_records = [
        ordinary,
        end_of_battle,
        _rebuild_state_evidence(
            ordinary,
            current_rules_unit_position_witnesses=(),
        ),
    ]
    with pytest.raises(GameLifecycleError, match="boundaries must have unique"):
        validate_primary_scoring_state_evidence_records(
            duplicate_boundary_records,
            game_id=state.game_id,
            mission_setup=state.mission_setup,
            turn_order=state.turn_order,
            objective_control_records=tuple(state.objective_control_records),
        )


def test_phase17n_step5a_end_of_battle_requires_exact_final_boundary(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, source_record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise AssertionError("Step 5A fixture requires MissionSetup.")
    final_round = mission_scoring_policies_from_setup(mission_setup).game_length_battle_rounds
    first_player_id, final_player_id = state.turn_order
    invalid_boundaries = (
        (final_round - 1, final_player_id, BattlePhase.FIGHT, ObjectiveControlTiming.TURN_END),
        (final_round, first_player_id, BattlePhase.FIGHT, ObjectiveControlTiming.TURN_END),
        (final_round, final_player_id, BattlePhase.COMMAND, ObjectiveControlTiming.TURN_END),
        (final_round, final_player_id, BattlePhase.FIGHT, ObjectiveControlTiming.PHASE_END),
    )

    for battle_round, active_player_id, phase, timing in invalid_boundaries:
        record = replace(
            source_record,
            record_id=(
                f"phase17n-step5a-eob:{battle_round}:{active_player_id}:"
                f"{phase.value}:{timing.value}"
            ),
            battle_round=battle_round,
            active_player_id=active_player_id,
            phase=phase.value,
            timing=timing,
        )
        end_of_battle = _rebuild_state_evidence(
            evidence,
            record=record,
            scoring_boundary_kind=PrimaryScoringBoundaryKind.END_OF_BATTLE,
        )
        with pytest.raises(
            GameLifecycleError,
            match="last player's turn-end record at the final Fight-phase TURN_END boundary",
        ):
            validate_primary_scoring_state_evidence_context(
                end_of_battle,
                mission_setup=mission_setup,
                turn_order=state.turn_order,
                record=record,
                end_of_battle=True,
            )

    final_record = replace(
        source_record,
        record_id=(
            f"phase17n-step5a-eob:{final_round}:{final_player_id}:"
            f"{BattlePhase.FIGHT.value}:{ObjectiveControlTiming.TURN_END.value}"
        ),
        battle_round=final_round,
        active_player_id=final_player_id,
        phase=BattlePhase.FIGHT.value,
        timing=ObjectiveControlTiming.TURN_END,
    )
    final_evidence = _rebuild_state_evidence(
        evidence,
        record=final_record,
        scoring_boundary_kind=PrimaryScoringBoundaryKind.END_OF_BATTLE,
    )
    validate_primary_scoring_state_evidence_context(
        final_evidence,
        mission_setup=mission_setup,
        turn_order=state.turn_order,
        record=final_record,
        end_of_battle=True,
    )


def test_phase17n_step5a_public_payload_redacts_authoritative_state_evidence_registry(
    persisted_primary_scoring_boundary: tuple[
        GameState,
        PrimaryScoringStateEvidence,
    ],
) -> None:
    state, evidence = persisted_primary_scoring_boundary

    authoritative_payload = state.to_payload()
    assert authoritative_payload["primary_scoring_state_evidence_records"] == [
        evidence.to_payload()
    ]
    restored = GameState.from_payload(authoritative_payload)
    assert restored.primary_scoring_state_evidence_records == [evidence]
    for viewer_player_id in state.player_ids:
        assert (
            state.to_public_payload(viewer_player_id=viewer_player_id)[
                "primary_scoring_state_evidence_records"
            ]
            == []
        )


def test_phase17n_step5a_restore_authority_rewinds_later_marker_removal(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    source_state, source_record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    later_state = GameState.from_payload(source_state.to_payload())
    record = next(
        candidate
        for candidate in later_state.objective_control_records
        if candidate.record_id == source_record.record_id
    )
    marker = later_state.primary_mission_progress_state.markers[0]
    later_state.battle_round = 2
    later_state.active_player_id = "player-a"
    later_state.battle_phase_index = later_state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    later_state.replace_primary_mission_progress_state(
        replace(
            later_state.primary_mission_progress_state,
            markers=(
                marker.removed(
                    battle_round=2,
                    phase=BattlePhase.MOVEMENT.value,
                    active_player_id="player-a",
                    source_id="phase17n-step5a-later-removal-source",
                    event_id="phase17n-step5a-later-removal-event",
                ),
            ),
        )
    )

    validate_primary_scoring_state_evidence_restore_authority(
        evidence=evidence,
        state=later_state,
        record=record,
    )


def test_phase17n_step5a_bridge_rejects_rehashed_incomplete_state(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    drifted_values = (
        _rebuild_state_evidence(
            evidence,
            primary_mission_progress_state=PrimaryMissionProgressState.empty(),
        ),
        _rebuild_state_evidence(evidence, primary_mission_action_states=()),
        _rebuild_state_evidence(evidence, primary_battlefield_departure_states=()),
        _rebuild_state_evidence(evidence, current_rules_unit_position_witnesses=()),
    )

    for drifted in drifted_values:
        assert drifted.evidence_hash != evidence.evidence_hash
        with pytest.raises(GameLifecycleError, match="authoritative GameState"):
            validate_primary_scoring_state_evidence_authority(
                drifted,
                state=state,
                record=record,
                end_of_battle=False,
            )


@pytest.mark.parametrize(
    "omitted_family",
    ["progress", "actions", "departures", "positions"],
)
def test_phase17n_step5a_persisted_restore_rejects_coordinated_rehash_and_ledger_update(
    persisted_primary_scoring_boundary: tuple[
        GameState,
        PrimaryScoringStateEvidence,
    ],
    omitted_family: str,
) -> None:
    state, evidence = persisted_primary_scoring_boundary
    if omitted_family == "progress":
        drifted = _rebuild_state_evidence(
            evidence,
            primary_mission_progress_state=PrimaryMissionProgressState.empty(),
        )
    elif omitted_family == "actions":
        drifted = _rebuild_state_evidence(evidence, primary_mission_action_states=())
    elif omitted_family == "departures":
        drifted = _rebuild_state_evidence(
            evidence,
            primary_battlefield_departure_states=(),
        )
    else:
        drifted = _rebuild_state_evidence(
            evidence,
            current_rules_unit_position_witnesses=(),
        )
    assert drifted.evidence_id != evidence.evidence_id
    assert drifted.evidence_hash != evidence.evidence_hash

    payload = deepcopy(state.to_payload())
    payload["primary_scoring_state_evidence_records"] = [drifted.to_payload()]
    updated_transactions = 0
    for ledger_payload in payload["victory_point_ledgers"]:
        for transaction_payload in ledger_payload["transactions"]:
            if transaction_payload["source_kind"] != "primary":
                continue
            metadata = cast(dict[str, object], transaction_payload["metadata"])
            metadata["primary_scoring_state_evidence_id"] = drifted.evidence_id
            metadata["primary_scoring_state_evidence_hash"] = drifted.evidence_hash
            updated_transactions += 1
    assert updated_transactions > 0

    with pytest.raises(
        GameLifecycleError,
        match=r"(?:incomplete for authoritative GameState|cover every authoritative component)",
    ):
        GameState.from_payload(payload)


@pytest.mark.parametrize(
    "field_name",
    ["eligible_unit_instance_ids", "interruption_conditions"],
)
def test_phase17n_step5a_bridge_rejects_malformed_nested_action_lists(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
    field_name: str,
) -> None:
    _state, _record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    payload = cast(dict[str, object], deepcopy(evidence.to_payload()))
    action_payloads = cast(list[object], payload["primary_mission_action_states"])
    action_payload = cast(dict[str, object], action_payloads[0])
    action_payload[field_name] = None

    with pytest.raises(GameLifecycleError, match=rf"{field_name} payload must be a list"):
        PrimaryScoringStateEvidence.from_payload(payload)


def test_phase17n_step5a_current_positions_reject_unaccounted_alive_models(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, _evidence, _departed_unit_id = completed_primary_scoring_boundary
    restored = GameState.from_payload(state.to_payload())
    restored_record = next(
        candidate
        for candidate in restored.objective_control_records
        if candidate.record_id == record.record_id
    )
    battlefield = restored.battlefield_state
    if battlefield is None:
        raise AssertionError("Step 5A fixture requires battlefield state.")
    placed_unit = next(
        placement
        for placed_army in battlefield.placed_armies
        for placement in placed_army.unit_placements
    )
    restored.battlefield_state = battlefield.without_unit_placement(placed_unit.unit_instance_id)

    with pytest.raises(GameLifecycleError, match="alive model with no accounted placement"):
        build_primary_scoring_state_evidence(
            state=restored,
            record=restored_record,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="alive model with no accounted placement"):
        build_primary_rules_unit_turn_start_snapshot(state=restored)


def test_phase17n_step5a_context_rejects_rehashed_started_action_at_turn_end(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    action = evidence.primary_mission_action_states[0]
    started = replace(
        action,
        status=MissionActionStatus.STARTED,
        completed_battle_round=None,
        completed_phase=None,
        interrupted_reason=None,
        score_transaction_id=None,
    )
    drifted = _rebuild_state_evidence(
        evidence,
        primary_mission_action_states=(started,),
    )
    if state.mission_setup is None:
        raise AssertionError("Step 5A fixture requires MissionSetup.")

    with pytest.raises(GameLifecycleError, match=r"cannot retain.*started Action"):
        validate_primary_scoring_state_evidence_context(
            drifted,
            mission_setup=state.mission_setup,
            turn_order=state.turn_order,
            record=record,
            end_of_battle=False,
        )


def test_phase17n_step5a_context_rejects_started_immediate_action(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    action = evidence.primary_mission_action_states[0]
    started = replace(
        action,
        status=MissionActionStatus.STARTED,
        completed_battle_round=None,
        completed_phase=None,
        interrupted_reason=None,
        score_transaction_id=None,
    )
    if state.mission_setup is None:
        raise AssertionError("Step 5A fixture requires MissionSetup.")

    with pytest.raises(
        GameLifecycleError,
        match="cannot retain a started immediate Action",
    ):
        validate_primary_scoring_action_boundary(
            action=started,
            policy=primary_scoring_action_policies_by_id(state.mission_setup)["surveil-enemy-unit"],
            record=record,
            turn_order=state.turn_order,
            battle_phase_sequence=tuple(phase.value for phase in BattlePhase),
        )


def test_phase17n_step5a_context_binds_action_victory_points_to_source_policy(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    if state.mission_setup is None:
        raise AssertionError("Step 5A fixture requires MissionSetup.")
    action = evidence.primary_mission_action_states[0]
    forged_action = replace(
        action,
        victory_points=1,
        score_transaction_id="phase17n-step5a-forged-action-transaction",
    )
    forged_evidence = _rebuild_state_evidence(
        evidence,
        primary_mission_action_states=(forged_action,),
    )

    with pytest.raises(GameLifecycleError, match="drifted from its registered policy"):
        validate_primary_scoring_state_evidence_context(
            forged_evidence,
            mission_setup=state.mission_setup,
            turn_order=state.turn_order,
            record=record,
            end_of_battle=False,
        )


def test_phase17n_step5a_context_rejects_future_progress_boundaries(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise AssertionError("Step 5A fixture requires MissionSetup.")
    progress = evidence.primary_mission_progress_state
    marker = progress.markers[0]
    player_b_mission_id = mission_setup.primary_mission_assignment_for_player(
        "player-b"
    ).primary_mission_id
    player_b_position = next(
        witness
        for witness in evidence.current_rules_unit_position_witnesses
        if witness.owner_player_id == "player-b"
    )
    future_selection = _condemned_selection(
        game_id=evidence.game_id,
        owner_player_id="player-b",
        mission_id=player_b_mission_id,
        battle_round=1,
    )
    future_creation = _consecration_designation(
        game_id=evidence.game_id,
        owner_player_id="player-b",
        mission_id=player_b_mission_id,
        rules_unit_instance_id=player_b_position.rules_unit_instance_id,
        component_unit_instance_ids=(
            player_b_position.rules_unit_membership.component_unit_instance_ids
        ),
        created_active_player_id="player-b",
        created_phase=BattlePhase.COMMAND.value,
    )
    future_resolution = _consecration_designation(
        game_id=evidence.game_id,
        owner_player_id="player-b",
        mission_id=player_b_mission_id,
        rules_unit_instance_id=player_b_position.rules_unit_instance_id,
        component_unit_instance_ids=(
            player_b_position.rules_unit_membership.component_unit_instance_ids
        ),
        created_active_player_id="player-a",
        created_phase=BattlePhase.COMMAND.value,
    ).resolved_without_consumption(
        battle_round=1,
        active_player_id="player-b",
        event_id="phase17n-step5a-future-resolution-event",
    )
    future_progress_values = (
        (
            replace(
                progress,
                markers=(
                    marker.removed(
                        battle_round=2,
                        phase=BattlePhase.MOVEMENT.value,
                        active_player_id="player-a",
                        source_id="phase17n-step5a-future-removal-source",
                        event_id="phase17n-step5a-future-removal-event",
                    ),
                ),
            ),
            "mission marker removal cannot come from a future boundary",
        ),
        (
            replace(progress, condemned_selections=(future_selection,)),
            "condemned selection cannot come from a future turn",
        ),
        (
            replace(progress, consecration_designations=(future_creation,)),
            "consecration creation cannot come from a future boundary",
        ),
        (
            replace(progress, consecration_designations=(future_resolution,)),
            "consecration resolution cannot come from a future turn",
        ),
    )

    for drifted_progress, expected_error in future_progress_values:
        drifted = _rebuild_state_evidence(
            evidence,
            primary_mission_progress_state=drifted_progress,
        )
        with pytest.raises(GameLifecycleError, match=expected_error):
            validate_primary_scoring_state_evidence_context(
                drifted,
                mission_setup=mission_setup,
                turn_order=state.turn_order,
                record=record,
                end_of_battle=False,
            )


def test_phase17n_step5a_bridge_filters_non_primary_actions_and_preserves_groups(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    restored = GameState.from_payload(state.to_payload())
    restored_record = next(
        candidate
        for candidate in restored.objective_control_records
        if candidate.record_id == record.record_id
    )
    primary_action = evidence.primary_mission_action_states[0]
    restored.mission_action_states.append(
        replace(
            primary_action,
            action_id="phase17n-step5a-secondary-action",
            mission_action_id="cleanse-objective",
            mission_id="cleanse",
            scoring_source_id="cleanse",
        )
    )
    restored.mission_action_states.sort(key=lambda action: action.action_id)
    player_a_army = next(army for army in restored.army_definitions if army.player_id == "player-a")
    bodyguard, leader = player_a_army.units[:2]
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    formation = AttachedUnitFormation(
        attached_unit_instance_id=(
            f"attached-unit:{player_a_army.army_id}:phase17n-step5a-player-a"
        ),
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=component_ids,
        source_id="phase17n-step5a-attached-source",
        attachment_source_ids=("phase17n-step5a-attachment-rule",),
    )
    restored.army_definitions = [
        replace(army, attached_units=(formation,)) if army.player_id == "player-a" else army
        for army in restored.army_definitions
    ]
    unit_by_id = {
        unit.unit_instance_id: unit for army in restored.army_definitions for unit in army.units
    }
    restored.starting_attached_unit_records.append(
        StartingAttachedUnitRecord.from_formation(
            player_id="player-a",
            attached_unit=formation,
            unit_by_id=unit_by_id,
        )
    )
    restored.starting_attached_unit_records.sort(
        key=lambda record: record.attached_unit_instance_id
    )

    grouped = build_primary_scoring_state_evidence(
        state=restored,
        record=restored_record,
        end_of_battle=False,
    )

    assert grouped.primary_mission_action_states == (primary_action,)
    group_witness = grouped.position_witness_for_rules_unit(formation.attached_unit_instance_id)
    assert group_witness.owner_player_id == "player-a"
    assert group_witness.rules_unit_membership.component_unit_instance_ids == component_ids


def test_phase17n_step5a_bridge_rejects_unknown_assigned_primary_action(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    restored = GameState.from_payload(state.to_payload())
    restored_record = next(
        candidate
        for candidate in restored.objective_control_records
        if candidate.record_id == record.record_id
    )
    primary_action = evidence.primary_mission_action_states[0]
    restored.mission_action_states.append(
        replace(
            primary_action,
            action_id="phase17n-step5a-unknown-primary-action",
            mission_action_id="unknown-primary-action",
        )
    )
    restored.mission_action_states.sort(key=lambda action: action.action_id)

    with pytest.raises(GameLifecycleError, match="Action policy is not registered"):
        build_primary_scoring_state_evidence(
            state=restored,
            record=restored_record,
            end_of_battle=False,
        )


def test_phase17n_step5a_bridge_fails_closed_for_tamper_and_unauthenticated_state(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    state, record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    for field_name, drifted_value in {
        "game_id": "phase17n-step5a-foreign-game",
        "battlefield_id": "phase17n-step5a-foreign-battlefield",
        "battle_round": record.battle_round + 1,
        "active_player_id": "player-b",
        "phase": BattlePhase.COMMAND.value,
        "timing": ObjectiveControlTiming.PHASE_END.value,
        "scoring_boundary_kind": "end_of_battle",
        "objective_control_record_id": "phase17n-step5a-foreign-record",
        "objective_control_record_hash": "0" * 64,
    }.items():
        payload = cast(dict[str, object], deepcopy(evidence.to_payload()))
        payload[field_name] = drifted_value
        with pytest.raises(GameLifecycleError, match="hash drifted"):
            PrimaryScoringStateEvidence.from_payload(payload)

    drifted = PrimaryScoringStateEvidence.create(
        game_id="phase17n-step5a-foreign-game",
        battlefield_id=evidence.battlefield_id,
        battle_round=evidence.battle_round,
        active_player_id=evidence.active_player_id,
        phase=evidence.phase,
        timing=evidence.timing,
        scoring_boundary_kind=evidence.scoring_boundary_kind,
        objective_control_record_id=evidence.objective_control_record_id,
        objective_control_record_hash=evidence.objective_control_record_hash,
        scoring_commit_checkpoint_id=evidence.scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=evidence.scoring_commit_checkpoint_hash,
        primary_mission_progress_state=evidence.primary_mission_progress_state,
        primary_mission_action_states=evidence.primary_mission_action_states,
        primary_battlefield_departure_states=(evidence.primary_battlefield_departure_states),
        primary_unit_destruction_state_ids=evidence.primary_unit_destruction_state_ids,
        current_rules_unit_position_witnesses=(evidence.current_rules_unit_position_witnesses),
        primary_scoring_spatial_evidence_by_player_id=(
            evidence.primary_scoring_spatial_evidence_by_player_id
        ),
    )
    if state.mission_setup is None:
        raise AssertionError("Step 5A fixture requires MissionSetup.")
    with pytest.raises(GameLifecycleError, match="ObjectiveControlRecord"):
        validate_primary_scoring_state_evidence_context(
            drifted,
            mission_setup=state.mission_setup,
            turn_order=state.turn_order,
            record=record,
            end_of_battle=False,
        )

    missing_record_state = GameState.from_payload(state.to_payload())
    missing_record_state.objective_control_records = []
    with pytest.raises(GameLifecycleError, match="authoritative stored record"):
        build_primary_scoring_state_evidence(
            state=missing_record_state,
            record=record,
            end_of_battle=False,
        )

    duplicate_record_state = GameState.from_payload(state.to_payload())
    duplicate_record = next(
        candidate
        for candidate in duplicate_record_state.objective_control_records
        if candidate.record_id == record.record_id
    )
    duplicate_record_state.objective_control_records.append(duplicate_record)
    with pytest.raises(GameLifecycleError, match="authoritative stored record"):
        build_primary_scoring_state_evidence(
            state=duplicate_record_state,
            record=duplicate_record,
            end_of_battle=False,
        )


def test_phase17n_step5a_bridge_rejects_duplicate_untyped_and_unsorted_rows(
    completed_primary_scoring_boundary: tuple[
        GameState,
        ObjectiveControlRecord,
        PrimaryScoringStateEvidence,
        str,
    ],
) -> None:
    _state, _record, evidence, _departed_unit_id = completed_primary_scoring_boundary
    action = evidence.primary_mission_action_states[0]
    departure = evidence.primary_battlefield_departure_states[0]
    with pytest.raises(GameLifecycleError, match="Action identities must be unique"):
        _rebuild_state_evidence(
            evidence,
            primary_mission_action_states=(action, action),
        )
    with pytest.raises(GameLifecycleError, match="typed states"):
        _rebuild_state_evidence(
            evidence,
            primary_mission_action_states=cast(
                tuple[MissionActionState, ...],
                ("not-an-action",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="Action history must be sorted"):
        _rebuild_state_evidence(
            evidence,
            primary_mission_action_states=(
                replace(action, action_id="phase17n-step5a-z-action"),
                action,
            ),
        )
    with pytest.raises(GameLifecycleError, match="departure identities must be unique"):
        _rebuild_state_evidence(
            evidence,
            primary_battlefield_departure_states=(departure, departure),
        )
    with pytest.raises(GameLifecycleError, match="positions must be unique"):
        _rebuild_state_evidence(
            evidence,
            current_rules_unit_position_witnesses=(
                evidence.current_rules_unit_position_witnesses[0],
                evidence.current_rules_unit_position_witnesses[0],
            ),
        )


def test_phase17n_step5a_turn_end_bridge_rejects_unresolved_primary_action() -> None:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="reconnaissance-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id="extract-intelligence",
        current_phase=BattlePhase.FIGHT,
    )
    record = phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )

    with pytest.raises(GameLifecycleError, match=r"cannot retain.*started Action"):
        build_primary_scoring_state_evidence(
            state=state,
            record=record,
            end_of_battle=False,
        )


@pytest.fixture(scope="module")
def retained_objective_control_authority() -> tuple[
    GameState,
    ObjectiveControlRecord,
    ObjectiveControlRecordAuthority,
]:
    state, _decisions, _action, _target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise AssertionError("Step 5A sticky fixture requires mission setup.")
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=mission_setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
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
    player_b_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
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
    return state, retained_record, state.objective_control_record_authorities[-1]


def test_phase17n_step5a_retained_zero_control_authority_round_trips(
    retained_objective_control_authority: tuple[
        GameState,
        ObjectiveControlRecord,
        ObjectiveControlRecordAuthority,
    ],
) -> None:
    state, record, authority = retained_objective_control_authority
    retained_result = next(
        result for result in record.results if result.retained_control_source_id is not None
    )

    assert retained_result.contributors == ()
    assert retained_result.scores == (ObjectiveControlScore(player_id="player-a", score=0),)
    assert authority.retained_sticky_objective_control_states == tuple(
        state.sticky_objective_control_states
    )
    assert GameState.from_payload(deepcopy(state.to_payload())).to_payload() == state.to_payload()


def test_phase17n_step5a_authority_round_trip_preserves_record_history_order(
    retained_objective_control_authority: tuple[
        GameState,
        ObjectiveControlRecord,
        ObjectiveControlRecordAuthority,
    ],
) -> None:
    source_state, turn_end_record, _authority = retained_objective_control_authority
    state = GameState.from_payload(deepcopy(source_state.to_payload()))
    phase_end_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.FIGHT,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    phase_end_record = apply_sticky_objective_control(
        record=phase_end_record,
        states=tuple(state.sticky_objective_control_states),
    )
    state.record_objective_control_record(phase_end_record)

    record_ids = [record.record_id for record in state.objective_control_records]
    assert record_ids == [turn_end_record.record_id, phase_end_record.record_id]
    assert record_ids != sorted(record_ids)
    assert [
        authority.objective_control_record_id
        for authority in state.objective_control_record_authorities
    ] == record_ids

    payload = state.to_payload()
    assert GameState.from_payload(deepcopy(payload)).to_payload() == payload


@pytest.mark.parametrize(
    ("field_name", "forged_value", "message"),
    [
        ("authority_hash", "0" * 64, "authority hash drifted"),
        ("authority_id", f"objective-control-record-authority:{'0' * 64}", "identity drifted"),
    ],
)
def test_phase17n_step5a_restore_rejects_malformed_objective_control_authority_identity(
    retained_objective_control_authority: tuple[
        GameState,
        ObjectiveControlRecord,
        ObjectiveControlRecordAuthority,
    ],
    field_name: str,
    forged_value: str,
    message: str,
) -> None:
    state, _record, _authority = retained_objective_control_authority
    payload = deepcopy(state.to_payload())
    cast(dict[str, object], payload["objective_control_record_authorities"][0])[field_name] = (
        forged_value
    )

    with pytest.raises(GameLifecycleError, match=message):
        GameState.from_payload(payload)


def test_phase17n_step5a_restore_rejects_incomplete_objective_control_authority_registry(
    retained_objective_control_authority: tuple[
        GameState,
        ObjectiveControlRecord,
        ObjectiveControlRecordAuthority,
    ],
) -> None:
    state, _record, _authority = retained_objective_control_authority
    payload = deepcopy(state.to_payload())
    payload["objective_control_record_authorities"] = []

    with pytest.raises(GameLifecycleError, match="authority registry is incomplete"):
        GameState.from_payload(payload)


def test_phase17n_step5a_restore_rejects_rehashed_unregistered_sticky_source_witness(
    retained_objective_control_authority: tuple[
        GameState,
        ObjectiveControlRecord,
        ObjectiveControlRecordAuthority,
    ],
) -> None:
    state, record, authority = retained_objective_control_authority
    source_witness = authority.retained_sticky_objective_control_states[0]
    forged_witness = replace(
        source_witness,
        state_id="phase17n-step5a-forged-retained-control-state",
        source_rule_id="phase17n-step5a-forged-retained-control-source",
        source_event_id="phase17n-step5a-forged-retained-control-event",
    )
    retained_result = next(
        result for result in record.results if result.retained_control_source_id is not None
    )
    forged_result = replace(
        retained_result,
        retained_control_source_id=forged_witness.source_rule_id,
    )
    forged_record = replace(
        record,
        results=tuple(
            forged_result if result.objective_id == forged_result.objective_id else result
            for result in record.results
        ),
    )

    with pytest.raises(GameLifecycleError, match="lacks state or expiry authority"):
        GameState.from_payload(
            _coordinated_objective_control_authority_payload(
                state=state,
                forged_record=forged_record,
                authority=authority,
                retained_sticky_objective_control_states=(forged_witness,),
            )
        )


def test_phase17n_step5a_restore_rejects_rehashed_objective_control_distance_forgery(
    retained_objective_control_authority: tuple[
        GameState,
        ObjectiveControlRecord,
        ObjectiveControlRecordAuthority,
    ],
) -> None:
    state, record, authority = retained_objective_control_authority
    contributing_result = next(result for result in record.results if result.contributors)
    contribution = contributing_result.contributors[0]
    forged_result = replace(
        contributing_result,
        contributors=(
            replace(
                contribution,
                horizontal_distance_inches=contribution.horizontal_distance_inches + 1.0,
            ),
            *contributing_result.contributors[1:],
        ),
    )
    forged_record = replace(
        record,
        results=tuple(
            forged_result if result.objective_id == forged_result.objective_id else result
            for result in record.results
        ),
    )

    with pytest.raises(GameLifecycleError, match="identity or characteristic authority drifted"):
        GameState.from_payload(
            _coordinated_objective_control_authority_payload(
                state=state,
                forged_record=forged_record,
                authority=authority,
            )
        )


def test_phase17n_step5a_restore_rejects_rehashed_objective_membership_forgery(
    retained_objective_control_authority: tuple[
        GameState,
        ObjectiveControlRecord,
        ObjectiveControlRecordAuthority,
    ],
) -> None:
    state, record, authority = retained_objective_control_authority
    source = next(result for result in record.results if result.contributors)
    destination = next(
        result
        for result in record.results
        if not result.contributors and result.retained_control_source_id is None
    )
    contribution = source.contributors[0]
    forged_source = ObjectiveControlResult.from_contributors(
        objective_id=source.objective_id,
        contributors=source.contributors[1:],
    )
    forged_destination = ObjectiveControlResult.from_contributors(
        objective_id=destination.objective_id,
        contributors=(contribution,),
    )
    forged_record = replace(
        record,
        results=tuple(
            forged_source
            if result.objective_id == source.objective_id
            else (forged_destination if result.objective_id == destination.objective_id else result)
            for result in record.results
        ),
    )

    with pytest.raises(GameLifecycleError, match="contributor objective membership drifted"):
        GameState.from_payload(
            _coordinated_objective_control_authority_payload(
                state=state,
                forged_record=forged_record,
                authority=authority,
            )
        )


def test_phase17n_step5a_restore_rejects_rehashed_battle_shock_removal() -> None:
    state, _decisions, _action, _target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise AssertionError("Step 5A Battle-shock fixture requires mission setup.")
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=mission_setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    shocked_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    shocked_state = BattleShockedUnitState(
        player_id="player-b",
        unit_instance_id=shocked_unit.unit_instance_id,
        model_instance_ids=shocked_unit.own_model_ids(),
        source_result_id="phase17n-step5a-battle-shock-result",
        battle_round_started=state.battle_round,
        expires_at_player_command_phase_start="player-b",
        expires_at_battle_round=state.battle_round + 1,
    )
    state.battle_shocked_unit_ids = [shocked_unit.unit_instance_id]
    state.battle_shocked_unit_states = [shocked_state]
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=BattlePhase.FIGHT,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    shocked_contributors = tuple(
        contribution
        for result in record.results
        for contribution in result.contributors
        if contribution.unit_instance_id == shocked_unit.unit_instance_id
    )
    assert shocked_contributors
    assert all(
        contribution.battle_shocked and contribution.effective_objective_control == 0
        for contribution in shocked_contributors
    )
    state.record_objective_control_record(record)
    authority = state.objective_control_record_authorities[-1]
    forged_checkpoint = _rebuild_objective_control_checkpoint(
        authority.boundary_checkpoint,
        battle_shocked_unit_instance_ids=(),
    )
    forged_results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=result.objective_id,
            contributors=tuple(
                replace(
                    contribution,
                    battle_shocked=False,
                    effective_objective_control=contribution.objective_control,
                )
                if contribution.unit_instance_id == shocked_unit.unit_instance_id
                else contribution
                for contribution in result.contributors
            ),
        )
        for result in record.results
    )
    forged_record = replace(record, results=forged_results)

    with pytest.raises(
        GameLifecycleError,
        match="current-boundary Battle-shock authority drifted",
    ):
        GameState.from_payload(
            _coordinated_objective_control_authority_payload(
                state=state,
                forged_record=forged_record,
                authority=authority,
                boundary_checkpoint=forged_checkpoint,
            )
        )


def test_phase17n_step5a_restore_rejects_rehashed_retained_control_without_source_authority(
    persisted_primary_scoring_boundary: tuple[
        GameState,
        PrimaryScoringStateEvidence,
    ],
) -> None:
    state, evidence = persisted_primary_scoring_boundary
    assert state.sticky_objective_control_states == []
    record = next(
        candidate
        for candidate in state.objective_control_records
        if candidate.record_id == evidence.objective_control_record_id
    )
    controlled_result = next(
        result for result in record.results if result.controlled_by_player_id == "player-a"
    )
    retained_result = replace(
        controlled_result,
        status=ObjectiveControlStatus.CONTROLLED,
        controlled_by_player_id="player-a",
        scores=(ObjectiveControlScore(player_id="player-a", score=0),),
        contributors=(),
        retained_control_source_id="phase17n-step5a-forged-retained-source",
    )
    forged_record = replace(
        record,
        results=tuple(
            retained_result if result.objective_id == retained_result.objective_id else result
            for result in record.results
        ),
    )

    with pytest.raises(
        GameLifecycleError,
        match=r"(?:[Oo]bjective(?:[ -]?[Cc])ontrol|Primary scoring)",
    ):
        GameState.from_payload(
            _coordinated_objective_control_forgery_payload(
                state=state,
                evidence=evidence,
                forged_record=forged_record,
            )
        )


def test_phase17n_step5a_restore_rejects_rehashed_inflated_effective_oc_contributor(
    persisted_primary_scoring_boundary: tuple[
        GameState,
        PrimaryScoringStateEvidence,
    ],
) -> None:
    state, evidence = persisted_primary_scoring_boundary
    record = next(
        candidate
        for candidate in state.objective_control_records
        if candidate.record_id == evidence.objective_control_record_id
    )
    controlled_result = next(
        result for result in record.results if result.controlled_by_player_id == "player-a"
    )
    contribution = controlled_result.contributors[0]
    inflated_result = ObjectiveControlResult.from_contributors(
        objective_id=controlled_result.objective_id,
        contributors=(
            replace(
                contribution,
                effective_objective_control=contribution.effective_objective_control + 8,
            ),
        ),
    )
    forged_record = replace(
        record,
        results=tuple(
            inflated_result if result.objective_id == inflated_result.objective_id else result
            for result in record.results
        ),
    )

    with pytest.raises(
        GameLifecycleError,
        match=r"(?:[Oo]bjective(?:[ -]?[Cc])ontrol|Primary scoring)",
    ):
        GameState.from_payload(
            _coordinated_objective_control_forgery_payload(
                state=state,
                evidence=evidence,
                forged_record=forged_record,
            )
        )


@pytest.mark.parametrize(
    ("removed_transaction_count", "remove_evidence"),
    [(1, False), (None, False), (None, True)],
)
def test_phase17n_step5a_restore_rejects_primary_scoring_bridge_erasure(
    persisted_primary_scoring_boundary: tuple[
        GameState,
        PrimaryScoringStateEvidence,
    ],
    removed_transaction_count: int | None,
    remove_evidence: bool,
) -> None:
    state, _evidence = persisted_primary_scoring_boundary
    payload = deepcopy(state.to_payload())
    removed = 0
    for ledger in payload["victory_point_ledgers"]:
        primary_indices = [
            index
            for index, transaction in enumerate(ledger["transactions"])
            if transaction["source_kind"] == "primary"
        ]
        if not primary_indices:
            continue
        count = len(primary_indices) if removed_transaction_count is None else 1
        if removed_transaction_count == 1 and len(primary_indices) < 2:
            raise AssertionError("Step 5A partial-erasure fixture requires multiple awards.")
        removed_indices = set(primary_indices[-count:])
        ledger["transactions"] = [
            transaction
            for index, transaction in enumerate(ledger["transactions"])
            if index not in removed_indices
        ]
        ledger["victory_points"] = sum(
            transaction["amount"] for transaction in ledger["transactions"]
        )
        removed += count
    if removed == 0:
        raise AssertionError("Step 5A erasure fixture requires Primary transactions.")
    if remove_evidence:
        payload["primary_scoring_state_evidence_records"] = []

    with pytest.raises(
        GameLifecycleError,
        match=r"Primary (?:VP transactions|scoring-state evidence registry)",
    ):
        GameState.from_payload(payload)


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
    forged_state.primary_scoring_state_evidence_records = []
    forged_evidence = build_primary_scoring_state_evidence(
        state=forged_state,
        record=forged_record,
        end_of_battle=False,
    )
    forged_state.primary_scoring_state_evidence_records = [forged_evidence]
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
) -> PrimaryScoringStateEvidence:
    return PrimaryScoringStateEvidence.create(
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
