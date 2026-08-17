from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from json import loads as json_loads
from re import escape

import pytest
from tests.phase11c_command_phase_helpers import with_model_offsets
from tests.phase17n_primary_mission_helpers import (
    append_authenticated_normal_move,
    phase17n_event_setup,
    phase17n_state_with_setup,
)
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

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
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
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
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PRIMARY_SCORING_PENDING_WINDOW_PRIMARY_MISSION_CHOICE,
    PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH,
    PrimaryScoringBoundaryStatus,
    mark_pending_primary_scoring_boundaries,
    pending_primary_scoring_boundary_keys,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    bound_primary_scoring_commit_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
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
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
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
    with pytest.raises(GameLifecycleError, match="drifted"):
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
    with pytest.raises(
        GameLifecycleError,
        match=escape(
            "Primary scoring position evidence requires exactly one scoring-commit checkpoint."
        ),
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())


def _pending_command_boundary_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.COMMAND, battle_round=2)
    state = lifecycle.state
    assert state is not None
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=lifecycle.decision_controller, record=record)
    _queue_pending_window(
        lifecycle=lifecycle,
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH,
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
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_PRIMARY_MISSION_CHOICE,
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
