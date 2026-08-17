from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from json import loads as json_loads
from re import escape
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    army_muster_request,
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    ruleset,
    secondary_choice,
    with_model_offsets,
)
from tests.phase11c_command_phase_helpers import (
    mission_setup as phase11c_mission_setup,
)
from tests.phase17n_primary_mission_helpers import (
    append_authenticated_normal_move,
    phase17n_event_setup,
    phase17n_state_with_setup,
)
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
)
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
    PrimaryMissionObjectiveControlModifierSource,
)
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    primary_mission_model_placements_from_checkpoint,
)
from warhammer40k_core.engine.primary_position_membership import (
    build_primary_rules_unit_membership_from_model_placements,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH,
    PrimaryScoringBoundaryLifecyclePayload,
    PrimaryScoringBoundaryStatus,
    mark_pending_primary_scoring_boundaries,
    pending_primary_scoring_boundary_keys,
    resolve_primary_scoring_boundary_lifecycle,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    bound_primary_scoring_commit_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint_authority import (
    validate_primary_scoring_spatial_rows_from_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitnessPayload,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    TABLE_QUARTER_NORTH_WEST,
    PrimaryTerritoryUnitWitness,
    build_primary_scoring_spatial_evidence,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
    PrimaryScoringStateEvidencePayload,
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.return_on_death import (
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    PendingReturnOnDeath,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    apply_return_on_death_placement_decision,
    resolve_pending_return_on_death_phase_end,
)
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.sticky_objective_control import StickyObjectiveControlState
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
)
from warhammer40k_core.geometry.pose import Pose

_OC_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
)


def test_scoreable_command_boundary_restores_while_end_phase_decision_is_pending() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    state = restored.state
    assert state is not None
    assert pending_primary_scoring_boundary_keys(state=state)
    assert all(
        row.status is PrimaryScoringBoundaryStatus.PENDING
        for row in state.primary_scoring_boundary_lifecycles
    )
    assert state.primary_scoring_state_evidence_records == []


def test_final_turn_end_boundary_restores_while_step_four_choice_is_pending() -> None:
    lifecycle = _pending_final_turn_end_boundary_lifecycle()
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    state = restored.state
    assert state is not None
    assert any(
        row.scoring_boundary_kind.value == "end_of_battle"
        and row.status is PrimaryScoringBoundaryStatus.PENDING
        for row in state.primary_scoring_boundary_lifecycles
    )


def test_resolving_pending_command_boundary_closes_exactly_once() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    state = lifecycle.state
    assert state is not None
    request = lifecycle.decision_controller.queue.peek_next()
    lifecycle.decision_controller.submit_result(
        DecisionResult.for_request(
            result_id=f"{request.request_id}-resolved",
            request=request,
            selected_option_id="continue",
        )
    )
    record = state.objective_control_records[-1]
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=lifecycle.decision_controller.event_log,
    )
    evidence_ids = tuple(
        evidence.evidence_id for evidence in state.primary_scoring_state_evidence_records
    )
    transaction_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY
    )
    assert evidence_ids
    assert all(
        row.status is PrimaryScoringBoundaryStatus.RESOLVED
        for row in state.primary_scoring_boundary_lifecycles
    )
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert (
        tuple(evidence.evidence_id for evidence in state.primary_scoring_state_evidence_records)
        == evidence_ids
    )
    assert (
        tuple(
            transaction.transaction_id
            for ledger in state.victory_point_ledgers
            for transaction in ledger.transactions
            if transaction.source_kind is VictoryPointSourceKind.PRIMARY
        )
        == transaction_ids
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_restore_rejects_unclosed_scoreable_boundary_after_lifecycle_advances() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    payload["state"]["battle_round"] = 3
    with pytest.raises(
        GameLifecycleError,
        match=escape("Primary scoring boundary remains unclosed after the lifecycle has advanced."),
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_pending_boundary_without_queue_authority() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    payload["decisions"]["queue"]["pending_requests"] = []
    with pytest.raises(
        GameLifecycleError,
        match=escape("Pending Primary scoring boundary has no corresponding queue authority."),
    ):
        GameLifecycle.from_payload(payload)


def test_unmet_secondary_leaves_lifecycle_payload_unchanged_when_primary_would_score() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=2)
    state = lifecycle.state
    assert state is not None
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.CENTRAL)
    _place_player_away_from_objectives(state, player_id="player-b")
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=2,
            source_result_id="p2-unmet-bring-it-down",
        )
    )
    before = canonical_json(lifecycle.to_payload())
    with pytest.raises(
        GameLifecycleError,
        match=escape("State-backed secondary mission requirements are not met."),
    ):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert canonical_json(lifecycle.to_payload()) == before
    assert state.objective_control_records == []
    assert state.primary_scoring_state_evidence_records == []


def test_unmet_secondary_at_zero_award_primary_boundary_leaves_no_oc_or_evidence() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=1)
    state = lifecycle.state
    assert state is not None
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=1,
            source_result_id="p2-zero-award-bring-it-down",
        )
    )
    with pytest.raises(
        GameLifecycleError,
        match=escape("State-backed secondary mission requirements are not met."),
    ):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert state.objective_control_records == []
    assert state.objective_control_record_authorities == []
    assert state.primary_scoring_state_evidence_records == []


def test_successful_state_backed_scoring_restores_full_lifecycle_without_manual_event() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=2)
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.ATTACKER_HOME)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.DEFENDER_HOME)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=2,
            source_result_id="p2-defend-stronghold",
        )
    )
    scored = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert scored.status.value == "scored"
    assert any(
        event.event_type == "end_boundary_objective_control_determined"
        for event in lifecycle.decision_controller.event_log.records
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    assert restored.decision_controller.to_payload() == lifecycle.decision_controller.to_payload()


def test_secondary_ledger_failure_rolls_back_entire_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    original = GameState.award_victory_points

    def _fail_secondary(self: GameState, award: VictoryPointAward) -> VictoryPointTransaction:
        if self is state and award.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
            raise GameLifecycleError("injected secondary ledger failure")
        return original(self, award)

    monkeypatch.setattr(GameState, "award_victory_points", _fail_secondary)
    before = canonical_json(lifecycle.to_payload())
    with pytest.raises(GameLifecycleError, match="injected secondary ledger failure"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert canonical_json(lifecycle.to_payload()) == before


def test_tactical_card_failure_rolls_back_ledgers_and_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    original = GameState.replace_secondary_mission_card_state

    def _fail_card(self: GameState, card_state: SecondaryMissionCardState) -> None:
        if self is state:
            raise GameLifecycleError("injected tactical card failure")
        original(self, card_state)

    monkeypatch.setattr(GameState, "replace_secondary_mission_card_state", _fail_card)
    before = canonical_json(lifecycle.to_payload())
    with pytest.raises(GameLifecycleError, match="injected tactical card failure"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert canonical_json(lifecycle.to_payload()) == before


def test_second_state_backed_scoring_call_is_deterministic() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    after_first = canonical_json(lifecycle.to_payload())
    second = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert second == first
    assert canonical_json(lifecycle.to_payload()) == after_first
    primary_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY
    )
    secondary_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
    )
    assert len(primary_ids) == len(set(primary_ids))
    assert len(secondary_ids) == 1


def test_primary_rescore_after_tactical_card_commit_uses_frozen_evidence() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    turn_end_records = tuple(
        record
        for record in state.objective_control_records
        if record.timing is ObjectiveControlTiming.TURN_END
    )
    assert len(turn_end_records) == 1
    evidence_before = tuple(state.primary_scoring_state_evidence_records)
    ledgers_before = tuple(state.victory_point_ledgers)
    score_primary_objective_control_boundary(
        state=state,
        record=turn_end_records[0],
        end_of_battle=False,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert tuple(state.primary_scoring_state_evidence_records) == evidence_before
    assert tuple(state.victory_point_ledgers) == ledgers_before


def test_authenticated_movement_between_oc_and_scoring_round_trips() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle)


def test_authenticated_destruction_between_oc_and_scoring_round_trips() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="destroy")
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle)


def test_authenticated_return_on_death_between_oc_and_scoring_round_trips() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="return_on_death")
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle)


def test_coordinated_rewrite_of_post_oc_mutation_and_scoring_checkpoint_fails() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    commit_event = next(
        event for event in events if event["event_type"] == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
    )
    assert isinstance(commit_event, dict)
    raw_payload = commit_event["payload"]
    assert isinstance(raw_payload, dict)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(raw_payload["checkpoint"])
    rewritten_states = tuple(_offset_checkpoint_model_state(row) for row in checkpoint.model_states)
    rewritten = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=checkpoint.active_player_id,
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=rewritten_states,
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=checkpoint.battle_shocked_unit_instance_ids,
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=checkpoint.objective_control_modifier_sources,
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )
    raw_payload["checkpoint"] = rewritten.to_payload()
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    old_evidence_id = evidence["evidence_id"]
    evidence["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
    evidence["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
    content = {
        key: value for key, value in evidence.items() if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    evidence["evidence_id"] = f"primary-scoring-state-evidence:{digest}"
    evidence["evidence_hash"] = digest
    for ledger in payload["state"]["victory_point_ledgers"]:
        for transaction in ledger["transactions"]:
            metadata = transaction["metadata"]
            if not isinstance(metadata, dict):
                continue
            if metadata.get("primary_scoring_state_evidence_id") != old_evidence_id:
                continue
            metadata["primary_scoring_state_evidence_id"] = evidence["evidence_id"]
            metadata["primary_scoring_state_evidence_hash"] = digest
    for row in payload["state"]["primary_scoring_boundary_lifecycles"]:
        if row["evidence_id"] != old_evidence_id:
            continue
        row["evidence_id"] = evidence["evidence_id"]
        row["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
        row["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
        lifecycle_content = {
            key: value
            for key, value in row.items()
            if key not in {"lifecycle_id", "lifecycle_hash"}
        }
        lifecycle_digest = canonical_payload_sha256(lifecycle_content)
        row["lifecycle_id"] = f"primary-scoring-boundary-lifecycle:{lifecycle_digest}"
        row["lifecycle_hash"] = lifecycle_digest
    with pytest.raises(GameLifecycleError, match="movement history"):
        GameLifecycle.from_payload(payload)


def test_evidence_without_scoring_commit_checkpoint_event_fails_restore() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.COMMAND, battle_round=2)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=decisions, record=record)
    evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=False,
    )
    assert state.mission_setup is not None
    awards = mission_scoring_policies_from_setup(
        state.mission_setup
    ).primary_awards_from_objective_control(
        record=record,
        authoritative_state=state,
        end_of_battle=False,
    )
    record_primary_scoring_state_evidence(state=state, evidence=evidence)
    for award in awards:
        state.award_victory_points(award)
    resolve_primary_scoring_boundary_lifecycle(
        state=state,
        record=record,
        scoring_boundary_kind=PrimaryScoringBoundaryKind.ORDINARY,
        scoring_commit_checkpoint_id=evidence.scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=evidence.scoring_commit_checkpoint_hash,
        evidence_id=evidence.evidence_id,
    )
    with pytest.raises(
        GameLifecycleError,
        match=escape(
            "Primary scoring position evidence requires exactly one scoring-commit checkpoint."
        ),
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())


def test_forged_table_quarter_witness_fails_restore_after_coordinated_rehash() -> None:
    lifecycle = _scored_reconnaissance_turn_end_lifecycle()
    state = lifecycle.state
    assert state is not None
    payload = deepcopy(lifecycle.to_payload())
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    spatial_rows = evidence["primary_scoring_spatial_evidence_by_player_id"]
    assert spatial_rows
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == "player-a"
        for candidate in army.units
    )
    spatial_rows[0]["table_quarter_unit_witnesses"] = [
        {
            "rules_unit_instance_id": unit.unit_instance_id,
            "quarter_id": TABLE_QUARTER_NORTH_WEST,
            "model_instance_ids": [unit.own_models[0].model_instance_id],
        }
    ]
    _rehash_evidence_transactions_and_lifecycles(payload, evidence=evidence)
    with pytest.raises(GameLifecycleError, match="spatial evidence drifted"):
        GameLifecycle.from_payload(payload)


def test_forged_territory_witness_fails_restore_after_coordinated_rehash() -> None:
    lifecycle = _scored_determined_acquisition_command_lifecycle()
    state = lifecycle.state
    assert state is not None
    payload = deepcopy(lifecycle.to_payload())
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    spatial_rows = evidence["primary_scoring_spatial_evidence_by_player_id"]
    assert spatial_rows
    territory_row = next(
        row
        for row in spatial_rows
        if "each_controlled_objective_in_opponent_territory" in row["requested_condition_ids"]
    )
    assert state.mission_setup is not None
    marker_id = next(
        marker.objective_marker_id
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.DEFENDER_HOME
    )
    authentic = list(territory_row["opponent_territory_objective_ids"])
    if marker_id in authentic:
        territory_row["opponent_territory_objective_ids"] = [
            objective_id for objective_id in authentic if objective_id != marker_id
        ]
    else:
        territory_row["opponent_territory_objective_ids"] = [*authentic, marker_id]
    _rehash_evidence_transactions_and_lifecycles(payload, evidence=evidence)
    with pytest.raises(GameLifecycleError, match="spatial evidence"):
        GameLifecycle.from_payload(payload)


def test_forged_territory_unit_witness_fails_checkpoint_spatial_rebuild() -> None:
    setup = phase17n_event_setup(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=5,
    )
    state.turn_order = ("player-b", "player-a")
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.ATTACKER_HOME)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    checkpoint = bound_primary_scoring_commit_checkpoint(
        state=state,
        record=record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=None,
    )
    evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=True,
        scoring_commit_checkpoint=checkpoint,
    )
    payload = evidence.to_payload()
    spatial_row = next(
        row
        for row in payload["primary_scoring_spatial_evidence_by_player_id"]
        if PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION in row["requested_condition_ids"]
    )
    enemy = next(
        candidate
        for army in state.army_definitions
        if army.player_id == "player-b"
        for candidate in army.units
    )
    authentic = list(spatial_row["enemy_units_wholly_within_own_territory"])
    if authentic:
        spatial_row["enemy_units_wholly_within_own_territory"] = [
            {
                "rules_unit_instance_id": authentic[0]["rules_unit_instance_id"],
                "model_instance_ids": [enemy.own_models[0].model_instance_id],
            }
        ]
    else:
        spatial_row["enemy_units_wholly_within_own_territory"] = [
            PrimaryTerritoryUnitWitness(
                rules_unit_instance_id=enemy.unit_instance_id,
                model_instance_ids=(enemy.own_models[0].model_instance_id,),
            ).to_payload()
        ]
    content = {
        key: value for key, value in payload.items() if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    payload["evidence_id"] = f"primary-scoring-state-evidence:{digest}"
    payload["evidence_hash"] = digest
    forged_evidence = PrimaryScoringStateEvidence.from_payload(payload)
    placements = primary_mission_model_placements_from_checkpoint(
        state=state,
        checkpoint=checkpoint,
    )
    with pytest.raises(GameLifecycleError, match="spatial evidence drifted"):
        validate_primary_scoring_spatial_rows_from_checkpoint(
            state=state,
            evidence=forged_evidence,
            model_placements=placements,
        )


def test_forged_commit_checkpoint_pose_without_physical_event_fails_restore() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    state = lifecycle.state
    assert state is not None
    payload = deepcopy(lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    commit_event = next(
        event for event in events if event["event_type"] == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
    )
    raw_payload = commit_event["payload"]
    assert isinstance(raw_payload, dict)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(raw_payload["checkpoint"])
    rewritten_states = tuple(_offset_checkpoint_model_state(row) for row in checkpoint.model_states)
    rewritten = _checkpoint_with_model_states(checkpoint, rewritten_states)
    raw_payload["checkpoint"] = rewritten.to_payload()
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    forged_placements = primary_mission_model_placements_from_checkpoint(
        state=state,
        checkpoint=rewritten,
    )
    rebuilt_witnesses: list[PrimaryScoringRulesUnitPositionWitnessPayload] = []
    for witness in evidence["current_rules_unit_position_witnesses"]:
        membership_payload = witness["rules_unit_membership"]
        component_unit_instance_ids = tuple(
            component["unit_instance_id"]
            for component in membership_payload["component_memberships"]
        )
        membership = build_primary_rules_unit_membership_from_model_placements(
            state=state,
            rules_unit_instance_id=membership_payload["rules_unit_instance_id"],
            owner_player_id=witness["owner_player_id"],
            component_unit_instance_ids=component_unit_instance_ids,
            model_placements=forged_placements,
        )
        rebuilt_witnesses.append(
            {
                "owner_player_id": witness["owner_player_id"],
                "rules_unit_membership": membership.to_payload(),
            }
        )
    evidence["current_rules_unit_position_witnesses"] = rebuilt_witnesses
    record = state.objective_control_records[-1]
    evidence["primary_scoring_spatial_evidence_by_player_id"] = [
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id=row["player_id"],
            record=record,
            requested_condition_ids=tuple(row["requested_condition_ids"]),
            model_placements=forged_placements,
        ).to_payload()
        if row["requested_condition_ids"]
        else row
        for row in evidence["primary_scoring_spatial_evidence_by_player_id"]
    ]
    evidence["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
    evidence["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
    _rehash_evidence_transactions_and_lifecycles(
        payload,
        evidence=evidence,
        scoring_commit_checkpoint=rewritten,
    )
    with pytest.raises(GameLifecycleError, match="movement history"):
        GameLifecycle.from_payload(payload)


def test_forged_commit_checkpoint_modifier_source_fails_registry_restore() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    commit_event = next(
        event for event in events if event["event_type"] == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
    )
    raw_payload = commit_event["payload"]
    assert isinstance(raw_payload, dict)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(raw_payload["checkpoint"])
    first = checkpoint.model_states[0]
    resolved_payload = validate_json_value(json_loads(first.resolved_objective_control_json))
    assert isinstance(resolved_payload, dict)
    raw_applied = resolved_payload.get("applied_modifier_ids")
    applied: list[str] = []
    if isinstance(raw_applied, list):
        for modifier_id in raw_applied:
            assert isinstance(modifier_id, str)
            applied.append(modifier_id)
    applied.append("p2-forged-oc-modifier")
    resolved_payload["applied_modifier_ids"] = validate_json_value(applied)
    rewritten_states = (
        replace(first, resolved_objective_control_json=canonical_json(resolved_payload)),
        *checkpoint.model_states[1:],
    )
    rewritten = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=checkpoint.active_player_id,
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=rewritten_states,
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=checkpoint.battle_shocked_unit_instance_ids,
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=(
            *checkpoint.objective_control_modifier_sources,
            PrimaryMissionObjectiveControlModifierSource(
                modifier_id="p2-forged-oc-modifier",
                source_id="p2-forged-oc-source",
                source_effect_id=None,
                source_effect_json=None,
            ),
        ),
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )
    raw_payload["checkpoint"] = rewritten.to_payload()
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    evidence["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
    evidence["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
    _rehash_evidence_transactions_and_lifecycles(
        payload,
        evidence=evidence,
        scoring_commit_checkpoint=rewritten,
    )
    with pytest.raises(GameLifecycleError, match="unregistered"):
        GameLifecycle.from_payload(payload)


def test_sticky_control_satisfies_secondary_at_opponent_turn_end() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    home = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.ATTACKER_HOME
    )
    sticky = _sticky_state_for(
        state,
        player_id="player-a",
        objective_id=home.objective_marker_id,
        active_player_id="player-b",
    )
    state.record_sticky_objective_control_state(sticky)
    _place_player_away_from_objectives(state, player_id="player-a")
    scored = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert scored.status.value == "scored"
    record = state.objective_control_records[-1]
    home_result = record.result_by_objective_id(home.objective_marker_id)
    assert home_result.retained_control_source_id is not None


def test_sticky_control_expires_during_successful_atomic_secondary() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    central = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    sticky = _sticky_state_for(
        state,
        player_id="player-a",
        objective_id=central.objective_marker_id,
        active_player_id="player-b",
    )
    state.record_sticky_objective_control_state(sticky)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.CENTRAL)
    assert state.sticky_objective_control_states
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert state.sticky_objective_control_states == []


def test_runtime_oc_modifier_changes_secondary_scoring_result() -> None:
    def _zero_oc(context: ObjectiveControlModifierContext) -> int:
        assert context.current_objective_control >= 0
        return 0

    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id="p2-zero-oc",
                source_id="p2-zero-oc-source",
                handler=_zero_oc,
            ),
        )
    )
    modified_lifecycle, modified_state = _defend_stronghold_ready_lifecycle()
    modified_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=modified_lifecycle.decision_controller.event_log,
        runtime_modifier_registry=registry,
    )
    baseline_lifecycle, baseline_state = _defend_stronghold_ready_lifecycle()
    scored = baseline_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=baseline_lifecycle.decision_controller.event_log,
    )
    assert scored.status.value == "scored"
    assert _tactical_secondary_amount(
        modified_state,
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
    ) != _tactical_secondary_amount(
        baseline_state,
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
    )


def test_preexisting_canonical_sticky_record_is_reused_exactly() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    home = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.ATTACKER_HOME
    )
    sticky = _sticky_state_for(
        state,
        player_id="player-a",
        objective_id=home.objective_marker_id,
        active_player_id="player-b",
    )
    state.record_sticky_objective_control_state(sticky)
    stored = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    _place_player_away_from_objectives(state, player_id="player-a")
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert state.objective_control_records == [stored]


def test_failure_after_canonical_oc_projection_restores_sticky_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    home = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.ATTACKER_HOME
    )
    sticky = _sticky_state_for(
        state,
        player_id="player-a",
        objective_id=home.objective_marker_id,
        active_player_id="player-b",
    )
    state.record_sticky_objective_control_state(sticky)
    original = GameState.award_victory_points

    def _fail_secondary(self: GameState, award: VictoryPointAward) -> VictoryPointTransaction:
        if self is state and award.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
            raise GameLifecycleError("injected secondary ledger failure")
        return original(self, award)

    monkeypatch.setattr(GameState, "award_victory_points", _fail_secondary)
    before = tuple(state.sticky_objective_control_states)
    with pytest.raises(GameLifecycleError, match="injected secondary ledger failure"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert tuple(state.sticky_objective_control_states) == before


def test_secondary_retry_without_applicable_primary_evidence() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.ATTACKER_HOME)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.DEFENDER_HOME)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=3,
            source_result_id="p2-no-primary-retry",
        )
    )
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert state.primary_scoring_state_evidence_records == []
    second = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert second == first
    secondary_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
    )
    assert len(secondary_ids) == 1


def test_fixed_bring_it_down_scores_distinct_turn_end_records() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
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
    _set_unit_starting_wounds(state, player_a_unit.unit_instance_id, wounds=10)
    _set_unit_starting_wounds(state, player_b_unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-b",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    state.record_secondary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        destroyed_model_instance_ids=(player_b_unit.own_models[0].model_instance_id,),
        started_turn_objective_marker_ids=(),
        source_id="p2-bring-it-down-a",
    )
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    first_record_id = state.objective_control_records[-1].record_id
    state.active_player_id = "player-b"
    state.record_secondary_unit_destruction(
        destroying_player_id="player-b",
        destroyed_unit_instance_id=player_a_unit.unit_instance_id,
        destroyed_model_instance_ids=(player_a_unit.own_models[0].model_instance_id,),
        started_turn_objective_marker_ids=(),
        source_id="p2-bring-it-down-b",
    )
    second = state.score_secondary_mission_from_state(
        player_id="player-b",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    second_record_id = state.objective_control_records[-1].record_id
    assert first.status.value == "active"
    assert second.status.value == "active"
    assert first_record_id != second_record_id
    record_ids = _fixed_secondary_record_ids(state)
    assert record_ids == (first_record_id, second_record_id)
    state.active_player_id = "player-a"
    retry_a = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    state.active_player_id = "player-b"
    retry_b = state.score_secondary_mission_from_state(
        player_id="player-b",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert retry_a == first
    assert retry_b == second
    assert record_ids == _fixed_secondary_record_ids(state)
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_fixed_bring_it_down_same_card_scores_two_turn_end_records() -> None:
    lifecycle = _two_defender_battlefield_dominance_lifecycle(
        phase=BattlePhase.FIGHT,
        battle_round=3,
    )
    state = lifecycle.state
    assert state is not None
    defender_units = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    assert len(defender_units) == 2
    for unit in defender_units:
        _set_unit_starting_wounds(state, unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    state.record_secondary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id=defender_units[0].unit_instance_id,
        destroyed_model_instance_ids=(defender_units[0].own_models[0].model_instance_id,),
        started_turn_objective_marker_ids=(),
        source_id="p2-bring-it-down-same-card-a",
    )
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    first_record_id = state.objective_control_records[-1].record_id
    state.active_player_id = "player-b"
    state.record_secondary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id=defender_units[1].unit_instance_id,
        destroyed_model_instance_ids=(defender_units[1].own_models[0].model_instance_id,),
        started_turn_objective_marker_ids=(),
        source_id="p2-bring-it-down-same-card-b",
    )
    second = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    second_record_id = state.objective_control_records[-1].record_id
    assert first.status.value == "active"
    assert second.status.value == "active"
    assert first_record_id != second_record_id
    assert _fixed_secondary_record_ids(state) == (first_record_id, second_record_id)
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_restore_rejects_duplicate_fixed_secondary_at_same_record() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    duplicate = deepcopy(secondary[0])
    transactions = _json_list(ledger["transactions"], label="victory point transactions")
    battle_round = duplicate["battle_round"]
    assert isinstance(battle_round, int)
    duplicate["transaction_id"] = (
        f"victory-point:player-a:round-{battle_round:02d}:{len(transactions) + 1:06d}"
    )
    transactions.append(duplicate)
    amount = duplicate["amount"]
    assert isinstance(amount, int)
    victory_points = ledger["victory_points"]
    assert isinstance(victory_points, int)
    ledger["victory_points"] = victory_points + amount
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP ledger must not repeat a source at one boundary",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_secondary_transaction_with_unknown_source_id() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    secondary[0]["source_id"] = "unknown-secondary-mission"
    metadata = _json_object(secondary[0]["metadata"], label="secondary metadata")
    metadata["secondary_mission_id"] = "unknown-secondary-mission"
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP source is not source-backed",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_secondary_moved_to_different_oc_record() -> None:
    lifecycle = _two_player_bring_it_down_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    player_a_ledger = _ledger_payload(payload, player_id="player-a")
    player_b_ledger = _ledger_payload(payload, player_id="player-b")
    player_a_secondary = _secondary_transaction_payloads(
        player_a_ledger,
        source_kind="fixed_secondary",
    )
    player_b_secondary = _secondary_transaction_payloads(
        player_b_ledger,
        source_kind="fixed_secondary",
    )
    assert len(player_a_secondary) == 1
    assert len(player_b_secondary) == 1
    player_a_metadata = _json_object(
        player_a_secondary[0]["metadata"],
        label="player-a secondary metadata",
    )
    player_b_metadata = _json_object(
        player_b_secondary[0]["metadata"],
        label="player-b secondary metadata",
    )
    original_record_id = player_a_metadata["objective_control_record_id"]
    moved_record_id = player_b_metadata["objective_control_record_id"]
    assert original_record_id != moved_record_id
    player_a_metadata["objective_control_record_id"] = moved_record_id
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transactions drifted from authoritative scoring-state semantics",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_rewritten_secondary_amount_and_evidence_below_caps() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    transaction = secondary[0]
    original_amount = transaction["amount"]
    assert isinstance(original_amount, int)
    new_amount = original_amount + 4
    transaction["amount"] = new_amount
    victory_points = ledger["victory_points"]
    assert isinstance(victory_points, int)
    ledger["victory_points"] = victory_points + 4
    metadata = _json_object(transaction["metadata"], label="secondary metadata")
    score_count_by_rule = _json_object(
        metadata["score_count_by_rule"],
        label="score_count_by_rule",
    )
    victory_points_by_rule = _json_object(
        metadata["victory_points_by_rule"],
        label="victory_points_by_rule",
    )
    evidence_by_rule = _json_object(metadata["evidence_by_rule"], label="evidence_by_rule")
    for rule_id in tuple(score_count_by_rule):
        score_count_by_rule[rule_id] = 2
        victory_points_by_rule[rule_id] = new_amount
        evidence = _json_object(evidence_by_rule[rule_id], label="rule evidence")
        evidence["score_count"] = 2
        destroyed_models = evidence.get("destroyed_model_instance_ids")
        if type(destroyed_models) is list and destroyed_models:
            typed_models = cast(list[object], destroyed_models)
            first_model = typed_models[0]
            assert isinstance(first_model, str)
            evidence["destroyed_model_instance_ids"] = [first_model, f"{first_model}-forged"]
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transactions drifted from authoritative scoring-state semantics",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_scored_tactical_card_without_identified_transaction() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    payload = deepcopy(lifecycle.to_payload())
    state_payload = _json_object(payload["state"], label="lifecycle state")
    cards = _json_list(
        state_payload["secondary_mission_card_states"],
        label="secondary mission card states",
    )
    scored_cards = [
        card
        for card in (_json_object(raw_card, label="secondary card") for raw_card in cards)
        if card.get("status") == "scored"
    ]
    assert len(scored_cards) == 1
    scored_cards[0]["scored_transaction_id"] = "victory-point:player-a:round-02:999999"
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card does not identify its ledger transaction",
    ):
        GameLifecycle.from_payload(payload)


def test_deleted_resolved_lifecycle_row_fails_restore() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    rows = payload["state"]["primary_scoring_boundary_lifecycles"]
    assert rows
    payload["state"]["primary_scoring_boundary_lifecycles"] = rows[1:]
    with pytest.raises(
        GameLifecycleError,
        match="lifecycle registry is incomplete or unexpected",
    ):
        GameLifecycle.from_payload(payload)


def test_deleted_all_resolved_lifecycle_rows_fails_restore() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    payload["state"]["primary_scoring_boundary_lifecycles"] = []
    with pytest.raises(
        GameLifecycleError,
        match="lifecycle registry is incomplete or unexpected",
    ):
        GameLifecycle.from_payload(payload)


def test_incorrect_legal_pending_window_fails_restore() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    for row in payload["state"]["primary_scoring_boundary_lifecycles"]:
        row["pending_window"] = PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH
        _rehash_lifecycle_row(row)
    with pytest.raises(
        GameLifecycleError,
        match="window does not match the queue-head decision family",
    ):
        GameLifecycle.from_payload(payload)


def test_pending_row_bound_to_unrelated_queue_head_fails_restore() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    queue = payload["decisions"]["queue"]["pending_requests"]
    queue[0]["decision_type"] = SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] != "decision_requested":
            continue
        request_payload = event["payload"]
        if (
            isinstance(request_payload, dict)
            and request_payload.get("request_id") == queue[0]["request_id"]
        ):
            request_payload["decision_type"] = SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    with pytest.raises(
        GameLifecycleError,
        match="window does not match the queue-head decision family",
    ):
        GameLifecycle.from_payload(payload)


def test_coordinated_lifecycle_deletion_with_evidence_and_ledger_rewrite_fails() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    payload["state"]["primary_scoring_boundary_lifecycles"] = []
    payload["state"]["primary_scoring_state_evidence_records"] = []
    for ledger in payload["state"]["victory_point_ledgers"]:
        ledger["transactions"] = [
            transaction
            for transaction in ledger["transactions"]
            if transaction["source_kind"] != "primary"
        ]
        ledger["victory_points"] = sum(
            transaction["amount"] for transaction in ledger["transactions"]
        )
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def _pending_command_boundary_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.COMMAND, battle_round=2)
    state = lifecycle.state
    assert state is not None
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=lifecycle.decision_controller, record=record)
    _queue_pending_window(
        lifecycle=lifecycle,
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    )
    return lifecycle


def _pending_final_turn_end_boundary_lifecycle() -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-priority-assets-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="priority-assets",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-b",
        phase=BattlePhase.FIGHT,
        battle_round=5,
    )
    decisions = DecisionController()
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    _emit_oc_event(decisions=decisions, record=record)
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    _queue_pending_window(
        lifecycle=lifecycle,
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    )
    return lifecycle


def _scored_command_boundary_after_mutation(*, kind: str) -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.COMMAND, battle_round=2)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    enemy = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    original_placement: UnitPlacement | None = None
    if kind == "return_on_death":
        _place_unit_interior_non_overlapping(state, unit_instance_id=enemy.unit_instance_id)
        original_placement = _destroy_unit_with_events(
            state=state,
            decisions=decisions,
            unit_instance_id=enemy.unit_instance_id,
        )
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=decisions, record=record)
    if kind == "move":
        append_authenticated_normal_move(
            state=state,
            decisions=decisions,
            unit_instance_id=enemy.unit_instance_id,
            suffix="post-oc",
            pose_transform=lambda pose: Pose.at(
                pose.position.x,
                pose.position.y + 6.0,
                pose.position.z,
                facing_degrees=pose.facing.degrees,
            ),
        )
    elif kind == "destroy":
        _destroy_first_model(
            state=state, decisions=decisions, unit_instance_id=enemy.unit_instance_id
        )
    elif kind == "return_on_death":
        assert original_placement is not None
        _return_destroyed_unit(
            state=state,
            decisions=decisions,
            original_placement=original_placement,
        )
    else:
        raise AssertionError(f"unsupported mutation kind: {kind}")
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    return lifecycle


def _battlefield_dominance_lifecycle(
    *,
    phase: BattlePhase,
    battle_round: int,
) -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=phase,
        battle_round=battle_round,
    )
    return GameLifecycle(state=state, decision_controller=DecisionController())


def _two_defender_battlefield_dominance_lifecycle(
    *,
    phase: BattlePhase,
    battle_round: int,
) -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    config = GameConfig(
        game_id="phase11c-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(default_unit_selection("intercessor-unit-1"),),
            ),
            army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(
                    default_unit_selection("intercessor-unit-3"),
                    default_unit_selection("intercessor-unit-4"),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=phase11c_mission_setup(),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11c-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )
    complete_setup_through_gate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )
    state.mission_setup = setup
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                setup.primary_mission_assignment_for_player(army.player_id).force_disposition_id
            ),
        )
        for army in state.army_definitions
    ]
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = battle_round
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    return GameLifecycle(state=state, decision_controller=DecisionController())


def _bring_it_down_player_a_scored_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    player_b_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    _set_unit_starting_wounds(state, player_b_unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    state.record_secondary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        destroyed_model_instance_ids=(player_b_unit.own_models[0].model_instance_id,),
        started_turn_objective_marker_ids=(),
        source_id="p2-bring-it-down-restore",
    )
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    return lifecycle


def _two_player_bring_it_down_scored_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
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
    _set_unit_starting_wounds(state, player_a_unit.unit_instance_id, wounds=10)
    _set_unit_starting_wounds(state, player_b_unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-b",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    state.record_secondary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        destroyed_model_instance_ids=(player_b_unit.own_models[0].model_instance_id,),
        started_turn_objective_marker_ids=(),
        source_id="p2-bring-it-down-a",
    )
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    state.active_player_id = "player-b"
    state.record_secondary_unit_destruction(
        destroying_player_id="player-b",
        destroyed_unit_instance_id=player_a_unit.unit_instance_id,
        destroyed_model_instance_ids=(player_a_unit.own_models[0].model_instance_id,),
        started_turn_objective_marker_ids=(),
        source_id="p2-bring-it-down-b",
    )
    state.score_secondary_mission_from_state(
        player_id="player-b",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    return lifecycle


def _ledger_payload(payload: GameLifecyclePayload, *, player_id: str) -> dict[str, object]:
    state = _json_object(payload["state"], label="lifecycle state")
    ledgers = _json_list(state["victory_point_ledgers"], label="victory point ledgers")
    for ledger in ledgers:
        ledger_map = _json_object(ledger, label="victory point ledger")
        if ledger_map["player_id"] == player_id:
            return ledger_map
    raise AssertionError(f"ledger for {player_id} was not found")


def _secondary_transaction_payloads(
    ledger: dict[str, object],
    *,
    source_kind: str,
) -> list[dict[str, object]]:
    transactions = _json_list(ledger["transactions"], label="victory point transactions")
    matches: list[dict[str, object]] = []
    for transaction in transactions:
        transaction_map = _json_object(transaction, label="victory point transaction")
        if transaction_map["source_kind"] == source_kind:
            matches.append(transaction_map)
    return matches


def _defend_stronghold_ready_lifecycle() -> tuple[GameLifecycle, GameState]:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=2)
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.ATTACKER_HOME)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.DEFENDER_HOME)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=2,
            source_result_id="p2-defend-stronghold-ready",
        )
    )
    return lifecycle, state


def _queue_pending_window(*, lifecycle: GameLifecycle, pending_window: str) -> None:
    state = lifecycle.state
    assert state is not None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
        actor_id=state.active_player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "pending_window": pending_window,
            }
        ),
        options=(DecisionOption(option_id="continue", label="continue"),),
    )
    lifecycle.decision_controller.request_decision(request)
    mark_pending_primary_scoring_boundaries(
        state=state,
        pending_window=pending_window,
        pending_decision_request_id=request.request_id,
    )


def _emit_oc_event(*, decisions: DecisionController, record: ObjectiveControlRecord) -> None:
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": record.game_id,
            "battle_round": record.battle_round,
            "phase": record.phase,
            "record_ids": [record.record_id],
            "source_rule_id": _OC_SOURCE_RULE_ID,
        },
    )


def _place_player_on_role(
    state: GameState,
    *,
    player_id: str,
    role: ObjectiveMarkerRole,
) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == player_id
        for candidate in army.units
    )
    marker = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is role
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            marker,
            offsets=((0.0, 0.0), (0.8, 0.0), (1.6, 0.0), (0.0, 0.8), (0.8, 0.8)),
        )
    )


def _place_unit_interior_non_overlapping(state: GameState, *, unit_instance_id: str) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    marker = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            marker,
            offsets=((0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (0.0, 2.0), (2.0, 2.0)),
        )
    )


def _place_player_away_from_objectives(state: GameState, *, player_id: str) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == player_id
        for candidate in army.units
    )
    marker = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            marker,
            offsets=((18.0, 18.0), (18.8, 18.0), (19.6, 18.0), (18.0, 18.8), (18.8, 18.8)),
        )
    )


def _destroy_first_model(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
) -> None:
    unit = next(
        candidate
        for army in state.army_definitions
        for candidate in army.units
        if candidate.unit_instance_id == unit_instance_id
    )
    model = unit.own_models[0]
    destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "model_instance_id": model.model_instance_id,
        },
    )


def _destroy_unit_with_events(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
) -> UnitPlacement:
    assert state.battlefield_state is not None
    assert state.active_player_id is not None
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    original_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    unit = next(
        candidate
        for army in state.army_definitions
        for candidate in army.units
        if candidate.unit_instance_id == unit_instance_id
    )
    source_unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == "player-a"
        for candidate in army.units
    )
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=source_unit.unit_instance_id,
    )
    destroyed_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=unit.unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_unit.own_models[0].model_instance_id,
    )
    destroyed_events: list[str] = []
    departures: list[PrimaryBattlefieldDepartureState] = []
    for model in unit.own_models:
        model_placement = next(
            row
            for row in original_placement.model_placements
            if row.model_instance_id == model.model_instance_id
        )
        event = decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "model_instance_id": model.model_instance_id,
                "target_unit_instance_id": unit.unit_instance_id,
                "destroyed_model_placement": model_placement.to_payload(),
                "source_rules_unit_objective_proximity_witness": source_witness.to_payload(),
                "destroyed_rules_unit_objective_proximity_witness": (
                    destroyed_witness.to_payload()
                ),
                **attribution.to_payload(),
            },
        )
        destroyed_events.append(event.event_id)
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
        model_departures = record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model.model_instance_id,),
            source_id=f"core-rules:primary-unit-destruction-tracking:{event.event_id}",
            occurrence_id=event.event_id,
        )
        departures.extend(model_departures)
        for departure in model_departures:
            record_primary_battlefield_departure_event(
                event_log=decisions.event_log,
                departure=departure,
            )
    last_event_id = destroyed_events[-1]
    source_id = f"core-rules:primary-unit-destruction-tracking:{last_event_id}"
    destruction_ids_before = tuple(
        destruction.destruction_id for destruction in state.primary_unit_destruction_states
    )
    state.record_primary_unit_destruction(
        destruction_attribution=attribution,
        source_model_destroyed_event_id=last_event_id,
        source_rules_unit_objective_proximity_witness=source_witness,
        source_battlefield_departure_ids=tuple(departure.departure_id for departure in departures),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_unit_instance_id=unit.unit_instance_id,
        source_id=f"{source_id}:{unit.unit_instance_id}",
    )
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=decisions.event_log,
        destruction_ids_before=destruction_ids_before,
    )
    first_model = original_placement.model_placements[0]
    pending = PendingReturnOnDeath(
        pending_id="p2-return-on-death-pending",
        source_rule_id="p2-return-on-death-rule",
        source_ability_id="p2-return-on-death-ability",
        source_clause_id="p2-return-on-death-clause",
        source_effect_index=0,
        owner_player_id="player-b",
        target_scope=ReturnDestroyedTargetScope.DESTROYED_UNIT,
        destroyed_unit_instance_id=unit_instance_id,
        destroyed_model_instance_id=None,
        destroyed_position_payload=validate_json_value(
            {
                "source": "model_destroyed_event",
                "model_destroyed_event_id": destroyed_events[0],
                "model_destroyed_payload": {
                    "model_instance_id": first_model.model_instance_id,
                    "destroyed_model_placement": first_model.to_payload(),
                },
            }
        ),
        trigger_battle_round=state.battle_round,
        trigger_phase=BattlePhase.COMMAND.value,
        resolution_timing="phase_end",
        roll_expression="D6",
        roll_count=1,
        success_threshold=2,
        placement_anchor="destroyed_position",
        placement_preference="as_close_as_possible",
        engagement_range_restriction=True,
        restore_wounds_mode=ReturnRestoreWoundsMode.FULL_HEALTH,
        wounds_remaining=None,
        resolved=False,
    )
    state.record_pending_return_on_death(pending)
    stored = state.pending_return_on_death_by_id(pending.pending_id)
    decisions.event_log.append(
        RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "model_destroyed_event_id": destroyed_events[0],
            "pending": stored.to_payload(),
        },
    )
    return original_placement


def _return_destroyed_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    original_placement: UnitPlacement,
) -> None:
    pending = state.pending_return_on_death_by_id("p2-return-on-death-pending")
    dice_manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="p2-return-on-death-roll",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="return_on_death_phase_end_gate",
                    roll_type="return_on_death",
                    actor_id=pending.owner_player_id,
                    reroll_forbidden_rule_ids=(pending.source_rule_id,),
                ),
                values=(6,),
                source="injected",
            ),
        ),
    )
    request = resolve_pending_return_on_death_phase_end(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
    )
    assert request is not None
    result = DecisionResult(
        result_id=f"{request.request_id}-placement-result",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            {
                "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                "attempted_placement": original_placement.to_payload(),
            }
        ),
    )
    decisions.submit_result(result)
    apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )


def _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle: GameLifecycle) -> None:
    state = lifecycle.state
    assert state is not None
    record = state.objective_control_records[-1]
    authority = next(
        candidate
        for candidate in state.objective_control_record_authorities
        if candidate.objective_control_record_id == record.record_id
    )
    commit = bound_primary_scoring_commit_checkpoint(
        state=state,
        record=record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=None,
    )
    evidence = state.primary_scoring_state_evidence_records[-1]
    assert evidence.scoring_commit_checkpoint_id == commit.checkpoint_id
    assert authority.boundary_checkpoint.model_states != commit.model_states


def _offset_checkpoint_model_state(
    row: PrimaryMissionBoundaryModelState,
) -> PrimaryMissionBoundaryModelState:
    placement_json = row.model_placement_json
    if placement_json is None:
        return row
    placement = ModelPlacement.from_payload(json_loads(placement_json))
    moved = placement.with_pose(
        Pose.at(
            placement.pose.position.x,
            placement.pose.position.y + 12.0,
            placement.pose.position.z,
            facing_degrees=placement.pose.facing.degrees,
        )
    )
    return replace(row, model_placement_json=canonical_json(moved.to_payload()))


def _checkpoint_with_model_states(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    model_states: tuple[PrimaryMissionBoundaryModelState, ...],
) -> PrimaryMissionBoundaryCheckpoint:
    return PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=checkpoint.active_player_id,
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=model_states,
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=checkpoint.battle_shocked_unit_instance_ids,
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=checkpoint.objective_control_modifier_sources,
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )


def _json_object(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise AssertionError(f"{label} must be a JSON object.")
    return cast(dict[str, object], value)


def _json_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise AssertionError(f"{label} must be a JSON list.")
    return cast(list[object], value)


def _fixed_secondary_record_ids(state: GameState) -> tuple[str, ...]:
    record_ids: list[str] = []
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if transaction.source_kind is not VictoryPointSourceKind.FIXED_SECONDARY:
                continue
            metadata = transaction.metadata
            assert isinstance(metadata, dict)
            record_id = metadata.get("objective_control_record_id")
            assert isinstance(record_id, str)
            record_ids.append(record_id)
    return tuple(record_ids)


def _rehash_evidence_transactions_and_lifecycles(
    payload: GameLifecyclePayload,
    *,
    evidence: PrimaryScoringStateEvidencePayload,
    scoring_commit_checkpoint: PrimaryMissionBoundaryCheckpoint | None = None,
) -> None:
    evidence_map = _json_object(evidence, label="primary scoring evidence")
    old_evidence_id = evidence_map["evidence_id"]
    assert isinstance(old_evidence_id, str)
    content = {
        key: value
        for key, value in evidence_map.items()
        if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    new_evidence_id = f"primary-scoring-state-evidence:{digest}"
    evidence_map["evidence_id"] = new_evidence_id
    evidence_map["evidence_hash"] = digest
    state = payload["state"]
    for ledger in state["victory_point_ledgers"]:
        for transaction in ledger["transactions"]:
            metadata = transaction["metadata"]
            if type(metadata) is not dict:
                continue
            metadata_map = cast(dict[str, object], metadata)
            if metadata_map.get("primary_scoring_state_evidence_id") != old_evidence_id:
                continue
            metadata_map["primary_scoring_state_evidence_id"] = new_evidence_id
            metadata_map["primary_scoring_state_evidence_hash"] = digest
    for row in state["primary_scoring_boundary_lifecycles"]:
        if row["evidence_id"] != old_evidence_id:
            continue
        row["evidence_id"] = new_evidence_id
        if scoring_commit_checkpoint is not None:
            row["scoring_commit_checkpoint_id"] = scoring_commit_checkpoint.checkpoint_id
            row["scoring_commit_checkpoint_hash"] = scoring_commit_checkpoint.checkpoint_hash
        _rehash_lifecycle_row(row)


def _rehash_lifecycle_row(row: PrimaryScoringBoundaryLifecyclePayload) -> None:
    row_map = _json_object(row, label="primary scoring boundary lifecycle")
    content = {
        key: value
        for key, value in row_map.items()
        if key not in {"lifecycle_id", "lifecycle_hash"}
    }
    digest = canonical_payload_sha256(content)
    row_map["lifecycle_id"] = f"primary-scoring-boundary-lifecycle:{digest}"
    row_map["lifecycle_hash"] = digest


def _scored_reconnaissance_turn_end_lifecycle() -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="take-and-hold",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=1,
    )
    decisions = DecisionController()
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    _emit_oc_event(decisions=decisions, record=record)
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    return GameLifecycle(state=state, decision_controller=decisions)


def _scored_determined_acquisition_command_lifecycle() -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="disruption",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=2,
    )
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.DEFENDER_HOME)
    decisions = DecisionController()
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=decisions, record=record)
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    return GameLifecycle(state=state, decision_controller=decisions)


def _tactical_secondary_amount(
    state: GameState,
    *,
    player_id: str,
    secondary_mission_id: str,
) -> int:
    ledger = state.victory_point_ledger_for_player(player_id)
    amounts = tuple(
        transaction.amount
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
        and transaction.source_id == secondary_mission_id
    )
    assert len(amounts) == 1
    return amounts[0]


def _sticky_state_for(
    state: GameState,
    *,
    player_id: str,
    objective_id: str,
    active_player_id: str,
) -> StickyObjectiveControlState:
    originating = next(
        unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
    )
    destroyed = next(
        unit
        for army in state.army_definitions
        if army.player_id != player_id
        for unit in army.units
    )
    return StickyObjectiveControlState(
        state_id=f"p2-sticky-{player_id}-{objective_id}",
        game_id=state.game_id,
        player_id=player_id,
        objective_id=objective_id,
        source_rule_id="p2-sticky-source",
        source_event_id="p2-sticky-event",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        active_player_id=active_player_id,
        originating_unit_instance_id=originating.unit_instance_id,
        destroyed_unit_instance_id=destroyed.unit_instance_id,
        replay_payload={"source": "p2-sticky"},
    )


def _set_unit_starting_wounds(state: GameState, unit_instance_id: str, *, wounds: int) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = list(army.units)
        for unit_index, unit in enumerate(units):
            if unit.unit_instance_id != unit_instance_id:
                continue
            units[unit_index] = replace(
                unit,
                own_models=tuple(
                    replace(model, starting_wounds=wounds, wounds_remaining=wounds)
                    for model in unit.own_models
                ),
            )
            state.army_definitions[army_index] = replace(army, units=tuple(units))
            return
    raise AssertionError(f"unit {unit_instance_id} was not found")
