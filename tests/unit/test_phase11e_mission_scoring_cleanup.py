from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.actions import (
    MissionActionState,
    MissionActionStatus,
    mission_action_status_from_token,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    UnitPlacement,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_scoring_policy_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    objective_control_timing_from_token,
    secondary_mission_card_mode_from_token,
    secondary_mission_card_status_from_token,
    victory_point_source_kind_from_token,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.turn_cleanup import (
    CoherencyCleanupRemoval,
    EndTurnCleanupState,
    battlefield_removal_kind_from_token,
    resolve_end_turn_cleanup,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_primary_scoring_uses_objective_control_at_configured_command_timing() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),),
        player_b_offsets=((20.0, 20.0),),
    )

    completed_phase = state.advance_to_next_battle_phase()
    ledger = state.victory_point_ledger_for_player("player-a")

    assert completed_phase is BattlePhase.COMMAND
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.victory_point_total("player-a") == 5
    assert ledger.transactions[0].source_kind is VictoryPointSourceKind.PRIMARY
    assert ledger.transactions[0].source_id == "take-and-hold"
    assert ledger.transactions[0].metadata == {
        "objective_control_record_id": ("objective-control:round-01:player-a:command:phase_end"),
        "controlled_objective_ids": ["tipping-point-center"],
    }


def test_fixed_secondary_scoring_is_public_after_secondary_reveal() -> None:
    state = _battle_state()

    scored = state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="assassination",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.COMMAND,
    )
    own_payload = state.to_public_payload(viewer_player_id="player-a")
    opponent_payload = state.to_public_payload(viewer_player_id="player-b")

    assert scored.status is SecondaryMissionCardStatus.SCORED
    assert state.victory_point_total("player-a") == 5
    own_ledger = _public_ledger(own_payload, player_id="player-a")
    opponent_ledger = _public_ledger(opponent_payload, player_id="player-a")
    own_transactions = cast(list[JsonValue], own_ledger["transactions"])
    own_transaction = cast(dict[str, JsonValue], own_transactions[0])
    opponent_transactions = cast(list[JsonValue], opponent_ledger["transactions"])
    assert own_transaction["source_id"] == "assassination"
    assert opponent_transactions[0] == {
        "transaction_id": "victory-point:player-a:round-01:000001",
        "player_id": "player-a",
        "battle_round": 1,
        "phase": "command",
        "amount": 5,
        "source_kind": "fixed_secondary",
        "source_id": "assassination",
        "scoring_timing": "secondary_mission_score",
        "hidden": False,
        "metadata": {"secondary_mission_id": "assassination"},
    }
    assert any(
        card_payload["player_id"] == "player-a"
        and card_payload["secondary_mission_id"] == "assassination"
        and card_payload["mode"] == "fixed"
        and card_payload["hidden"] is False
        for card_payload in _public_card_states(opponent_payload)
    )


def test_secondary_choices_remain_secret_until_all_players_select() -> None:
    state = GameState.from_config(_config())
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )

    player_b_payload = state.to_public_payload(viewer_player_id="player-b")
    player_a_choice = _public_secondary_choice(player_b_payload, player_id="player-a")

    assert state.secondary_mission_choices_are_revealed() is False
    assert player_a_choice == {
        "player_id": "player-a",
        "selected": True,
        "hidden": True,
    }
    assert "assassination" not in json.dumps(player_b_payload, sort_keys=True)
    assert "bring-it-down" not in json.dumps(player_b_payload, sort_keys=True)
    assert player_b_payload["secondary_mission_card_states"] == []


def test_secondary_choices_are_public_after_all_players_select() -> None:
    state = _battle_state(
        player_a_secondary=SecondaryMissionMode.FIXED,
        player_b_secondary=SecondaryMissionMode.TACTICAL,
    )

    player_a_payload = state.to_public_payload(viewer_player_id="player-a")
    player_b_payload = state.to_public_payload(viewer_player_id="player-b")

    assert state.secondary_mission_choices_are_revealed() is True
    assert _public_secondary_choice(player_a_payload, player_id="player-b") == {
        "player_id": "player-b",
        "selected": True,
        "hidden": False,
        "mode": "tactical",
        "fixed_mission_ids": [],
    }
    assert _public_secondary_choice(player_b_payload, player_id="player-a") == {
        "player_id": "player-a",
        "selected": True,
        "hidden": False,
        "mode": "fixed",
        "fixed_mission_ids": ["assassination", "bring-it-down"],
    }


def test_secondary_reveal_event_emits_after_both_choices_without_pre_reveal_leak() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_config())
    first_status = _advance_to_secondary_request(lifecycle)
    first_request = first_status.decision_request
    assert first_request is not None
    assert first_request.actor_id == "player-a"

    lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=first_request.request_id,
            selected_option_id="fixed:assassination:bring-it-down",
            result_id="phase11e-first-secondary",
        ).to_result(first_request)
    )
    player_b_before_reveal = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    assert not any(
        event["event_type"] == "secondary_missions_revealed"
        for event in player_b_before_reveal["events"]
    )
    first_choice_event = next(
        event
        for event in player_b_before_reveal["events"]
        if event["event_type"] == "secondary_mission_choice_recorded"
    )
    assert cast(dict[str, JsonValue], first_choice_event["payload"]) == {
        "game_id": "phase11e-game",
        "player_id": "player-a",
        "setup_step": "select_secondary_missions",
        "selected": True,
        "hidden": True,
    }
    player_a_before_second_submit = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    second_request_event = next(
        event
        for event in player_a_before_second_submit["events"]
        if event["event_type"] == "decision_requested"
        and cast(dict[str, JsonValue], event["payload"])["actor_id"] == "player-b"
    )
    assert cast(dict[str, JsonValue], second_request_event["payload"]) == {
        "request_id": "decision-request-000002",
        "decision_type": "select_secondary_missions",
        "actor_id": "player-b",
        "secret": True,
        "hidden": True,
    }

    second_status = lifecycle.advance_until_decision_or_terminal()
    second_request = second_status.decision_request
    assert second_request is not None
    assert second_request.actor_id == "player-b"
    lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=second_request.request_id,
            selected_option_id="tactical",
            result_id="phase11e-second-secondary",
        ).to_result(second_request)
    )

    player_a_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    reveal_event = next(
        event
        for event in player_a_events["events"]
        if event["event_type"] == "secondary_missions_revealed"
    )
    reveal_payload = cast(dict[str, JsonValue], reveal_event["payload"])
    assert reveal_payload["choices"] == [
        {
            "player_id": "player-a",
            "mode": "fixed",
            "fixed_mission_ids": ["assassination", "bring-it-down"],
        },
        {
            "player_id": "player-b",
            "mode": "tactical",
            "fixed_mission_ids": [],
        },
    ]


def test_secondary_reveal_event_does_not_perturb_later_dice_history() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Post secondary reveal roll",
        roll_type="phase11e_regression_roll",
        actor_id="player-a",
    )
    baseline_history = EventLog()
    baseline_history.append(
        "phase11e_post_reveal_marker",
        {
            "game_id": "phase11e-game",
            "marker": "after-secondary-selection",
        },
    )
    reveal_history = EventLog()
    reveal_history.append(
        "secondary_missions_revealed",
        {
            "game_id": "phase11e-game",
            "setup_step": "select_secondary_missions",
            "choices": [
                {
                    "player_id": "player-a",
                    "mode": "fixed",
                    "fixed_mission_ids": ["assassination", "bring-it-down"],
                },
                {
                    "player_id": "player-b",
                    "mode": "tactical",
                    "fixed_mission_ids": list[str](),
                },
            ],
        },
    )
    reveal_history.append(
        "phase11e_post_reveal_marker",
        {
            "game_id": "phase11e-game",
            "marker": "after-secondary-selection",
        },
    )

    baseline_roll = DiceRollManager(
        "phase11e-reveal-neutral",
        event_log=baseline_history,
    ).roll(spec)
    reveal_roll = DiceRollManager(
        "phase11e-reveal-neutral",
        event_log=reveal_history,
    ).roll(spec)

    assert reveal_roll.to_payload() == baseline_roll.to_payload()


def test_tactical_secondary_draw_score_discard_flow_is_public_after_reveal() -> None:
    state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    decisions = DecisionController()
    handler = CommandPhaseHandler()
    waiting = handler.begin_phase(state=state, decisions=decisions)
    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE

    result = DecisionResult.for_request(
        result_id="phase11e-tactical-draw",
        request=request,
        selected_option_id="draw",
    )
    decisions.submit_result(result)
    handler.apply_decision(state=state, result=result, decisions=decisions)

    active_cards = [
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a" and card.mode is SecondaryMissionCardMode.TACTICAL
    ]
    assert len(active_cards) == state.tactical_secondary_draw_count
    scored = state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id=active_cards[0].secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )
    discarded = state.discard_tactical_secondary(
        player_id="player-a",
        secondary_mission_id=active_cards[1].secondary_mission_id,
        result_id="phase11e-discard-tactical",
    )
    decisions.event_log.append(
        "tactical_secondary_mission_discarded",
        {
            "game_id": state.game_id,
            "player_id": "player-a",
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "secondary_mission_card_state": discarded.to_payload(),
        },
    )
    opponent_events = EventStreamCursor().events_since(
        decisions.event_log,
        viewer_player_id="player-b",
    )
    opponent_payload = state.to_public_payload(viewer_player_id="player-b")

    assert scored.status is SecondaryMissionCardStatus.SCORED
    assert discarded.status is SecondaryMissionCardStatus.DISCARDED
    assert state.victory_point_total("player-a") == 5
    draw_event = next(
        event
        for event in opponent_events["events"]
        if event["event_type"] == "tactical_secondary_missions_drawn"
    )
    draw_payload = cast(dict[str, JsonValue], draw_event["payload"])
    drawn_cards = cast(list[JsonValue], draw_payload["secondary_mission_card_states"])
    assert draw_payload["player_id"] == "player-a"
    assert draw_payload["draw_count"] == 2
    assert {
        str(cast(dict[str, JsonValue], card)["secondary_mission_id"]) for card in drawn_cards
    } == {card.secondary_mission_id for card in active_cards}
    discard_event = next(
        event
        for event in opponent_events["events"]
        if event["event_type"] == "tactical_secondary_mission_discarded"
    )
    assert cast(dict[str, JsonValue], discard_event["payload"])["player_id"] == "player-a"
    assert opponent_payload["tactical_secondary_draws"] == [
        {
            "player_id": "player-a",
            "battle_round": 1,
            "request_id": request.request_id,
            "result_id": "phase11e-tactical-draw",
            "draw_count": 2,
        }
    ]
    assert any(
        card_payload["player_id"] == "player-a"
        and card_payload["secondary_mission_id"] == active_cards[0].secondary_mission_id
        and card_payload["mode"] == "tactical"
        and card_payload["status"] == "scored"
        for card_payload in _public_card_states(opponent_payload)
    )
    player_a_ledger = _public_ledger(opponent_payload, player_id="player-a")
    transactions = cast(list[JsonValue], player_a_ledger["transactions"])
    transaction = cast(dict[str, JsonValue], transactions[0])
    assert transaction["source_kind"] == "tactical_secondary"
    assert transaction["source_id"] == active_cards[0].secondary_mission_id
    assert transaction["metadata"] == {"secondary_mission_id": active_cards[0].secondary_mission_id}


def test_mission_action_can_complete_interrupt_and_score() -> None:
    state = _battle_state()
    completed_action = MissionActionState.start(
        action_id="cleanse:center:player-a",
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        mission_id="cleanse",
        battle_round=1,
        phase=BattlePhase.MOVEMENT.value,
        start_timing="movement_phase_unit_selected",
        completion_timing="turn_end",
        eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        interruption_conditions=("unit_moved", "unit_destroyed"),
        scoring_source_id="cleanse",
        victory_points=5,
    )
    interrupted_action = MissionActionState.start(
        action_id="cleanse:west:player-a",
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        mission_id="cleanse",
        battle_round=1,
        phase=BattlePhase.MOVEMENT.value,
        start_timing="movement_phase_unit_selected",
        completion_timing="turn_end",
        eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        interruption_conditions=("unit_moved", "unit_destroyed"),
        scoring_source_id="cleanse",
        victory_points=5,
    )
    state.record_mission_action_state(completed_action)
    state.record_mission_action_state(interrupted_action)

    completed = state.complete_mission_action(
        action_id=completed_action.action_id,
        completion_phase=BattlePhase.FIGHT,
    )
    interrupted = state.interrupt_mission_action(
        action_id=interrupted_action.action_id,
        reason="unit_moved",
    )

    assert completed.status is MissionActionStatus.COMPLETED
    assert completed.score_transaction_id == "victory-point:player-a:round-01:000001"
    assert interrupted.status is MissionActionStatus.INTERRUPTED
    assert interrupted.interrupted_reason == "unit_moved"
    assert state.victory_point_total("player-a") == 5


def test_end_turn_coherency_cleanup_removes_models_without_destroyed_triggers() -> None:
    state = _battle_state()
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    broken = _with_model_offsets(
        unit_placement,
        _center_marker_definition(state),
        offsets=((2.0, 0.0), (4.0, 0.0), (6.0, 0.0), (8.0, 0.0), (30.0, 0.0)),
    )
    removed_model_id = broken.model_placements[-1].model_instance_id
    state.battlefield_state = state.battlefield_state.with_unit_placement(broken)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()
    cleanup = state.end_turn_cleanup_states[-1]

    assert removed_model_id in state.battlefield_state.removed_model_ids
    assert cleanup.removed_model_instance_ids == (removed_model_id,)
    assert cleanup.removals[0].removal_kind.value == "destroyed"
    assert cleanup.removals[0].destroyed_model_rules_triggered is False


def test_unarrived_reserves_are_destroyed_at_mission_deadline() -> None:
    state, reserve_unit_id = _battle_state_with_unarrived_reserve_at_round_three_deadline()
    reserve_model_ids = tuple(
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == reserve_unit_id
        for model in unit.own_models
    )

    state.advance_to_next_battle_phase()
    reserve_state = state.reserve_state_for_unit(reserve_unit_id)

    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.DESTROYED
    assert state.battlefield_state is not None
    assert set(reserve_model_ids) <= set(state.battlefield_state.removed_model_ids)


def test_victory_point_ledger_round_trips_without_object_reprs() -> None:
    state = _battle_state()
    state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="assassination",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.COMMAND,
    )
    payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert GameState.from_payload(payload).to_payload() == state.to_payload()
    assert (
        VictoryPointLedger.from_payload(payload["victory_point_ledgers"][0]).to_payload()
        == state.victory_point_ledgers[0].to_payload()
    )


def test_game_ends_after_configured_battle_rounds_with_draw_result() -> None:
    state = _battle_state()
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    completed_phase = state.advance_to_next_battle_phase()
    result = state.game_result_payload()

    assert completed_phase is BattlePhase.FIGHT
    assert state.stage is GameLifecycleStage.COMPLETE
    assert state.current_battle_phase is None
    assert result["winner_player_ids"] == ["player-a", "player-b"]
    assert result["is_draw"] is True


def test_scoring_policy_ledger_and_card_state_fail_fast_paths() -> None:
    policy = mission_scoring_policy_from_setup(_mission_setup())
    award = policy.mission_action_award(
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.COMMAND.value,
        action_id="cleanse:center:player-a",
        source_id="cleanse",
    )

    ledger, transaction = VictoryPointLedger.initial(player_id="player-a").award(award)
    fixed_card = SecondaryMissionCardState.active_fixed(
        player_id="player-a",
        secondary_mission_id="assassination",
    )
    scored_card = fixed_card.score(transaction_id=transaction.transaction_id)

    assert MissionScoringPolicy.from_payload(policy.to_payload()) == policy
    assert award.to_payload()["source_kind"] == "mission_action"
    assert VictoryPointTransaction.from_payload(transaction.to_payload()) == transaction
    assert ledger.points_from_source_kind(VictoryPointSourceKind.MISSION_ACTION) == 5
    assert SecondaryMissionCardState.from_payload(scored_card.to_payload()) == scored_card
    assert fixed_card.to_public_payload(
        viewer_player_id="player-b",
        secondary_mission_choices_revealed=False,
    ) == {
        "player_id": "player-a",
        "hidden": True,
    }
    assert fixed_card.to_public_payload(
        viewer_player_id="player-b",
        secondary_mission_choices_revealed=True,
    ) == {
        "player_id": "player-a",
        "secondary_mission_id": "assassination",
        "mode": "fixed",
        "battle_round": 1,
        "status": "active",
        "source_result_id": None,
        "scored_transaction_id": None,
        "discarded_result_id": None,
        "hidden": False,
    }

    with pytest.raises(GameLifecycleError):
        policy.secondary_award(
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.COMMAND.value,
            secondary_mission_id="assassination",
            source_kind=VictoryPointSourceKind.PRIMARY,
            hidden=True,
        )
    with pytest.raises(GameLifecycleError):
        ledger.award(cast(VictoryPointAward, "not-an-award"))
    with pytest.raises(GameLifecycleError):
        ledger.award(replace(award, player_id="player-b"))
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=99,
            transactions=ledger.transactions,
        )
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=transaction.amount,
            transactions=cast(tuple[VictoryPointTransaction, ...], ("not-a-transaction",)),
        )
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=transaction.amount,
            transactions=(replace(transaction, player_id="player-b"),),
        )
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=transaction.amount * 2,
            transactions=(transaction, transaction),
        )
    with pytest.raises(GameLifecycleError):
        fixed_card.discard(result_id="discard-fixed")
    with pytest.raises(GameLifecycleError):
        scored_card.score(transaction_id="another-transaction")
    with pytest.raises(GameLifecycleError):
        scored_card.discard(result_id="discard-scored")
    with pytest.raises(GameLifecycleError):
        SecondaryMissionCardState(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.FIXED,
            battle_round=1,
            status=SecondaryMissionCardStatus.SCORED,
        )
    with pytest.raises(GameLifecycleError):
        SecondaryMissionCardState(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.TACTICAL,
            battle_round=1,
            status=SecondaryMissionCardStatus.DISCARDED,
        )
    with pytest.raises(GameLifecycleError):
        SecondaryMissionCardState(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.TACTICAL,
            battle_round=1,
            scored_transaction_id="victory-point:player-a:round-01:000001",
        )


def test_phase11e_token_parsers_reject_malformed_values() -> None:
    with pytest.raises(GameLifecycleError):
        victory_point_source_kind_from_token(1)
    with pytest.raises(GameLifecycleError):
        victory_point_source_kind_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_status_from_token(1)
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_status_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_mode_from_token(1)
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_mode_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        objective_control_timing_from_token(1)
    with pytest.raises(GameLifecycleError):
        objective_control_timing_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        mission_action_status_from_token(1)
    with pytest.raises(GameLifecycleError):
        mission_action_status_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        battlefield_removal_kind_from_token(1)
    with pytest.raises(GameLifecycleError):
        battlefield_removal_kind_from_token("unsupported")


def test_mission_action_state_rejects_drifted_completion_and_status_fields() -> None:
    action = _mission_action_state(action_id="cleanse:center:player-a")
    award = VictoryPointAward(
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        amount=5,
        source_kind=VictoryPointSourceKind.MISSION_ACTION,
        source_id="cleanse",
        scoring_timing="mission_action_complete",
        metadata={"action_id": action.action_id},
    )

    completed = action.complete(
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        completion_timing="turn_end",
        award=award,
        transaction_id="victory-point:player-a:round-01:000001",
    )

    assert MissionActionState.from_payload(action.to_payload()) == action
    assert completed.status is MissionActionStatus.COMPLETED

    with pytest.raises(GameLifecycleError):
        completed.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=award,
            transaction_id="victory-point:player-a:round-01:000002",
        )
    with pytest.raises(GameLifecycleError):
        completed.interrupt(reason="unit_moved")
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="wrong_timing",
            award=award,
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=cast(VictoryPointAward, "not-an-award"),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=replace(award, player_id="player-b"),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=replace(award, source_id="behind-enemy-lines"),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=replace(award, amount=10),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.interrupt(reason="unit_destroyed")
    with pytest.raises(GameLifecycleError):
        MissionActionState.start(
            action_id="cleanse:invalid:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-2",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError):
        MissionActionState(
            action_id="cleanse:started-with-completion:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            mission_id="cleanse",
            battle_round_started=1,
            phase_started=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            completed_battle_round=1,
        )
    with pytest.raises(GameLifecycleError):
        MissionActionState(
            action_id="cleanse:completed-without-round:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            mission_id="cleanse",
            battle_round_started=1,
            phase_started=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            status=MissionActionStatus.COMPLETED,
            score_transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        MissionActionState(
            action_id="cleanse:interrupted-with-score:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            mission_id="cleanse",
            battle_round_started=1,
            phase_started=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            status=MissionActionStatus.INTERRUPTED,
            interrupted_reason="unit_moved",
            score_transaction_id="victory-point:player-a:round-01:000001",
        )


def test_mission_policy_and_tactical_draw_are_fail_fast() -> None:
    setup = _mission_setup()

    assert deterministic_tactical_secondary_draw(
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        draw_count=1,
    )

    with pytest.raises(GameLifecycleError):
        mission_scoring_policy_from_setup(cast(MissionSetup, object()))
    with pytest.raises(GameLifecycleError):
        mission_scoring_policy_from_setup(replace(setup, mission_pack_id="unsupported-pack"))
    with pytest.raises(GameLifecycleError):
        mission_scoring_policy_from_setup(replace(setup, primary_mission_id="unsupported-primary"))
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=cast(MissionSetup, object()),
            player_id="player-a",
            battle_round=1,
            draw_count=1,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=replace(setup, mission_pack_id="unsupported-pack"),
            player_id="player-a",
            battle_round=1,
            draw_count=1,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            draw_count=999,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=setup,
            player_id="player-a",
            battle_round=0,
            draw_count=1,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            draw_count=1,
            excluded_secondary_mission_ids=("cleanse", "cleanse"),
        )


def test_turn_cleanup_payloads_and_resolver_reject_invalid_contexts() -> None:
    removal = CoherencyCleanupRemoval(
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        model_instance_id="army-alpha:intercessor-unit-1:model-1",
    )
    cleanup = EndTurnCleanupState(
        cleanup_id="end-turn-cleanup:phase11e-game:round-01:player-a",
        game_id="phase11e-game",
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removals=(removal,),
        coherency_results=(),
        transition_batch=BattlefieldTransitionBatch(),
    )
    state = _battle_state()
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )

    assert CoherencyCleanupRemoval.from_payload(removal.to_payload()) == removal
    assert EndTurnCleanupState.from_payload(cleanup.to_payload()) == cleanup

    with pytest.raises(GameLifecycleError):
        CoherencyCleanupRemoval(
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:model-1",
            removal_kind=BattlefieldRemovalKind.EMBARK,
        )
    with pytest.raises(GameLifecycleError):
        CoherencyCleanupRemoval(
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:model-1",
            destroyed_model_rules_triggered=True,
        )
    with pytest.raises(GameLifecycleError):
        EndTurnCleanupState(
            cleanup_id="end-turn-cleanup:phase11e-game:round-01:player-a",
            game_id="phase11e-game",
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT.value,
            removals=(removal, removal),
            coherency_results=(),
            transition_batch=BattlefieldTransitionBatch(),
        )
    with pytest.raises(GameLifecycleError):
        EndTurnCleanupState(
            cleanup_id="end-turn-cleanup:phase11e-game:round-01:player-a",
            game_id="phase11e-game",
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT.value,
            removals=(removal,),
            coherency_results=(),
            transition_batch=cast(BattlefieldTransitionBatch, object()),
        )
    with pytest.raises(GameLifecycleError):
        resolve_end_turn_cleanup(
            game_id="phase11e-game",
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=_ruleset(),
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT,
        )
    with pytest.raises(GameLifecycleError):
        resolve_end_turn_cleanup(
            game_id="phase11e-game",
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT,
        )
    with pytest.raises(GameLifecycleError):
        resolve_end_turn_cleanup(
            game_id="phase11e-game",
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            battle_round=1,
            active_player_id="player-a",
            phase=cast(BattlePhase, "fight"),
        )


def _battle_state_with_center_objective_positions(
    *,
    player_a_offsets: tuple[tuple[float, float], ...],
    player_b_offsets: tuple[tuple[float, float], ...],
) -> GameState:
    state = _battle_state()
    assert state.battlefield_state is not None
    marker = _center_marker_definition(state)
    player_a = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    player_b = state.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-3")
    battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(player_a, marker, offsets=player_a_offsets)
    )
    battlefield_state = battlefield_state.with_unit_placement(
        _with_model_offsets(player_b, marker, offsets=player_b_offsets)
    )
    state.battlefield_state = battlefield_state
    return state


def _with_model_offsets(
    unit_placement: UnitPlacement,
    marker: ObjectiveMarkerDefinition,
    *,
    offsets: tuple[tuple[float, float], ...],
) -> UnitPlacement:
    placements = list(unit_placement.model_placements)
    for index, (offset_x, offset_y) in enumerate(offsets):
        placement = placements[index]
        placements[index] = placement.with_pose(
            Pose.at(
                marker.x_inches + offset_x,
                marker.y_inches + offset_y,
                marker.z_inches,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
    return unit_placement.with_model_placements(tuple(placements))


def _battle_state_with_unarrived_reserve_at_round_three_deadline() -> tuple[GameState, str]:
    state = _battle_state()
    assert state.battlefield_state is not None
    reserve_unit = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=reserve_unit.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                mission_scoring_policy_from_setup(_mission_setup())
            ),
        )
    )
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    return state, reserve_unit.unit_instance_id


def _mission_action_state(*, action_id: str) -> MissionActionState:
    return MissionActionState.start(
        action_id=action_id,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        mission_id="cleanse",
        battle_round=1,
        phase=BattlePhase.MOVEMENT.value,
        start_timing="movement_phase_unit_selected",
        completion_timing="turn_end",
        eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        interruption_conditions=("unit_moved",),
        scoring_source_id="cleanse",
        victory_points=5,
    )


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if marker.objective_marker_id.endswith("-center"):
            return marker
    raise AssertionError("missing center objective marker")


def _public_ledger(payload: dict[str, JsonValue], *, player_id: str) -> dict[str, JsonValue]:
    ledgers = payload["victory_point_ledgers"]
    assert isinstance(ledgers, list)
    for ledger_value in ledgers:
        assert isinstance(ledger_value, dict)
        ledger = ledger_value
        if ledger["player_id"] == player_id:
            return ledger
    raise AssertionError(f"missing public ledger for {player_id}")


def _public_card_states(payload: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    card_states = payload["secondary_mission_card_states"]
    assert isinstance(card_states, list)
    public_states: list[dict[str, JsonValue]] = []
    for card_state_value in card_states:
        assert isinstance(card_state_value, dict)
        public_states.append(card_state_value)
    return public_states


def _public_secondary_choice(
    payload: dict[str, JsonValue],
    *,
    player_id: str,
) -> dict[str, JsonValue]:
    choices = payload["secondary_mission_choices"]
    assert isinstance(choices, list)
    for choice_value in choices:
        assert isinstance(choice_value, dict)
        if choice_value["player_id"] == player_id:
            return choice_value
    raise AssertionError(f"missing public secondary choice for {player_id}")


def _advance_to_secondary_request(lifecycle: GameLifecycle) -> LifecycleStatus:
    for _index in range(32):
        status = lifecycle.advance_until_decision_or_terminal()
        request = status.decision_request
        if request is not None and request.decision_type == SECONDARY_MISSION_DECISION_TYPE:
            return status
    raise AssertionError("lifecycle did not reach secondary mission selection")


def _battle_state(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
) -> GameState:
    config = _config()
    state = GameState.from_config(config)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11e-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=player_a_secondary)
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=player_b_secondary)
    )
    while state.current_setup_step is not None:
        state.complete_current_setup_step()
    assert state.stage is GameLifecycleStage.BATTLE
    assert state.current_battle_phase is BattlePhase.COMMAND
    return state


def _secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "bring-it-down"),
    )


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase11e-game",
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_tenth_chapter_approved_2025_26(
        descriptor_version="core-v2-phase11e-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
