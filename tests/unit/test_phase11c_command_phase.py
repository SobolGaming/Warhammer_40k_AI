from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_shock import (
    BattleShockedUnitState,
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    StratagemTargetPermission,
    StratagemTargetPermissionStatus,
    battle_shock_test_reason_from_token,
    collect_battle_shock_test_requests,
    friendly_stratagem_target_permission,
    stratagem_target_permission_status_from_token,
)
from warhammer40k_core.engine.battlefield_state import UnitPlacement
from warhammer40k_core.engine.command_points import (
    CommandPhaseStep,
    CommandPointGainResult,
    CommandPointGainStatus,
    CommandPointLedger,
    CommandPointSourceKind,
    CommandPointTransaction,
    CommandStepState,
    command_phase_step_from_token,
    command_point_gain_status_from_token,
    command_point_source_kind_from_token,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    StartingStrengthRecord,
    starting_strength_records_for_units,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_command_step_grants_both_players_cp_once_before_tactical_draw() -> None:
    state = _battle_state(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_b_secondary=SecondaryMissionMode.FIXED,
    )
    decisions = DecisionController()
    handler = CommandPhaseHandler()

    waiting = handler.begin_phase(state=state, decisions=decisions)

    tactical_request = _decision_request(waiting)
    assert tactical_request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE
    assert state.command_point_total("player-a") == 1
    assert state.command_point_total("player-b") == 1
    assert state.command_step_state is not None
    assert state.command_step_state.command_points_granted
    assert state.command_step_state.scoring_hooks_resolved
    assert not state.command_step_state.battle_shock_step_resolved
    assert _event_index(decisions, "command_points_gained") < _event_index(
        decisions,
        "decision_requested",
    )

    _submit_direct_decision(
        decisions=decisions,
        handler=handler,
        state=state,
        request=tactical_request,
        option_id="draw",
        result_id="phase11c-result-draw",
    )
    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert state.command_point_total("player-a") == 1
    assert state.command_point_total("player-b") == 1
    command_state = state.command_step_state
    assert command_state is not None
    battle_shock_step_resolved: bool = command_state.battle_shock_step_resolved
    assert battle_shock_step_resolved

    state.command_step_state = None
    state.active_player_id = "player-b"
    handler.begin_phase(state=state, decisions=decisions)

    assert state.command_point_total("player-a") == 2
    assert state.command_point_total("player-b") == 2


def test_non_command_cp_gain_cap_is_enforced_per_battle_round() -> None:
    state = _battle_state()

    first = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="ability-gain-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    capped = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="second-ability-gain-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    exempt = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="explicit-cap-override",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )

    assert first.status is CommandPointGainStatus.APPLIED
    assert capped.status is CommandPointGainStatus.CAPPED
    assert capped.capped_reason == "non_command_cp_gain_cap_reached"
    assert exempt.status is CommandPointGainStatus.APPLIED
    assert state.command_point_total("player-a") == 2


def test_below_half_strength_unit_emits_battle_shock_test_request() -> None:
    state = _battle_state()
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)

    requests = _active_battle_shock_requests(state)

    assert len(requests) == 1
    request = requests[0]
    assert request.reason is BattleShockTestReason.BELOW_HALF_STRENGTH
    assert request.leadership_target == 6
    assert request.below_half_strength_context.current_model_count == 2
    assert request.below_half_strength_context.is_below_half_strength


def test_command_phase_resolves_non_reroll_battle_shock_dice_without_decision_pause() -> None:
    state = _battle_state()
    decisions = DecisionController()
    handler = CommandPhaseHandler()
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)

    completed = handler.begin_phase(state=state, decisions=decisions)

    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert decisions.queue.pending_requests == ()
    assert "decision_requested" not in event_types
    assert "dice_rolled" in event_types
    assert "battle_shock_test_requested" in event_types
    assert "battle_shock_test_resolved" in event_types
    assert event_types.index("battle_shock_test_requested") < event_types.index(
        "battle_shock_test_resolved"
    )


def test_below_starting_strength_forced_test_suppresses_duplicate_below_half() -> None:
    state = _battle_state()
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)

    suppressed = _active_battle_shock_requests(
        state,
        forced_below_starting_strength_unit_ids=(unit_id,),
    )
    duplicated = _active_battle_shock_requests(
        state,
        forced_below_starting_strength_unit_ids=(unit_id,),
        allow_duplicate_below_half_tests=True,
    )

    assert [request.reason for request in suppressed] == [
        BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED
    ]
    assert [request.reason for request in duplicated] == [
        BattleShockTestReason.BELOW_HALF_STRENGTH,
        BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
    ]


def test_failed_battle_shock_persists_and_sets_effective_oc_to_zero() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0), (-2.0, 0.0)),
        player_b_offsets=((0.0, 2.0),),
    )
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    request = _battle_shock_request_for_unit(state, unit)
    failed_roll = DiceRollManager("phase11c-rolls").roll_fixed(request.spec, [1, 1])
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c-failed-battle-shock",
        request=request,
        roll_state=failed_roll,
    )

    state.record_battle_shock_result(failed)
    result = _center_objective_result(
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=BattlePhase.COMMAND,
            )
        )
    )

    assert not failed.passed
    assert "army-alpha:intercessor-unit-1" in state.battle_shocked_unit_ids
    assert state.battle_shocked_unit_states[0].expires_at_battle_round == 2
    assert result.controlled_by_player_id == "player-b"
    assert {
        contribution.model_instance_id: contribution.effective_objective_control
        for contribution in result.contributors
        if contribution.player_id == "player-a"
    } == {
        "army-alpha:intercessor-unit-1:core-intercessor-like:001": 0,
        "army-alpha:intercessor-unit-1:core-intercessor-like:002": 0,
    }


def test_passed_battle_shock_does_not_mark_unit() -> None:
    state = _battle_state()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    request = _battle_shock_request_for_unit(state, unit)
    passed_roll = DiceRollManager("phase11c-rolls").roll_fixed(request.spec, [6, 6])
    passed = BattleShockResult.from_roll_state(
        result_id="phase11c-passed-battle-shock",
        request=request,
        roll_state=passed_roll,
    )

    state.record_battle_shock_result(passed)

    assert passed.passed
    assert state.battle_shocked_unit_ids == []
    assert state.battle_shocked_unit_states == []


def test_battle_shocked_friendly_unit_cannot_be_stratagem_target_by_default() -> None:
    blocked = friendly_stratagem_target_permission(
        player_id="player-a",
        target_player_id="player-a",
        target_unit_instance_id="army-alpha:intercessor-unit-1",
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
    )
    allowed = friendly_stratagem_target_permission(
        player_id="player-a",
        target_player_id="player-a",
        target_unit_instance_id="army-alpha:intercessor-unit-1",
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
        allow_battle_shocked=True,
    )

    assert not blocked.is_allowed
    assert blocked.denial_reason == "friendly_battle_shocked_unit"
    assert allowed.is_allowed


def test_record_battle_shock_result_rejects_unit_owner_drift() -> None:
    state = _battle_state()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    valid_request = _battle_shock_request_for_unit(state, unit)
    wrong_player_request = BattleShockTestRequest.for_unit(
        request_id="phase11c-battle-shock-owner-drift",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=valid_request.leadership_target,
        below_half_strength_context=replace(
            valid_request.below_half_strength_context,
            player_id="player-b",
        ),
    )
    result = BattleShockResult.from_roll_state(
        result_id="phase11c-battle-shock-owner-drift-result",
        request=wrong_player_request,
        roll_state=DiceRollManager("phase11c-owner-drift").roll_fixed(
            wrong_player_request.spec,
            [1, 1],
        ),
    )

    with pytest.raises(GameLifecycleError, match="unit owner drift"):
        state.record_battle_shock_result(result)

    assert state.battle_shocked_unit_ids == []
    assert state.battle_shocked_unit_states == []


def test_battle_shocked_payload_requires_state_for_every_shocked_unit_id() -> None:
    state = _battle_state()
    payload = state.to_payload()
    payload["battle_shocked_unit_ids"] = ["army-alpha:intercessor-unit-1"]

    with pytest.raises(GameLifecycleError, match="battle_shocked_unit_ids must match"):
        GameState.from_payload(payload)


def test_starting_strength_and_below_half_work_for_single_and_multi_model_units() -> None:
    multi = _battle_state()
    _remove_first_models(multi, unit_instance_id="army-alpha:intercessor-unit-1", count=3)
    multi_request = _active_battle_shock_requests(multi)[0]

    single = _battle_state(
        player_a_units=(
            _unit_selection(
                unit_selection_id="captain-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        )
    )
    _set_single_model_wounds(single, unit_instance_id="army-alpha:captain-unit", wounds=2)
    single_request = _active_battle_shock_requests(single)[0]

    assert multi_request.below_half_strength_context.starting_model_count == 5
    assert multi_request.below_half_strength_context.current_model_count == 2
    assert single_request.below_half_strength_context.starting_model_count == 1
    assert single_request.below_half_strength_context.single_model_starting_wounds == 5
    assert single_request.below_half_strength_context.single_model_wounds_remaining == 2
    assert single_request.below_half_strength_context.is_below_half_strength


def test_attached_unit_split_recovers_original_starting_strength_records() -> None:
    bodyguard_id = "army-alpha:intercessor-unit-1"
    leader_id = "army-alpha:captain-unit"
    attached_id = "attached-unit:army-alpha:captain-intercessors"
    state = _battle_state(
        player_a_units=(
            _default_unit_selection("intercessor-unit-1"),
            _unit_selection(
                unit_selection_id="captain-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        )
    )
    state.starting_strength_records = [
        record
        for record in state.starting_strength_records
        if record.unit_instance_id not in {bodyguard_id, leader_id}
    ]
    state.starting_strength_records.extend(
        (
            StartingStrengthRecord(
                player_id="player-a",
                unit_instance_id=attached_id,
                starting_model_count=6,
                single_model_starting_wounds=None,
                source_id="attached-unit-join:captain-intercessors",
            ),
            StartingStrengthRecord(
                player_id="player-a",
                unit_instance_id=bodyguard_id,
                starting_model_count=6,
                single_model_starting_wounds=None,
                source_id="attached-unit-join:captain-intercessors",
            ),
            StartingStrengthRecord(
                player_id="player-a",
                unit_instance_id=leader_id,
                starting_model_count=2,
                single_model_starting_wounds=None,
                source_id="attached-unit-join:captain-intercessors",
            ),
        )
    )

    recovered = state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id, bodyguard_id),
    )

    assert tuple(record.unit_instance_id for record in recovered) == (leader_id, bodyguard_id)
    assert state.starting_strength_record_for_unit(bodyguard_id).starting_model_count == 5
    leader_record = state.starting_strength_record_for_unit(leader_id)
    assert leader_record.starting_model_count == 1
    assert leader_record.single_model_starting_wounds == 5
    assert attached_id not in {
        record.unit_instance_id for record in state.starting_strength_records
    }
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_attached_unit_split_recovery_rejects_invalid_survivors() -> None:
    state = _battle_state()
    with pytest.raises(GameLifecycleError, match="must not include attached_unit_instance_id"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id="army-alpha:intercessor-unit-1",
            surviving_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        )
    payload_before_missing_attached = state.to_payload()
    with pytest.raises(GameLifecycleError, match="existing StartingStrengthRecord"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id="attached-unit:typo",
            surviving_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        )
    assert state.to_payload() == payload_before_missing_attached
    with pytest.raises(GameLifecycleError, match="survivor unit is unknown"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id="army-alpha:intercessor-unit-1",
            surviving_unit_instance_ids=("missing-unit",),
        )
    with pytest.raises(GameLifecycleError, match="survivor player_id drift"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id="army-alpha:intercessor-unit-1",
            surviving_unit_instance_ids=("army-beta:intercessor-unit-3",),
        )


def test_phase11c_payloads_round_trip_without_object_reprs() -> None:
    state = _battle_state()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    request = _battle_shock_request_for_unit(state, unit)
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c-round-trip-failed",
        request=request,
        roll_state=DiceRollManager("phase11c-rolls").roll_fixed(request.spec, [1, 1]),
    )
    state.record_battle_shock_result(failed)
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="round-trip-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )

    payload = cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert GameState.from_payload(payload).to_payload() == state.to_payload()


def test_command_point_and_step_state_validation_is_fail_fast() -> None:
    command_state = CommandStepState.start(
        battle_round=1,
        active_player_id="player-a",
    ).with_command_points_granted()
    assert CommandStepState.from_payload(command_state.to_payload()) == command_state

    ledger, applied = CommandPointLedger.initial(player_id="player-a").gain(
        battle_round=1,
        amount=1,
        source_id="phase11c-test-source",
        source_kind=CommandPointSourceKind.OTHER,
    )
    transaction = applied.transaction
    assert transaction is not None
    assert CommandPointLedger.from_payload(ledger.to_payload()) == ledger
    assert CommandPointGainResult.from_payload(applied.to_payload()) == applied
    assert CommandPointTransaction.from_payload(transaction.to_payload()) == transaction

    with pytest.raises(GameLifecycleError, match="Battle-shock before Command step CP gain"):
        CommandStepState(
            battle_round=1,
            active_player_id="player-a",
            current_step=CommandPhaseStep.BATTLE_SHOCK,
        )
    with pytest.raises(GameLifecycleError, match="Battle-shock step requires Command step CP gain"):
        CommandStepState.start(
            battle_round=1, active_player_id="player-a"
        ).enter_battle_shock_step()
    with pytest.raises(GameLifecycleError, match="resolved Battle-shock state"):
        CommandStepState(
            battle_round=1,
            active_player_id="player-a",
            battle_shock_step_resolved=True,
        )
    with pytest.raises(GameLifecycleError, match="command_points must match transactions"):
        CommandPointLedger(
            player_id="player-a",
            command_points=2,
            transactions=(transaction,),
        )
    with pytest.raises(GameLifecycleError, match="player_id drift"):
        CommandPointLedger(
            player_id="player-b",
            command_points=1,
            transactions=(transaction,),
        )
    with pytest.raises(GameLifecycleError, match="duplicate transactions"):
        CommandPointLedger(
            player_id="player-a",
            command_points=2,
            transactions=(transaction, transaction),
        )
    with pytest.raises(GameLifecycleError, match="Applied CommandPointGainResult requires"):
        CommandPointGainResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointGainStatus.APPLIED,
            source_id="phase11c-test-source",
            source_kind=CommandPointSourceKind.OTHER,
        )
    with pytest.raises(GameLifecycleError, match="Applied CommandPointGainResult amount drift"):
        CommandPointGainResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=0,
            status=CommandPointGainStatus.APPLIED,
            source_id="phase11c-test-source",
            source_kind=CommandPointSourceKind.OTHER,
            transaction=transaction,
        )
    with pytest.raises(GameLifecycleError, match="Applied CommandPointGainResult cannot"):
        CommandPointGainResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointGainStatus.APPLIED,
            source_id="phase11c-test-source",
            source_kind=CommandPointSourceKind.OTHER,
            transaction=transaction,
            capped_reason="not-valid",
        )
    with pytest.raises(GameLifecycleError, match="Capped CommandPointGainResult cannot"):
        CommandPointGainResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=0,
            status=CommandPointGainStatus.CAPPED,
            source_id="phase11c-test-source",
            source_kind=CommandPointSourceKind.OTHER,
            transaction=transaction,
            capped_reason="cap",
        )
    with pytest.raises(GameLifecycleError, match="Capped CommandPointGainResult applies no CP"):
        CommandPointGainResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointGainStatus.CAPPED,
            source_id="phase11c-test-source",
            source_kind=CommandPointSourceKind.OTHER,
            capped_reason="cap",
        )
    with pytest.raises(GameLifecycleError, match="Capped CommandPointGainResult requires"):
        CommandPointGainResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=0,
            status=CommandPointGainStatus.CAPPED,
            source_id="phase11c-test-source",
            source_kind=CommandPointSourceKind.OTHER,
        )

    assert command_phase_step_from_token(CommandPhaseStep.COMMAND) is CommandPhaseStep.COMMAND
    assert (
        command_point_source_kind_from_token(CommandPointSourceKind.OTHER)
        is CommandPointSourceKind.OTHER
    )
    assert (
        command_point_gain_status_from_token(CommandPointGainStatus.CAPPED)
        is CommandPointGainStatus.CAPPED
    )
    with pytest.raises(GameLifecycleError, match="CommandPhaseStep token must be a string"):
        command_phase_step_from_token(cast(Any, 1))
    with pytest.raises(GameLifecycleError, match="Unsupported CommandPhaseStep token"):
        command_phase_step_from_token("not-a-step")
    with pytest.raises(GameLifecycleError, match="CommandPointSourceKind token must be a string"):
        command_point_source_kind_from_token(cast(Any, 1))
    with pytest.raises(GameLifecycleError, match="Unsupported CommandPointSourceKind token"):
        command_point_source_kind_from_token("not-a-source")
    with pytest.raises(GameLifecycleError, match="CommandPointGainStatus token must be a string"):
        command_point_gain_status_from_token(cast(Any, 1))
    with pytest.raises(GameLifecycleError, match="Unsupported CommandPointGainStatus token"):
        command_point_gain_status_from_token("not-a-status")


def test_strength_context_validation_rejects_drift_and_invalid_shapes() -> None:
    state = _battle_state()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    record = state.starting_strength_record_for_unit(unit.unit_instance_id)
    current_ids = unit.own_model_ids()
    context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=unit,
        starting_strength=record,
        current_model_ids=current_ids,
    )

    assert StartingStrengthRecord.from_payload(record.to_payload()) == record
    assert starting_strength_records_for_units(player_id="player-a", units=(unit,)) == (record,)
    assert BelowHalfStrengthContext.from_payload(context.to_payload()) == context

    below_starting_payload = context.to_payload()
    below_starting_payload["is_below_starting_strength"] = True
    with pytest.raises(GameLifecycleError, match="below-starting payload drift"):
        BelowHalfStrengthContext.from_payload(below_starting_payload)

    below_half_payload = context.to_payload()
    below_half_payload["is_below_half_strength"] = True
    with pytest.raises(GameLifecycleError, match="below-half payload drift"):
        BelowHalfStrengthContext.from_payload(below_half_payload)

    with pytest.raises(GameLifecycleError, match="Single-model StartingStrengthRecord"):
        StartingStrengthRecord(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            single_model_starting_wounds=None,
            source_id="test",
        )
    with pytest.raises(GameLifecycleError, match="Multi-model StartingStrengthRecord"):
        StartingStrengthRecord(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=2,
            single_model_starting_wounds=3,
            source_id="test",
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        StartingStrengthRecord.from_unit(player_id="player-a", unit=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="current_model_count exceeds"):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            current_model_count=2,
            single_model_starting_wounds=5,
            single_model_wounds_remaining=5,
        )
    with pytest.raises(GameLifecycleError, match="requires starting wounds"):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            current_model_count=1,
            single_model_starting_wounds=None,
            single_model_wounds_remaining=5,
        )
    with pytest.raises(GameLifecycleError, match="requires remaining wounds"):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            current_model_count=1,
            single_model_starting_wounds=5,
            single_model_wounds_remaining=None,
        )
    with pytest.raises(GameLifecycleError, match="remaining wounds exceed"):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            current_model_count=1,
            single_model_starting_wounds=5,
            single_model_wounds_remaining=6,
        )
    with pytest.raises(GameLifecycleError, match="must not include single-model wounds"):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=2,
            current_model_count=2,
            single_model_starting_wounds=5,
            single_model_wounds_remaining=None,
        )
    with pytest.raises(GameLifecycleError, match="must not include remaining wounds"):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=2,
            current_model_count=2,
            single_model_starting_wounds=None,
            single_model_wounds_remaining=5,
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        BelowHalfStrengthContext.from_unit(
            player_id="player-a",
            unit=cast(Any, object()),
            starting_strength=record,
            current_model_ids=current_ids,
        )
    with pytest.raises(GameLifecycleError, match="requires a StartingStrengthRecord"):
        BelowHalfStrengthContext.from_unit(
            player_id="player-a",
            unit=unit,
            starting_strength=cast(Any, object()),
            current_model_ids=current_ids,
        )
    with pytest.raises(GameLifecycleError, match="player_id drift"):
        BelowHalfStrengthContext.from_unit(
            player_id="player-b",
            unit=unit,
            starting_strength=record,
            current_model_ids=current_ids,
        )
    with pytest.raises(GameLifecycleError, match="unit drift"):
        BelowHalfStrengthContext.from_unit(
            player_id="player-a",
            unit=unit,
            starting_strength=replace(record, unit_instance_id="other-unit"),
            current_model_ids=current_ids,
        )
    with pytest.raises(GameLifecycleError, match="current model is not in unit"):
        BelowHalfStrengthContext.from_unit(
            player_id="player-a",
            unit=unit,
            starting_strength=record,
            current_model_ids=("unknown-model",),
        )
    with pytest.raises(GameLifecycleError, match="duplicates"):
        BelowHalfStrengthContext.from_unit(
            player_id="player-a",
            unit=unit,
            starting_strength=record,
            current_model_ids=(current_ids[0], current_ids[0]),
        )
    with pytest.raises(GameLifecycleError, match="starting strength units must be a tuple"):
        starting_strength_records_for_units(player_id="player-a", units=cast(Any, [unit]))


def test_battle_shock_payload_and_validation_paths_are_fail_fast() -> None:
    state = _battle_state()
    assert state.battlefield_state is not None
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    army = state.army_definition_for_player("player-a")
    assert army is not None
    request = _battle_shock_request_for_unit(state, unit)
    failed_roll = DiceRollManager("phase11c-validation").roll_fixed(request.spec, [1, 1])
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c-validation-failed",
        request=request,
        roll_state=failed_roll,
    )
    passed = BattleShockResult.from_roll_state(
        result_id="phase11c-validation-passed",
        request=request,
        roll_state=DiceRollManager("phase11c-validation").roll_fixed(request.spec, [6, 6]),
    )
    shocked = BattleShockedUnitState.from_result(result=failed, unit=unit)
    permission = friendly_stratagem_target_permission(
        player_id="player-a",
        target_player_id="player-b",
        target_unit_instance_id="army-beta:intercessor-unit-3",
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    assert BattleShockTestRequest.from_payload(request.to_payload()) == request
    assert BattleShockResult.from_payload(failed.to_payload()) == failed
    assert BattleShockedUnitState.from_payload(shocked.to_payload()) == shocked
    assert StratagemTargetPermission.from_payload(permission.to_payload()) == permission
    assert permission.is_allowed

    other_context = replace(request.below_half_strength_context, player_id="player-b")
    with pytest.raises(GameLifecycleError, match="context player drift"):
        BattleShockTestRequest(
            request_id="request-context-player-drift",
            game_id="phase11c-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            leadership_target=6,
            below_half_strength_context=other_context,
            spec=request.spec,
        )
    other_unit_context = replace(request.below_half_strength_context, unit_instance_id="other-unit")
    with pytest.raises(GameLifecycleError, match="context unit drift"):
        BattleShockTestRequest(
            request_id="request-context-unit-drift",
            game_id="phase11c-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            leadership_target=6,
            below_half_strength_context=other_unit_context,
            spec=request.spec,
        )
    with pytest.raises(GameLifecycleError, match="must be a DiceRollSpec"):
        BattleShockTestRequest(
            request_id="request-bad-spec",
            game_id="phase11c-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            leadership_target=6,
            below_half_strength_context=request.below_half_strength_context,
            spec=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="must roll 2D6"):
        BattleShockTestRequest(
            request_id="request-bad-expression",
            game_id="phase11c-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            leadership_target=6,
            below_half_strength_context=request.below_half_strength_context,
            spec=DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="invalid",
                roll_type=request.spec.roll_type,
                actor_id=unit.unit_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="spec roll_type drift"):
        BattleShockTestRequest(
            request_id="request-bad-roll-type",
            game_id="phase11c-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            leadership_target=6,
            below_half_strength_context=request.below_half_strength_context,
            spec=DiceRollSpec(
                expression=request.spec.expression,
                reason="invalid",
                roll_type="not-battle-shock",
                actor_id=unit.unit_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="spec actor drift"):
        BattleShockTestRequest(
            request_id="request-bad-actor",
            game_id="phase11c-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            leadership_target=6,
            below_half_strength_context=request.below_half_strength_context,
            spec=DiceRollSpec(
                expression=request.spec.expression,
                reason="invalid",
                roll_type=request.spec.roll_type,
                actor_id="other-unit",
            ),
        )

    wrong_spec_roll = DiceRollManager("phase11c-validation").roll_fixed(
        DiceRollSpec(
            expression=request.spec.expression,
            reason="different spec",
            roll_type=request.spec.roll_type,
            actor_id=unit.unit_instance_id,
        ),
        [1, 1],
    )
    with pytest.raises(GameLifecycleError, match="request must be a BattleShockTestRequest"):
        BattleShockResult(
            result_id="bad-request",
            request=cast(Any, object()),
            roll_state=failed_roll,
            total=failed_roll.current_total,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="roll_state must be a DiceRollState"):
        BattleShockResult(
            result_id="bad-roll-state",
            request=request,
            roll_state=cast(Any, object()),
            total=failed_roll.current_total,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="roll_state spec drift"):
        BattleShockResult(
            result_id="bad-spec-drift",
            request=request,
            roll_state=wrong_spec_roll,
            total=wrong_spec_roll.current_total,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="total drift"):
        BattleShockResult(
            result_id="bad-total",
            request=request,
            roll_state=failed_roll,
            total=failed_roll.current_total + 1,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="leadership target drift"):
        BattleShockResult(
            result_id="bad-leadership",
            request=request,
            roll_state=failed_roll,
            total=failed_roll.current_total,
            leadership_target=request.leadership_target + 1,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="passed must be a bool"):
        BattleShockResult(
            result_id="bad-passed-type",
            request=request,
            roll_state=failed_roll,
            total=failed_roll.current_total,
            leadership_target=request.leadership_target,
            passed=cast(Any, "no"),
        )
    with pytest.raises(GameLifecycleError, match="pass/fail drift"):
        BattleShockResult(
            result_id="bad-passed-drift",
            request=request,
            roll_state=failed_roll,
            total=failed_roll.current_total,
            leadership_target=request.leadership_target,
            passed=True,
        )

    with pytest.raises(GameLifecycleError, match="Passed Battle-shock results"):
        BattleShockedUnitState.from_result(result=passed, unit=unit)
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        BattleShockedUnitState.from_result(result=failed, unit=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="unit drift"):
        BattleShockedUnitState.from_result(
            result=failed,
            unit=_unit_by_id(state, "army-beta:intercessor-unit-3"),
        )
    with pytest.raises(GameLifecycleError, match="at least 1 values"):
        BattleShockedUnitState(
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            model_instance_ids=(),
            source_result_id=failed.result_id,
            battle_round_started=1,
            expires_at_player_command_phase_start="player-a",
            expires_at_battle_round=2,
        )
    with pytest.raises(GameLifecycleError, match="expiry must be a future round"):
        BattleShockedUnitState(
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            model_instance_ids=(unit.own_model_ids()[0],),
            source_result_id=failed.result_id,
            battle_round_started=1,
            expires_at_player_command_phase_start="player-a",
            expires_at_battle_round=1,
        )

    with pytest.raises(GameLifecycleError, match="allow_battle_shocked must be bool"):
        StratagemTargetPermission(
            player_id="player-a",
            target_player_id="player-a",
            target_unit_instance_id=unit.unit_instance_id,
            status=StratagemTargetPermissionStatus.ALLOWED,
            allow_battle_shocked=cast(Any, "no"),
        )
    with pytest.raises(GameLifecycleError, match="Allowed StratagemTargetPermission"):
        StratagemTargetPermission(
            player_id="player-a",
            target_player_id="player-a",
            target_unit_instance_id=unit.unit_instance_id,
            status=StratagemTargetPermissionStatus.ALLOWED,
            denial_reason="not-valid",
        )
    with pytest.raises(GameLifecycleError, match="Denied StratagemTargetPermission"):
        StratagemTargetPermission(
            player_id="player-a",
            target_player_id="player-a",
            target_unit_instance_id=unit.unit_instance_id,
            status=StratagemTargetPermissionStatus.DENIED,
        )

    assert (
        battle_shock_test_reason_from_token(BattleShockTestReason.BELOW_HALF_STRENGTH)
        is BattleShockTestReason.BELOW_HALF_STRENGTH
    )
    assert (
        stratagem_target_permission_status_from_token(StratagemTargetPermissionStatus.ALLOWED)
        is StratagemTargetPermissionStatus.ALLOWED
    )
    with pytest.raises(GameLifecycleError, match="BattleShockTestReason token must be a string"):
        battle_shock_test_reason_from_token(cast(Any, 1))
    with pytest.raises(GameLifecycleError, match="Unsupported BattleShockTestReason"):
        battle_shock_test_reason_from_token("not-a-reason")
    with pytest.raises(
        GameLifecycleError,
        match="StratagemTargetPermissionStatus token must be a string",
    ):
        stratagem_target_permission_status_from_token(cast(Any, 1))
    with pytest.raises(GameLifecycleError, match="Unsupported StratagemTargetPermissionStatus"):
        stratagem_target_permission_status_from_token("not-a-status")

    with pytest.raises(GameLifecycleError, match="require an ArmyDefinition"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=cast(Any, object()),
            battlefield_state=state.battlefield_state,
            starting_strength_records=tuple(state.starting_strength_records),
        )
    with pytest.raises(GameLifecycleError, match="army player drift"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-b",
            army=army,
            battlefield_state=state.battlefield_state,
            starting_strength_records=tuple(state.starting_strength_records),
        )
    with pytest.raises(GameLifecycleError, match="require BattlefieldRuntimeState"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=cast(Any, object()),
            starting_strength_records=tuple(state.starting_strength_records),
        )
    with pytest.raises(GameLifecycleError, match="missing StartingStrengthRecord"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=state.battlefield_state,
            starting_strength_records=(),
        )
    with pytest.raises(GameLifecycleError, match="allow_duplicate_below_half_tests must be a bool"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=state.battlefield_state,
            starting_strength_records=tuple(state.starting_strength_records),
            allow_duplicate_below_half_tests=cast(Any, "no"),
        )
    with pytest.raises(GameLifecycleError, match="forced_below_starting_strength_unit_ids"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=state.battlefield_state,
            starting_strength_records=tuple(state.starting_strength_records),
            forced_below_starting_strength_unit_ids=cast(Any, [unit.unit_instance_id]),
        )


def _submit_direct_decision(
    *,
    decisions: DecisionController,
    handler: CommandPhaseHandler,
    state: GameState,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    handler.apply_decision(state=state, result=result, decisions=decisions)


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _active_battle_shock_requests(
    state: GameState,
    *,
    forced_below_starting_strength_unit_ids: tuple[str, ...] = (),
    allow_duplicate_below_half_tests: bool = False,
) -> tuple[BattleShockTestRequest, ...]:
    assert state.active_player_id is not None
    assert state.battlefield_state is not None
    army = state.army_definition_for_player(state.active_player_id)
    assert army is not None
    return collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=state.active_player_id,
        army=army,
        battlefield_state=state.battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
        forced_below_starting_strength_unit_ids=forced_below_starting_strength_unit_ids,
        allow_duplicate_below_half_tests=allow_duplicate_below_half_tests,
    )


def _battle_shock_request_for_unit(
    state: GameState,
    unit: UnitInstance,
) -> BattleShockTestRequest:
    context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=unit,
        starting_strength=state.starting_strength_record_for_unit(unit.unit_instance_id),
        current_model_ids=unit.own_model_ids(),
    )
    return BattleShockTestRequest.for_unit(
        request_id=f"phase11c-battle-shock:{unit.unit_instance_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=6,
        below_half_strength_context=context,
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


def _remove_first_models(state: GameState, *, unit_instance_id: str, count: int) -> None:
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    removed_ids = tuple(
        placement.model_instance_id for placement in unit_placement.model_placements[:count]
    )
    state.battlefield_state = state.battlefield_state.with_removed_models(removed_ids)


def _set_single_model_wounds(state: GameState, *, unit_instance_id: str, wounds: int) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            model = unit.own_models[0]
            updated_units.append(
                replace(unit, own_models=(replace(model, wounds_remaining=wounds),))
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if marker.objective_marker_id.endswith("-center"):
            return marker
    raise AssertionError("missing center objective marker")


def _center_objective_result(record: ObjectiveControlRecord) -> ObjectiveControlResult:
    for result in record.results:
        if result.objective_id.endswith("-center"):
            return result
    raise AssertionError("missing center objective result")


def _battle_state(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
) -> GameState:
    config = _config(player_a_units=player_a_units)
    state = GameState.from_config(config)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11c-battlefield",
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
    return state


def _secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _config(*, player_a_units: tuple[UnitMusterSelection, ...] | None = None) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase11c-game",
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(
                    (_default_unit_selection("intercessor-unit-1"),)
                    if player_a_units is None
                    else player_a_units
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(_default_unit_selection("intercessor-unit-3"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
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
        descriptor_version="core-v2-phase11c-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
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
        unit_selections=unit_selections,
    )


def _default_unit_selection(unit_selection_id: str) -> UnitMusterSelection:
    return _unit_selection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
    )


def _unit_selection(
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


def _event_index(decisions: DecisionController, event_type: str) -> int:
    for index, event in enumerate(decisions.event_log.records):
        if event.event_type == event_type:
            return index
    raise AssertionError(f"missing event {event_type}")
