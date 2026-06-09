from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
)

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.actions import (
    MissionActionState,
    MissionActionStatus,
    interrupt_mission_action_for_battlefield_departure,
    interrupt_mission_action_for_displacement,
    mission_action_interruption_reason_for_displacement,
    mission_action_status_from_token,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    UnitPlacement,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    TacticalSecondaryDraw,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_decisions import (
    START_MISSION_ACTION_DECISION_TYPE,
    TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
    TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
    request_mission_action_start,
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_scoring_policy_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    SecondaryDestroyedModelState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionScoringRule,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    SecondaryUnitDestructionState,
    TacticalSecondaryAchievementContext,
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
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.turn_cleanup import (
    CoherencyCleanupRemoval,
    EndTurnCleanupState,
    battlefield_removal_kind_from_token,
    resolve_end_turn_cleanup,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

SEEDED_TACTICAL_DRAW_REQUEST_ID = "phase11e-seeded-tactical-draw-request"
SEEDED_TACTICAL_DRAW_RESULT_ID = "phase11e-seeded-tactical-draw"


def test_take_and_hold_does_not_score_before_battle_round_two() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),),
        player_b_offsets=((20.0, 20.0),),
    )

    completed_phase = state.advance_to_next_battle_phase()
    ledger = state.victory_point_ledger_for_player("player-a")

    assert completed_phase is BattlePhase.COMMAND
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.victory_point_total("player-a") == 0
    assert ledger.transactions == ()


def test_take_and_hold_scores_from_battle_round_two_at_configured_command_timing() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),),
        player_b_offsets=((20.0, 20.0),),
    )
    state.battle_round = 2

    completed_phase = state.advance_to_next_battle_phase()
    ledger = state.victory_point_ledger_for_player("player-a")

    assert completed_phase is BattlePhase.COMMAND
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.victory_point_total("player-a") == 10
    assert ledger.transactions[0].source_kind is VictoryPointSourceKind.PRIMARY
    assert ledger.transactions[0].source_id == "take-and-hold"
    assert ledger.transactions[0].metadata == {
        "objective_control_record_id": ("objective-control:round-02:player-a:command:phase_end"),
        "score_count": 2,
        "controlled_objective_ids": [
            "primary-immovable-object-layout-3-center-central",
            "primary-immovable-object-layout-3-left-home",
        ],
        "home_objective_ids": [],
        "turn_start_controlled_objective_ids": [],
        "trapped_terrain_feature_ids": [],
        "destroyed_unit_instance_ids": [],
        "scoring_rule_id": "take-and-hold-control",
        "scoring_rule_condition": "each_controlled_objective_from_battle_round_two",
        "scoring_rule_source_id": (
            "gw-11e-chapter-approved-2026-27:primary:take-and-hold:"
            "scoring-rule:take-and-hold-control"
        ),
        "victory_points_per_count": 5,
    }


def test_immovable_object_scores_central_and_non_home_objectives_by_round() -> None:
    turn_end_state = _battle_state_for_primary("primary-immovable-object")
    _place_unit_near_objective(
        turn_end_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    turn_end_state.battle_phase_index = turn_end_state.battle_phase_sequence.index(
        BattlePhase.FIGHT
    )

    turn_end_state.advance_to_next_battle_phase()

    assert turn_end_state.victory_point_total("player-a") == 3
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"]
        for transaction in turn_end_state.victory_point_ledger_for_player("player-a").transactions
    ] == ["immovable-object-central-turn-end"]

    command_state = _battle_state_for_primary("primary-immovable-object")
    command_state.battle_round = 2
    _place_unit_near_objective(
        command_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    command_state.advance_to_next_battle_phase()

    assert command_state.victory_point_total("player-a") == 5
    command_transaction = command_state.victory_point_ledger_for_player("player-a").transactions[0]
    command_metadata = _transaction_metadata(command_transaction)
    assert command_metadata["scoring_rule_id"] == ("immovable-object-rounds-two-to-four-command")
    assert command_metadata["controlled_objective_ids"] == [
        "primary-immovable-object-layout-3-center-central"
    ]

    fifth_round_state = _battle_state_for_primary("primary-immovable-object")
    fifth_round_state.battle_round = 5
    _place_unit_near_objective(
        fifth_round_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    fifth_round_state.battle_phase_index = fifth_round_state.battle_phase_sequence.index(
        BattlePhase.FIGHT
    )

    fifth_round_state.advance_to_next_battle_phase()

    assert fifth_round_state.victory_point_total("player-a") == 8
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"]
        for transaction in fifth_round_state.victory_point_ledger_for_player(
            "player-a"
        ).transactions
    ] == [
        "immovable-object-central-turn-end",
        "immovable-object-round-five-turn-end",
    ]


def test_unstoppable_force_scores_kills_new_objectives_and_end_battle_central_control() -> None:
    turn_state = _battle_state_for_primary("primary-unstoppable-force")
    _place_unit_near_objective(
        turn_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    turn_state.record_primary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id="army-beta:intercessor-unit-3",
        started_turn_terrain_feature_ids=(),
        source_id="phase16:unstoppable-force:enemy-destroyed",
    )
    turn_state.battle_phase_index = turn_state.battle_phase_sequence.index(BattlePhase.FIGHT)

    turn_state.advance_to_next_battle_phase()

    assert turn_state.victory_point_total("player-a") == 6
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"]
        for transaction in turn_state.victory_point_ledger_for_player("player-a").transactions
    ] == [
        "unstoppable-force-enemy-destroyed-turn-end",
        "unstoppable-force-new-objective-turn-end",
    ]

    command_state = _battle_state_for_primary("primary-unstoppable-force")
    command_state.battle_round = 2
    _place_unit_near_objective(
        command_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    command_state.advance_to_next_battle_phase()

    assert command_state.victory_point_total("player-a") == 4
    assert (
        _transaction_metadata(
            command_state.victory_point_ledger_for_player("player-a").transactions[0]
        )["scoring_rule_id"]
        == "unstoppable-force-objectives"
    )

    end_state = _battle_state_for_primary("primary-unstoppable-force")
    end_state.battle_round = 5
    end_state.active_player_id = "player-b"
    end_state.record_primary_objective_turn_start_state(
        PrimaryObjectiveTurnStartState(
            state_id="phase16:unstoppable-force:round-05:player-b:turn-start",
            game_id=end_state.game_id,
            player_id="player-b",
            active_player_id="player-b",
            battle_round=5,
            controlled_objective_ids=(),
            source_id="phase16:unstoppable-force:round-05:player-b:turn-start",
        )
    )
    _place_unit_near_objective(
        end_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    end_state.battle_phase_index = end_state.battle_phase_sequence.index(BattlePhase.FIGHT)

    end_state.advance_to_next_battle_phase()

    assert end_state.stage is GameLifecycleStage.COMPLETE
    assert end_state.victory_point_total("player-a") == 5
    assert (
        _transaction_metadata(
            end_state.victory_point_ledger_for_player("player-a").transactions[0]
        )["scoring_rule_id"]
        == "unstoppable-force-central-end-battle"
    )


def test_death_trap_booby_trap_action_tracks_and_scores_trapped_objective_terrain() -> None:
    feature_id = "primary-immovable-object-layout-3-center-ruin"
    lifecycle = _battle_lifecycle_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=feature_id,
    )
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    feature = next(
        feature
        for feature in state.mission_setup.terrain_features
        if feature.feature_id == feature_id
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_unit_near_point(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        x_inches=feature.footprint_center_x_inches,
        y_inches=feature.footprint_center_y_inches,
    )

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="booby-trap-terrain",
    )
    request = waiting.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["target_id"] == feature_id
    )
    lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option.option_id,
            result_id="phase16-start-booby-trap",
        ).to_result(request)
    )
    action = state.mission_action_state_by_id("mission-action:phase16-start-booby-trap")
    trap_state = state.primary_terrain_trap_states[0]

    assert action.status is MissionActionStatus.COMPLETED
    assert action.score_transaction_id is None
    assert trap_state.terrain_feature_id == feature_id
    assert trap_state.is_objective is True

    state.record_primary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id="army-beta:intercessor-unit-3",
        started_turn_terrain_feature_ids=(feature_id,),
        source_id="phase16:death-trap:enemy-destroyed-in-trapped-terrain",
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()

    assert state.victory_point_total("player-a") == 8
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"]
        for transaction in state.victory_point_ledger_for_player("player-a").transactions
    ] == [
        "death-trap-destroyed-in-trapped-terrain-turn-end",
        "death-trap-objective-terrain-bonus-turn-end",
        "death-trap-terrain-trapped-turn-end",
    ]


def test_phase16_primary_scoring_states_round_trip_and_fail_fast() -> None:
    feature_id = "primary-immovable-object-layout-3-center-ruin"
    state = _battle_state_for_primary("primary-death-trap")
    first_turn_start = state.primary_objective_turn_start_states[0]

    with pytest.raises(GameLifecycleError, match="unknown started-turn terrain"):
        state.record_primary_unit_destruction(
            destroying_player_id="player-a",
            destroyed_unit_instance_id="army-beta:intercessor-unit-3",
            started_turn_terrain_feature_ids=("missing-terrain",),
            source_id="phase16:death-trap:unknown-terrain",
        )
    with pytest.raises(GameLifecycleError, match="must target an enemy unit"):
        state.record_primary_unit_destruction(
            destroying_player_id="player-a",
            destroyed_unit_instance_id="army-alpha:intercessor-unit-1",
            started_turn_terrain_feature_ids=(),
            source_id="phase16:death-trap:friendly-unit",
        )

    trap = state.record_primary_terrain_trap(
        player_id="player-a",
        terrain_feature_id=feature_id,
        action_id="mission-action:phase16-booby-trap-round-trip",
        phase=BattlePhase.SHOOTING,
        source_id="phase16:death-trap:booby-trap",
    )
    destruction = state.record_primary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id="army-beta:intercessor-unit-3",
        started_turn_terrain_feature_ids=(feature_id,),
        source_id="phase16:death-trap:enemy-destroyed",
    )
    payload = cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))

    assert PrimaryObjectiveTurnStartState.from_payload(first_turn_start.to_payload()) == (
        first_turn_start
    )
    assert PrimaryTerrainTrapState.from_payload(trap.to_payload()) == trap
    assert PrimaryUnitDestructionState.from_payload(destruction.to_payload()) == destruction
    assert GameState.from_payload(payload).to_payload() == state.to_payload()

    with pytest.raises(GameLifecycleError, match="terrain trap already exists"):
        state.record_primary_terrain_trap(
            player_id="player-a",
            terrain_feature_id=feature_id,
            action_id="mission-action:phase16-booby-trap-duplicate",
            phase=BattlePhase.SHOOTING,
            source_id="phase16:death-trap:booby-trap-duplicate",
        )
    with pytest.raises(GameLifecycleError, match="destruction already exists"):
        state.record_primary_unit_destruction(
            destroying_player_id="player-a",
            destroyed_unit_instance_id="army-beta:intercessor-unit-3",
            started_turn_terrain_feature_ids=(feature_id,),
            source_id="phase16:death-trap:enemy-destroyed-duplicate",
        )
    with pytest.raises(GameLifecycleError, match="owner's turn"):
        replace(trap, active_player_id="player-b")
    with pytest.raises(GameLifecycleError, match="must target an enemy unit"):
        replace(destruction, destroyed_player_id="player-a")


def test_booby_trap_action_is_primary_scoped_and_immediate_zero_vp() -> None:
    lifecycle = _battle_lifecycle_for_primary("primary-immovable-object")
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)

    unsupported = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="booby-trap-terrain",
    )
    unsupported_payload = cast(dict[str, JsonValue], unsupported.payload)

    assert unsupported.status_kind.value == "unsupported"
    assert unsupported.decision_request is None
    assert unsupported_payload["mission_id"] == "primary-death-trap"
    assert unsupported_payload["active_primary_mission_id"] == "primary-immovable-object"

    zero_vp_action = MissionActionState.start(
        action_id="mission-action:phase16-zero-vp-complete",
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_id="primary-immovable-object-layout-3-center-ruin",
        mission_id="primary-death-trap",
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        start_timing="shooting_phase",
        completion_timing="immediate",
        eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        interruption_conditions=(),
        scoring_source_id="booby-trap-terrain",
        victory_points=0,
    )
    completed = zero_vp_action.complete_without_award(
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        completion_timing="immediate",
    )

    assert completed.status is MissionActionStatus.COMPLETED
    assert completed.score_transaction_id is None

    with pytest.raises(GameLifecycleError, match="Only started mission Actions can complete"):
        completed.complete_without_award(
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            completion_timing="immediate",
        )
    with pytest.raises(GameLifecycleError, match="Only zero-VP mission Actions"):
        _mission_action_state(action_id="phase16-positive-vp-no-award").complete_without_award(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
        )
    with pytest.raises(GameLifecycleError, match="completion timing drift"):
        zero_vp_action.complete_without_award(
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            completion_timing="turn_end",
        )
    with pytest.raises(GameLifecycleError, match="cannot complete actions"):
        zero_vp_action.complete_without_award(
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            completion_timing="immediate",
            battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
        )
    with pytest.raises(GameLifecycleError, match="zero-VP mission Action must not score"):
        replace(
            completed,
            score_transaction_id="victory-point:player-a:round-01:000001",
        )


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
    assert state.victory_point_total("player-a") == 4
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
        "amount": 4,
        "source_kind": "fixed_secondary",
        "source_id": "assassination",
        "scoring_timing": "secondary_mission_score",
        "hidden": False,
        "metadata": {
            "secondary_mission_id": "assassination",
            "scoring_rule_id": "assassination-fixed",
            "scoring_rule_condition": "fixed_secondary_condition",
            "scoring_rule_source_id": (
                "gw-11e-chapter-approved-2026-27:secondary:assassination:"
                "scoring-rule:assassination-fixed"
            ),
        },
    }
    assert any(
        card_payload["player_id"] == "player-a"
        and card_payload["secondary_mission_id"] == "assassination"
        and card_payload["mode"] == "fixed"
        and card_payload["hidden"] is False
        for card_payload in _public_card_states(opponent_payload)
    )


def test_secondary_scoring_uses_source_backed_fixed_and_tactical_card_values() -> None:
    fixed_state = _battle_state()

    fixed_state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.COMMAND,
    )

    tactical_state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    tactical_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=1,
            source_result_id="phase11e-test-draw",
        )
    )
    tactical_state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )

    assert fixed_state.victory_point_total("player-a") == 4
    assert tactical_state.victory_point_total("player-a") == 5
    fixed_transaction = fixed_state.victory_point_ledger_for_player("player-a").transactions[0]
    tactical_transaction = tactical_state.victory_point_ledger_for_player("player-a").transactions[
        0
    ]
    assert fixed_transaction.metadata == {
        "secondary_mission_id": "bring-it-down",
        "scoring_rule_id": "bring-it-down-fixed",
        "scoring_rule_condition": "each_enemy_model_w10_or_more_destroyed_this_turn",
        "scoring_rule_source_id": (
            "gw-11e-chapter-approved-2026-27:secondary:bring-it-down:"
            "scoring-rule:bring-it-down-fixed"
        ),
    }
    assert tactical_transaction.metadata == {
        "secondary_mission_id": "bring-it-down",
        "scoring_rule_id": "bring-it-down-tactical",
        "scoring_rule_condition": "each_enemy_model_w10_or_more_destroyed_this_turn",
        "scoring_rule_source_id": (
            "gw-11e-chapter-approved-2026-27:secondary:bring-it-down:"
            "scoring-rule:bring-it-down-tactical"
        ),
    }


def test_bring_it_down_scores_each_destroyed_w10_model_and_caps_tactical() -> None:
    fixed_state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3", "vehicle-unit-4"))
    )
    fixed_state.battle_phase_index = fixed_state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _record_secondary_vehicle_destruction(fixed_state, "army-beta:vehicle-unit-3")
    _record_secondary_vehicle_destruction(fixed_state, "army-beta:vehicle-unit-4")

    fixed_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
    )

    tactical_state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3", "vehicle-unit-4")),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    tactical_state.battle_phase_index = tactical_state.battle_phase_sequence.index(
        BattlePhase.FIGHT
    )
    tactical_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=1,
            source_result_id="phase16-bring-it-down-draw",
        )
    )
    _record_secondary_vehicle_destruction(tactical_state, "army-beta:vehicle-unit-3")
    _record_secondary_vehicle_destruction(tactical_state, "army-beta:vehicle-unit-4")

    tactical_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    assert fixed_state.victory_point_total("player-a") == 8
    assert tactical_state.victory_point_total("player-a") == 5
    fixed_metadata = _transaction_metadata(
        fixed_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    tactical_metadata = _transaction_metadata(
        tactical_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert fixed_metadata["score_count_by_rule"] == {"bring-it-down-fixed": 2}
    assert fixed_metadata["victory_points_by_rule"] == {"bring-it-down-fixed": 8}
    assert tactical_metadata["score_count_by_rule"] == {"bring-it-down-tactical": 2}
    assert tactical_metadata["victory_points_by_rule"] == {"bring-it-down-tactical": 5}


def test_overwhelming_force_scores_destroyed_units_that_started_on_objectives_with_cap() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3", "vehicle-unit-4")),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="overwhelming-force",
            battle_round=1,
            source_result_id="phase16-overwhelming-force-draw",
        )
    )
    _record_secondary_vehicle_destruction(
        state,
        "army-beta:vehicle-unit-3",
        started_turn_objective_marker_ids=("primary-immovable-object-layout-3-center-central",),
    )
    _record_secondary_vehicle_destruction(
        state,
        "army-beta:vehicle-unit-4",
        started_turn_objective_marker_ids=("primary-immovable-object-layout-3-upper-central",),
    )

    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="overwhelming-force",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    metadata = _transaction_metadata(
        state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert state.victory_point_total("player-a") == 5
    assert metadata["score_count_by_rule"] == {"overwhelming-force-tactical": 2}
    assert metadata["victory_points_by_rule"] == {"overwhelming-force-tactical": 5}


def test_cleanse_and_plunder_score_from_recorded_action_evidence() -> None:
    cleanse_state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    cleanse_state.battle_phase_index = cleanse_state.battle_phase_sequence.index(BattlePhase.FIGHT)
    cleanse_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="cleanse",
            battle_round=1,
            source_result_id="phase16-cleanse-draw",
        )
    )
    cleanse_state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id="primary-immovable-object-layout-3-center-central",
        action_id="phase16-cleanse-center",
        phase=BattlePhase.FIGHT,
        source_id="cleanse",
    )
    cleanse_state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id="primary-immovable-object-layout-3-upper-central",
        action_id="phase16-cleanse-northwest",
        phase=BattlePhase.FIGHT,
        source_id="cleanse",
    )

    cleanse_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="cleanse",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    plunder_state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    plunder_state.battle_phase_index = plunder_state.battle_phase_sequence.index(BattlePhase.FIGHT)
    plunder_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="plunder",
            battle_round=1,
            source_result_id="phase16-plunder-draw",
        )
    )
    assert plunder_state.mission_setup is not None
    plunder_state.record_secondary_terrain_plunder(
        player_id="player-a",
        terrain_feature_id=plunder_state.mission_setup.terrain_features[0].feature_id,
        action_id="phase16-plunder-terrain",
        phase=BattlePhase.SHOOTING,
        source_id="plunder",
    )

    plunder_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="plunder",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    cleanse_metadata = _transaction_metadata(
        cleanse_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    plunder_metadata = _transaction_metadata(
        plunder_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert cleanse_state.victory_point_total("player-a") == 5
    assert cleanse_metadata["victory_points_by_rule"] == {
        "cleanse-tactical-one-objective": 2,
        "cleanse-tactical-two-objectives": 3,
    }
    assert plunder_state.victory_point_total("player-a") == 5
    assert plunder_metadata["victory_points_by_rule"] == {"plunder-tactical": 5}


def test_defend_stronghold_scores_at_opponent_turn_end_with_deployment_zone_bonus() -> None:
    state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state.battle_round = 2
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=2,
            source_result_id="phase16-defend-stronghold-draw",
        )
    )
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="left-home",
    )
    _place_unit_near_objective(
        state,
        unit_instance_id="army-beta:intercessor-unit-3",
        target_suffix="southwest",
    )

    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    metadata = _transaction_metadata(
        state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert state.victory_point_total("player-a") == 5
    assert metadata["victory_points_by_rule"] == {
        "defend-stronghold-home-objective": 3,
        "defend-stronghold-no-enemy-in-deployment-zone": 2,
    }


def test_secondary_scoring_evidence_payloads_round_trip_and_fail_fast() -> None:
    model = SecondaryDestroyedModelState(
        model_instance_id="army-beta:vehicle-unit-3:model-1",
        starting_wounds=10,
    )
    destruction = SecondaryUnitDestructionState(
        destruction_id="secondary-unit-destruction:phase11e-game:round-01:vehicle-unit-3",
        game_id="phase11e-game",
        destroying_player_id="player-a",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        destroyed_unit_instance_id="army-beta:vehicle-unit-3",
        destroyed_models=(model,),
        started_turn_objective_marker_ids=("primary-immovable-object-layout-3-center-central",),
        source_id="phase16:test-destruction",
    )
    cleanse = SecondaryObjectiveCleanseState(
        cleanse_id="secondary-objective-cleanse:phase11e-game:round-01:player-a:center",
        game_id="phase11e-game",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        objective_marker_id="primary-immovable-object-layout-3-center-central",
        action_id="mission-action:phase16-cleanse-center",
        source_id="cleanse",
    )
    plunder = SecondaryTerrainPlunderState(
        plunder_id="secondary-terrain-plunder:phase11e-game:round-01:player-a:ruin-1",
        game_id="phase11e-game",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        terrain_feature_id="ruin-1",
        action_id="mission-action:phase16-plunder-ruin-1",
        source_id="plunder",
    )
    rule = SecondaryMissionScoringRule(
        secondary_mission_id="plunder",
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        timing="your_turn_end",
        victory_points=5,
        cap=None,
        condition="one_or_more_terrain_areas_plundered_this_turn",
        rule_id="plunder-tactical",
        source_id="phase16:plunder-rule",
    )

    assert SecondaryDestroyedModelState.from_payload(model.to_payload()) == model
    assert SecondaryUnitDestructionState.from_payload(destruction.to_payload()) == destruction
    assert SecondaryObjectiveCleanseState.from_payload(cleanse.to_payload()) == cleanse
    assert SecondaryTerrainPlunderState.from_payload(plunder.to_payload()) == plunder
    assert SecondaryMissionScoringRule.from_payload(rule.to_payload()) == rule
    with pytest.raises(GameLifecycleError, match="enemy unit"):
        SecondaryUnitDestructionState(
            destruction_id="secondary-unit-destruction:phase11e-game:round-01:friendly",
            game_id="phase11e-game",
            destroying_player_id="player-a",
            destroyed_player_id="player-a",
            active_player_id="player-a",
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            destroyed_unit_instance_id="army-alpha:intercessor-unit-1",
            destroyed_models=(model,),
            started_turn_objective_marker_ids=(),
            source_id="phase16:test-friendly-destruction",
        )
    with pytest.raises(GameLifecycleError, match="owner's turn"):
        SecondaryObjectiveCleanseState(
            cleanse_id="secondary-objective-cleanse:phase11e-game:round-01:player-a:bad",
            game_id="phase11e-game",
            player_id="player-a",
            active_player_id="player-b",
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            objective_marker_id="primary-immovable-object-layout-3-center-central",
            action_id="mission-action:phase16-cleanse-bad",
            source_id="cleanse",
        )
    with pytest.raises(GameLifecycleError, match="owner's turn"):
        SecondaryTerrainPlunderState(
            plunder_id="secondary-terrain-plunder:phase11e-game:round-01:player-a:bad",
            game_id="phase11e-game",
            player_id="player-a",
            active_player_id="player-b",
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            terrain_feature_id="ruin-1",
            action_id="mission-action:phase16-plunder-bad",
            source_id="plunder",
        )
    with pytest.raises(GameLifecycleError, match="secondary source kind"):
        SecondaryMissionScoringRule(
            secondary_mission_id="plunder",
            source_kind=VictoryPointSourceKind.PRIMARY,
            timing="your_turn_end",
            victory_points=5,
            cap=None,
            condition="terrain_area_plundered_this_turn",
            rule_id="plunder-primary-invalid",
            source_id="phase16:plunder-rule-invalid",
        )
    with pytest.raises(GameLifecycleError, match="Unsupported secondary scoring rule condition"):
        SecondaryMissionScoringRule(
            secondary_mission_id="plunder",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            timing="your_turn_end",
            victory_points=5,
            cap=None,
            condition="unsupported_condition",
            rule_id="plunder-condition-invalid",
            source_id="phase16:plunder-rule-invalid",
        )


def test_state_backed_secondary_scoring_rejects_invalid_contexts_and_zero_evidence() -> None:
    state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    assert state.mission_setup is not None
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=BattlePhase.FIGHT,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
    )
    policy = mission_scoring_policy_from_setup(state.mission_setup)
    empty_destructions: tuple[SecondaryUnitDestructionState, ...] = ()
    empty_cleanses: tuple[SecondaryObjectiveCleanseState, ...] = ()
    empty_plunders: tuple[SecondaryTerrainPlunderState, ...] = ()
    empty_enemy_zone_units: tuple[str, ...] = ()

    assert (
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="requires objective record"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=cast(ObjectiveControlRecord, object()),
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="requires MissionSetup"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=cast(MissionSetup, object()),
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="requires secondary kind"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.PRIMARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="record timing drift"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round + 1,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="not source-backed"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="not-source-backed",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )

    unsupported_timing_policy = replace(
        policy,
        secondary_scoring_rules=(
            SecondaryMissionScoringRule(
                secondary_mission_id="phase16-test-secondary",
                source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
                timing="unsupported-timing",
                victory_points=1,
                cap=None,
                condition="one_or_more_terrain_areas_plundered_this_turn",
                rule_id="phase16-test-secondary-unsupported-timing",
                source_id="phase16:test-secondary-unsupported-timing",
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="Unsupported secondary scoring rule timing"):
        unsupported_timing_policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="phase16-test-secondary",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )


def test_game_state_secondary_scoring_evidence_round_trips_and_rejects_duplicates() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3",)),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _record_secondary_vehicle_destruction(
        state,
        "army-beta:vehicle-unit-3",
        started_turn_objective_marker_ids=("primary-immovable-object-layout-3-center-central",),
    )
    state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id="primary-immovable-object-layout-3-center-central",
        action_id="phase16-cleanse-center",
        phase=BattlePhase.FIGHT,
        source_id="cleanse",
    )
    assert state.mission_setup is not None
    state.record_secondary_terrain_plunder(
        player_id="player-a",
        terrain_feature_id=state.mission_setup.terrain_features[0].feature_id,
        action_id="phase16-plunder-terrain",
        phase=BattlePhase.FIGHT,
        source_id="plunder",
    )

    payload = state.to_payload()
    restored = GameState.from_payload(payload)

    assert restored.secondary_unit_destruction_states == state.secondary_unit_destruction_states
    assert restored.secondary_objective_cleanse_states == state.secondary_objective_cleanse_states
    assert restored.secondary_terrain_plunder_states == state.secondary_terrain_plunder_states
    duplicate_unit_state = replace(
        state.secondary_unit_destruction_states[0],
        destruction_id=f"{state.secondary_unit_destruction_states[0].destruction_id}:duplicate",
    )
    duplicate_cleanse_state = replace(
        state.secondary_objective_cleanse_states[0],
        cleanse_id=f"{state.secondary_objective_cleanse_states[0].cleanse_id}:duplicate",
        action_id="phase16-cleanse-center-duplicate",
    )
    duplicate_plunder_state = replace(
        state.secondary_terrain_plunder_states[0],
        plunder_id=f"{state.secondary_terrain_plunder_states[0].plunder_id}:duplicate",
        action_id="phase16-plunder-terrain-duplicate",
    )
    with pytest.raises(GameLifecycleError, match="unique per destroyed unit"):
        replace(
            state,
            secondary_unit_destruction_states=[
                *state.secondary_unit_destruction_states,
                duplicate_unit_state,
            ],
        )
    with pytest.raises(GameLifecycleError, match="unique per objective turn"):
        replace(
            state,
            secondary_objective_cleanse_states=[
                *state.secondary_objective_cleanse_states,
                duplicate_cleanse_state,
            ],
        )
    with pytest.raises(GameLifecycleError, match="unique per player turn"):
        replace(
            state,
            secondary_terrain_plunder_states=[
                *state.secondary_terrain_plunder_states,
                duplicate_plunder_state,
            ],
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
    lifecycle = _battle_lifecycle(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    waiting = lifecycle.advance_until_decision_or_terminal()
    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE

    result = DecisionResult.for_request(
        result_id="phase11e-tactical-draw",
        request=request,
        selected_option_id="draw",
    )
    draw_status = lifecycle.submit_decision(result)
    draw_status = _decline_stratagem_window_if_pending(
        lifecycle,
        draw_status,
        result_id="phase11e-tactical-draw-decline-stratagem",
    )
    automatic_follow_up = draw_status.decision_request
    assert automatic_follow_up is not None
    assert automatic_follow_up.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    drawn_cards = [
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a" and card.mode is SecondaryMissionCardMode.TACTICAL
    ]
    assert len(drawn_cards) == state.tactical_secondary_draw_count
    draw_opponent_events = EventStreamCursor().events_since(
        decisions.event_log,
        viewer_player_id="player-b",
    )
    draw_event = next(
        event
        for event in draw_opponent_events["events"]
        if event["event_type"] == "tactical_secondary_missions_drawn"
    )
    draw_payload = cast(dict[str, JsonValue], draw_event["payload"])
    drawn_card_payloads = cast(list[JsonValue], draw_payload["secondary_mission_card_states"])
    assert draw_payload["player_id"] == "player-a"
    assert draw_payload["draw_count"] == 2
    assert {
        str(cast(dict[str, JsonValue], card)["secondary_mission_id"])
        for card in drawn_card_payloads
    } == {card.secondary_mission_id for card in drawn_cards}

    discard_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = discard_lifecycle.state
    assert state is not None
    decisions = discard_lifecycle.decision_controller
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
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=decisions,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    assert discard_request.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE
    discard_option_id = f"discard:{active_cards[1].secondary_mission_id}"
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=discard_option_id,
        result_id="phase11e-discard-tactical",
    ).to_result(discard_request)
    discard_lifecycle.submit_decision(discard_result)
    discarded = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=active_cards[1].secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert discarded is None
    discarded_record = next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.secondary_mission_id == active_cards[1].secondary_mission_id
        and card.mode is SecondaryMissionCardMode.TACTICAL
    )
    discard_opponent_events = EventStreamCursor().events_since(
        decisions.event_log,
        viewer_player_id="player-b",
    )
    opponent_payload = state.to_public_payload(viewer_player_id="player-b")

    assert scored.status is SecondaryMissionCardStatus.SCORED
    assert discarded_record.status is SecondaryMissionCardStatus.DISCARDED
    expected_score = state.victory_point_ledger_for_player("player-a").transactions[0].amount
    assert state.victory_point_total("player-a") == expected_score
    assert decisions.records[-1].request.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE
    assert decisions.records[-1].result.result_id == "phase11e-discard-tactical"
    discard_event = next(
        event
        for event in discard_opponent_events["events"]
        if event["event_type"] == "tactical_secondary_mission_discarded"
    )
    assert cast(dict[str, JsonValue], discard_event["payload"])["player_id"] == "player-a"
    assert opponent_payload["tactical_secondary_draws"] == [
        {
            "player_id": "player-a",
            "battle_round": 1,
            "request_id": SEEDED_TACTICAL_DRAW_REQUEST_ID,
            "result_id": SEEDED_TACTICAL_DRAW_RESULT_ID,
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
    assert transaction["metadata"] == {
        "secondary_mission_id": active_cards[0].secondary_mission_id,
        "scoring_rule_id": f"{active_cards[0].secondary_mission_id}-tactical",
        "scoring_rule_condition": "tactical_secondary_condition",
        "scoring_rule_source_id": (
            f"gw-11e-chapter-approved-2026-27:secondary:"
            f"{active_cards[0].secondary_mission_id}:scoring-rule:"
            f"{active_cards[0].secondary_mission_id}-tactical"
        ),
    }
    round_tripped = GameLifecycle.from_payload(discard_lifecycle.to_payload())
    encoded = json.dumps(round_tripped.to_payload(), sort_keys=True)
    assert "<" not in encoded
    assert "object at 0x" not in encoded


def test_tactical_secondary_discard_rejects_drifted_lifecycle_option() -> None:
    lifecycle = _battle_lifecycle(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    waiting = lifecycle.advance_until_decision_or_terminal()
    draw_request = waiting.decision_request
    assert draw_request is not None
    draw_result = FiniteOptionSubmission(
        request_id=draw_request.request_id,
        selected_option_id="draw",
        result_id="phase11e-drift-draw",
    ).to_result(draw_request)
    draw_status = lifecycle.submit_decision(draw_result)
    draw_status = _decline_stratagem_window_if_pending(
        lifecycle,
        draw_status,
        result_id="phase11e-drift-draw-decline-stratagem",
    )
    automatic_follow_up = draw_status.decision_request
    assert automatic_follow_up is not None
    assert automatic_follow_up.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    discard_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = discard_lifecycle.state
    assert state is not None
    decisions = discard_lifecycle.decision_controller
    active_card = next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
    )
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=decisions,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_card.secondary_mission_id}",
        result_id="phase11e-drift-discard",
    ).to_result(discard_request)
    state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id=active_card.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )

    status = discard_lifecycle.submit_decision(discard_result)

    assert status.status_kind.value == "invalid"
    assert not decisions.records
    assert decisions.queue.peek_next().request_id == discard_request.request_id


def test_phase14j_tactical_secondary_score_requires_engine_achievement_context() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    card = _active_tactical_card(state)
    unrecorded_context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-unrecorded-achievement",
    )

    unsupported = request_tactical_secondary_score(
        state=state,
        decisions=lifecycle.decision_controller,
        achievement_context=unrecorded_context,
    )

    assert unsupported.status_kind.value == "unsupported"
    assert unsupported.decision_request is None
    assert lifecycle.decision_controller.queue.pending_requests == ()


def test_phase14j_tactical_secondary_score_decision_can_score_or_retain_card() -> None:
    retain_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    retain_state = retain_lifecycle.state
    assert retain_state is not None
    retain_card = _active_tactical_card(retain_state)
    retain_context = _record_tactical_secondary_achievement_context(
        state=retain_state,
        card=retain_card,
        achievement_id="phase14j-retain-achievement",
    )
    retain_waiting = request_tactical_secondary_score(
        state=retain_state,
        decisions=retain_lifecycle.decision_controller,
        achievement_context=retain_context,
    )
    retain_request = retain_waiting.decision_request
    assert retain_request is not None
    assert retain_request.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE
    assert retain_request.actor_id == "player-a"
    assert [option.option_id for option in retain_request.options] == [
        f"retain:{retain_card.secondary_mission_id}",
        f"score:{retain_card.secondary_mission_id}",
    ]
    retain_payload = cast(dict[str, JsonValue], retain_request.payload)
    assert retain_payload["achievement_id"] == retain_context.achievement_id
    assert retain_payload["victory_points"] == 5
    assert retain_payload["scoring_rule_id"] == f"{retain_card.secondary_mission_id}-tactical"
    assert retain_payload["scoring_rule_source_id"] == (
        f"gw-11e-chapter-approved-2026-27:secondary:{retain_card.secondary_mission_id}:"
        f"scoring-rule:{retain_card.secondary_mission_id}-tactical"
    )

    retain_lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=retain_request.request_id,
            selected_option_id=f"retain:{retain_card.secondary_mission_id}",
            result_id="phase14j-retain-tactical-score",
        ).to_result(retain_request)
    )

    retained = retain_state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=retain_card.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    retain_event = next(
        event
        for event in retain_lifecycle.decision_controller.event_log.records
        if event.event_type == "tactical_secondary_mission_score_declined"
    )
    assert retained is not None
    assert retained.status is SecondaryMissionCardStatus.ACTIVE
    assert (
        retain_state.tactical_secondary_achievement_context(retain_context.achievement_id) is None
    )
    assert retain_state.victory_point_total("player-a") == 0
    assert cast(dict[str, JsonValue], retain_event.payload)["retained"] is True

    score_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    score_state = score_lifecycle.state
    assert score_state is not None
    score_card = _active_tactical_card(score_state)
    score_context = _record_tactical_secondary_achievement_context(
        state=score_state,
        card=score_card,
        achievement_id="phase14j-score-achievement",
    )
    score_waiting = request_tactical_secondary_score(
        state=score_state,
        decisions=score_lifecycle.decision_controller,
        achievement_context=score_context,
    )
    score_request = score_waiting.decision_request
    assert score_request is not None

    score_lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=score_request.request_id,
            selected_option_id=f"score:{score_card.secondary_mission_id}",
            result_id="phase14j-score-tactical",
        ).to_result(score_request)
    )

    assert (
        score_state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=score_card.secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    scored_record = next(
        card
        for card in score_state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.secondary_mission_id == score_card.secondary_mission_id
        and card.mode is SecondaryMissionCardMode.TACTICAL
    )
    score_event = next(
        event
        for event in score_lifecycle.decision_controller.event_log.records
        if event.event_type == "tactical_secondary_mission_scored"
    )
    score_payload = cast(dict[str, JsonValue], score_event.payload)
    assert scored_record.status is SecondaryMissionCardStatus.SCORED
    assert score_state.tactical_secondary_achievement_context(score_context.achievement_id) is None
    assert score_state.victory_point_total("player-a") == 5
    assert score_payload["discarded_after_score"] is True
    event_context = cast(dict[str, JsonValue], score_payload["achievement_context"])
    assert event_context["achievement_id"] == score_context.achievement_id
    transaction = cast(dict[str, JsonValue], score_payload["victory_point_transaction"])
    assert transaction["source_kind"] == "tactical_secondary"
    assert transaction["source_id"] == score_card.secondary_mission_id
    transaction_metadata = cast(dict[str, JsonValue], transaction["metadata"])
    assert transaction_metadata["scoring_rule_source_id"] == score_context.scoring_rule_source_id


def test_phase14j_tactical_secondary_score_rejects_drifted_lifecycle_option() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    card = _active_tactical_card(state)
    context = _record_tactical_secondary_achievement_context(
        state=state,
        card=card,
        achievement_id="phase14j-card-drift-achievement",
    )
    waiting = request_tactical_secondary_score(
        state=state,
        decisions=lifecycle.decision_controller,
        achievement_context=context,
    )
    request = waiting.decision_request
    assert request is not None
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"score:{card.secondary_mission_id}",
        result_id="phase14j-score-drift",
    ).to_result(request)
    state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id=card.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )

    status = lifecycle.submit_decision(result)

    assert status.status_kind.value == "invalid"
    assert not lifecycle.decision_controller.records
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_phase14j_tactical_secondary_score_rejects_stale_achievement_context() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    card = _active_tactical_card(state)
    context = _record_tactical_secondary_achievement_context(
        state=state,
        card=card,
        achievement_id="phase14j-missing-achievement",
    )
    waiting = request_tactical_secondary_score(
        state=state,
        decisions=lifecycle.decision_controller,
        achievement_context=context,
    )
    request = waiting.decision_request
    assert request is not None
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"score:{card.secondary_mission_id}",
        result_id="phase14j-score-missing-achievement",
    ).to_result(request)
    state.consume_tactical_secondary_achievement_context(context.achievement_id)

    status = lifecycle.submit_decision(result)

    assert status.status_kind.value == "invalid"
    invalid_payload = cast(dict[str, JsonValue], status.payload)
    assert invalid_payload["invalid_reason"] == "achievement_context_missing"
    assert not lifecycle.decision_controller.records
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_phase14j_tactical_secondary_score_rejects_round_phase_and_rule_drift() -> None:
    round_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    round_state = round_lifecycle.state
    assert round_state is not None
    round_card = _active_tactical_card(round_state)
    round_context = _record_tactical_secondary_achievement_context(
        state=round_state,
        card=round_card,
        achievement_id="phase14j-round-drift-achievement",
    )
    round_waiting = request_tactical_secondary_score(
        state=round_state,
        decisions=round_lifecycle.decision_controller,
        achievement_context=round_context,
    )
    round_request = round_waiting.decision_request
    assert round_request is not None
    round_result = FiniteOptionSubmission(
        request_id=round_request.request_id,
        selected_option_id=f"score:{round_card.secondary_mission_id}",
        result_id="phase14j-round-drift",
    ).to_result(round_request)
    round_state.battle_round += 1

    round_status = round_lifecycle.submit_decision(round_result)

    assert round_status.status_kind.value == "invalid"
    round_payload = cast(dict[str, JsonValue], round_status.payload)
    assert round_payload["invalid_reason"] == "battle_round_drift"

    phase_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    phase_state = phase_lifecycle.state
    assert phase_state is not None
    phase_card = _active_tactical_card(phase_state)
    phase_context = _record_tactical_secondary_achievement_context(
        state=phase_state,
        card=phase_card,
        achievement_id="phase14j-phase-drift-achievement",
    )
    phase_waiting = request_tactical_secondary_score(
        state=phase_state,
        decisions=phase_lifecycle.decision_controller,
        achievement_context=phase_context,
    )
    phase_request = phase_waiting.decision_request
    assert phase_request is not None
    phase_result = FiniteOptionSubmission(
        request_id=phase_request.request_id,
        selected_option_id=f"score:{phase_card.secondary_mission_id}",
        result_id="phase14j-phase-drift",
    ).to_result(phase_request)
    phase_state.battle_phase_index = phase_state.battle_phase_sequence.index(BattlePhase.MOVEMENT)

    phase_status = phase_lifecycle.submit_decision(phase_result)

    assert phase_status.status_kind.value == "invalid"
    phase_payload = cast(dict[str, JsonValue], phase_status.payload)
    assert phase_payload["invalid_reason"] == "phase_drift"

    rule_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    rule_state = rule_lifecycle.state
    assert rule_state is not None
    rule_card = _active_tactical_card(rule_state)
    rule_context = _record_tactical_secondary_achievement_context(
        state=rule_state,
        card=rule_card,
        achievement_id="phase14j-rule-drift-achievement",
    )
    rule_waiting = request_tactical_secondary_score(
        state=rule_state,
        decisions=rule_lifecycle.decision_controller,
        achievement_context=rule_context,
    )
    rule_request = rule_waiting.decision_request
    assert rule_request is not None
    rule_result = FiniteOptionSubmission(
        request_id=rule_request.request_id,
        selected_option_id=f"score:{rule_card.secondary_mission_id}",
        result_id="phase14j-rule-drift",
    ).to_result(rule_request)
    rule_state.tactical_secondary_achievement_contexts[0] = replace(
        rule_context,
        victory_points=rule_context.victory_points + 1,
    )

    rule_status = rule_lifecycle.submit_decision(rule_result)

    assert rule_status.status_kind.value == "invalid"
    rule_payload = cast(dict[str, JsonValue], rule_status.payload)
    assert rule_payload["invalid_reason"] == "victory_points_drift"


def test_phase14j_tactical_secondary_achievement_context_is_source_validated() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-invalid-achievement",
    )

    with pytest.raises(GameLifecycleError, match="VP drift"):
        state.record_tactical_secondary_achievement_context(
            replace(context, victory_points=context.victory_points + 1)
        )


def test_phase14j_tactical_secondary_achievement_context_round_trips_and_is_redacted() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _record_tactical_secondary_achievement_context(
        state=state,
        card=card,
        achievement_id="phase14j-round-trip-achievement",
    )

    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_tactical_secondary_achievement_context(context)
    with pytest.raises(GameLifecycleError, match="already exists for this card"):
        state.record_tactical_secondary_achievement_context(
            replace(context, achievement_id="phase14j-duplicate-card-achievement")
        )

    payload = state.to_payload()
    assert payload["tactical_secondary_achievement_contexts"] == [context.to_payload()]
    restored = GameState.from_payload(payload)
    assert restored.tactical_secondary_achievement_context(context.achievement_id) == context
    public_payload = restored.to_public_payload(viewer_player_id="player-a")
    assert public_payload["tactical_secondary_achievement_contexts"] == []


def test_phase14j_tactical_secondary_achievement_context_state_validation_rejects_drift() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-state-validation-achievement",
    )

    with pytest.raises(GameLifecycleError, match="game_id drift"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                replace(context, game_id="phase14j-other-game")
            ],
        )
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                replace(context, player_id="phase14j-missing-player")
            ],
        )
    with pytest.raises(GameLifecycleError, match="active_player_id is not in this game"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                replace(context, active_player_id="phase14j-missing-active-player")
            ],
        )
    with pytest.raises(GameLifecycleError, match="must not duplicate IDs"):
        replace(state, tactical_secondary_achievement_contexts=[context, context])
    with pytest.raises(GameLifecycleError, match="must not duplicate cards"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                context,
                replace(context, achievement_id="phase14j-state-duplicate-card"),
            ],
        )
    with pytest.raises(GameLifecycleError, match="does not exist"):
        state.consume_tactical_secondary_achievement_context("phase14j-missing-achievement")


def test_phase14j_tactical_secondary_achievement_context_rejects_non_tactical_mode() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-invalid-mode-achievement",
    )

    with pytest.raises(GameLifecycleError, match="Tactical mode"):
        replace(context, mode=SecondaryMissionCardMode.FIXED)


def test_tactical_secondary_discard_awards_chapter_approved_cp_in_own_turn() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    active_card = next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
    )
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    result_id = "phase11e-own-turn-discard"
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_card.secondary_mission_id}",
        result_id=result_id,
    ).to_result(discard_request)

    lifecycle.submit_decision(discard_result)

    expected_source_id = (
        f"chapter-approved-2026-27:tactical-secondary-discard:{result_id}:cp-reward"
    )
    ledger = state.command_point_ledger_for_player("player-a")
    reward_transactions = [
        transaction
        for transaction in ledger.transactions
        if transaction.source_id == expected_source_id
    ]
    assert state.command_point_total("player-a") == 1
    assert len(reward_transactions) == 1
    assert reward_transactions[0].amount == 1
    assert reward_transactions[0].source_kind.value == "other"
    discard_payload = cast(
        dict[str, JsonValue],
        next(
            record.payload
            for record in lifecycle.decision_controller.event_log.records
            if record.event_type == "tactical_secondary_mission_discarded"
        ),
    )
    command_point_gain = cast(dict[str, JsonValue], discard_payload["command_point_gain"])
    assert discard_payload["active_player_id"] == "player-a"
    assert discard_payload["command_point_reward_eligible"] is True
    assert discard_payload["command_point_reward_reason"] == "discarding_players_turn"
    assert command_point_gain["source_id"] == expected_source_id
    assert command_point_gain["status"] == "applied"


def test_tactical_secondary_discard_in_opponents_turn_has_no_chapter_approved_cp_reward() -> None:
    lifecycle = _battle_lifecycle(player_b_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-b",
            battle_round=state.battle_round,
            request_id="phase11e-opponent-turn-tactical-draw-request",
            result_id="phase11e-opponent-turn-tactical-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    active_cards = state.draw_tactical_secondary_cards(
        player_id="player-b",
        source_result_id="phase11e-opponent-turn-tactical-draw",
    )
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-b",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    assert discard_request.actor_id == "player-b"
    request_payload = cast(dict[str, JsonValue], discard_request.payload)
    assert request_payload["active_player_id"] == "player-a"
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_cards[0].secondary_mission_id}",
        result_id="phase11e-opponent-turn-discard",
    ).to_result(discard_request)

    lifecycle.submit_decision(discard_result)

    assert state.command_point_total("player-b") == 0
    assert all(
        not transaction.source_id.startswith("chapter-approved-2026-27:tactical-secondary-discard:")
        for transaction in state.command_point_ledger_for_player("player-b").transactions
    )
    discard_payload = cast(
        dict[str, JsonValue],
        next(
            record.payload
            for record in lifecycle.decision_controller.event_log.records
            if record.event_type == "tactical_secondary_mission_discarded"
        ),
    )
    assert discard_payload["player_id"] == "player-b"
    assert discard_payload["active_player_id"] == "player-a"
    assert discard_payload["command_point_reward_eligible"] is False
    assert discard_payload["command_point_reward_reason"] == "not_discarding_players_turn"
    assert discard_payload["command_point_gain"] is None


def test_mission_action_can_complete_interrupt_and_score() -> None:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    completed_action = _start_mission_action_via_lifecycle(
        lifecycle=lifecycle,
        target_suffix="center",
        result_id="phase11e-start-cleanse-center",
    )
    interrupted_action = _mission_action_state(
        action_id="mission-action:phase11e-start-cleanse-northwest",
        target_id="primary-immovable-object-layout-3-upper-central",
    )
    state.record_mission_action_state(interrupted_action)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    completed = state.complete_mission_action(
        action_id=completed_action.action_id,
        completion_phase=BattlePhase.FIGHT,
    )
    interrupted = state.interrupt_mission_action(
        action_id=interrupted_action.action_id,
        reason="unit_moved",
    )

    assert completed.status is MissionActionStatus.COMPLETED
    assert completed.score_transaction_id is None
    assert _objective_marker_matches_suffix(completed.target_id, "center")
    assert interrupted.status is MissionActionStatus.INTERRUPTED
    assert _objective_marker_matches_suffix(interrupted.target_id, "northwest")
    assert interrupted.interrupted_reason == "unit_moved"
    assert state.victory_point_total("player-a") == 0
    assert [
        cleanse.objective_marker_id for cleanse in state.secondary_objective_cleanse_states
    ] == [completed.target_id]
    assert lifecycle.decision_controller.records[-1].request.decision_type == (
        START_MISSION_ACTION_DECISION_TYPE
    )
    opponent_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    action_events = [
        event
        for event in opponent_events["events"]
        if event["event_type"] == "mission_action_started"
    ]
    assert len(action_events) == 1
    assert cast(dict[str, JsonValue], action_events[0]["payload"])["mission_action_id"] == (
        "cleanse-objective"
    )
    round_tripped = GameLifecycle.from_payload(lifecycle.to_payload())
    round_tripped_state = round_tripped.state
    assert round_tripped_state is not None
    assert (
        round_tripped_state.mission_action_state_by_id(completed.action_id).target_id
        == completed.target_id
    )


def test_plunder_mission_action_completes_immediately_and_records_secondary_evidence() -> None:
    lifecycle = _battle_lifecycle(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    terrain_feature = _first_non_player_deployment_terrain_feature(state, player_id="player-a")
    min_x, min_y, max_x, max_y = terrain_feature.bounds()
    _place_unit_near_point(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        x_inches=(min_x + max_x) / 2.0,
        y_inches=(min_y + max_y) / 2.0,
    )

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="plunder-terrain",
    )
    request = waiting.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["target_id"] == terrain_feature.feature_id
    )
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option.option_id,
        result_id="phase16-start-plunder",
    ).to_result(request)

    lifecycle.submit_decision(result)

    action = state.mission_action_state_by_id("mission-action:phase16-start-plunder")
    assert action.status is MissionActionStatus.COMPLETED
    assert action.score_transaction_id is None
    assert state.victory_point_total("player-a") == 0
    assert [plunder.terrain_feature_id for plunder in state.secondary_terrain_plunder_states] == [
        terrain_feature.feature_id
    ]
    assert (
        request_mission_action_start(
            state=state,
            decisions=lifecycle.decision_controller,
            player_id="player-a",
            mission_action_id="plunder-terrain",
        ).status_kind
        is LifecycleStatusKind.UNSUPPORTED
    )
    assert any(
        record.event_type == "secondary_terrain_area_plundered"
        for record in lifecycle.decision_controller.event_log.records
    )


def test_public_payload_redacts_hidden_secondary_scoring_evidence() -> None:
    state = _battle_state_from_config(_config_with_player_b_vehicles(("vehicle-unit-3",)))
    state.secondary_mission_choices = [
        choice for choice in state.secondary_mission_choices if choice.player_id == "player-a"
    ]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _record_secondary_vehicle_destruction(state, "army-beta:vehicle-unit-3")
    state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id="primary-immovable-object-layout-3-center-central",
        action_id="phase16-public-cleanse",
        phase=BattlePhase.FIGHT,
        source_id="cleanse",
    )
    terrain_feature = _first_non_player_deployment_terrain_feature(state, player_id="player-a")
    state.record_secondary_terrain_plunder(
        player_id="player-a",
        terrain_feature_id=terrain_feature.feature_id,
        action_id="phase16-public-plunder",
        phase=BattlePhase.SHOOTING,
        source_id="plunder",
    )

    player_payload = state.to_public_payload(viewer_player_id="player-a")
    opponent_payload = state.to_public_payload(viewer_player_id="player-b")

    assert len(cast(list[JsonValue], player_payload["secondary_unit_destruction_states"])) == 1
    assert len(cast(list[JsonValue], player_payload["secondary_objective_cleanse_states"])) == 1
    assert len(cast(list[JsonValue], player_payload["secondary_terrain_plunder_states"])) == 1
    assert opponent_payload["secondary_unit_destruction_states"] == []
    assert opponent_payload["secondary_objective_cleanse_states"] == []
    assert opponent_payload["secondary_terrain_plunder_states"] == []


def test_mission_action_cancellation_maps_displacements_and_battlefield_departure() -> None:
    action = replace(
        _mission_action_state(action_id="phase14d-cancel-action"),
        interruption_conditions=("unit_moved", "unit_left_battlefield"),
    )

    interrupted_by_move = interrupt_mission_action_for_displacement(
        action,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    pile_in_result = interrupt_mission_action_for_displacement(
        action,
        displacement_kind=ModelDisplacementKind.PILE_IN,
    )
    consolidate_result = interrupt_mission_action_for_displacement(
        action,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
    )
    interrupted_by_departure = interrupt_mission_action_for_battlefield_departure(action)

    assert (
        mission_action_interruption_reason_for_displacement(ModelDisplacementKind.ADVANCE)
        == "unit_moved"
    )
    assert (
        mission_action_interruption_reason_for_displacement(ModelDisplacementKind.PILE_IN) is None
    )
    assert interrupted_by_move is not None
    assert interrupted_by_move.status is MissionActionStatus.INTERRUPTED
    assert interrupted_by_move.interrupted_reason == "unit_moved"
    assert pile_in_result is None
    assert consolidate_result is None
    assert interrupted_by_departure.status is MissionActionStatus.INTERRUPTED
    assert interrupted_by_departure.interrupted_reason == "unit_left_battlefield"

    with pytest.raises(GameLifecycleError, match="interruption reason is not configured"):
        interrupt_mission_action_for_battlefield_departure(
            _mission_action_state(action_id="phase14d-unconfigured-departure")
        )


def test_started_mission_action_is_interrupted_by_runtime_normal_move() -> None:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    action = replace(
        _mission_action_state(action_id="phase14d-runtime-cancel-action"),
        interruption_conditions=("unit_moved", "unit_left_battlefield"),
    )
    state.record_mission_action_state(action)
    movement_status = lifecycle.advance_until_decision_or_terminal()
    movement_request = movement_status.decision_request
    assert movement_request is not None
    assert movement_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14d-runtime-cancel-select-unit",
            request=movement_request,
            selected_option_id=action.unit_instance_id,
        )
    )
    action_request = action_status.decision_request
    assert action_request is not None
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase14d-runtime-cancel-normal-move",
        proposal_result_id="phase14d-runtime-cancel-normal-move-proposal",
        unit_instance_id=action.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=action.unit_instance_id,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_pending(
        lifecycle,
        status,
        result_id="phase14d-runtime-cancel-decline-stratagem",
    )
    interrupted = state.mission_action_state_by_id(action.action_id)
    interruption_event = next(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "mission_action_interrupted"
    )
    event_payload = cast(dict[str, JsonValue], interruption_event.payload)

    assert interrupted.status is MissionActionStatus.INTERRUPTED
    assert interrupted.interrupted_reason == "unit_moved"
    assert event_payload["interrupted_reason"] == "unit_moved"
    assert event_payload["unit_instance_id"] == action.unit_instance_id


def test_mission_action_terminal_state_validation_is_fail_fast() -> None:
    action = _mission_action_state(action_id="phase14d-terminal-validation")

    with pytest.raises(GameLifecycleError, match="Started mission Action must not have terminal"):
        replace(action, score_transaction_id="victory-point:player-a:round-01:000001")
    with pytest.raises(
        GameLifecycleError, match="Completed scoring mission Action requires transaction"
    ):
        replace(
            action,
            status=MissionActionStatus.COMPLETED,
            completed_battle_round=1,
            completed_phase=BattlePhase.FIGHT.value,
        )
    with pytest.raises(GameLifecycleError, match="Completed mission Action cannot be interrupted"):
        replace(
            action,
            status=MissionActionStatus.COMPLETED,
            completed_battle_round=1,
            completed_phase=BattlePhase.FIGHT.value,
            interrupted_reason="unit_moved",
            score_transaction_id="victory-point:player-a:round-01:000002",
        )
    with pytest.raises(GameLifecycleError, match="Interrupted mission Action requires a reason"):
        replace(action, status=MissionActionStatus.INTERRUPTED)
    with pytest.raises(
        GameLifecycleError,
        match="Interrupted mission Action cannot have completion fields",
    ):
        replace(
            action,
            status=MissionActionStatus.INTERRUPTED,
            completed_battle_round=1,
            interrupted_reason="unit_moved",
        )


def test_mission_action_interruption_helpers_reject_malformed_state() -> None:
    not_an_action = cast(MissionActionState, object())

    with pytest.raises(GameLifecycleError, match="action_state must be a MissionActionState"):
        interrupt_mission_action_for_displacement(
            not_an_action,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        )
    with pytest.raises(GameLifecycleError, match="action_state must be a MissionActionState"):
        interrupt_mission_action_for_battlefield_departure(not_an_action)


def test_mission_action_start_rejects_drifted_lifecycle_option() -> None:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
    )
    request = waiting.decision_request
    assert request is not None
    option = request.options[0]
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option.option_id,
        result_id="phase11e-drift-start-action",
    ).to_result(request)
    unit_id = cast(dict[str, JsonValue], option.payload)["unit_instance_id"]
    assert isinstance(unit_id, str)
    state.battlefield_state = state.battlefield_state.without_unit_placement(unit_id)

    status = lifecycle.submit_decision(result)

    assert status.status_kind.value == "invalid"
    assert not lifecycle.decision_controller.records
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_cleanse_mission_action_filters_ineligible_vehicle_units() -> None:
    lifecycle = _battle_lifecycle_with_player_a_vehicle()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:vehicle-unit-2",
        target_suffix="center",
    )

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
    )
    request = waiting.decision_request
    assert request is not None

    option_payloads = [cast(dict[str, JsonValue], option.payload) for option in request.options]
    assert option_payloads
    assert {
        cast(str, option_payload["unit_instance_id"]) for option_payload in option_payloads
    } == {"army-alpha:intercessor-unit-1"}
    assert all(
        "army-alpha:vehicle-unit-2"
        not in cast(list[JsonValue], option_payload["eligible_unit_instance_ids"])
        for option_payload in option_payloads
    )


def test_mission_action_start_excludes_units_that_shot_this_shooting_phase() -> None:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit_id = "army-alpha:intercessor-unit-1"
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_id,
        target_suffix="center",
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(unit_id,),
        shot_unit_ids=(unit_id,),
    )

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
    )

    assert waiting.status_kind.value == "unsupported"
    assert waiting.decision_request is None
    waiting_payload = cast(dict[str, JsonValue], waiting.payload)
    assert waiting_payload["mission_action_id"] == "cleanse-objective"


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
    mission_pack = chapter_approved_2026_27_mission_pack()
    primary = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "take-and-hold"
    )
    policy = mission_scoring_policy_from_setup(_mission_setup_for_primary("take-and-hold"))
    primary_rule = policy.primary_scoring_rules[0]
    award = policy.mission_action_award(
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.COMMAND.value,
        action_id="establish-locus:center:player-a",
        source_id="establish-locus",
    )

    ledger, transaction = VictoryPointLedger.initial(player_id="player-a").award(award)
    fixed_card = SecondaryMissionCardState.active_fixed(
        player_id="player-a",
        secondary_mission_id="assassination",
    )
    scored_card = fixed_card.score(transaction_id=transaction.transaction_id)

    assert MissionScoringPolicy.from_payload(policy.to_payload()) == policy
    assert policy.mission_pack_id == mission_pack.mission_pack_id
    assert policy.game_length_battle_rounds == mission_pack.scoring.game_length_battle_rounds
    assert policy.primary_max_vp_per_turn == primary.max_vp_per_turn
    assert policy.primary_vp_per_controlled_objective == primary.vp_per_controlled_objective
    assert policy.primary_scoring_rule_id == "take-and-hold-control"
    assert policy.primary_scoring_rule_condition == (
        "each_controlled_objective_from_battle_round_two"
    )
    assert PrimaryMissionScoringRule.from_payload(primary_rule.to_payload()) == primary_rule
    assert policy.primary_vp_cap == mission_pack.scoring.primary_vp_cap
    assert policy.total_vp_cap == mission_pack.scoring.total_vp_cap
    assert award.to_payload()["source_kind"] == "mission_action"
    assert VictoryPointTransaction.from_payload(transaction.to_payload()) == transaction
    assert ledger.points_from_source_kind(VictoryPointSourceKind.MISSION_ACTION) == 4
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
    with pytest.raises(GameLifecycleError, match="source_kind must be primary"):
        replace(primary_rule, source_kind=VictoryPointSourceKind.MISSION_ACTION)
    with pytest.raises(GameLifecycleError, match="primary_scoring_rules must contain"):
        replace(
            policy,
            primary_scoring_rules=cast(
                tuple[PrimaryMissionScoringRule, ...],
                ("not-a-rule",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="primary_scoring_rules must not contain"):
        replace(policy, primary_scoring_rules=(primary_rule, primary_rule))
    with pytest.raises(GameLifecycleError, match="primary_scoring_rules must not be empty"):
        replace(policy, primary_scoring_rules=())
    scoring_state = _battle_state()
    assert scoring_state.mission_setup is not None
    assert scoring_state.battlefield_state is not None
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            scoring_state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=BattlePhase.FIGHT,
        )
    )
    with pytest.raises(GameLifecycleError, match="ObjectiveControlRecord"):
        policy.primary_awards_from_objective_control(
            record=cast(ObjectiveControlRecord, object()),
            mission_setup=scoring_state.mission_setup,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="MissionSetup"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=cast(MissionSetup, object()),
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported primary scoring rule timing"):
        replace(
            policy,
            primary_scoring_rules=(replace(primary_rule, timing="unsupported-timing"),),
        ).primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    turn_start = scoring_state.primary_objective_turn_start_states[0]
    with pytest.raises(GameLifecycleError, match="turn-start states must be a tuple"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=cast(tuple[PrimaryObjectiveTurnStartState, ...], []),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="turn-start states must contain"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=cast(
                tuple[PrimaryObjectiveTurnStartState, ...],
                ("not-a-turn-start-state",),
            ),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="turn-start states must not duplicate"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=(turn_start, turn_start),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="terrain trap states must be a tuple"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=cast(tuple[PrimaryTerrainTrapState, ...], []),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="terrain trap states must contain"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=cast(tuple[PrimaryTerrainTrapState, ...], ("not-a-trap",)),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="unit destruction states must be a tuple"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=cast(tuple[PrimaryUnitDestructionState, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="unit destruction states must contain"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=cast(
                tuple[PrimaryUnitDestructionState, ...],
                ("not-a-destruction",),
            ),
        )
    with pytest.raises(GameLifecycleError):
        mission_scoring_policy_from_setup(
            replace(_mission_setup(), primary_mission_id="the-ritual")
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
            target_id="primary-immovable-object-layout-3-center-central",
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
            target_id="primary-immovable-object-layout-3-center-central",
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
            target_id="primary-immovable-object-layout-3-center-central",
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
    with pytest.raises(GameLifecycleError, match="eligible_unit_instance_ids must be a tuple"):
        MissionActionState.start(
            action_id="cleanse:eligible-not-tuple:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=cast(tuple[str, ...], []),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="eligible_unit_instance_ids must not contain"):
        MissionActionState.start(
            action_id="cleanse:duplicate-eligible:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=(
                "army-alpha:intercessor-unit-1",
                "army-alpha:intercessor-unit-1",
            ),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="eligible_unit_instance_ids must contain"):
        MissionActionState.start(
            action_id="cleanse:no-eligible:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=(),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id must be a string"):
        MissionActionState.start(
            action_id="cleanse:non-string-unit:player-a",
            player_id="player-a",
            unit_instance_id=cast(str, 1),
            target_id="primary-immovable-object-layout-3-center-central",
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
    with pytest.raises(GameLifecycleError, match="unit_instance_id must not be empty"):
        MissionActionState.start(
            action_id="cleanse:empty-unit:player-a",
            player_id="player-a",
            unit_instance_id=" ",
            target_id="primary-immovable-object-layout-3-center-central",
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
    with pytest.raises(GameLifecycleError, match="battle_round_started must be an integer"):
        MissionActionState.start(
            action_id="cleanse:round-not-int:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=cast(int, "1"),
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="battle_round_started must be at least 1"):
        MissionActionState.start(
            action_id="cleanse:round-zero:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=0,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="victory_points must be an integer"):
        MissionActionState.start(
            action_id="cleanse:vp-not-int:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=cast(int, "5"),
        )
    with pytest.raises(GameLifecycleError, match="victory_points must not be negative"):
        MissionActionState.start(
            action_id="cleanse:vp-negative:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=-1,
        )
    with pytest.raises(GameLifecycleError):
        MissionActionState(
            action_id="cleanse:interrupted-with-score:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="primary-immovable-object-layout-3-center-central",
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
    state = _battle_state_for_primary("take-and-hold")
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


def _first_non_player_deployment_terrain_feature(
    state: GameState,
    *,
    player_id: str,
) -> TerrainFeatureDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    zones = tuple(
        zone for zone in state.mission_setup.deployment_zones if zone.player_id == player_id
    )
    for feature in state.mission_setup.terrain_features:
        min_x, min_y, max_x, max_y = feature.bounds()
        corners = (
            (min_x, min_y),
            (min_x, max_y),
            (max_x, min_y),
            (max_x, max_y),
        )
        if not all(any(zone.contains_point(x, y) for zone in zones) for x, y in corners):
            return feature
    raise AssertionError("test mission setup requires terrain outside player deployment zone")


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


def test_phase14c_battle_shocked_units_cannot_start_or_complete_mission_actions() -> None:
    unit_id = "army-alpha:intercessor-unit-1"
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

    with pytest.raises(GameLifecycleError, match="cannot start actions"):
        MissionActionState.start(
            action_id="cleanse:center:player-a",
            player_id="player-a",
            unit_instance_id=unit_id,
            target_id="primary-immovable-object-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=(unit_id,),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            battle_shocked_unit_ids=(unit_id,),
        )
    with pytest.raises(GameLifecycleError, match="cannot complete actions"):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=award,
            transaction_id="victory-point:player-a:round-01:000001",
            battle_shocked_unit_ids=(unit_id,),
        )


def _mission_action_state(
    *,
    action_id: str,
    target_id: str = "primary-immovable-object-layout-3-center-central",
) -> MissionActionState:
    return MissionActionState.start(
        action_id=action_id,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_id=target_id,
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
        if _objective_marker_matches_suffix(marker.objective_marker_id, "center"):
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


def _transaction_metadata(transaction: VictoryPointTransaction) -> dict[str, JsonValue]:
    metadata = transaction.metadata
    assert isinstance(metadata, dict)
    return metadata


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


def _start_mission_action_via_lifecycle(
    *,
    lifecycle: GameLifecycle,
    target_suffix: str,
    result_id: str,
    unit_instance_id: str = "army-alpha:intercessor-unit-1",
) -> MissionActionState:
    state = lifecycle.state
    assert state is not None
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_instance_id,
        target_suffix=target_suffix,
    )
    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
    )
    request = waiting.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if _objective_marker_matches_suffix(
            str(cast(dict[str, JsonValue], option.payload)["target_id"]),
            target_suffix,
        )
    )
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option.option_id,
        result_id=result_id,
    ).to_result(request)
    lifecycle.submit_decision(result)
    action_id = f"mission-action:{result_id}"
    return state.mission_action_state_by_id(action_id)


def _place_unit_near_objective(
    state: GameState,
    *,
    unit_instance_id: str,
    target_suffix: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    marker = next(
        marker
        for marker in state.mission_setup.objective_markers
        if _objective_marker_matches_suffix(marker.objective_marker_id, target_suffix)
    )
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    offsets = tuple(
        (2.0 + float(index), 0.0) for index in range(len(unit_placement.model_placements))
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(unit_placement, marker, offsets=offsets)
    )


def _place_unit_near_point(
    state: GameState,
    *,
    unit_instance_id: str,
    x_inches: float,
    y_inches: float,
) -> None:
    marker = replace(
        _center_marker_definition(state),
        x_inches=x_inches,
        y_inches=y_inches,
    )
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    offsets = tuple(
        (float(index) * 0.75, 0.0) for index in range(len(unit_placement.model_placements))
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(unit_placement, marker, offsets=offsets)
    )


def _decline_stratagem_window_if_pending(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
) -> LifecycleStatus:
    request = status.decision_request
    if request is None or request.decision_type != STRATAGEM_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _battle_lifecycle(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
) -> GameLifecycle:
    lifecycle = GameLifecycle()
    lifecycle.start(_config())
    lifecycle.state = _battle_state(
        player_a_secondary=player_a_secondary,
        player_b_secondary=player_b_secondary,
    )
    return lifecycle


def _battle_lifecycle_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> GameLifecycle:
    config = _config_for_primary(
        primary_mission_id,
        objective_terrain_feature_id=objective_terrain_feature_id,
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(config)
    return lifecycle


def _battle_lifecycle_with_active_tactical_cards() -> GameLifecycle:
    lifecycle = _battle_lifecycle(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id=SEEDED_TACTICAL_DRAW_REQUEST_ID,
            result_id=SEEDED_TACTICAL_DRAW_RESULT_ID,
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id=SEEDED_TACTICAL_DRAW_RESULT_ID,
    )
    return lifecycle


def _active_tactical_card(state: GameState) -> SecondaryMissionCardState:
    return next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
    )


def _record_tactical_secondary_achievement_context(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    achievement_id: str,
) -> TacticalSecondaryAchievementContext:
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id=achievement_id,
    )
    state.record_tactical_secondary_achievement_context(context)
    return context


def _tactical_secondary_achievement_context_for_card(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    achievement_id: str,
) -> TacticalSecondaryAchievementContext:
    assert state.mission_setup is not None
    assert state.active_player_id is not None
    phase = state.current_battle_phase
    assert phase is not None
    policy = mission_scoring_policy_from_setup(state.mission_setup)
    award = policy.secondary_award(
        player_id=card.player_id,
        battle_round=state.battle_round,
        phase=phase.value,
        secondary_mission_id=card.secondary_mission_id,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        hidden=False,
    )
    metadata = cast(dict[str, JsonValue], award.metadata)
    return TacticalSecondaryAchievementContext(
        achievement_id=achievement_id,
        game_id=state.game_id,
        player_id=card.player_id,
        active_player_id=state.active_player_id,
        secondary_mission_id=card.secondary_mission_id,
        battle_round=state.battle_round,
        phase=phase.value,
        card_battle_round=card.battle_round,
        victory_points=award.amount,
        scoring_rule_id=cast(str, metadata["scoring_rule_id"]),
        scoring_rule_condition=cast(str, metadata["scoring_rule_condition"]),
        scoring_rule_source_id=cast(str, metadata["scoring_rule_source_id"]),
        scoring_timing=award.scoring_timing,
        source_id=f"phase14j:{card.secondary_mission_id}:requirements-achieved",
        evidence={
            "evidence_kind": "source_backed_requirement_result",
            "requirements_met": True,
            "secondary_mission_id": card.secondary_mission_id,
        },
    )


def _battle_lifecycle_with_player_a_vehicle() -> GameLifecycle:
    config = _config_with_player_a_vehicle()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(config)
    return lifecycle


def _battle_state(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
) -> GameState:
    config = _config()
    return _battle_state_from_config(
        config,
        player_a_secondary=player_a_secondary,
        player_b_secondary=player_b_secondary,
    )


def _battle_state_for_primary(primary_mission_id: str) -> GameState:
    return _battle_state_from_config(_config_for_primary(primary_mission_id))


def _battle_state_from_config(
    config: GameConfig,
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
) -> GameState:
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


def _config_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> GameConfig:
    return replace(
        _config(),
        mission_setup=_mission_setup_for_primary(
            primary_mission_id,
            objective_terrain_feature_id=objective_terrain_feature_id,
        ),
    )


def _config_with_player_a_vehicle() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase11e-game",
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="intercessor-unit-1",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="vehicle-unit-2",
                        datasheet_id="core-vehicle-monster",
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    ),
                ),
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


def _config_with_player_b_vehicles(vehicle_unit_ids: tuple[str, ...]) -> GameConfig:
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
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                unit_selections=tuple(
                    _unit_muster_selection(
                        unit_selection_id=unit_id,
                        datasheet_id="core-vehicle-monster",
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    )
                    for unit_id in vehicle_unit_ids
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _record_secondary_vehicle_destruction(
    state: GameState,
    destroyed_unit_instance_id: str,
    *,
    started_turn_objective_marker_ids: tuple[str, ...] = (),
) -> None:
    unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == destroyed_unit_instance_id
    )
    state.record_secondary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id=destroyed_unit_instance_id,
        destroyed_model_instance_ids=tuple(model.model_instance_id for model in unit.own_models),
        started_turn_objective_marker_ids=started_turn_objective_marker_ids,
        source_id=f"phase16:{destroyed_unit_instance_id}:destroyed",
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-primary-immovable-object-layout-3",
        terrain_layout_id="primary-immovable-object-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _mission_setup_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> MissionSetup:
    mission_setup = replace(_mission_setup(), primary_mission_id=primary_mission_id)
    if objective_terrain_feature_id is None:
        return mission_setup
    feature = next(
        feature
        for feature in mission_setup.terrain_features
        if feature.feature_id == objective_terrain_feature_id
    )
    center_marker = _center_marker_definition_for_setup(mission_setup)
    objective_markers = tuple(
        replace(
            marker,
            x_inches=feature.footprint_center_x_inches,
            y_inches=feature.footprint_center_y_inches,
        )
        if marker.objective_marker_id == center_marker.objective_marker_id
        else marker
        for marker in mission_setup.objective_markers
    )
    return replace(mission_setup, objective_markers=objective_markers)


def _center_marker_definition_for_setup(
    mission_setup: MissionSetup,
) -> ObjectiveMarkerDefinition:
    for marker in mission_setup.objective_markers:
        if _objective_marker_matches_suffix(marker.objective_marker_id, "center"):
            return marker
    raise AssertionError("missing center objective marker")


def _objective_marker_matches_suffix(objective_marker_id: str, target_suffix: str) -> bool:
    return any(
        objective_marker_id.endswith(suffix)
        for suffix in _objective_marker_suffix_aliases(target_suffix)
    )


def _objective_marker_suffix_aliases(target_suffix: str) -> tuple[str, ...]:
    if target_suffix == "center":
        return ("-center", "-center-central")
    if target_suffix in {"northeast", "northwest"}:
        return (f"-{target_suffix}", "-upper-central")
    if target_suffix in {"southeast", "southwest"}:
        return (f"-{target_suffix}", "-lower-central")
    return (target_suffix,)


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
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
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=tuple(
            _unit_muster_selection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _unit_muster_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
