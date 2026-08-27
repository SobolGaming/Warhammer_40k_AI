from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.phase17n_secondary_mission_helpers import (
    drain_pending_secondary_mission_setup_for_command_handler,
)
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    ModifiedRollResult,
    RerollComponentSelectionPolicy,
    RerollPermission,
    UnmodifiedRollResult,
)
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
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockHookRegistry,
    BattleShockRerollPermissionContext,
    HistoricalBattleShockContribution,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    BattleShockPassedStatePolicy,
    record_battle_shock_result_and_outcome_events,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    PlacementError,
    UnitPlacement,
)
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
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.grey_knights import (
    army_rule as grey_knights_army_rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
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
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases import (
    command_battle_shock_rerolls as battle_shock_rerolls,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
    primary_reserve_entry_provider_from_accepted_ability_decision,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    StrategicReserveDeclaration,
)
from warhammer40k_core.engine.rules_units import (
    placed_alive_rules_unit_views,
    rules_unit_is_battle_shocked,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.setup_flow import SetupFlow
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.transports import (
    DisembarkedUnitState,
    DisembarkModeKind,
    TransportCapacityProfile,
    TransportMovementStatus,
)
from warhammer40k_core.engine.turn_end_hooks import (
    TurnEndHookRegistry,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    StartingStrengthRecord,
    starting_strength_records_for_units,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_command_step_grants_both_players_cp_once_before_tactical_draw() -> None:
    state = _battle_state(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_b_secondary=SecondaryMissionMode.FIXED,
    )
    decisions = DecisionController()
    handler = CommandPhaseHandler(stratagem_index=StratagemCatalogIndex.from_records(()))

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
    completed = drain_pending_secondary_mission_setup_for_command_handler(
        handler=handler,
        state=state,
        decisions=decisions,
        result_id_prefix="phase11c-secondary-setup",
    )

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


def test_restore_requires_command_step_anchor_after_core_cp_gain() -> None:
    decisions = DecisionController()
    state = _battle_state(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_b_secondary=SecondaryMissionMode.FIXED,
        decisions=decisions,
    )
    handler = CommandPhaseHandler(stratagem_index=StratagemCatalogIndex.from_records(()))

    waiting = handler.begin_phase(state=state, decisions=decisions)

    assert _decision_request(waiting).decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE
    command_state = _command_step_state(state)
    assert command_state.command_points_granted
    assert command_state.current_step is CommandPhaseStep.COMMAND
    assert not any(
        event.event_type == "battle_shock_step_snapshot_created"
        for event in decisions.event_log.records
    )
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()

    forged_payload = json.loads(json.dumps(lifecycle.to_payload()))
    forged_payload["decisions"]["event_log"] = [
        event
        for event in forged_payload["decisions"]["event_log"]
        if event["event_type"] != "command_step_started"
    ]
    for index, event in enumerate(forged_payload["decisions"]["event_log"], start=1):
        event["event_id"] = f"event-{index:06d}"

    with pytest.raises(GameLifecycleError, match="lacks its start anchor"):
        GameLifecycle.from_payload(forged_payload)


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "missing_gain_event",
        "duplicate_gain_event",
        "missing_ledger_transaction",
        "duplicate_ledger_transaction",
        "reordered_anchor_gains",
    ],
)
def test_restore_requires_exact_core_cp_gain_event_and_ledger_inventory(
    tamper_kind: str,
) -> None:
    decisions = DecisionController()
    state = _battle_state(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        decisions=decisions,
    )
    waiting = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(())
    ).begin_phase(state=state, decisions=decisions)
    assert _decision_request(waiting).decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE
    baseline = GameLifecycle(state=state, decision_controller=decisions).to_payload()
    assert GameLifecycle.from_payload(baseline).to_payload() == baseline

    forged = cast(dict[str, Any], json.loads(json.dumps(baseline)))
    events = cast(list[dict[str, Any]], forged["decisions"]["event_log"])
    anchor_index = next(
        index for index, event in enumerate(events) if event["event_type"] == "command_step_started"
    )
    if tamper_kind == "missing_gain_event":
        events.pop(anchor_index - 1)
    elif tamper_kind == "duplicate_gain_event":
        duplicate = json.loads(json.dumps(events[anchor_index - 1]))
        events.insert(anchor_index, duplicate)
    elif tamper_kind == "reordered_anchor_gains":
        events[anchor_index]["payload"]["command_point_gains"].reverse()
    else:
        ledger = next(
            value
            for value in forged["state"]["command_point_ledgers"]
            if value["player_id"] == "player-a"
        )
        if tamper_kind == "missing_ledger_transaction":
            removed = ledger["transactions"].pop()
            ledger["command_points"] -= removed["amount"]
        else:
            duplicate = json.loads(json.dumps(ledger["transactions"][0]))
            duplicate["transaction_id"] = "command-point:player-a:round-01:999999"
            ledger["transactions"].append(duplicate)
            ledger["command_points"] += duplicate["amount"]
    for index, event in enumerate(events, start=1):
        event["event_id"] = f"event-{index:06d}"

    with pytest.raises(GameLifecycleError, match=r"Command step|Core CP"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_restore_rejects_coordinated_deletion_of_complete_command_occurrence() -> None:
    decisions = DecisionController()
    state = _battle_state(decisions=decisions)
    handler = CommandPhaseHandler(stratagem_index=StratagemCatalogIndex.from_records(()))
    handler.begin_phase(state=state, decisions=decisions)
    state.command_step_state = None
    state.active_player_id = "player-b"
    handler.begin_phase(state=state, decisions=decisions)
    baseline = GameLifecycle(state=state, decision_controller=decisions).to_payload()
    assert GameLifecycle.from_payload(baseline).to_payload() == baseline

    forged = json.loads(json.dumps(baseline))
    source_id = (
        "gw-11e-core-command-phase-2026-08:app-core-rules:08.01.02-gain-core-cp:"
        "round-01:active-player-a"
    )
    forged["decisions"]["event_log"] = [
        event
        for event in forged["decisions"]["event_log"]
        if not (
            event["payload"].get("source_id") == source_id
            or (
                event["event_type"]
                in {
                    "command_step_started",
                    "battle_shock_step_snapshot_created",
                    "battle_shock_step_completed",
                }
                and event["payload"].get("battle_round") == 1
                and event["payload"].get("active_player_id") == "player-a"
            )
        )
    ]
    for ledger in forged["state"]["command_point_ledgers"]:
        removed = [
            transaction
            for transaction in ledger["transactions"]
            if transaction["source_id"] == source_id
        ]
        ledger["transactions"] = [
            transaction
            for transaction in ledger["transactions"]
            if transaction["source_id"] != source_id
        ]
        ledger["command_points"] -= sum(transaction["amount"] for transaction in removed)
    for index, event in enumerate(forged["decisions"]["event_log"], start=1):
        event["event_id"] = f"event-{index:06d}"

    with pytest.raises(GameLifecycleError, match="occurrence inventory"):
        GameLifecycle.from_payload(forged)


def test_non_command_cp_gain_cap_is_enforced_per_battle_round() -> None:
    state = _battle_state()

    core_gain = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="core-command-phase-gain",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    oversized = state.gain_command_points(
        player_id="player-a",
        amount=3,
        source_id="ability-gain-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    capped = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="second-ability-gain-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )

    assert core_gain.status is CommandPointGainStatus.APPLIED
    assert core_gain.transaction is not None
    assert core_gain.transaction.cap_exempt is True
    assert oversized.status is CommandPointGainStatus.CAPPED
    assert oversized.requested_amount == 3
    assert oversized.applied_amount == 1
    assert oversized.transaction is not None
    assert oversized.transaction.amount == 1
    assert oversized.transaction.cap_exempt is False
    assert oversized.capped_reason == "non_command_cp_gain_cap_reached"
    assert capped.status is CommandPointGainStatus.CAPPED
    assert capped.applied_amount == 0
    assert capped.transaction is None
    assert capped.capped_reason == "non_command_cp_gain_cap_reached"
    assert state.command_point_total("player-a") == 2


def test_below_half_strength_unit_emits_battle_shock_test_request() -> None:
    state = _battle_state()
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)

    requests = _active_battle_shock_requests(state)

    assert len(requests) == 1
    request = requests[0]
    assert request.reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
    assert request.leadership_target == 6
    assert request.below_half_strength_context.current_model_count == 2
    assert request.below_half_strength_context.is_below_half_strength


def test_currently_shocked_unit_requires_one_command_test_even_above_or_below_half() -> None:
    state = _battle_state()
    unit_id = "army-alpha:intercessor-unit-1"
    _record_unit_battle_shocked(state, unit_instance_id=unit_id)

    above_half_requests = _active_battle_shock_requests(state)

    assert len(above_half_requests) == 1
    assert above_half_requests[0].reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
    assert not above_half_requests[0].below_half_strength_context.is_at_or_below_half_strength

    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    dual_predicate_requests = _active_battle_shock_requests(state)

    assert len(dual_predicate_requests) == 1
    assert dual_predicate_requests[0].unit_instance_id == unit_id
    assert dual_predicate_requests[0].below_half_strength_context.is_below_half_strength


def test_exactly_half_strength_requires_command_test_for_multi_and_single_model_units() -> None:
    multi = _battle_state(
        player_a_units=(
            _unit_selection(
                unit_selection_id="four-model-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=10,
            ),
        )
    )
    _remove_first_models(multi, unit_instance_id="army-alpha:four-model-unit", count=5)
    multi_request = _active_battle_shock_requests(multi)[0]

    single = _battle_state(
        player_a_units=(
            _unit_selection(
                unit_selection_id="monster-unit",
                datasheet_id="core-vehicle-monster",
                model_profile_id="core-vehicle-monster",
                model_count=1,
            ),
        )
    )
    _set_single_model_wounds(single, unit_instance_id="army-alpha:monster-unit", wounds=6)
    single_request = _active_battle_shock_requests(single)[0]

    assert multi_request.below_half_strength_context.is_at_half_strength
    assert multi_request.below_half_strength_context.is_at_or_below_half_strength
    assert single_request.below_half_strength_context.is_at_half_strength
    assert single_request.below_half_strength_context.is_at_or_below_half_strength


def test_command_success_clears_step_start_shock_but_failure_and_forced_success_preserve() -> None:
    unit_id = "army-alpha:intercessor-unit-1"

    passed_state = _battle_state()
    _record_unit_battle_shocked(passed_state, unit_instance_id=unit_id)
    passed_request = _active_battle_shock_requests(passed_state)[0]
    passed_payload = _record_fixed_battle_shock_resolution(
        state=passed_state,
        request=passed_request,
        values=(6, 6),
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(unit_id,),
        passed_state_policy=BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
    )

    assert passed_state.battle_shocked_unit_ids == []
    assert passed_payload["state_update"] == "cleared_battle_shocked"
    assert passed_payload["cleared_battle_shocked_unit_ids"] == [unit_id]

    failed_state = _battle_state()
    original_failed_state = _record_unit_battle_shocked(
        failed_state,
        unit_instance_id=unit_id,
    )
    failed_request = _active_battle_shock_requests(failed_state)[0]
    failed_payload = _record_fixed_battle_shock_resolution(
        state=failed_state,
        request=failed_request,
        values=(1, 1),
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(unit_id,),
        passed_state_policy=BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
    )

    assert failed_state.battle_shocked_unit_states == [original_failed_state]
    assert failed_payload["state_update"] == "already_battle_shocked"
    assert failed_payload["cleared_battle_shocked_unit_ids"] == []

    forced_state = _battle_state()
    original_forced_state = _record_unit_battle_shocked(
        forced_state,
        unit_instance_id=unit_id,
    )
    forced_request = _active_battle_shock_requests(forced_state)[0]
    forced_payload = _record_fixed_battle_shock_resolution(
        state=forced_state,
        request=forced_request,
        values=(6, 6),
        phase=BattlePhase.SHOOTING,
        phase_start_battle_shocked_unit_ids=(),
        passed_state_policy=BattleShockPassedStatePolicy.PRESERVE,
    )

    assert forced_state.battle_shocked_unit_states == [original_forced_state]
    assert forced_payload["state_update"] == "not_required"
    assert forced_payload["cleared_battle_shocked_unit_ids"] == []


def test_attached_rules_unit_uses_one_canonical_required_test_and_clear_identity() -> None:
    attached_id = "attached-unit:army-alpha:bodyguard-unit"
    state = _battle_state(
        player_a_units=(
            _default_unit_selection("bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=attached_id)
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit,
        starting_strength=state.starting_strength_record_for_unit(attached_id),
        current_model_ids=tuple(model.model_instance_id for model in rules_unit.own_models),
    )
    failed_request = BattleShockTestRequest.for_unit(
        request_id="phase11c-attached-failed-test",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=attached_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=context,
    )
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c-attached-failed-result",
        request=failed_request,
        roll_state=DiceRollManager("phase11c-attached-fail").roll_fixed(
            failed_request.spec,
            [1, 1],
        ),
    )
    state.record_battle_shock_result(failed)
    canonical_start_ids = tuple(
        rules_unit.unit_instance_id
        for rules_unit in placed_alive_rules_unit_views(state=state)
        if rules_unit.owner_player_id == "player-a"
        and rules_unit_is_battle_shocked(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
        )
    )
    required = _active_battle_shock_requests(
        state,
        battle_shocked_unit_ids=canonical_start_ids,
    )

    assert canonical_start_ids == (attached_id,)
    assert len(required) == 1
    assert required[0].unit_instance_id == attached_id

    resolved = _record_fixed_battle_shock_resolution(
        state=state,
        request=required[0],
        values=(6, 6),
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=canonical_start_ids,
        passed_state_policy=BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
    )

    assert state.battle_shocked_unit_ids == []
    assert resolved["cleared_battle_shocked_unit_ids"] == [attached_id]


def test_off_battlefield_shocked_unit_remains_outside_command_candidate_scope() -> None:
    state = _battle_state()
    unit_id = "army-alpha:intercessor-unit-1"
    _record_unit_battle_shocked(state, unit_instance_id=unit_id)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(unit_id)

    assert _active_battle_shock_requests(state) == ()


def test_command_phase_resolves_non_reroll_battle_shock_dice_without_decision_pause() -> None:
    state = _battle_state()
    decisions = DecisionController()
    handler = CommandPhaseHandler(stratagem_index=StratagemCatalogIndex.from_records(()))
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


def test_command_phase_battle_shock_reroll_permission_pauses_and_resumes() -> None:
    state = _battle_state()
    decisions = DecisionController()
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)

    def reroll_permission(
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        return RerollPermission(
            source_id="test:battle-shock-reroll",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="test:battle-shock-reroll",
                    source_id="test:battle-shock-reroll",
                    reroll_permission_handler=reroll_permission,
                ),
            )
        ),
    )

    waiting = handler.begin_phase(state=state, decisions=decisions)

    reroll_request = _decision_request(waiting)
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert reroll_request.actor_id == "player-a"
    assert state.command_step_state is not None
    assert not state.command_step_state.battle_shock_step_resolved
    assert state.command_step_state.completed_battle_shock_test_request_ids == ()
    assert len(state.command_step_state.battle_shock_required_test_requests) == 1
    restored_state = GameState.from_payload(_game_state_payload_copy(state))
    assert (
        _command_step_state(restored_state).battle_shock_required_test_requests
        == state.command_step_state.battle_shock_required_test_requests
    )
    reroll_request_payload = cast(dict[str, Any], reroll_request.payload)
    reroll_context = cast(dict[str, Any], reroll_request_payload["battle_shock_context"])
    battle_shock_request_payload = cast(
        dict[str, Any],
        reroll_context["battle_shock_test_request"],
    )
    battle_shock_request_id = cast(str, battle_shock_request_payload["request_id"])
    assert reroll_context["passed_state_policy"] == "clear_if_step_start_shocked"

    _submit_direct_decision(
        decisions=decisions,
        handler=handler,
        state=state,
        request=reroll_request,
        option_id="decline",
        result_id="phase11c-battle-shock-reroll-declined",
    )

    command_state = state.command_step_state
    assert command_state is not None
    assert command_state.completed_battle_shock_test_request_ids == (battle_shock_request_id,)
    assert not command_state.battle_shock_step_resolved

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    resolved_command_state = _command_step_state(state)
    assert resolved_command_state.battle_shock_step_resolved
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert "dice_reroll_declined" in event_types
    assert "battle_shock_test_resolved" in event_types
    assert event_types.count("battle_shock_test_requested") == 1
    completed_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "battle_shock_step_completed"
    )
    assert isinstance(completed_event.payload, dict)
    assert completed_event.payload["battle_shock_test_count"] == 1
    assert len(cast(list[Any], completed_event.payload["battle_shock_results"])) == 1


def test_command_reroll_round_trip_preserves_full_candidate_and_result_prefixes() -> None:
    game_id = "phase11c-command-reroll-round-trip"
    unit_selections = (
        _default_unit_selection("intercessor-unit-1"),
        _default_unit_selection("intercessor-unit-2"),
    )
    config = _config(game_id=game_id, player_a_units=unit_selections)
    decisions = DecisionController()
    state = _battle_state(
        game_id=game_id,
        player_a_units=unit_selections,
        decisions=decisions,
    )
    for unit_id in (
        "army-alpha:intercessor-unit-1",
        "army-alpha:intercessor-unit-2",
    ):
        _remove_first_models(state, unit_instance_id=unit_id, count=3)

    def reroll_permission(
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        return RerollPermission(
            source_id="phase11c:source:command-battle-shock-reroll",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    binding = BattleShockHookBinding(
        hook_id="phase11c:hook:command-battle-shock-reroll",
        source_id="phase11c:source:command-battle-shock-reroll",
        reroll_permission_handler=reroll_permission,
        historical_contribution_handler=lambda context: HistoricalBattleShockContribution(
            reroll_permission=RerollPermission(
                source_id="phase11c:source:command-battle-shock-reroll",
                timing_window="battle_shock_test",
                owning_player_id=context.request.player_id,
                eligible_roll_type=context.request.spec.roll_type,
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            )
        ),
    )
    armies = tuple(state.army_definitions)
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=armies,
            catalog=config.army_catalog,
        ),
        armies=armies,
        catalog=config.army_catalog,
        contributions=(
            RuntimeContentContribution(
                contribution_id="phase11c:contribution:command-battle-shock-reroll",
                battle_shock_hook_bindings=(binding,),
            ),
        ),
    )
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        },
        runtime_content_bundle=bundle,
    )

    first_status = lifecycle.advance_until_decision_or_terminal()
    first_request = _decision_request(first_status)
    if first_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        first_status = lifecycle.submit_decision(
            DecisionResult(
                result_id="phase11c-command-reroll-decline-stratagem",
                request_id=first_request.request_id,
                decision_type=first_request.decision_type,
                actor_id=first_request.actor_id,
                selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                payload=stratagem_decline_payload(),
            )
        )
        first_request = _decision_request(first_status)
    assert first_request.decision_type == DICE_REROLL_DECISION_TYPE
    second_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase11c-command-reroll-first-declined",
            request=first_request,
            selected_option_id="decline",
        )
    )
    second_request = _decision_request(second_status)
    assert second_request.decision_type == DICE_REROLL_DECISION_TYPE
    second_context = cast(
        dict[str, Any],
        cast(dict[str, Any], second_request.payload)["battle_shock_context"],
    )
    assert second_context["additional_modifier_applications"] == []
    assert lifecycle.state is not None
    command_state = _command_step_state(lifecycle.state)
    assert len(command_state.battle_shock_candidate_inventory) == 2
    assert len(command_state.completed_battle_shock_test_request_ids) == 1
    candidate_prefix = tuple(command_state.battle_shock_candidate_inventory)
    completed_id_prefix = tuple(command_state.completed_battle_shock_test_request_ids)
    result_prefix = tuple(
        event.payload
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "battle_shock_test_resolved"
    )
    assert len(result_prefix) == 1

    payload = json.loads(json.dumps(lifecycle.to_payload()))
    restored = GameLifecycle.from_payload(payload, runtime_content_bundle=bundle)
    assert restored.state is not None
    restored_state = _command_step_state(restored.state)
    assert restored_state.battle_shock_candidate_inventory == candidate_prefix
    assert restored_state.completed_battle_shock_test_request_ids == completed_id_prefix
    assert (
        tuple(
            event.payload
            for event in restored.decision_controller.event_log.records
            if event.event_type == "battle_shock_test_resolved"
        )
        == result_prefix
    )
    assert _decision_request(restored.advance_until_decision_or_terminal()) == second_request


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "missing_anchor",
        "missing_snapshot",
        "missing_request",
        "missing_dice",
        "missing_result",
        "missing_completion",
        "drifted_snapshot_predicate",
        "drifted_result_state_update",
        "drifted_completion_results",
    ],
)
def test_post_command_restore_rejects_battle_shock_history_tamper(
    tamper_kind: str,
) -> None:
    decisions = DecisionController()
    state = _battle_state(decisions=decisions)
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)
    completed = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(())
    ).begin_phase(state=state, decisions=decisions)
    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    phase_end_record = state.determine_current_phase_end_objective_control(
        runtime_modifier_registry=None,
    )
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "record_ids": [phase_end_record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )
    state.advance_to_next_battle_phase(event_log=decisions.event_log)
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    baseline = lifecycle.to_payload()
    assert GameLifecycle.from_payload(baseline).to_payload() == baseline

    forged = cast(dict[str, Any], json.loads(json.dumps(baseline)))
    forged_decisions = cast(dict[str, Any], forged["decisions"])
    events = cast(list[dict[str, Any]], forged_decisions["event_log"])
    event_type_by_tamper = {
        "missing_anchor": "command_step_started",
        "missing_snapshot": "battle_shock_step_snapshot_created",
        "missing_request": "battle_shock_test_requested",
        "missing_dice": "dice_rolled",
        "missing_result": "battle_shock_test_resolved",
        "missing_completion": "battle_shock_step_completed",
    }
    deleted_event_type = event_type_by_tamper.get(tamper_kind)
    if deleted_event_type is not None:
        matching_indices = [
            index for index, event in enumerate(events) if event["event_type"] == deleted_event_type
        ]
        assert matching_indices
        events.pop(matching_indices[-1])
        for index, event in enumerate(events, start=1):
            event["event_id"] = f"event-{index:06d}"
    elif tamper_kind == "drifted_result_state_update":
        result_event = next(
            event for event in events if event["event_type"] == "battle_shock_test_resolved"
        )
        result_event["payload"]["state_update"] = "forged_update"
    elif tamper_kind == "drifted_snapshot_predicate":
        request_payloads: list[dict[str, Any]] = []
        for event in events:
            event_payload = cast(dict[str, Any], event["payload"])
            if event["event_type"] == "battle_shock_step_snapshot_created":
                request_payloads.extend(event_payload["battle_shock_required_test_requests"])
            if "battle_shock_test_request" in event_payload:
                request_payloads.append(event_payload["battle_shock_test_request"])
            if "battle_shock_result" in event_payload:
                request_payloads.append(event_payload["battle_shock_result"]["request"])
            if event["event_type"] == "battle_shock_step_completed":
                request_payloads.extend(
                    result_payload["request"]
                    for result_payload in event_payload["battle_shock_results"]
                )
        assert request_payloads
        for request_payload in request_payloads:
            context = request_payload["below_half_strength_context"]
            context["current_model_count"] = 3
            context["is_below_starting_strength"] = True
            context["is_at_half_strength"] = False
            context["is_below_half_strength"] = False
    else:
        completion_event = next(
            event for event in events if event["event_type"] == "battle_shock_step_completed"
        )
        completion_event["payload"]["battle_shock_results"] = []

    with pytest.raises(GameLifecycleError, match=r"Command|Battle-shock"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


@pytest.mark.parametrize(
    "tamper_kind",
    ["add", "delete", "source", "models", "round", "mutation_token"],
)
def test_restore_rejects_battle_shock_state_inventory_tamper(tamper_kind: str) -> None:
    decisions = DecisionController()
    state = _battle_state(decisions=decisions, game_id="phase11c-history-fail-13")
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
    )
    completed = handler.begin_phase(state=state, decisions=decisions)
    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert state.battle_shocked_unit_ids == [unit_id]
    lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _command_phase_handler=handler,
    )
    baseline = lifecycle.to_payload()
    assert GameLifecycle.from_payload(baseline).to_payload() == baseline

    forged = cast(dict[str, Any], json.loads(json.dumps(baseline)))
    forged_state = cast(dict[str, Any], forged["state"])
    shocked_states = cast(list[dict[str, Any]], forged_state["battle_shocked_unit_states"])
    assert len(shocked_states) == 1
    if tamper_kind == "add":
        forged_unit_id = "army-beta:intercessor-unit-3"
        forged_state["battle_shocked_unit_ids"].append(forged_unit_id)
        forged_state["battle_shocked_unit_ids"].sort()
        forged_unit = _unit_by_id(state, forged_unit_id)
        shocked_states.append(
            {
                "player_id": "player-b",
                "unit_instance_id": forged_unit_id,
                "model_instance_ids": list(forged_unit.own_model_ids()),
                "source_result_id": "forged:no-result",
                "battle_round_started": 1,
            }
        )
        shocked_states.sort(key=lambda value: value["unit_instance_id"])
    elif tamper_kind == "delete":
        forged_state["battle_shocked_unit_ids"] = []
        forged_state["battle_shocked_unit_states"] = []
    elif tamper_kind == "source":
        shocked_states[0]["source_result_id"] = "forged:no-result"
    elif tamper_kind == "models":
        shocked_states[0]["model_instance_ids"] = list(
            reversed(shocked_states[0]["model_instance_ids"])
        )
    elif tamper_kind == "round":
        shocked_states[0]["battle_round_started"] = 2
    else:
        result_event = next(
            event
            for event in forged["decisions"]["event_log"]
            if event["event_type"] == "battle_shock_test_resolved"
        )
        result_event["payload"]["state_update"] = "already_battle_shocked"

    with pytest.raises(GameLifecycleError, match="Battle-shock"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_battle_shock_reroll_payload_helpers_fail_fast_on_contract_drift() -> None:
    assert battle_shock_rerolls._payload_object(  # pyright: ignore[reportPrivateUsage]
        {"payload": "ok"},
        context="payload",
    ) == {"payload": "ok"}
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        battle_shock_rerolls._payload_object(  # pyright: ignore[reportPrivateUsage]
            1,
            context="payload",
        )

    assert (
        battle_shock_rerolls._payload_int(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"round": 1}),
            key="round",
        )
        == 1
    )
    with pytest.raises(GameLifecycleError, match="missing required key: round"):
        battle_shock_rerolls._payload_int(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {}),
            key="round",
        )
    with pytest.raises(GameLifecycleError, match="must be an integer: round"):
        battle_shock_rerolls._payload_int(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"round": "1"}),
            key="round",
        )

    assert (
        battle_shock_rerolls._payload_string(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"player_id": " player-a "}),
            key="player_id",
        )
        == "player-a"
    )
    with pytest.raises(GameLifecycleError, match="missing required key: player_id"):
        battle_shock_rerolls._payload_string(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {}),
            key="player_id",
        )
    with pytest.raises(GameLifecycleError, match="must be a string: player_id"):
        battle_shock_rerolls._payload_string(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"player_id": 1}),
            key="player_id",
        )
    with pytest.raises(GameLifecycleError, match="cannot be empty: player_id"):
        battle_shock_rerolls._payload_string(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"player_id": " "}),
            key="player_id",
        )

    assert battle_shock_rerolls._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
        cast(Any, {"unit_ids": [" unit-a ", "unit-b"]}),
        key="unit_ids",
    ) == ("unit-a", "unit-b")
    with pytest.raises(GameLifecycleError, match="missing required key: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="must be a list: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"unit_ids": "unit-a"}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="list must contain strings: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"unit_ids": [1]}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="list item is empty: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"unit_ids": [" "]}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="contains duplicates: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
            cast(Any, {"unit_ids": ["unit-a", "unit-a"]}),
            key="unit_ids",
        )

    state = _battle_state()
    assert battle_shock_rerolls._active_player_id(state) == "player-a"  # pyright: ignore[reportPrivateUsage]
    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        battle_shock_rerolls._active_player_id(state)  # pyright: ignore[reportPrivateUsage]

    state.active_player_id = "player-a"
    state.command_step_state = CommandStepState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    assert battle_shock_rerolls._command_step_state(state) is state.command_step_state  # pyright: ignore[reportPrivateUsage]
    state.command_step_state = None
    with pytest.raises(GameLifecycleError, match="requires command step state"):
        battle_shock_rerolls._command_step_state(state)  # pyright: ignore[reportPrivateUsage]


def test_battle_shock_reroll_applier_rejects_wrong_lifecycle_window() -> None:
    result = DecisionResult(
        result_id="phase11c-reroll-window-result",
        request_id="phase11c-reroll-window-request",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        selected_option_id="decline",
        payload={},
    )

    setup_state = _battle_state()
    setup_state.stage = GameLifecycleStage.SETUP
    with pytest.raises(GameLifecycleError, match="only during battle"):
        battle_shock_rerolls.apply_battle_shock_reroll_decision(
            state=setup_state,
            result=result,
            decisions=DecisionController(),
            battle_shock_hooks=BattleShockHookRegistry.empty(),
        )

    movement_state = _battle_state()
    movement_state.battle_phase_index = movement_state.battle_phase_sequence.index(
        BattlePhase.MOVEMENT
    )
    with pytest.raises(GameLifecycleError, match="only in command"):
        battle_shock_rerolls.apply_battle_shock_reroll_decision(
            state=movement_state,
            result=result,
            decisions=DecisionController(),
            battle_shock_hooks=BattleShockHookRegistry.empty(),
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
        BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
        BattleShockTestReason.COMMAND_PHASE_REQUIRED,
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
    assert state.battle_shocked_unit_states[0].battle_round_started == 1
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
    assert not multi_request.below_half_strength_context.is_at_half_strength
    assert single_request.below_half_strength_context.starting_model_count == 1
    assert single_request.below_half_strength_context.single_model_starting_wounds == 5
    assert single_request.below_half_strength_context.single_model_wounds_remaining == 2
    assert not single_request.below_half_strength_context.is_at_half_strength
    assert single_request.below_half_strength_context.is_below_half_strength

    even_multi = BelowHalfStrengthContext(
        player_id="player-a",
        unit_instance_id="army-alpha:even-unit",
        starting_model_count=4,
        current_model_count=2,
        single_model_starting_wounds=None,
        single_model_wounds_remaining=None,
    )
    even_single = BelowHalfStrengthContext(
        player_id="player-a",
        unit_instance_id="army-alpha:even-character",
        starting_model_count=1,
        current_model_count=1,
        single_model_starting_wounds=6,
        single_model_wounds_remaining=3,
    )

    assert even_multi.is_at_half_strength
    assert not even_multi.is_below_half_strength
    assert even_single.is_at_half_strength
    assert not even_single.is_below_half_strength


def test_runtime_added_unit_records_starting_strength_when_added() -> None:
    state = _battle_state()
    added_unit = _runtime_unit_for_selection(
        player_id="player-a",
        army_id="army-alpha",
        unit_selection_id="summoned-unit-1",
    )

    record = state.add_unit_to_army(
        player_id="player-a",
        unit=added_unit,
        source_id="phase11c-add-unit-rule",
    )

    assert record == state.starting_strength_record_for_unit(added_unit.unit_instance_id)
    assert record.source_id == "phase11c-add-unit-rule"
    assert record.starting_model_count == len(added_unit.own_models)
    assert _unit_by_id(state, added_unit.unit_instance_id) == added_unit
    assert GameState.from_payload(_game_state_payload_copy(state)).to_payload() == (
        state.to_payload()
    )

    with pytest.raises(GameLifecycleError, match="already exists"):
        state.add_unit_to_army(
            player_id="player-a",
            unit=added_unit,
            source_id="phase11c-add-unit-rule",
        )
    with pytest.raises(GameLifecycleError, match="added unit must be a UnitInstance"):
        state.add_unit_to_army(
            player_id="player-a",
            unit=cast(Any, object()),
            source_id="phase11c-add-unit-rule",
        )
    with pytest.raises(GameLifecycleError, match="source_id must not be empty"):
        state.add_unit_to_army(
            player_id="player-a",
            unit=added_unit,
            source_id=" ",
        )

    unmustered = GameState.from_config(_config())
    with pytest.raises(GameLifecycleError, match="before the player's army is mustered"):
        unmustered.add_unit_to_army(
            player_id="player-a",
            unit=added_unit,
            source_id="phase11c-add-unit-rule",
        )


def test_setup_declarations_keep_reserve_and_embarked_units_off_battlefield() -> None:
    config = _config(
        player_a_units=(
            _default_unit_selection("reserve-unit"),
            _default_unit_selection("passenger-unit"),
            _unit_selection(
                unit_selection_id="transport-unit",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        )
    )
    state = GameState.from_config(config)
    decisions = DecisionController()
    flow = SetupFlow()
    flow.advance(state=state, decisions=decisions, config=config)
    while state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        if state.current_setup_step is SetupStep.CREATE_BATTLEFIELD:
            flow.advance(state=state, decisions=decisions, config=config)
            continue
        state.complete_current_setup_step()
    reserve_unit = _unit_by_id(state, "army-alpha:reserve-unit")
    passenger = _unit_by_id(state, "army-alpha:passenger-unit")
    transport = _unit_by_id(state, "army-alpha:transport-unit")

    reserve_states = state.apply_strategic_reserve_declarations(
        declarations=(
            StrategicReserveDeclaration.for_unit(
                unit=reserve_unit,
                player_id="player-a",
                unit_points=100,
                embarked_unit_points=0,
                points_limit=100,
            ),
        ),
        destruction_deadline_policy=ReserveDestructionTimingPolicy.chapter_approved_2026_27(),
    )
    cargo_state = state.declare_battle_formation_embarkation(
        player_id="player-a",
        transport_unit_instance_id=transport.unit_instance_id,
        embarked_unit_instance_ids=(passenger.unit_instance_id,),
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id=transport.datasheet_id,
            max_model_count=10,
            allowed_keywords=("INFANTRY",),
        ),
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )

    state.complete_current_setup_step()
    deployment_status = flow.advance(state=state, decisions=decisions, config=config)
    lifecycle = GameLifecycle(decision_controller=decisions)
    lifecycle.start(config)
    lifecycle.state = state
    submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase11c-setup-deploy",
    )

    assert state.battlefield_state is not None
    assert reserve_states == (state.reserve_state_for_unit(reserve_unit.unit_instance_id),)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.player_id == cargo_state.player_id
    assert stored_cargo.transport_unit_instance_id == cargo_state.transport_unit_instance_id
    assert stored_cargo.capacity_profile == cargo_state.capacity_profile
    assert stored_cargo.embarked_unit_instance_ids == cargo_state.embarked_unit_instance_ids
    assert stored_cargo.phase_battle_round == 1
    assert (
        stored_cargo.started_phase_embarked_unit_instance_ids
        == cargo_state.embarked_unit_instance_ids
    )
    assert state.battlefield_state.unit_placement_by_id(transport.unit_instance_id)
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        state.battlefield_state.unit_placement_by_id(reserve_unit.unit_instance_id)
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        state.battlefield_state.unit_placement_by_id(passenger.unit_instance_id)
    assert set(state.battlefield_state.placed_model_ids()).isdisjoint(
        reserve_unit.own_model_ids() + passenger.own_model_ids()
    )
    assert GameState.from_payload(_game_state_payload_copy(state)).to_payload() == (
        state.to_payload()
    )


def test_setup_declarations_reject_points_and_transport_capacity_drift() -> None:
    config = _config(
        player_a_units=(
            _default_unit_selection("reserve-unit"),
            _default_unit_selection("passenger-unit"),
            _unit_selection(
                unit_selection_id="transport-unit",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        )
    )
    state = GameState.from_config(config)
    decisions = DecisionController()
    flow = SetupFlow()
    flow.advance(state=state, decisions=decisions, config=config)
    while state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        state.complete_current_setup_step()
    reserve_unit = _unit_by_id(state, "army-alpha:reserve-unit")
    passenger = _unit_by_id(state, "army-alpha:passenger-unit")
    transport = _unit_by_id(state, "army-alpha:transport-unit")

    with pytest.raises(GameLifecycleError, match="exceed the player's points limit"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=60,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
                StrategicReserveDeclaration.for_unit(
                    unit=passenger,
                    player_id="player-a",
                    unit_points=60,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
            ),
            destruction_deadline_policy=ReserveDestructionTimingPolicy.chapter_approved_2026_27(),
        )
    with pytest.raises(GameLifecycleError, match="exceeds Transport capacity"):
        state.declare_battle_formation_embarkation(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=4,
                allowed_keywords=("INFANTRY",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="capacity profile datasheet drift"):
        state.declare_battle_formation_embarkation(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="other-transport",
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
        )


def test_setup_declarations_reject_duplicate_and_drift_contexts() -> None:
    config = _config(
        player_a_units=(
            _default_unit_selection("reserve-unit"),
            _default_unit_selection("passenger-unit"),
            _unit_selection(
                unit_selection_id="transport-unit",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        )
    )
    state = _setup_state_at_declare_battle_formations(config)
    reserve_unit = _unit_by_id(state, "army-alpha:reserve-unit")
    passenger = _unit_by_id(state, "army-alpha:passenger-unit")
    transport = _unit_by_id(state, "army-alpha:transport-unit")
    policy = ReserveDestructionTimingPolicy.chapter_approved_2026_27()

    assert (
        state.apply_strategic_reserve_declarations(
            declarations=(),
            destruction_deadline_policy=policy,
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="declarations must be a tuple"):
        state.apply_strategic_reserve_declarations(
            declarations=cast(Any, []),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="ReserveDestructionTimingPolicy"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
            ),
            destruction_deadline_policy=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="must contain StrategicReserveDeclaration"):
        state.apply_strategic_reserve_declarations(
            declarations=(cast(Any, object()),),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id is unknown"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration(
                    player_id="player-a",
                    unit_instance_id="army-alpha:missing-unit",
                    reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
                    declared_during_step=SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
            ),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="player_id drift"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration(
                    player_id="player-b",
                    unit_instance_id=reserve_unit.unit_instance_id,
                    reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
                    declared_during_step=SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
            ),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="must not duplicate units"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
            ),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="use one points limit"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
                StrategicReserveDeclaration.for_unit(
                    unit=passenger,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=120,
                ),
            ),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id is unknown"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                    embarked_unit_instance_ids=("army-alpha:missing-passenger",),
                ),
            ),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="embarked unit player_id drift"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                    embarked_unit_instance_ids=("army-beta:intercessor-unit-3",),
                ),
            ),
            destruction_deadline_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="also declare embarked units"):
        state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration.for_unit(
                    unit=reserve_unit,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                    embarked_unit_instance_ids=(passenger.unit_instance_id,),
                ),
                StrategicReserveDeclaration.for_unit(
                    unit=passenger,
                    player_id="player-a",
                    unit_points=10,
                    embarked_unit_points=0,
                    points_limit=100,
                ),
            ),
            destruction_deadline_policy=policy,
        )

    with pytest.raises(GameLifecycleError, match="requires a TRANSPORT"):
        state.declare_battle_formation_embarkation(
            player_id="player-a",
            transport_unit_instance_id=reserve_unit.unit_instance_id,
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=reserve_unit.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="cannot embark itself"):
        state.declare_battle_formation_embarkation(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            embarked_unit_instance_ids=(transport.unit_instance_id,),
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="unit is unknown"):
        state.declare_battle_formation_embarkation(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            embarked_unit_instance_ids=("army-alpha:missing-passenger",),
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
        )


def test_authenticated_reposition_preserves_prior_turn_fall_back_history() -> None:
    state, decisions, registry, request, unit, _transport = _gate_of_infinity_pending_decision()
    fell_back = FellBackUnitState(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    state.record_fell_back_unit_state(fell_back)

    result, provider = _accept_gate_of_infinity_decision(
        state=state,
        decisions=decisions,
        request=request,
        unit=unit,
        result_id="phase11c-gate-preserve-fall-back-history",
    )
    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
        )
        == fell_back
    )
    assert state.primary_battlefield_departure_states[-1].source_id == provider.occurrence_id
    assert GameState.from_payload(_game_state_payload_copy(state)).to_payload() == (
        state.to_payload()
    )


def test_authenticated_reposition_preserves_prior_turn_advance_history() -> None:
    state, decisions, registry, request, unit, _transport = _gate_of_infinity_pending_decision()
    advanced = _advanced_unit_state(state=state, unit_instance_id=unit.unit_instance_id)
    state.record_advanced_unit_state(advanced)

    result, provider = _accept_gate_of_infinity_decision(
        state=state,
        decisions=decisions,
        request=request,
        unit=unit,
        result_id="phase11c-gate-preserve-advance-history",
    )
    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert (
        state.advanced_unit_state_for_unit(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
        )
        == advanced
    )
    assert state.primary_battlefield_departure_states[-1].source_id == provider.occurrence_id
    assert GameState.from_payload(_game_state_payload_copy(state)).to_payload() == (
        state.to_payload()
    )


def test_authenticated_reposition_preserves_disembark_history_and_effects() -> None:
    state, decisions, registry, request, unit, transport = _gate_of_infinity_pending_decision()
    unit_id = unit.unit_instance_id
    assert "INFANTRY" in unit.keywords
    assert "TRANSPORT" in transport.keywords
    disembarked = DisembarkedUnitState.for_mode(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit_id,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.REMAIN_STATIONARY,
    )
    effect = PersistingEffect(
        effect_id="phase11c-repositioned-effect",
        source_rule_id="phase14h-repositioned-rule",
        owner_player_id="player-a",
        target_unit_instance_ids=(unit_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id="player-a",
        ),
        effect_payload={"modifier": "phase14h-repositioned-effect"},
    )
    state.record_disembarked_unit_state(disembarked)
    state.record_persisting_effect(effect)

    result, provider = _accept_gate_of_infinity_decision(
        state=state,
        decisions=decisions,
        request=request,
        unit=unit,
        result_id="phase11c-gate-preserve-history",
    )
    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert (
        state.disembarked_unit_state_for_unit(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        == disembarked
    )
    assert effect in state.persisting_effects_for_unit(unit_id)
    reserve_state = state.reserve_state_for_unit(unit_id)
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.reserve_origin is ReserveOrigin.DURING_BATTLE_ABILITY
    assert reserve_state.source_rule_ids == (provider.source_rule_id,)
    assert state.battlefield_state is not None
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        state.battlefield_state.unit_placement_by_id(unit_id)
    assert set(state.battlefield_state.removed_model_ids).isdisjoint(unit.own_model_ids())
    (departure,) = state.primary_battlefield_departure_states
    assert departure.rules_unit_instance_id == unit_id
    assert departure.component_unit_instance_ids == (unit_id,)
    assert departure.departed_component_unit_instance_ids == (unit_id,)
    assert departure.removed_model_instance_ids == unit.own_model_ids()
    assert departure.removal_kind is BattlefieldRemovalKind.INTO_RESERVES
    assert departure.source_id == provider.occurrence_id
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


def test_repositioned_unit_rejects_invalid_contexts_before_mutation() -> None:
    state, decisions, registry, request, unit, _transport = _gate_of_infinity_pending_decision()
    unit_id = unit.unit_instance_id
    result, provider = _accept_gate_of_infinity_decision(
        state=state,
        decisions=decisions,
        request=request,
        unit=unit,
        result_id="phase11c-gate-invalid-contexts",
    )
    source_rule_ids = (provider.source_rule_id,)
    setup_state = GameState.from_config(_config())
    with pytest.raises(GameLifecycleError, match="only enter reserves during battle"):
        setup_state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id="player-a",
            unit_instance_id=unit_id,
            provider=provider,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=source_rule_ids,
        )

    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    before_events = decisions.event_log.records
    with pytest.raises(GameLifecycleError, match="ability or Stratagem reserve origin"):
        state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id="player-a",
            unit_instance_id=unit_id,
            provider=provider,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            source_rule_ids=source_rule_ids,
            required_arrival_battle_round=2,
            required_arrival_phase=BattlePhase.MOVEMENT,
            required_arrival_source_rule_id=provider.source_rule_id,
        )
    with pytest.raises(GameLifecycleError, match="reserve provider context drift"):
        state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id="player-b",
            unit_instance_id=unit_id,
            provider=provider,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=source_rule_ids,
            required_arrival_battle_round=2,
            required_arrival_phase=BattlePhase.MOVEMENT,
            required_arrival_source_rule_id=provider.source_rule_id,
        )
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.reserve_state_for_unit(unit_id) is None
    assert decisions.event_log.records == before_events

    with pytest.raises(GameLifecycleError, match="required-arrival authority drift"):
        state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id="player-a",
            unit_instance_id=unit_id,
            provider=provider,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=source_rule_ids,
            required_arrival_battle_round=3,
            required_arrival_phase=BattlePhase.MOVEMENT,
            required_arrival_source_rule_id=provider.source_rule_id,
        )
    assert state.battlefield_state is not None
    unplaced_state = GameState.from_payload(_game_state_payload_copy(state))
    assert unplaced_state.battlefield_state is not None
    unplaced_state.battlefield_state = unplaced_state.battlefield_state.without_unit_placement(
        unit_id
    )
    with pytest.raises(GameLifecycleError, match="must be on the battlefield"):
        unplaced_state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id="player-a",
            unit_instance_id=unit_id,
            provider=provider,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=source_rule_ids,
            required_arrival_battle_round=2,
            required_arrival_phase=BattlePhase.MOVEMENT,
            required_arrival_source_rule_id=provider.source_rule_id,
        )
    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    with pytest.raises(GameLifecycleError, match="non-terminal-arrival ReserveState"):
        state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id="player-a",
            unit_instance_id=unit_id,
            provider=provider,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=source_rule_ids,
            required_arrival_battle_round=2,
            required_arrival_phase=BattlePhase.MOVEMENT,
            required_arrival_source_rule_id=provider.source_rule_id,
        )


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
    unit_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    state.starting_attached_unit_records = [
        StartingAttachedUnitRecord(
            player_id="player-a",
            attached_unit_instance_id=attached_id,
            bodyguard_unit_instance_id=bodyguard_id,
            leader_unit_instance_ids=(leader_id,),
            support_unit_instance_ids=(),
            component_unit_instance_ids=(leader_id, bodyguard_id),
            starting_model_instance_ids_by_component=(
                (leader_id, unit_by_id[leader_id].own_model_ids()),
                (bodyguard_id, unit_by_id[bodyguard_id].own_model_ids()),
            ),
            starting_model_count=6,
            source_id="attached-unit-join:captain-intercessors",
        )
    ]

    recovered = state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id, bodyguard_id),
        event_log=EventLog(),
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


def test_mustered_attached_unit_uses_attached_starting_strength_until_split() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    state = GameState.from_config(_config())
    army = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _default_unit_selection("bodyguard-unit"),
                _unit_selection(
                    unit_selection_id="leader-unit",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
                _unit_selection(
                    unit_selection_id="support-unit",
                    datasheet_id="core-character-support",
                    model_profile_id="core-character-support",
                    model_count=1,
                ),
            ),
            attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader-unit",
                    bodyguard_unit_selection_id="bodyguard-unit",
                ),
                AttachmentDeclaration(
                    source_unit_selection_id="support-unit",
                    bodyguard_unit_selection_id="bodyguard-unit",
                ),
            ),
        ),
    )
    state.record_army_definition(army)

    attached_id = "attached-unit:army-alpha:bodyguard-unit"
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    support_id = "army-alpha:support-unit"
    record_ids = {record.unit_instance_id for record in state.starting_strength_records}
    attached_record = state.starting_strength_record_for_unit(attached_id)

    assert attached_record.starting_model_count == 7
    assert attached_record.single_model_starting_wounds is None
    assert bodyguard_id not in record_ids
    assert leader_id not in record_ids
    assert support_id not in record_ids
    assert state.unit_started_battle_as_attached_leader_or_support(leader_id)
    assert state.unit_started_battle_as_attached_leader_or_support(support_id)
    assert not state.unit_started_battle_as_attached_leader_or_support(bodyguard_id)
    assert tuple(
        record.attached_unit_instance_id for record in state.starting_attached_unit_records
    ) == (attached_id,)
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()

    recovered = state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id, support_id, bodyguard_id),
        event_log=EventLog(),
    )

    assert tuple(record.unit_instance_id for record in recovered) == (
        bodyguard_id,
        leader_id,
        support_id,
    )
    assert not state.army_definitions[0].attached_units
    assert state.unit_started_battle_as_attached_leader_or_support(leader_id)
    assert state.unit_started_battle_as_attached_leader_or_support(support_id)
    assert not state.unit_started_battle_as_attached_leader_or_support(bodyguard_id)
    assert state.starting_strength_record_for_unit(bodyguard_id).starting_model_count == 5
    assert state.starting_strength_record_for_unit(leader_id).single_model_starting_wounds == 5
    assert state.starting_strength_record_for_unit(support_id).single_model_starting_wounds == 4
    assert attached_id not in {
        record.unit_instance_id for record in state.starting_strength_records
    }
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_attached_unit_split_rejects_omitted_living_component() -> None:
    state, attached_id, bodyguard_id, leader_id = _attached_battle_state_for_split()
    events = EventLog()

    with pytest.raises(GameLifecycleError, match="exact alive components"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id=attached_id,
            surviving_unit_instance_ids=(leader_id,),
            event_log=events,
        )

    assert events.records == ()
    assert state.army_definitions[0].attached_units
    assert any(model.is_alive for model in _unit_by_id(state, bodyguard_id).own_models)


def test_attached_unit_split_rejects_destroyed_component_as_survivor() -> None:
    state, attached_id, bodyguard_id, leader_id = _attached_battle_state_for_split()
    for model in _unit_by_id(state, bodyguard_id).own_models:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=attached_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )

    with pytest.raises(GameLifecycleError, match="exact alive components"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id=attached_id,
            surviving_unit_instance_ids=(bodyguard_id, leader_id),
            event_log=EventLog(),
        )


def test_battle_shock_result_rejects_attached_component_target_identity() -> None:
    state, _attached_id, bodyguard_id, _leader_id = _attached_battle_state_for_split()
    bodyguard = _unit_by_id(state, bodyguard_id)
    context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=bodyguard,
        starting_strength=StartingStrengthRecord.from_unit(
            player_id="player-a",
            unit=bodyguard,
        ),
        current_model_ids=bodyguard.own_model_ids(),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase11c-component-battle-shock",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=bodyguard_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=context,
    )
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c-component-battle-shock:result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
    )

    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=bodyguard_id)
    with pytest.raises(GameLifecycleError, match="canonical rules-unit ID"):
        BattleShockedUnitState.from_rules_unit(result=failed, rules_unit=rules_unit)

    with pytest.raises(GameLifecycleError, match="canonical rules-unit"):
        state.record_battle_shock_result(failed)

    assert state.battle_shocked_unit_ids == []


@pytest.mark.parametrize("passed", [False, True])
def test_attached_root_battle_shock_result_reconciles_split_before_resolution(
    passed: bool,
) -> None:
    state, attached_id, bodyguard_id, leader_id = _attached_battle_state_for_split()
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=attached_id)
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit,
        starting_strength=state.starting_strength_record_for_unit(attached_id),
        current_model_ids=tuple(model.model_instance_id for model in rules_unit.alive_models()),
    )
    request = BattleShockTestRequest.for_unit(
        request_id=f"phase11c-split-before-result:{passed}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=attached_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        leadership_target=6,
        below_half_strength_context=context,
    )
    if passed:
        prior_failed = BattleShockResult.from_roll_state(
            result_id="phase11c-split-before-result:prior-failed",
            request=request,
            roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
        )
        state.record_battle_shock_result(prior_failed)
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll_fixed(request.spec, [3, 3] if passed else [1, 1])

    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id, bodyguard_id),
        event_log=decisions.event_log,
    )
    record_battle_shock_result_and_outcome_events(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        request=request,
        roll_state=roll_state,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=((attached_id,) if passed else ()),
        passed_state_policy=BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
        base_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.COMMAND.value,
            "source_kind": "command_battle_shock",
        },
        resolved_event_types=("battle_shock_test_resolved",),
    )

    expected_ids = () if passed else tuple(sorted((bodyguard_id, leader_id)))
    assert tuple(state.battle_shocked_unit_ids) == expected_ids
    assert (
        tuple(shocked_state.unit_instance_id for shocked_state in state.battle_shocked_unit_states)
        == expected_ids
    )


def test_attached_root_failure_records_descendant_missing_from_partial_shock_state() -> None:
    state, attached_id, bodyguard_id, leader_id = _attached_battle_state_for_split()
    attached = rules_unit_view_by_id(state=state, unit_instance_id=attached_id)
    attached_context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=attached,
        starting_strength=state.starting_strength_record_for_unit(attached_id),
        current_model_ids=tuple(model.model_instance_id for model in attached.alive_models()),
    )
    attached_request = BattleShockTestRequest.for_unit(
        request_id="phase11c-partial-successors:attached",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=attached_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        leadership_target=6,
        below_half_strength_context=attached_context,
    )
    decisions = DecisionController()
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id, bodyguard_id),
        event_log=decisions.event_log,
    )
    leader = _unit_by_id(state, leader_id)
    leader_context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=leader,
        starting_strength=state.starting_strength_record_for_unit(leader_id),
        current_model_ids=leader.own_model_ids(),
    )
    leader_request = BattleShockTestRequest.for_unit(
        request_id="phase11c-partial-successors:leader",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=leader_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=leader_context,
    )
    leader_failed = BattleShockResult.from_roll_state(
        result_id="phase11c-partial-successors:leader:result",
        request=leader_request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(leader_request.spec, [1, 1]),
    )
    state.record_battle_shock_result(leader_failed)
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    resolved = record_battle_shock_result_and_outcome_events(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        request=attached_request,
        roll_state=manager.roll_fixed(attached_request.spec, [1, 1]),
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=(),
        passed_state_policy=BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
        base_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.COMMAND.value,
            "source_kind": "command_battle_shock",
        },
        resolved_event_types=("battle_shock_test_resolved",),
    )

    assert isinstance(resolved, dict)
    assert resolved["state_update"] == "recorded_missing_battle_shocked_descendants"
    assert tuple(state.battle_shocked_unit_ids) == tuple(sorted((bodyguard_id, leader_id)))
    assert {
        shocked_state.unit_instance_id: shocked_state.source_result_id
        for shocked_state in state.battle_shocked_unit_states
    } == {
        bodyguard_id: "phase11c-partial-successors:attached:result",
        leader_id: "phase11c-partial-successors:leader:result",
    }


def test_attached_split_and_battle_shock_transfer_events_are_public_to_both_viewers() -> None:
    state, attached_id, bodyguard_id, leader_id = _attached_battle_state_for_split()
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=attached_id)
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit,
        starting_strength=state.starting_strength_record_for_unit(attached_id),
        current_model_ids=tuple(model.model_instance_id for model in rules_unit.alive_models()),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase11c-public-split-events",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=attached_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=context,
    )
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c-public-split-events:result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
    )
    state.record_battle_shock_result(failed)
    decisions = DecisionController()
    cursor = EventStreamCursor(len(decisions.event_log.records))

    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id, bodyguard_id),
        event_log=decisions.event_log,
    )
    session = LocalGameSession(lifecycle=GameLifecycle(state=state, decision_controller=decisions))
    player_a = session.events_since(cursor, viewer_player_id="player-a")
    player_b = session.events_since(cursor, viewer_player_id="player-b")
    public_types = {
        "attached_rules_unit_split_reconciled",
        "battle_shock_state_transferred_after_attached_unit_split",
    }
    player_a_events = tuple(
        event for event in player_a["events"] if event["event_type"] in public_types
    )
    player_b_events = tuple(
        event for event in player_b["events"] if event["event_type"] in public_types
    )

    assert tuple(event["event_type"] for event in player_a_events) == (
        "attached_rules_unit_split_reconciled",
        "battle_shock_state_transferred_after_attached_unit_split",
    )
    assert player_a_events == player_b_events
    public_json = json.dumps(player_a_events, sort_keys=True).lower()
    assert "reserve" not in public_json
    assert "embark" not in public_json


def test_command_battle_shock_public_event_chain_is_identical_for_both_viewers() -> None:
    decisions = DecisionController()
    state = _battle_state(
        game_id="phase11c-public-command-battle-shock-chain",
        decisions=decisions,
    )
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)
    cursor = EventStreamCursor(len(decisions.event_log.records))
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=BattleShockHookRegistry.empty(),
    )

    status = handler.begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    session = LocalGameSession(lifecycle=GameLifecycle(state=state, decision_controller=decisions))
    player_a = session.events_since(cursor, viewer_player_id="player-a")
    player_b = session.events_since(cursor, viewer_player_id="player-b")
    chain_types = {
        "battle_shock_step_snapshot_created",
        "battle_shock_modifier_applications_recorded",
        "battle_shock_test_resolved",
        "battle_shock_step_completed",
    }
    player_a_events = tuple(
        event for event in player_a["events"] if event["event_type"] in chain_types
    )
    player_b_events = tuple(
        event for event in player_b["events"] if event["event_type"] in chain_types
    )

    assert tuple(event["event_type"] for event in player_a_events) == (
        "battle_shock_step_snapshot_created",
        "battle_shock_modifier_applications_recorded",
        "battle_shock_test_resolved",
        "battle_shock_step_completed",
    )
    assert player_a_events == player_b_events


def test_attached_unit_split_recovery_rejects_invalid_survivors() -> None:
    state, attached_id, _bodyguard_id, _leader_id = _attached_battle_state_for_split()
    with pytest.raises(GameLifecycleError, match="must not include attached_unit_instance_id"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id=attached_id,
            surviving_unit_instance_ids=(attached_id,),
            event_log=EventLog(),
        )
    payload_before_missing_attached = state.to_payload()
    with pytest.raises(GameLifecycleError, match="existing StartingStrengthRecord"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id="attached-unit:typo",
            surviving_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            event_log=EventLog(),
        )
    assert state.to_payload() == payload_before_missing_attached
    with pytest.raises(GameLifecycleError, match="exact alive components"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id=attached_id,
            surviving_unit_instance_ids=("missing-unit",),
            event_log=EventLog(),
        )
    with pytest.raises(GameLifecycleError, match="exact alive components"):
        state.recover_starting_strength_after_attached_unit_split(
            player_id="player-a",
            attached_unit_instance_id=attached_id,
            surviving_unit_instance_ids=("army-beta:intercessor-unit-3",),
            event_log=EventLog(),
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
    ).with_command_phase_start_synchronous_hooks_resolved()
    assert not command_state.command_phase_start_boundary_resolved
    command_state = command_state.with_command_phase_start_boundary_resolved()
    command_state = command_state.with_command_points_granted()
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
    with pytest.raises(GameLifecycleError, match="Core CP cannot be granted"):
        CommandStepState.start(
            battle_round=1,
            active_player_id="player-a",
        ).with_command_points_granted()
    with pytest.raises(GameLifecycleError, match="before synchronous hooks resolve"):
        CommandStepState.start(
            battle_round=1,
            active_player_id="player-a",
        ).with_command_phase_start_boundary_resolved()
    synchronous_only_state = CommandStepState.start(
        battle_round=1,
        active_player_id="player-a",
    ).with_command_phase_start_synchronous_hooks_resolved()
    with pytest.raises(GameLifecycleError, match="before the Command-start boundary resolves"):
        synchronous_only_state.with_command_points_granted()
    with pytest.raises(GameLifecycleError, match="already resolved"):
        synchronous_only_state.with_command_phase_start_boundary_resolved().with_command_phase_start_boundary_resolved()
    with pytest.raises(GameLifecycleError, match="already resolved"):
        CommandStepState.start(
            battle_round=1,
            active_player_id="player-a",
        ).with_command_phase_start_synchronous_hooks_resolved().with_command_phase_start_synchronous_hooks_resolved()
    with pytest.raises(GameLifecycleError, match="before the Command-start boundary resolves"):
        CommandStepState(
            battle_round=1,
            active_player_id="player-a",
            command_phase_start_synchronous_hooks_resolved=True,
            command_phase_start_boundary_resolved=False,
            command_points_granted=True,
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
    forged_pre_step_payload = command_state.to_payload()
    forged_pre_step_payload["completed_battle_shock_test_request_ids"] = ["forged-future-request"]
    with pytest.raises(GameLifecycleError, match="snapshot or progress before its step"):
        CommandStepState.from_payload(forged_pre_step_payload)
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
    with pytest.raises(GameLifecycleError, match=r"Zero-applied capped.*cannot"):
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
    with pytest.raises(GameLifecycleError, match="must apply less than requested"):
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

    at_half_payload = context.to_payload()
    at_half_payload["is_at_half_strength"] = True
    with pytest.raises(GameLifecycleError, match="at-half payload drift"):
        BelowHalfStrengthContext.from_payload(at_half_payload)

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
    with pytest.raises(GameLifecycleError, match="starting strength units must be a tuple"):
        starting_strength_records_for_units(player_id="player-a", units=cast(Any, [unit]))
    with pytest.raises(
        GameLifecycleError, match="StartingStrengthRecord player_id must be a string"
    ):
        StartingStrengthRecord(
            player_id=cast(Any, 1),
            unit_instance_id="unit-a",
            starting_model_count=2,
            single_model_starting_wounds=None,
            source_id="test",
        )
    with pytest.raises(GameLifecycleError, match="current_model_count exceeds"):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            current_model_count=2,
            single_model_starting_wounds=5,
            single_model_wounds_remaining=5,
        )
    with pytest.raises(
        GameLifecycleError,
        match="BelowHalfStrengthContext starting_model_count must be an integer",
    ):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=cast(Any, "1"),
            current_model_count=1,
            single_model_starting_wounds=5,
            single_model_wounds_remaining=5,
        )
    with pytest.raises(
        GameLifecycleError,
        match="BelowHalfStrengthContext starting_model_count must be at least 1",
    ):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=0,
            current_model_count=0,
            single_model_starting_wounds=None,
            single_model_wounds_remaining=None,
        )
    with pytest.raises(
        GameLifecycleError,
        match="BelowHalfStrengthContext current_model_count must be an integer",
    ):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            current_model_count=cast(Any, "1"),
            single_model_starting_wounds=5,
            single_model_wounds_remaining=5,
        )
    with pytest.raises(
        GameLifecycleError,
        match="BelowHalfStrengthContext current_model_count must not be negative",
    ):
        BelowHalfStrengthContext(
            player_id="player-a",
            unit_instance_id="unit-a",
            starting_model_count=1,
            current_model_count=-1,
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
    with pytest.raises(GameLifecycleError, match="must be 2D6 or 3D6"):
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
            modified_roll=_modified_roll_from_state(failed_roll),
            total=failed_roll.current_total,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="roll_state must be a DiceRollState"):
        BattleShockResult(
            result_id="bad-roll-state",
            request=request,
            roll_state=cast(Any, object()),
            modified_roll=_modified_roll_from_state(failed_roll),
            total=failed_roll.current_total,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="roll_state spec drift"):
        BattleShockResult(
            result_id="bad-spec-drift",
            request=request,
            roll_state=wrong_spec_roll,
            modified_roll=_modified_roll_from_state(wrong_spec_roll),
            total=wrong_spec_roll.current_total,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="total drift"):
        BattleShockResult(
            result_id="bad-total",
            request=request,
            roll_state=failed_roll,
            modified_roll=_modified_roll_from_state(failed_roll),
            total=failed_roll.current_total + 1,
            leadership_target=request.leadership_target,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="leadership target drift"):
        BattleShockResult(
            result_id="bad-leadership",
            request=request,
            roll_state=failed_roll,
            modified_roll=_modified_roll_from_state(failed_roll),
            total=failed_roll.current_total,
            leadership_target=request.leadership_target + 1,
            passed=False,
        )
    with pytest.raises(GameLifecycleError, match="passed must be a bool"):
        BattleShockResult(
            result_id="bad-passed-type",
            request=request,
            roll_state=failed_roll,
            modified_roll=_modified_roll_from_state(failed_roll),
            total=failed_roll.current_total,
            leadership_target=request.leadership_target,
            passed=cast(Any, "no"),
        )
    with pytest.raises(GameLifecycleError, match="pass/fail drift"):
        BattleShockResult(
            result_id="bad-passed-drift",
            request=request,
            roll_state=failed_roll,
            modified_roll=_modified_roll_from_state(failed_roll),
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
            battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="army player drift"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-b",
            army=army,
            battlefield_state=state.battlefield_state,
            starting_strength_records=tuple(state.starting_strength_records),
            battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="require BattlefieldRuntimeState"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=cast(Any, object()),
            starting_strength_records=tuple(state.starting_strength_records),
            battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="missing StartingStrengthRecord"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=state.battlefield_state,
            starting_strength_records=(),
            battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="allow_duplicate_below_half_tests must be a bool"):
        collect_battle_shock_test_requests(
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=state.battlefield_state,
            starting_strength_records=tuple(state.starting_strength_records),
            battle_shocked_unit_ids=(),
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
            battle_shocked_unit_ids=(),
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


def _command_step_state(state: GameState) -> CommandStepState:
    if state.command_step_state is None:
        raise AssertionError("Expected command step state.")
    return state.command_step_state


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _active_battle_shock_requests(
    state: GameState,
    *,
    battle_shocked_unit_ids: tuple[str, ...] | None = None,
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
        battle_shocked_unit_ids=(
            tuple(state.battle_shocked_unit_ids)
            if battle_shocked_unit_ids is None
            else battle_shocked_unit_ids
        ),
        forced_below_starting_strength_unit_ids=forced_below_starting_strength_unit_ids,
        allow_duplicate_below_half_tests=allow_duplicate_below_half_tests,
    )


def _record_unit_battle_shocked(
    state: GameState,
    *,
    unit_instance_id: str,
) -> BattleShockedUnitState:
    unit = _unit_by_id(state, unit_instance_id)
    request = _battle_shock_request_for_unit(state, unit)
    failed = BattleShockResult.from_roll_state(
        result_id=f"phase11c-existing-shock:{unit_instance_id}",
        request=request,
        roll_state=DiceRollManager("phase11c-existing-shock").roll_fixed(
            request.spec,
            [1, 1],
        ),
    )
    state.record_battle_shock_result(failed)
    return state.battle_shocked_unit_states[-1]


def _record_fixed_battle_shock_resolution(
    *,
    state: GameState,
    request: BattleShockTestRequest,
    values: tuple[int, ...],
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    passed_state_policy: BattleShockPassedStatePolicy,
) -> dict[str, Any]:
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    resolved = record_battle_shock_result_and_outcome_events(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        request=request,
        roll_state=manager.roll_fixed(request.spec, list(values)),
        active_player_id="player-a",
        phase=phase,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        passed_state_policy=passed_state_policy,
        base_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": phase.value,
        },
        resolved_event_types=("phase11c_battle_shock_resolved",),
    )
    assert isinstance(resolved, dict)
    return cast(dict[str, Any], resolved)


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


def _modified_roll_from_state(roll_state: DiceRollState) -> ModifiedRollResult:
    return ModifiedRollResult.from_unmodified(UnmodifiedRollResult.from_state(roll_state))


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
    models_by_id = {
        model.model_instance_id: model for model in _unit_by_id(state, unit_instance_id).own_models
    }
    for model_id in removed_ids:
        model = models_by_id[model_id]
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit_instance_id,
            model_instance_id=model_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )


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


def _advanced_unit_state(*, state: GameState, unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"phase11c-advance-{unit_instance_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase11c-repositioned-advance").roll_fixed(
        request.spec,
        [3],
    )
    advance_roll = AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=advance_roll,
        ),
    )


def _gate_of_infinity_pending_decision() -> tuple[
    GameState,
    DecisionController,
    TurnEndHookRegistry,
    DecisionRequest,
    UnitInstance,
    UnitInstance,
]:
    config = _config(
        player_a_units=(
            _default_unit_selection("gate-unit"),
            _unit_selection(
                unit_selection_id="transport-unit",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        )
    )
    army, enemy_army = _mustered_armies(config)
    unit = army.unit_by_id("army-alpha:gate-unit")
    transport = army.unit_by_id("army-alpha:transport-unit")
    unit = replace(
        unit,
        faction_keywords=tuple(sorted((*unit.faction_keywords, "GREY KNIGHTS"))),
        datasheet_abilities=(
            *unit.datasheet_abilities,
            DatasheetAbilityDescriptor(
                ability_id=grey_knights_army_rule.GATE_OF_INFINITY_ABILITY_ID,
                name=grey_knights_army_rule.GATE_OF_INFINITY_ABILITY_NAME,
                source_id=grey_knights_army_rule.SOURCE_RULE_ID,
                support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                source_kind=CatalogAbilitySourceKind.DATASHEET,
                effect_description="Select this unit for Gate of Infinity.",
                timing_tags=("end_turn",),
                parameter_tokens=("strategic_reserves",),
            ),
        ),
    )
    army = replace(
        army,
        detachment_selection=DetachmentSelection(
            faction_id=grey_knights_army_rule.GREY_KNIGHTS_FACTION_ID,
            detachment_ids=("warpbane-task-force",),
        ),
        units=(unit, transport),
    )
    descriptor = _ruleset()
    battle_phase_sequence = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="phase11c-authenticated-reposition-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=battle_phase_sequence,
        setup_step_index=None,
        battle_phase_index=battle_phase_sequence.index(BattlePhase.FIGHT),
        battle_round=1,
        active_player_id="player-b",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        mission_setup=_mission_setup(),
    )
    state.record_army_definition(army)
    state.record_army_definition(enemy_army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="phase11c-authenticated-reposition-battlefield",
            armies=(army, enemy_army),
        ).battlefield_state
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_completed_command_occurrences_for_fixture(
        state,
        decisions=decisions,
        config=config,
    )
    registry = TurnEndHookRegistry.from_bindings(
        grey_knights_army_rule.runtime_contribution().turn_end_hook_bindings
    )
    request = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert request is not None
    assert request.actor_id == army.player_id
    decisions.request_decision(request)
    return state, decisions, registry, request, unit, transport


def _accept_gate_of_infinity_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    unit: UnitInstance,
    result_id: str,
) -> tuple[DecisionResult, PrimaryReserveEntryProvider]:
    use_option = next(option for option in request.options if option.option_id.endswith(":use"))
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=use_option.option_id,
    )
    decisions.submit_result(result)
    provider = primary_reserve_entry_provider_from_accepted_ability_decision(
        state=state,
        decisions=decisions,
        result=result,
        provider_id=grey_knights_army_rule.HOOK_ID,
        source_rule_id=grey_knights_army_rule.SOURCE_RULE_ID,
        target_rules_unit_instance_id=unit.unit_instance_id,
        source_terminal_event_type=grey_knights_army_rule.GATE_OF_INFINITY_USED_EVENT,
    )
    return result, provider


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if _is_center_objective_id(marker.objective_marker_id):
            return marker
    raise AssertionError("missing center objective marker")


def _center_objective_result(record: ObjectiveControlRecord) -> ObjectiveControlResult:
    for result in record.results:
        if _is_center_objective_id(result.objective_id):
            return result
    raise AssertionError("missing center objective result")


def _is_center_objective_id(objective_id: str) -> bool:
    return objective_id.endswith(("-center", "-center-central"))


def _battle_state(
    *,
    game_id: str = "phase11c-game",
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
    player_a_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    decisions: DecisionController | None = None,
) -> GameState:
    config = _config(
        game_id=game_id,
        player_a_units=player_a_units,
        player_a_attachment_declarations=player_a_attachment_declarations,
    )
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
    resolved_decisions = DecisionController() if decisions is None else decisions
    _complete_setup_through_gate(state=state, decisions=resolved_decisions, config=config)
    return state


def _attached_battle_state_for_split() -> tuple[GameState, str, str, str]:
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    attached_id = "attached-unit:army-alpha:bodyguard-unit"
    state = _battle_state(
        player_a_units=(
            _default_unit_selection("bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )
    return state, attached_id, bodyguard_id, leader_id


def _complete_setup_through_gate(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    battle_start = SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=decisions,
        config=config,
    )
    decisions.event_log.append("battle_started", battle_start.to_payload())


def _setup_state_at_declare_battle_formations(config: GameConfig) -> GameState:
    state = GameState.from_config(config)
    decisions = DecisionController()
    flow = SetupFlow()
    flow.advance(state=state, decisions=decisions, config=config)
    while state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        state.complete_current_setup_step()
    return state


def _secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "bring-it-down"),
    )


def _config(
    *,
    game_id: str = "phase11c-game",
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
    player_a_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
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
                attachment_declarations=player_a_attachment_declarations,
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
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11c-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=unit_selections,
        attachment_declarations=attachment_declarations,
    )


def _default_unit_selection(unit_selection_id: str) -> UnitMusterSelection:
    return _unit_selection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
    )


def _runtime_unit_for_selection(
    *,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> UnitInstance:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id=player_id,
            army_id=army_id,
            unit_selections=(_default_unit_selection(unit_selection_id),),
        ),
    )
    return army.unit_by_id(f"{army_id}:{unit_selection_id}")


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


def _game_state_payload_copy(state: GameState) -> GameStatePayload:
    return cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))


def _event_index(decisions: DecisionController, event_type: str) -> int:
    for index, event in enumerate(decisions.event_log.records):
        if event.event_type == event_type:
            return index
    raise AssertionError(f"missing event {event_type}")
