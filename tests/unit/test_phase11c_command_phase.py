# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.battle_shock_historical_helpers import historical_battle_shock_context_for_unit
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
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine import battle_shock as battle_shock_module
from warhammer40k_core.engine import battle_shock_event_authority as battle_event_authority
from warhammer40k_core.engine import (
    battle_shock_historical_authority as historical_battle_shock_authority,
)
from warhammer40k_core.engine import battle_shock_hooks as battle_hooks
from warhammer40k_core.engine import (
    battle_shock_lifecycle_authority,
    battle_shock_pending_authority,
    battle_shock_state_history,
    unit_move_completed_hooks,
)
from warhammer40k_core.engine import battle_shock_resolution as battle_resolution
from warhammer40k_core.engine import (
    battle_shock_resolution_authority as battle_resolution_authority,
)
from warhammer40k_core.engine import (
    battle_shock_source_family_authority as battle_source_authority,
)
from warhammer40k_core.engine import battle_shock_state as battle_state
from warhammer40k_core.engine import (
    battle_shock_stratagem_authority as battle_stratagem_authority,
)
from warhammer40k_core.engine import battle_shock_test_service as battle_test_service
from warhammer40k_core.engine import command_battle_shock_candidates as command_candidates
from warhammer40k_core.engine import (
    command_battle_shock_forced_provider_authority as forced_provider_authority,
)
from warhammer40k_core.engine import command_battle_shock_history as command_history
from warhammer40k_core.engine import (
    command_battle_shock_runtime_authority as command_runtime_authority,
)
from warhammer40k_core.engine import command_phase_start_authority as command_start_authority
from warhammer40k_core.engine import command_phase_start_hooks as command_start_hooks
from warhammer40k_core.engine import command_points as command_points_module
from warhammer40k_core.engine import sequencing as sequencing_module
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
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
    BattleShockDiceExpressionContext,
    BattleShockForcedTestApplication,
    BattleShockHookBinding,
    BattleShockHookRegistry,
    BattleShockModifierApplication,
    BattleShockModifierApplicationAuthorityContext,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
    BattleShockPendingOutcomeAuthority,
    BattleShockPendingOutcomeAuthorityContext,
    BattleShockRerollPermissionContext,
    HistoricalBattleShockContribution,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    BattleShockPassedStatePolicy,
    record_battle_shock_result_and_outcome_events,
)
from warhammer40k_core.engine.battle_shock_test_service import (
    BattleShockTestExecution,
    BattleShockTestRuntime,
    materialize_battle_shock_test_request,
    resolve_battle_shock_test,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartHookBinding,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartProviderDisposition,
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
from warhammer40k_core.engine.damage_allocation import (
    DamageKind,
    MortalWoundApplicationProgress,
    apply_damage_to_model,
    continue_mortal_wound_application,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import (
    EventLog,
    EventRecord,
    JsonValue,
    validate_json_value,
)
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
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
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
from warhammer40k_core.engine.phases import command as command_phase_module
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
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    UnitCharacteristicModifierBinding,
)
from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE
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
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleEffectSpec, RuleParameter


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


def test_remaining_p08_battle_shock_contract_edges_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-p08-contract-edges")
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    request = _battle_shock_request_for_unit(state, unit)
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c:p08-contract-edges:failed",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
    )

    with pytest.raises(GameLifecycleError, match="typed request"):
        BattleShockTestExecution(
            request=cast(BattleShockTestRequest, object()),
            resolution=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="typed resolution"):
        BattleShockTestExecution(request=request, resolution=cast(Any, object()))

    runtime = BattleShockTestRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(()),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        battle_shock_hook_registry=BattleShockHookRegistry.empty(),
    )
    resolve_values: dict[str, Any] = {
        "runtime": runtime,
        "state": state,
        "decisions": DecisionController(),
        "request_id": "phase11c:p08-contract-edges:request",
        "target_unit_instance_id": unit_id,
        "reason": BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND,
        "phase_start_battle_shocked_unit_ids": (),
        "passed_state_policy": BattleShockPassedStatePolicy.PRESERVE,
        "source_kind": "phase11c:p08-contract-edges",
        "source_payload": {},
        "resolved_event_types": ("phase11c_p08_contract_edges_resolved",),
        "pending_phase_body_status": "phase11c_p08_contract_edges_pending",
    }
    for overrides, message in (
        ({"decisions": object()}, "requires DecisionController"),
        ({"source_payload": None}, "must be an object"),
        ({"source_payload": {"game_id": "reserved"}}, "reserved fields"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            resolve_battle_shock_test(
                **{**resolve_values, **overrides}  # pyright: ignore[reportArgumentType]
            )
    with pytest.raises(GameLifecycleError, match="requires runtime authority"):
        battle_test_service.apply_stratagem_battle_shock_reroll_decision(
            runtime=cast(BattleShockTestRuntime, object()),
            state=state,
            decisions=DecisionController(),
            result=cast(DecisionResult, object()),
        )
    invalid_identifier_values: tuple[tuple[object, str], ...] = (
        ([], "must be a tuple"),
        (("a", "a"), "duplicates"),
    )
    for value, message in invalid_identifier_values:
        with pytest.raises(GameLifecycleError, match=message):
            battle_test_service._validate_identifier_tuple("identifiers", cast(Any, value))

    with pytest.raises(GameLifecycleError, match="must be a BattleShockResult"):
        battle_state.apply_battle_shock_result_state(
            state=state,
            result=cast(BattleShockResult, object()),
        )
    for drifted_request, message in (
        (replace(request, game_id="drifted-game"), "game_id drift"),
        (replace(request, battle_round=2), "battle_round drift"),
        (
            replace(
                request,
                player_id="missing-player",
                below_half_strength_context=replace(
                    request.below_half_strength_context,
                    player_id="missing-player",
                ),
            ),
            "player_id is not in this game",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_state.apply_battle_shock_result_state(
                state=state,
                result=replace(failed, request=drifted_request),
            )
    already_state = _battle_state(game_id="phase11c-p08-contract-already")
    already_request = _battle_shock_request_for_unit(
        already_state,
        _unit_by_id(already_state, unit_id),
    )
    already_failed = BattleShockResult.from_roll_state(
        result_id="phase11c:p08-contract-already:failed",
        request=already_request,
        roll_state=DiceRollManager(already_state.game_id).roll_fixed(
            already_request.spec,
            [1, 1],
        ),
    )
    assert (
        battle_state.apply_battle_shock_result_state(
            state=already_state,
            result=already_failed,
        )
        == battle_state.BATTLE_SHOCK_STATE_RECORDED
    )
    assert (
        battle_state.apply_battle_shock_result_state(
            state=already_state,
            result=already_failed,
        )
        == battle_state.BATTLE_SHOCK_STATE_ALREADY
    )
    with pytest.raises(GameLifecycleError, match="already marked"):
        battle_state.record_battle_shock_result(
            state=already_state,
            result=already_failed,
        )
    with pytest.raises(GameLifecycleError, match="not Battle-shocked"):
        battle_state.clear_battle_shock_for_rules_unit(
            state=state,
            unit_instance_id=unit_id,
        )
    with pytest.raises(GameLifecycleError, match="requires EventLog"):
        battle_state.transfer_battle_shock_after_attached_unit_split(
            state=state,
            event_log=cast(EventLog, object()),
            attached_unit_instance_id="missing-attached-unit",
            surviving_unit_instance_ids=(),
        )
    battle_state.transfer_battle_shock_after_attached_unit_split(
        state=state,
        event_log=EventLog(),
        attached_unit_instance_id="missing-attached-unit",
        surviving_unit_instance_ids=(),
    )
    with pytest.raises(GameLifecycleError, match="survivor unit is unknown"):
        battle_state._physical_unit_model_ids(
            state=state,
            unit_instance_id="missing-unit",
        )

    modifier = RollModifier(
        modifier_id="phase11c:p08-contract-modifier",
        source_id="phase11c:p08-contract-source",
        operand=-1,
    )
    permission = RerollPermission(
        source_id="phase11c:p08-contract-source",
        timing_window="after_battle_shock_roll",
        owning_player_id="player-a",
        eligible_roll_type="battle_shock_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    for contribution_overrides, message in (
        ({"dice_expression": object()}, "dice expression must be typed"),
        ({"reroll_permission": object()}, "reroll permission must be typed"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            HistoricalBattleShockContribution(**cast(Any, contribution_overrides))
    with pytest.raises(GameLifecycleError, match="requires unit IDs"):
        BattleShockForcedTestApplication(
            hook_id="phase11c:p08-contract-hook",
            source_id="phase11c:p08-contract-source",
            unit_instance_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="payload drifted"):
        BattleShockForcedTestApplication.from_payload(
            {
                "hook_id": "phase11c:p08-contract-hook",
                "source_id": "phase11c:p08-contract-source",
                "unit_instance_ids": ["unit-b", "unit-a"],
            }
        )
    with pytest.raises(GameLifecycleError, match="requires modifiers"):
        BattleShockModifierApplication(
            hook_id="phase11c:p08-contract-hook",
            source_id="phase11c:p08-contract-source",
            modifiers=(),
        )
    with pytest.raises(GameLifecycleError, match="source drifted"):
        BattleShockModifierApplication(
            hook_id="phase11c:p08-contract-hook",
            source_id="phase11c:other-source",
            modifiers=(modifier,),
        )
    no_source_modifier = RollModifier(
        modifier_id="phase11c:p08-contract-no-source",
        source_id=None,
        operand=-1,
    )
    with pytest.raises(GameLifecycleError, match="require source IDs"):
        battle_hooks.battle_shock_modifier_applications_from_modifiers(
            provider_id="phase11c:p08-contract-hook",
            modifiers=(no_source_modifier,),
        )
    application = BattleShockModifierApplication(
        hook_id="phase11c:p08-contract-hook",
        source_id="phase11c:p08-contract-source",
        modifiers=(modifier,),
    )
    authority_values: dict[str, Any] = {
        "state": state,
        "request": request,
        "application": application,
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND,
        "phase_start_battle_shocked_unit_ids": (),
    }
    for overrides, message in (
        ({"state": object()}, "requires GameState"),
        ({"request": object()}, "requires a request"),
        ({"application": object()}, "requires an application"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            BattleShockModifierApplicationAuthorityContext(
                **{**authority_values, **overrides}  # pyright: ignore[reportArgumentType]
            )
    for kwargs, message in (
        ({"result": object(), "resolved_event_index": 0}, "result must be typed"),
        ({"result": failed, "resolved_event_index": -1}, "index is invalid"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            BattleShockPendingOutcomeAuthority(**cast(Any, kwargs))
    pending_request = DecisionRequest(
        request_id="phase11c:p08-contract-pending",
        decision_type="phase11c:p08-contract-pending",
        actor_id="player-a",
        payload=None,
        options=(DecisionOption(option_id="accept", label="Accept"),),
    )
    pending_values: dict[str, Any] = {
        "state": state,
        "decisions": DecisionController(),
        "request": pending_request,
    }
    for overrides, message in (
        ({"state": object()}, "requires GameState"),
        ({"decisions": object()}, "requires DecisionController"),
        ({"request": object()}, "requires DecisionRequest"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            BattleShockPendingOutcomeAuthorityContext(
                **{**pending_values, **overrides}  # pyright: ignore[reportArgumentType]
            )

    def callable_handler(_context: object) -> None:
        return None

    invalid_bindings: tuple[tuple[dict[str, Any], str], ...] = (
        ({}, "requires at least one handler"),
        ({"forced_test_handler": object()}, "forced_test_handler must be callable"),
        ({"dice_expression_handler": object()}, "dice_expression_handler must be callable"),
        ({"modifier_handler": object()}, "modifier_handler must be callable"),
        (
            {
                "modifier_handler": callable_handler,
                "modifier_application_validator": object(),
            },
            "modifier_application_validator must be callable",
        ),
        (
            {"modifier_handler": callable_handler, "modifier_source_effect_evidence": 1},
            "source_effect_evidence must be a bool",
        ),
        (
            {
                "outcome_handler": callable_handler,
                "modifier_application_validator": callable_handler,
            },
            "modifier authority requires a modifier handler",
        ),
        (
            {
                "modifier_handler": callable_handler,
                "modifier_application_validator": callable_handler,
                "modifier_source_effect_evidence": True,
            },
            "authority path must be unambiguous",
        ),
        ({"reroll_permission_handler": object()}, "reroll_permission_handler must be callable"),
        ({"outcome_handler": object()}, "outcome_handler must be callable"),
        (
            {"outcome_handler": callable_handler, "pending_outcome_authority_validator": object()},
            "pending outcome authority validator must be callable",
        ),
        (
            {
                "forced_test_handler": callable_handler,
                "pending_outcome_authority_validator": callable_handler,
            },
            "pending outcome authority requires an outcome handler",
        ),
        (
            {"outcome_handler": callable_handler, "historical_contribution_handler": object()},
            "historical contribution handler must be callable",
        ),
    )
    for overrides, message in invalid_bindings:
        with pytest.raises(GameLifecycleError, match=message):
            BattleShockHookBinding(
                hook_id="phase11c:p08-contract-hook",
                source_id="phase11c:p08-contract-source",
                **cast(Any, overrides),
            )

    reroll_context = BattleShockRerollPermissionContext(
        state=state,
        request=request,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(),
    )
    dice_context = BattleShockDiceExpressionContext(
        state=state,
        player_id="player-a",
        unit_instance_id=unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        default_expression=DiceExpression(quantity=2, sides=6),
        phase_start_battle_shocked_unit_ids=(),
    )
    invalid_reroll_registry = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:p08-invalid-reroll",
                source_id="phase11c:p08-invalid-reroll",
                reroll_permission_handler=lambda _context: cast(RerollPermission, object()),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return RerollPermission"):
        invalid_reroll_registry.reroll_permission_for(reroll_context)
    conflicting_reroll_registry = BattleShockHookRegistry.from_bindings(
        tuple(
            BattleShockHookBinding(
                hook_id=f"phase11c:p08-reroll-{index}",
                source_id=f"phase11c:p08-reroll-{index}",
                reroll_permission_handler=lambda _context: permission,
            )
            for index in range(2)
        )
    )
    with pytest.raises(GameLifecycleError, match="Multiple Battle-shock reroll"):
        conflicting_reroll_registry.reroll_permission_for(reroll_context)
    invalid_dice_registry = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:p08-invalid-dice",
                source_id="phase11c:p08-invalid-dice",
                dice_expression_handler=lambda _context: cast(DiceExpression, object()),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return DiceExpression"):
        invalid_dice_registry.dice_expression_for(dice_context)
    conflicting_dice_registry = BattleShockHookRegistry.from_bindings(
        tuple(
            BattleShockHookBinding(
                hook_id=f"phase11c:p08-dice-{quantity}",
                source_id=f"phase11c:p08-dice-{quantity}",
                dice_expression_handler=cast(
                    Any,
                    lambda _context, q=quantity: DiceExpression(  # pyright: ignore[reportUnknownLambdaType]
                        quantity=q,
                        sides=6,
                    ),
                ),
            )
            for quantity in (3, 2)
        )
    )
    with pytest.raises(GameLifecycleError, match="conflicting overrides"):
        conflicting_dice_registry.dice_expression_for(dice_context)
    for method, message in (
        (BattleShockHookRegistry.empty().reroll_permission_for, "reroll hooks require"),
        (BattleShockHookRegistry.empty().dice_expression_for, "dice-expression hooks require"),
        (
            BattleShockHookRegistry.empty().forced_test_applications_for,
            "forced-test hooks require",
        ),
        (BattleShockHookRegistry.empty().resolve_outcomes, "outcome hooks require"),
        (
            BattleShockHookRegistry.empty().pending_outcome_authority_for,
            "outcome hooks require context",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            method(cast(Any, object()))

    generic_effect: dict[str, JsonValue] = {
        "context": {"record_persisting_effects": False},
        "effect": {"parameters": []},
    }
    assert battle_stratagem_authority._producer_effect_payload(generic_effect)["context"] == {
        "record_persisting_effects": True
    }
    with pytest.raises(GameLifecycleError, match="execution mode drifted"):
        battle_stratagem_authority._producer_effect_payload(
            {"context": {"record_persisting_effects": True}}
        )
    unchanged_event = EventRecord(
        "phase11c:p08-contract-event",
        "phase11c_p08_contract_event",
        None,
    )
    assert battle_stratagem_authority._producer_event_record(unchanged_event) == unchanged_event
    assert (
        battle_stratagem_authority._optional_int_parameter(
            generic_effect,
            "missing",
        )
        is None
    )
    assert (
        battle_stratagem_authority._optional_string_parameter(
            generic_effect,
            "missing",
        )
        is None
    )
    for payload, helper, message in (
        (
            {"effect": {"parameters": [{"key": "value", "value": "bad"}]}},
            battle_stratagem_authority._optional_int_parameter,
            "operand is invalid",
        ),
        (
            {"effect": {"parameters": [{"key": "value", "value": 1}]}},
            battle_stratagem_authority._optional_string_parameter,
            "suffix is invalid",
        ),
        (
            {"effect": {"parameters": None}},
            battle_stratagem_authority._parameter,
            "parameters are invalid",
        ),
        (
            {
                "effect": {
                    "parameters": [
                        {"key": "value", "value": 1},
                        {"key": "value", "value": 2},
                    ]
                }
            },
            battle_stratagem_authority._parameter,
            "parameter is duplicated",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            helper(cast(Any, payload), "value")
    with pytest.raises(GameLifecycleError, match="must be an object"):
        battle_stratagem_authority._object(None, "test")

    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    candidate = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )[0]
    in_flight = replace(
        request,
        request_id=command_candidates.command_battle_shock_request_id(
            battle_round=state.battle_round,
            active_player_id="player-a",
            unit_instance_id=unit_id,
            reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        ),
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
    )
    with pytest.raises(GameLifecycleError, match="in-flight request is excess"):
        command_candidates.validate_command_battle_shock_step_progress(
            battle_shock_step_started=True,
            command_points_granted=True,
            battle_shock_step_resolved=True,
            phase_start_unit_ids=(),
            candidate_inventory=(candidate,),
            candidate_order_unit_ids=(unit_id,),
            in_flight_test_request=in_flight,
            completed_test_request_ids=(in_flight.request_id,),
            battle_round=state.battle_round,
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        command_candidates._validate_identifier_tuple(
            "identifiers",
            cast(Any, []),
        )


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


def test_off_battlefield_singleton_returns_restorable_typed_command_unsupported() -> None:
    state, decisions, registry, request, unit, _transport = _gate_of_infinity_pending_decision()
    prewound = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id="phase11c-off-battlefield-restore:prewound-request",
        progress=MortalWoundApplicationProgress.start(
            application_id="phase11c-off-battlefield-restore:prewound",
            source_rule_id="phase11c:test:off-battlefield-prewound",
            source_context={"source_kind": "phase11c_off_battlefield_fixture"},
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=state,
                destroying_player_id="player-b",
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=BattlePhase.FIGHT,
                source_step="phase11c_off_battlefield_fixture",
            ),
            target_unit_instance_id=unit.unit_instance_id,
            defender_player_id="player-a",
            mortal_wounds=sum(model.wounds_remaining for model in unit.own_models[:3]),
            spill_over=True,
        ),
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )
    assert prewound.request is None
    assert prewound.application is not None
    result, _provider = _accept_gate_of_infinity_decision(
        state=state,
        decisions=decisions,
        request=request,
        unit=unit,
        result_id="phase11c-off-battlefield-restore:gate",
    )
    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    state.active_player_id = "player-a"
    state.battle_round = 2
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    state.command_step_state = None
    unit_id = unit.unit_instance_id

    handler = CommandPhaseHandler(stratagem_index=StratagemCatalogIndex.from_records(()))
    status = handler.begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert status.payload == {
        "source_rule_id": "gw-11e-core-rules:command-phase:battle-shock",
        "section_id": "08.03",
        "unit_instance_id": unit_id,
        "component_unit_instance_ids": [unit_id],
        "candidate_reasons": ["at_or_below_half_strength"],
        "unsupported_scope": "off_battlefield_battle_shock_test",
    }
    command_state = _command_step_state(state)
    assert command_state.current_step is CommandPhaseStep.BATTLE_SHOCK
    assert not command_state.battle_shock_step_resolved
    assert command_state.battle_shock_required_unit_ids == ()
    assert command_state.battle_shock_in_flight_test_request is None
    lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _command_phase_handler=handler,
    )
    restored = GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    )
    before_reentry = restored.to_payload()

    assert restored.state is not None
    reentered = handler.begin_phase(
        state=restored.state,
        decisions=restored.decision_controller,
    )

    assert reentered.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert reentered.payload == status.payload
    assert restored.to_payload() == before_reentry


def test_completed_rerolled_battle_shock_target_destruction_does_not_block_reentry() -> None:
    game_id = "phase11c-command-rerolled-self-destruction"
    unit_id = "army-alpha:intercessor-unit-1"
    state = _battle_state(game_id=game_id)
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    decisions = DecisionController()
    modifier = RollModifier(
        modifier_id="phase11c:command-self-destruction:modifier",
        source_id="phase11c:command-self-destruction:source",
        operand=-3,
    )

    def destroy_failed_target(context: BattleShockOutcomeContext) -> None:
        if context.result.passed:
            raise AssertionError("forced modifier must make the rerolled test fail")
        unit = _unit_by_id(context.state, context.result.request.unit_instance_id)
        for model in unit.own_models:
            if not model.is_alive:
                continue
            apply_damage_to_model(
                state=context.state,
                target_unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                damage=model.wounds_remaining,
                damage_kind=DamageKind.NORMAL,
            )

    def reroll_permission(
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        return RerollPermission(
            source_id="phase11c:command-self-destruction:reroll",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    hooks = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:command-self-destruction:hook",
                source_id="phase11c:command-self-destruction:source",
                modifier_handler=lambda _context: (modifier,),
                reroll_permission_handler=reroll_permission,
                outcome_handler=destroy_failed_target,
                historical_contribution_handler=lambda _context: HistoricalBattleShockContribution(
                    modifiers=(modifier,),
                    reroll_permission=RerollPermission(
                        source_id="phase11c:command-self-destruction:reroll",
                        timing_window="battle_shock_test",
                        owning_player_id="player-a",
                        eligible_roll_type="battle_shock_roll",
                        component_selection_policy=(RerollComponentSelectionPolicy.WHOLE_ROLL),
                    ),
                ),
            ),
        )
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=hooks,
    )

    waiting = handler.begin_phase(state=state, decisions=decisions)
    reroll_request = _decision_request(waiting)
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    reroll_result = DecisionResult.for_request(
        result_id="phase11c:command-self-destruction:reroll-result",
        request=reroll_request,
        selected_option_id="reroll:0,1",
    )
    decisions.submit_result(reroll_result)
    battle_shock_rerolls.apply_battle_shock_reroll_decision(
        state=state,
        result=reroll_result,
        decisions=decisions,
        battle_shock_hooks=hooks,
    )
    command_state = _command_step_state(state)
    assert len(command_state.completed_battle_shock_test_request_ids) == 1
    assert not command_state.battle_shock_step_resolved
    assert not any(model.is_alive for model in _unit_by_id(state, unit_id).own_models)

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert _command_step_state(state).battle_shock_step_resolved


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
    assert state.command_step_state.battle_shock_in_flight_test_request is not None
    restored_state = GameState.from_payload(_game_state_payload_copy(state))
    assert (
        _command_step_state(restored_state).battle_shock_in_flight_test_request
        == state.command_step_state.battle_shock_in_flight_test_request
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
    assert first_request.decision_type == SEQUENCING_DECISION_TYPE
    first_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase11c-command-battle-shock-order",
            request=first_request,
            selected_option_id=("next:command-battle-shock-test:army-alpha:intercessor-unit-1"),
        )
    )
    first_request = _decision_request(first_status)
    assert first_request.decision_type == DICE_REROLL_DECISION_TYPE
    second_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase11c-command-reroll-first-accepted",
            request=first_request,
            selected_option_id="reroll:0,1",
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
    assert command_state.battle_shock_candidate_order_unit_ids == (
        "army-alpha:intercessor-unit-1",
        "army-alpha:intercessor-unit-2",
    )
    assert len(command_state.completed_battle_shock_test_request_ids) == 1
    assert command_state.battle_shock_in_flight_test_request is not None
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


def test_ten_command_battle_shock_candidates_use_bounded_select_next_requests() -> None:
    game_id = "phase11c-command-bounded-select-next"
    unit_selections = tuple(
        _default_unit_selection(f"intercessor-unit-{index:02d}") for index in range(1, 11)
    )
    decisions = DecisionController()
    state = _battle_state(
        game_id=game_id,
        player_a_units=unit_selections,
        decisions=decisions,
    )
    for selection in unit_selections:
        _remove_first_models(
            state,
            unit_instance_id=f"army-alpha:{selection.unit_selection_id}",
            count=3,
        )
    initial_state_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload())),
    )
    initial_decisions_payload = json.loads(json.dumps(decisions.to_payload()))

    def resolve_all() -> tuple[GameState, DecisionController]:
        restored_state = GameState.from_payload(initial_state_payload)
        restored_decisions = DecisionController.from_payload(initial_decisions_payload)
        handler = CommandPhaseHandler(stratagem_index=StratagemCatalogIndex.from_records(()))
        status = handler.begin_phase(state=restored_state, decisions=restored_decisions)
        request = _decision_request(status)
        option_counts: list[int] = []
        selection_index = 0
        while request.decision_type == SEQUENCING_DECISION_TYPE:
            option_counts.append(len(request.options))
            assert len(request.options) <= 10
            assert request.payload == json.loads(json.dumps(request.payload))
            restored_state = GameState.from_payload(
                cast(
                    GameStatePayload,
                    json.loads(json.dumps(restored_state.to_payload())),
                )
            )
            restored_decisions = DecisionController.from_payload(
                json.loads(json.dumps(restored_decisions.to_payload()))
            )
            assert restored_decisions.queue.pending_requests == (request,)
            if not request.options:
                raise AssertionError("bounded sequencing request requires options")
            result = DecisionResult.for_request(
                result_id=f"phase11c-bounded-selection-{selection_index:02d}",
                request=request,
                selected_option_id=request.options[0].option_id,
            )
            record = restored_decisions.submit_result(result)
            selection = sequencing_module.apply_select_next_sequencing_participant_from_request(
                request=record.request,
                result=record.result,
            )
            restored_decisions.event_log.append(
                "sequencing_next_participant_selected",
                selection.to_payload(),
            )
            status = handler.begin_phase(
                state=restored_state,
                decisions=restored_decisions,
            )
            selection_index += 1
            command_state = _command_step_state(restored_state)
            if command_state.battle_shock_step_resolved:
                break
            request = _decision_request(status)
        assert option_counts == list(range(10, 1, -1))
        command_state = _command_step_state(restored_state)
        assert command_state.battle_shock_step_resolved
        assert len(command_state.battle_shock_candidate_order_unit_ids) == 10
        assert len(command_state.completed_battle_shock_test_request_ids) == 10
        return restored_state, restored_decisions

    first_state, first_decisions = resolve_all()
    second_state, second_decisions = resolve_all()
    assert first_state.to_payload() == second_state.to_payload()
    assert first_decisions.to_payload() == second_decisions.to_payload()


def test_restore_rejects_two_candidate_selections_before_first_test_resolves() -> None:
    selections = tuple(
        _default_unit_selection(f"intercessor-unit-{index}") for index in range(1, 4)
    )
    decisions = DecisionController()
    state = _battle_state(
        game_id="phase11c-command-premature-second-selection",
        player_a_units=selections,
        decisions=decisions,
    )
    for selection in selections:
        _remove_first_models(
            state,
            unit_instance_id=f"army-alpha:{selection.unit_selection_id}",
            count=3,
        )
    status = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(())
    ).begin_phase(state=state, decisions=decisions)
    first_request = _decision_request(status)
    first_result = DecisionResult.for_request(
        result_id="phase11c-premature-selection:first",
        request=first_request,
        selected_option_id=first_request.options[0].option_id,
    )
    first_record = decisions.submit_result(first_result)
    first_selection = sequencing_module.apply_select_next_sequencing_participant_from_request(
        request=first_record.request,
        result=first_record.result,
    )
    decisions.event_log.append(
        "sequencing_next_participant_selected",
        first_selection.to_payload(),
    )
    assert (
        command_phase_module._resolve_command_battle_shock_candidate_order(
            state=state,
            decisions=decisions,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="lacks its in-flight test authority"):
        command_history._validate_pending_candidate_order_restore_authority(
            state=state,
            pending_decision_requests=(),
        )
    first_payload = cast(dict[str, Any], first_request.payload)
    conflict = sequencing_module.SequencingConflictContext.from_payload(
        first_payload["sequencing_conflict"]
    )
    participants = tuple(
        sequencing_module.SequencingParticipant.from_payload(payload)
        for payload in first_payload["participants"]
    )
    remaining = tuple(
        participant
        for participant in participants
        if participant.participant_id != first_selection.selected_participant_id
    )
    second_request = sequencing_module.create_select_next_sequencing_participant_request(
        request_id=state.next_decision_request_id(),
        context=conflict,
        previously_selected_participant_ids=(first_selection.selected_participant_id,),
        remaining_participants=remaining,
    )
    decisions.request_decision(second_request)
    second_result = DecisionResult.for_request(
        result_id="phase11c-premature-selection:second",
        request=second_request,
        selected_option_id=second_request.options[0].option_id,
    )
    second_record = decisions.submit_result(second_result)
    second_selection = sequencing_module.apply_select_next_sequencing_participant_from_request(
        request=second_record.request,
        result=second_record.result,
    )
    decisions.event_log.append(
        "sequencing_next_participant_selected",
        second_selection.to_payload(),
    )
    command_state = _command_step_state(state)
    selected_unit_ids = tuple(
        selection.selected_participant_id.removeprefix("command-battle-shock-test:")
        for selection in (first_selection, second_selection)
    )
    candidates = {
        candidate.unit_instance_id: candidate
        for candidate in command_state.battle_shock_candidate_inventory
    }
    first_candidate = candidates[selected_unit_ids[0]]
    second_candidate = candidates[selected_unit_ids[1]]
    assert first_candidate.test_reason is not None
    assert second_candidate.test_reason is not None
    first_test_request_id = command_candidates.command_battle_shock_request_id(
        battle_round=state.battle_round,
        active_player_id="player-a",
        unit_instance_id=selected_unit_ids[0],
        reason=first_candidate.test_reason,
    )
    second_test_request = BattleShockTestRequest.for_unit(
        request_id=command_candidates.command_battle_shock_request_id(
            battle_round=state.battle_round,
            active_player_id="player-a",
            unit_instance_id=selected_unit_ids[1],
            reason=second_candidate.test_reason,
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=selected_unit_ids[1],
        reason=second_candidate.test_reason,
        leadership_target=6,
        below_half_strength_context=second_candidate.below_half_strength_context,
    )
    forged_command_state = replace(command_state)
    object.__setattr__(
        forged_command_state,
        "battle_shock_candidate_order_unit_ids",
        selected_unit_ids,
    )
    object.__setattr__(
        forged_command_state,
        "completed_battle_shock_test_request_ids",
        (first_test_request_id,),
    )
    object.__setattr__(
        forged_command_state,
        "battle_shock_in_flight_test_request",
        second_test_request,
    )
    state.command_step_state = forged_command_state

    with pytest.raises(GameLifecycleError, match="preceding test resolved"):
        command_history.validate_restore(
            state,
            decisions.event_log.records,
            decisions.records,
            (),
        )


def test_later_command_battle_shock_request_recomputes_after_prior_outcome() -> None:
    game_id = "phase11c-command-live-battle-shock-materialization"
    first_unit_id = "army-alpha:intercessor-unit-1"
    second_unit_id = "army-alpha:intercessor-unit-2"
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
    for unit_id in (first_unit_id, second_unit_id):
        _remove_first_models(state, unit_instance_id=unit_id, count=3)
    modifier_source_effect_id = "phase11c:effect:live-command-materialization"
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=modifier_source_effect_id,
            source_rule_id="phase11c:source:live-command-materialization",
            owner_player_id="player-a",
            target_unit_instance_ids=(second_unit_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.COMMAND,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload={"battle_shock_dice_expression": "3D6"},
        )
    )

    live_dice_contexts: list[tuple[str, BattleShockTestReason, bool]] = []

    def live_dice_expression(
        context: BattleShockDiceExpressionContext,
    ) -> DiceExpression | None:
        source_active = any(
            effect.effect_id == modifier_source_effect_id
            for effect in context.state.persisting_effects
        )
        live_dice_contexts.append((context.unit_instance_id, context.reason, source_active))
        if context.unit_instance_id == second_unit_id and source_active:
            return DiceExpression(quantity=3, sides=6)
        return None

    def remove_source_after_first_outcome(context: BattleShockOutcomeContext) -> None:
        if context.result.request.unit_instance_id != first_unit_id:
            return
        removed = context.state.remove_persisting_effects_by_id((modifier_source_effect_id,))
        assert tuple(effect.effect_id for effect in removed) == (modifier_source_effect_id,)

    binding = BattleShockHookBinding(
        hook_id="phase11c:hook:live-command-materialization",
        source_id="phase11c:source:live-command-materialization",
        dice_expression_handler=live_dice_expression,
        outcome_handler=remove_source_after_first_outcome,
        historical_contribution_handler=lambda _context: HistoricalBattleShockContribution(),
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
                contribution_id="phase11c:contribution:live-command-materialization",
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

    status = lifecycle.advance_until_decision_or_terminal()
    request = _decision_request(status)
    if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        status = lifecycle.submit_decision(
            DecisionResult(
                result_id="phase11c-live-materialization-decline-stratagem",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id=request.actor_id,
                selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                payload=stratagem_decline_payload(),
            )
        )
        request = _decision_request(status)
    assert request.decision_type == SEQUENCING_DECISION_TYPE
    assert live_dice_contexts == []
    serialized = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload())),
    )
    forged = cast(dict[str, Any], json.loads(json.dumps(serialized)))
    forged_state = cast(dict[str, Any], forged["state"])
    forged_command_state = cast(dict[str, Any], forged_state["command_step_state"])
    forged_command_state["battle_shock_candidate_order_unit_ids"] = [
        first_unit_id,
        second_unit_id,
    ]
    with pytest.raises(GameLifecycleError, match="sequencing"):
        GameLifecycle.from_payload(
            cast(GameLifecyclePayload, forged),
            runtime_content_bundle=bundle,
        )
    lifecycle = GameLifecycle.from_payload(
        serialized,
        runtime_content_bundle=bundle,
    )
    restored_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert restored_request == request
    request = restored_request

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase11c-live-materialization-order",
            request=request,
            selected_option_id=f"next:command-battle-shock-test:{first_unit_id}",
        )
    )

    assert live_dice_contexts == [
        (first_unit_id, BattleShockTestReason.COMMAND_PHASE_REQUIRED, True),
        (second_unit_id, BattleShockTestReason.COMMAND_PHASE_REQUIRED, False),
    ]
    assert lifecycle.state is not None
    assert all(
        effect.effect_id != modifier_source_effect_id
        for effect in lifecycle.state.persisting_effects
    )
    requested_payloads = [
        cast(dict[str, Any], event.payload)["battle_shock_test_request"]
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "battle_shock_test_requested"
    ]
    assert [payload["unit_instance_id"] for payload in requested_payloads] == [
        first_unit_id,
        second_unit_id,
    ]
    assert [payload["spec"]["expression"]["quantity"] for payload in requested_payloads] == [
        2,
        2,
    ]


def test_command_materialization_passes_forced_candidate_reason_to_dice_hook() -> None:
    state = _battle_state(game_id="phase11c-command-forced-reason")
    decisions = DecisionController()
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=1)
    observed_reasons: list[BattleShockTestReason] = []

    def dice_expression(
        context: BattleShockDiceExpressionContext,
    ) -> DiceExpression | None:
        observed_reasons.append(context.reason)
        return None

    hooks = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook:forced-reason",
                source_id="phase11c:source:forced-reason",
                forced_test_handler=lambda _context: (unit_id,),
                dice_expression_handler=dice_expression,
            ),
        )
    )

    status = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=hooks,
    ).begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert observed_reasons == [BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED]


def test_command_battle_shock_candidate_snapshot_round_trips_and_fails_closed() -> None:
    first_unit_id = "army-alpha:intercessor-unit-1"
    second_unit_id = "army-alpha:intercessor-unit-2"
    state = _battle_state(
        game_id="phase11c-command-candidate-validation",
        player_a_units=(
            _default_unit_selection("intercessor-unit-1"),
            _default_unit_selection("intercessor-unit-2"),
        ),
    )
    _remove_first_models(state, unit_instance_id=first_unit_id, count=3)
    _record_unit_battle_shocked(state, unit_instance_id=second_unit_id)
    forced_application = BattleShockForcedTestApplication(
        hook_id="phase11c:hook:candidate-validation",
        source_id="phase11c:source:candidate-validation",
        unit_instance_ids=(first_unit_id,),
    )
    inventory = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (forced_application,),
    )
    first, second = inventory

    assert tuple(candidate.unit_instance_id for candidate in inventory) == (
        first_unit_id,
        second_unit_id,
    )
    assert first.test_reason is BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED
    assert second.test_reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
    assert command_candidates.forced_test_unit_ids((forced_application,)) == (first_unit_id,)
    assert command_candidates.forced_test_applications_from_candidate_inventory(inventory) == (
        forced_application,
    )
    for candidate in inventory:
        assert (
            command_candidates.CommandBattleShockCandidate.from_payload(candidate.to_payload())
            == candidate
        )
    assert (
        command_candidates.validate_command_battle_shock_candidate_inventory(
            inventory,
            active_player_id="player-a",
            phase_start_battle_shocked_unit_ids=(second_unit_id,),
        )
        == inventory
    )
    assert (
        command_candidates.command_battle_shock_eligibility_reason_from_token(
            command_candidates.CommandBattleShockEligibilityReason.CURRENTLY_BATTLE_SHOCKED
        )
        is command_candidates.CommandBattleShockEligibilityReason.CURRENTLY_BATTLE_SHOCKED
    )

    payload_with_extra_field = cast(dict[str, Any], first.to_payload())
    payload_with_extra_field["unexpected"] = True
    player_drift_candidate = replace(
        first,
        below_half_strength_context=replace(
            first.below_half_strength_context,
            player_id="player-b",
        ),
    )
    malformed_calls = (
        lambda: command_candidates.CommandBattleShockCandidate.from_payload(
            cast(command_candidates.CommandBattleShockCandidatePayload, payload_with_extra_field)
        ),
        lambda: replace(first, component_unit_instance_ids=()),
        lambda: replace(first, component_unit_instance_ids=(first_unit_id, first_unit_id)),
        lambda: replace(first, is_battle_shocked=cast(bool, 1)),
        lambda: replace(
            first,
            below_half_strength_context=cast(BelowHalfStrengthContext, object()),
        ),
        lambda: replace(
            first,
            below_half_strength_context=replace(
                first.below_half_strength_context,
                current_model_count=0,
            ),
        ),
        lambda: replace(first, eligibility_reasons=()),
        lambda: replace(
            first,
            eligibility_reasons=cast(
                tuple[command_candidates.CommandBattleShockEligibilityReason, ...],
                [],
            ),
        ),
        lambda: replace(
            first,
            eligibility_reasons=(
                command_candidates.CommandBattleShockEligibilityReason.AT_OR_BELOW_HALF_STRENGTH,
                command_candidates.CommandBattleShockEligibilityReason.AT_OR_BELOW_HALF_STRENGTH,
                command_candidates.CommandBattleShockEligibilityReason.BELOW_STARTING_STRENGTH_FORCED,
            ),
        ),
        lambda: replace(
            first,
            forced_test_applications=(
                BattleShockForcedTestApplication(
                    hook_id=forced_application.hook_id,
                    source_id=forced_application.source_id,
                    unit_instance_ids=(second_unit_id,),
                ),
            ),
        ),
        lambda: command_candidates.CommandBattleShockCandidate(
            unit_instance_id=second_unit_id,
            component_unit_instance_ids=(second_unit_id,),
            is_battle_shocked=True,
            below_half_strength_context=second.below_half_strength_context,
            eligibility_reasons=(
                command_candidates.CommandBattleShockEligibilityReason.CURRENTLY_BATTLE_SHOCKED,
                command_candidates.CommandBattleShockEligibilityReason.BELOW_STARTING_STRENGTH_FORCED,
            ),
            forced_test_applications=(
                BattleShockForcedTestApplication(
                    hook_id=forced_application.hook_id,
                    source_id=forced_application.source_id,
                    unit_instance_ids=(second_unit_id,),
                ),
            ),
        ),
        lambda: command_candidates.command_battle_shock_candidate_inventory(
            cast(GameState, object()),
            "player-a",
            (),
        ),
        lambda: command_candidates.command_battle_shock_candidate_inventory(
            state,
            "player-missing",
            (),
        ),
        lambda: command_candidates.command_battle_shock_candidate_inventory(
            state,
            "player-a",
            (
                BattleShockForcedTestApplication(
                    hook_id="phase11c:hook:missing-target",
                    source_id="phase11c:source:missing-target",
                    unit_instance_ids=("army-alpha:missing-unit",),
                ),
            ),
        ),
        lambda: command_candidates.command_battle_shock_candidate_inventory(
            state,
            "player-a",
            (forced_application, forced_application),
        ),
        lambda: command_candidates.forced_test_unit_ids(cast(Any, [])),
        lambda: command_candidates.forced_test_applications_from_candidate_inventory(cast(Any, [])),
        lambda: command_candidates.validate_command_battle_shock_candidate_inventory(
            cast(Any, []),
            active_player_id="player-a",
            phase_start_battle_shocked_unit_ids=(second_unit_id,),
        ),
        lambda: command_candidates.validate_command_battle_shock_candidate_inventory(
            tuple(reversed(inventory)),
            active_player_id="player-a",
            phase_start_battle_shocked_unit_ids=(second_unit_id,),
        ),
        lambda: command_candidates.validate_command_battle_shock_candidate_inventory(
            (first, first),
            active_player_id="player-a",
            phase_start_battle_shocked_unit_ids=(),
        ),
        lambda: command_candidates.validate_command_battle_shock_candidate_inventory(
            (player_drift_candidate, second),
            active_player_id="player-a",
            phase_start_battle_shocked_unit_ids=(second_unit_id,),
        ),
        lambda: command_candidates.validate_command_battle_shock_candidate_inventory(
            inventory,
            active_player_id="player-a",
            phase_start_battle_shocked_unit_ids=(),
        ),
        lambda: command_candidates.command_battle_shock_eligibility_reason_from_token(1),
        lambda: command_candidates.command_battle_shock_eligibility_reason_from_token(
            "unsupported"
        ),
        lambda: command_candidates.command_battle_shock_request_id(
            battle_round=0,
            active_player_id="player-a",
            unit_instance_id=first_unit_id,
            reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        ),
        lambda: command_candidates.command_battle_shock_request_id(
            battle_round=1,
            active_player_id="player-a",
            unit_instance_id=first_unit_id,
            reason=cast(BattleShockTestReason, "unsupported"),
        ),
    )
    for malformed_call in malformed_calls:
        with pytest.raises(GameLifecycleError):
            malformed_call()


def test_command_battle_shock_progress_requires_exact_live_request_prefix() -> None:
    first_unit_id = "army-alpha:intercessor-unit-1"
    second_unit_id = "army-alpha:intercessor-unit-2"
    state = _battle_state(
        game_id="phase11c-command-progress-validation",
        player_a_units=(
            _default_unit_selection("intercessor-unit-1"),
            _default_unit_selection("intercessor-unit-2"),
        ),
    )
    _remove_first_models(state, unit_instance_id=first_unit_id, count=3)
    _record_unit_battle_shocked(state, unit_instance_id=second_unit_id)
    inventory = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )
    order = (first_unit_id, second_unit_id)
    first_candidate = inventory[0]
    first_request_id = command_candidates.command_battle_shock_request_id(
        battle_round=1,
        active_player_id="player-a",
        unit_instance_id=first_unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
    )
    second_request_id = command_candidates.command_battle_shock_request_id(
        battle_round=1,
        active_player_id="player-a",
        unit_instance_id=second_unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
    )
    in_flight = BattleShockTestRequest.for_unit(
        request_id=first_request_id,
        game_id=state.game_id,
        battle_round=1,
        player_id="player-a",
        unit_instance_id=first_unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        leadership_target=6,
        below_half_strength_context=first_candidate.below_half_strength_context,
    )

    def validate(**overrides: Any) -> None:
        values: dict[str, Any] = {
            "battle_shock_step_started": True,
            "command_points_granted": True,
            "battle_shock_step_resolved": False,
            "phase_start_unit_ids": (second_unit_id,),
            "candidate_inventory": inventory,
            "candidate_order_unit_ids": (first_unit_id,),
            "in_flight_test_request": in_flight,
            "completed_test_request_ids": (),
            "battle_round": 1,
            "active_player_id": "player-a",
        }
        values.update(overrides)
        command_candidates.validate_command_battle_shock_step_progress(**values)

    validate()
    validate(candidate_order_unit_ids=(), in_flight_test_request=None)
    validate(
        candidate_order_unit_ids=order,
        in_flight_test_request=None,
        completed_test_request_ids=(first_request_id, second_request_id),
        battle_shock_step_resolved=True,
    )
    invalid_progress = (
        {"command_points_granted": False},
        {
            "battle_shock_step_started": False,
            "battle_shock_step_resolved": True,
            "candidate_inventory": (),
            "candidate_order_unit_ids": (),
            "in_flight_test_request": None,
            "phase_start_unit_ids": (),
        },
        {
            "battle_shock_step_started": False,
            "candidate_inventory": inventory,
            "candidate_order_unit_ids": (),
            "in_flight_test_request": None,
        },
        {"candidate_order_unit_ids": ()},
        {
            "candidate_order_unit_ids": order,
        },
        {
            "in_flight_test_request": None,
            "completed_test_request_ids": (second_request_id,),
        },
        {
            "candidate_order_unit_ids": order,
            "completed_test_request_ids": (first_request_id, second_request_id),
        },
        {
            "in_flight_test_request": replace(in_flight, request_id="battle-shock:forged"),
        },
        {
            "in_flight_test_request": None,
            "completed_test_request_ids": (first_request_id,),
            "battle_shock_step_resolved": True,
        },
    )
    for overrides in invalid_progress:
        with pytest.raises(GameLifecycleError):
            validate(**overrides)


def test_live_battle_shock_materializer_validates_current_runtime_boundary() -> None:
    game_id = "phase11c-live-materializer-validation"
    config = _config(game_id=game_id)
    state = _battle_state(game_id=game_id)
    unit_id = "army-alpha:intercessor-unit-1"
    armies = tuple(state.army_definitions)
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=armies,
            catalog=config.army_catalog,
        ),
        armies=armies,
        catalog=config.army_catalog,
        contributions=(),
    )
    runtime = BattleShockTestRuntime.from_runtime_content_bundle(bundle)
    request_id = command_candidates.command_battle_shock_request_id(
        battle_round=state.battle_round,
        active_player_id="player-a",
        unit_instance_id=unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
    )

    def materialize(**overrides: Any) -> BattleShockTestRequest:
        values: dict[str, Any] = {
            "runtime": runtime,
            "state": state,
            "request_id": request_id,
            "target_unit_instance_id": unit_id,
            "reason": BattleShockTestReason.COMMAND_PHASE_REQUIRED,
            "active_player_id": "player-a",
            "phase": BattlePhase.COMMAND,
            "phase_start_battle_shocked_unit_ids": (),
        }
        values.update(overrides)
        return materialize_battle_shock_test_request(**values)

    request = materialize()
    assert request.unit_instance_id == unit_id
    assert request.spec.expression == DiceExpression(quantity=2, sides=6)
    assert request.leadership_target == 6

    invalid_runtime_calls: tuple[Callable[[], object], ...] = (
        lambda: BattleShockTestRuntime.from_runtime_content_bundle(cast(Any, object())),
        lambda: BattleShockTestRuntime(
            ability_indexes_by_player_id=cast(Any, ()),
            runtime_modifier_registry=runtime.runtime_modifier_registry,
            battle_shock_hook_registry=runtime.battle_shock_hook_registry,
        ),
        lambda: BattleShockTestRuntime(
            ability_indexes_by_player_id={"player-a": cast(Any, object())},
            runtime_modifier_registry=runtime.runtime_modifier_registry,
            battle_shock_hook_registry=runtime.battle_shock_hook_registry,
        ),
        lambda: BattleShockTestRuntime(
            ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
            runtime_modifier_registry=cast(Any, object()),
            battle_shock_hook_registry=runtime.battle_shock_hook_registry,
        ),
        lambda: BattleShockTestRuntime(
            ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
            runtime_modifier_registry=runtime.runtime_modifier_registry,
            battle_shock_hook_registry=cast(Any, object()),
        ),
    )
    for invalid_runtime_call in invalid_runtime_calls:
        with pytest.raises(GameLifecycleError):
            invalid_runtime_call()

    missing_index_runtime = BattleShockTestRuntime(
        ability_indexes_by_player_id={},
        runtime_modifier_registry=runtime.runtime_modifier_registry,
        battle_shock_hook_registry=runtime.battle_shock_hook_registry,
    )
    invalid_materializations = (
        {"runtime": cast(Any, object())},
        {"state": cast(Any, object())},
        {"request_id": ""},
        {"target_unit_instance_id": ""},
        {"reason": cast(Any, "unsupported")},
        {"active_player_id": "player-b"},
        {"phase": BattlePhase.MOVEMENT},
        {"phase_start_battle_shocked_unit_ids": ("unit-b", "unit-a")},
        {"phase_start_battle_shocked_unit_ids": ("unit-a", "unit-a")},
        {"runtime": missing_index_runtime},
    )
    for overrides in invalid_materializations:
        with pytest.raises(GameLifecycleError):
            materialize(**overrides)

    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(unit_id)
    with pytest.raises(GameLifecycleError, match="every alive model"):
        materialize()


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "missing_anchor",
        "missing_snapshot",
        "missing_request",
        "missing_dice",
        "missing_result",
        "missing_completion",
        "anchor_extra",
        "anchor_game",
        "anchor_phase",
        "snapshot_extra",
        "snapshot_game",
        "snapshot_round",
        "snapshot_player",
        "snapshot_phase",
        "snapshot_phase_start_type",
        "snapshot_phase_start_order",
        "snapshot_candidates_type",
        "completion_extra",
        "completion_game",
        "completion_round",
        "completion_player",
        "completion_phase",
        "completion_count",
        "completion_results_type",
        "completion_completed_ids",
        "completion_before_result",
        "result_phase",
        "result_game",
        "result_round",
        "result_active_player",
        "result_extra",
        "result_auto_passed_type",
        "result_cleared_type",
        "result_cleared_duplicate",
        "result_cleared_blank",
        "result_state_update_missing",
        "result_payload_type",
        "result_unknown_request",
        "duplicate_snapshot",
        "duplicate_request",
        "duplicate_dice",
        "duplicate_result",
        "duplicate_completion",
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
    elif tamper_kind.startswith("duplicate_"):
        duplicated_event_type = {
            "duplicate_snapshot": "battle_shock_step_snapshot_created",
            "duplicate_request": "battle_shock_test_requested",
            "duplicate_dice": "dice_rolled",
            "duplicate_result": "battle_shock_test_resolved",
            "duplicate_completion": "battle_shock_step_completed",
        }[tamper_kind]
        duplicated_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == duplicated_event_type
        )
        events.insert(
            duplicated_index + 1,
            cast(dict[str, Any], json.loads(json.dumps(events[duplicated_index]))),
        )
        for index, event in enumerate(events, start=1):
            event["event_id"] = f"event-{index:06d}"
    elif tamper_kind.startswith("anchor_"):
        anchor_event = next(
            event for event in events if event["event_type"] == "command_step_started"
        )
        anchor_payload = cast(dict[str, Any], anchor_event["payload"])
        if tamper_kind == "anchor_extra":
            anchor_payload["unexpected"] = True
        elif tamper_kind == "anchor_game":
            anchor_payload["game_id"] = "forged-game"
        else:
            anchor_payload["phase"] = BattlePhase.MOVEMENT.value
    elif tamper_kind.startswith("snapshot_"):
        snapshot_event = next(
            event for event in events if event["event_type"] == "battle_shock_step_snapshot_created"
        )
        snapshot_payload = cast(dict[str, Any], snapshot_event["payload"])
        if tamper_kind == "snapshot_extra":
            snapshot_payload["unexpected"] = True
        elif tamper_kind == "snapshot_game":
            snapshot_payload["game_id"] = "forged-game"
        elif tamper_kind == "snapshot_round":
            snapshot_payload["battle_round"] = 2
        elif tamper_kind == "snapshot_player":
            snapshot_payload["active_player_id"] = "player-b"
        elif tamper_kind == "snapshot_phase":
            snapshot_payload["phase"] = BattlePhase.MOVEMENT.value
        elif tamper_kind == "snapshot_phase_start_type":
            snapshot_payload["battle_shock_phase_start_unit_ids"] = "not-a-list"
        elif tamper_kind == "snapshot_phase_start_order":
            unit_id = "army-alpha:intercessor-unit-1"
            snapshot_payload["battle_shock_phase_start_unit_ids"] = [unit_id, unit_id]
        elif tamper_kind == "snapshot_candidates_type":
            snapshot_payload["battle_shock_candidate_inventory"] = "not-a-list"
        else:
            candidates = cast(
                list[dict[str, Any]],
                snapshot_payload["battle_shock_candidate_inventory"],
            )
            eligible = next(
                candidate for candidate in candidates if candidate["eligibility_reasons"]
            )
            eligible["eligibility_reasons"] = []
            context = eligible["below_half_strength_context"]
            context["current_model_count"] = 3
            context["is_below_starting_strength"] = True
            context["is_at_half_strength"] = False
            context["is_below_half_strength"] = False
    elif tamper_kind.startswith("completion_"):
        completion_event = next(
            event for event in events if event["event_type"] == "battle_shock_step_completed"
        )
        completion_payload = cast(dict[str, Any], completion_event["payload"])
        if tamper_kind == "completion_extra":
            completion_payload["unexpected"] = True
        elif tamper_kind == "completion_game":
            completion_payload["game_id"] = "forged-game"
        elif tamper_kind == "completion_round":
            completion_payload["battle_round"] = 2
        elif tamper_kind == "completion_player":
            completion_payload["active_player_id"] = "player-b"
        elif tamper_kind == "completion_count":
            completion_payload["battle_shock_test_count"] = 99
        elif tamper_kind == "completion_results_type":
            completion_payload["battle_shock_results"] = None
        elif tamper_kind == "completion_completed_ids":
            completion_payload["completed_battle_shock_test_request_ids"] = []
        elif tamper_kind == "completion_before_result":
            result_index = next(
                index
                for index, event in enumerate(events)
                if event["event_type"] == "battle_shock_test_resolved"
            )
            completion_index = events.index(completion_event)
            events.insert(result_index, events.pop(completion_index))
            for index, event in enumerate(events, start=1):
                event["event_id"] = f"event-{index:06d}"
        else:
            completion_payload["phase"] = BattlePhase.MOVEMENT.value
    elif tamper_kind.startswith("result_"):
        result_event = next(
            event for event in events if event["event_type"] == "battle_shock_test_resolved"
        )
        result_payload = cast(dict[str, Any], result_event["payload"])
        if tamper_kind == "result_phase":
            result_payload["phase"] = BattlePhase.MOVEMENT.value
        elif tamper_kind == "result_game":
            result_payload["game_id"] = "forged-game"
        elif tamper_kind == "result_round":
            result_payload["battle_round"] = 2
        elif tamper_kind == "result_active_player":
            result_payload["active_player_id"] = "player-b"
        elif tamper_kind == "result_extra":
            result_payload["unexpected"] = True
        elif tamper_kind == "result_auto_passed_type":
            result_payload["auto_passed"] = 1
        elif tamper_kind == "result_cleared_type":
            result_payload["cleared_battle_shocked_unit_ids"] = "not-a-list"
        elif tamper_kind == "result_cleared_blank":
            result_payload["cleared_battle_shocked_unit_ids"] = [""]
        elif tamper_kind == "result_state_update_missing":
            result_payload.pop("state_update")
        elif tamper_kind == "result_payload_type":
            result_payload["battle_shock_result"] = None
        elif tamper_kind == "result_unknown_request":
            result_payload["battle_shock_result"]["request"]["request_id"] = "battle-shock:forged"
        else:
            unit_id = "army-alpha:intercessor-unit-1"
            result_payload["cleared_battle_shocked_unit_ids"] = [unit_id, unit_id]
    elif tamper_kind == "drifted_result_state_update":
        result_event = next(
            event for event in events if event["event_type"] == "battle_shock_test_resolved"
        )
        result_event["payload"]["state_update"] = "forged_update"
    else:
        completion_event = next(
            event for event in events if event["event_type"] == "battle_shock_step_completed"
        )
        completion_event["payload"]["battle_shock_results"] = []

    with pytest.raises(GameLifecycleError, match=r"Command|Battle-shock|Historical"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_command_battle_shock_history_contract_helpers_fail_closed() -> None:
    unit_id = "army-alpha:intercessor-unit-1"
    state = _battle_state(game_id="phase11c-command-history-helpers")
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    inventory = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )
    candidate = inventory[0]
    reason = candidate.test_reason
    assert reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
    request = BattleShockTestRequest.for_unit(
        request_id=command_candidates.command_battle_shock_request_id(
            battle_round=state.battle_round,
            active_player_id="player-a",
            unit_instance_id=unit_id,
            reason=reason,
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_id,
        reason=reason,
        leadership_target=6,
        below_half_strength_context=candidate.below_half_strength_context,
    )

    command_step = (
        CommandStepState.start(
            battle_round=state.battle_round,
            active_player_id="player-a",
        )
        .with_command_phase_start_synchronous_hooks_resolved()
        .with_command_phase_start_boundary_resolved()
        .with_command_points_granted()
        .enter_battle_shock_step(
            phase_start_battle_shocked_unit_ids=(),
            candidate_inventory=inventory,
        )
    )
    state.command_step_state = command_step
    snapshot_log = EventLog()
    command_history.record_command_battle_shock_snapshot(
        state=state,
        event_log=snapshot_log,
    )
    (snapshot_event,) = snapshot_log.records
    assert (
        command_history.validate_command_battle_shock_snapshot_authority(
            state=state,
            event_records=(snapshot_event,),
        )
        == 0
    )
    with pytest.raises(GameLifecycleError, match="requires EventLog"):
        command_history.record_command_battle_shock_snapshot(
            state=state,
            event_log=cast(EventLog, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires event records"):
        command_history.validate_command_battle_shock_snapshot_authority(
            state=state,
            event_records=cast(tuple[EventRecord, ...], [snapshot_event]),
        )
    snapshot_payload = cast(dict[str, Any], snapshot_event.payload)
    for payload, message in (
        ({**snapshot_payload, "game_id": "other-game"}, "exactly one"),
        ({**snapshot_payload, "battle_round": 2}, "exactly one"),
        ({**snapshot_payload, "active_player_id": "player-b"}, "exactly one"),
        ({**snapshot_payload, "unexpected": True}, "payload shape"),
        ({**snapshot_payload, "phase": BattlePhase.MOVEMENT.value}, "phase drift"),
        (
            {
                **snapshot_payload,
                "battle_shock_phase_start_unit_ids": [unit_id],
            },
            "authority drift",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            command_history.validate_command_battle_shock_snapshot_authority(
                state=state,
                event_records=(replace(snapshot_event, payload=payload),),
            )
    with pytest.raises(GameLifecycleError, match="exactly one"):
        command_history.validate_command_battle_shock_snapshot_authority(
            state=state,
            event_records=(snapshot_event, snapshot_event),
        )
    pre_step = CommandStepState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    state.command_step_state = pre_step
    with pytest.raises(GameLifecycleError, match="requires Battle-shock step"):
        command_history.validate_command_battle_shock_snapshot_authority(
            state=state,
            event_records=(),
        )
    with pytest.raises(GameLifecycleError, match="requires Battle-shock step"):
        command_history._command_battle_shock_snapshot_payload(state=state)
    state.command_step_state = command_step

    def corrupted_step(**field_values: Any) -> CommandStepState:
        value = replace(command_step)
        for field_name, field_value in field_values.items():
            object.__setattr__(value, field_name, field_value)
        return value

    wrong_game_request = replace(request, game_id="other-game")
    wrong_reason_request = replace(request)
    object.__setattr__(wrong_reason_request, "reason", BattleShockTestReason.FORCED_BY_ARMY_RULE)
    wrong_id_request = replace(request, request_id="battle-shock:wrong")
    unknown_unit_request = replace(request)
    object.__setattr__(unknown_unit_request, "unit_instance_id", "missing-unit")
    object.__setattr__(
        unknown_unit_request,
        "request_id",
        command_candidates.command_battle_shock_request_id(
            battle_round=state.battle_round,
            active_player_id="player-a",
            unit_instance_id="missing-unit",
            reason=request.reason,
        ),
    )
    unknown_candidate = replace(candidate)
    object.__setattr__(unknown_candidate, "unit_instance_id", "missing-unit")
    corrupted_states = (
        (
            corrupted_step(battle_shock_in_flight_test_request=wrong_game_request),
            "game_id drift",
        ),
        (
            corrupted_step(battle_shock_in_flight_test_request=wrong_reason_request),
            "reason drift",
        ),
        (
            corrupted_step(battle_shock_in_flight_test_request=wrong_id_request),
            "request_id drift",
        ),
        (
            corrupted_step(battle_shock_in_flight_test_request=unknown_unit_request),
            "unit is not canonical",
        ),
        (
            corrupted_step(battle_shock_phase_start_unit_ids=("missing-unit",)),
            "phase-start unit is not canonical",
        ),
        (
            corrupted_step(battle_shock_candidate_inventory=(unknown_candidate,)),
            "candidate unit is not canonical",
        ),
    )
    for corrupt_state, message in corrupted_states:
        state.command_step_state = corrupt_state
        with pytest.raises(GameLifecycleError, match=message):
            command_history.validate_command_battle_shock_state_snapshot(state=state)
    state.command_step_state = command_step

    assert command_history._payload_object({"value": "ok"}) == {"value": "ok"}
    with pytest.raises(GameLifecycleError, match="must be an object"):
        command_history._payload_object(1)

    raw_request_payload = validate_json_value(
        {"battle_shock_result": {"request": {"request_id": request.request_id}}}
    )
    assert command_history._raw_result_request_id(raw_request_payload) == request.request_id
    raw_result_values: tuple[JsonValue, ...] = (
        None,
        {},
        {"battle_shock_result": None},
        {"battle_shock_result": {}},
        {"battle_shock_result": {"request": None}},
        {"battle_shock_result": {"request": {"request_id": 1}}},
    )
    for raw_result_value in raw_result_values:
        assert command_history._raw_result_request_id(cast(Any, raw_result_value)) is None

    assert (
        command_history._payload_string(
            {"field": "value"},
            "field",
        )
        == "value"
    )
    assert (
        command_history._payload_int(
            {"field": 2},
            "field",
        )
        == 2
    )
    for payload, helper in (
        ({}, command_history._payload_string),
        ({"field": ""}, command_history._payload_string),
        ({}, command_history._payload_int),
        ({"field": True}, command_history._payload_int),
    ):
        with pytest.raises(GameLifecycleError):
            helper(cast(Any, payload), "field")

    command_history._validate_request_against_candidate(
        request=request,
        candidate=candidate,
    )
    assert (
        command_history._candidate_by_id(
            inventory,
            unit_id,
        )
        == candidate
    )
    for candidates, requested_unit_id in (
        (inventory, "missing-unit"),
        ((candidate, candidate), unit_id),
    ):
        with pytest.raises(GameLifecycleError, match="ambiguous"):
            command_history._candidate_by_id(
                candidates,
                requested_unit_id,
            )
    with pytest.raises(GameLifecycleError, match="eligibility snapshot"):
        command_history._validate_request_against_candidate(
            request=replace(request, reason=BattleShockTestReason.BELOW_HALF_STRENGTH),
            candidate=candidate,
        )
    with pytest.raises(GameLifecycleError, match="CommandStepState"):
        command_history._ordered_candidates_by_request_id(object())

    option = DecisionOption(option_id="accept", label="Accept")

    def sequencing_request(*, request_id: str, payload: Any) -> DecisionRequest:
        return DecisionRequest(
            request_id=request_id,
            decision_type=SEQUENCING_DECISION_TYPE,
            actor_id="player-a",
            payload=payload,
            options=(option,),
        )

    assert (
        command_history._sequencing_request_conflict_id(
            sequencing_request(
                request_id="sequencing-valid",
                payload={"sequencing_conflict": {"conflict_id": "conflict-a"}},
            )
        )
        == "conflict-a"
    )
    invalid_sequencing_payloads: tuple[JsonValue, ...] = (
        None,
        {"sequencing_conflict": None},
        {"sequencing_conflict": {}},
        {"sequencing_conflict": {"conflict_id": 1}},
    )
    for index, sequencing_payload in enumerate(invalid_sequencing_payloads):
        assert (
            command_history._sequencing_request_conflict_id(
                sequencing_request(
                    request_id=f"sequencing-invalid-{index}",
                    payload=sequencing_payload,
                )
            )
            is None
        )


def test_command_battle_shock_completed_event_history_guards_fail_closed() -> None:
    decisions = DecisionController()
    state = _battle_state(
        game_id="phase11c-command-completed-history-guards",
        decisions=decisions,
    )
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    completed = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(())
    ).begin_phase(state=state, decisions=decisions)
    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    event_records = decisions.event_log.records
    decision_records = decisions.records
    baseline = command_history.ordered_completed_command_battle_shock_results(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    assert len(baseline) == 1
    result_event_index = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_test_resolved"
    )
    result_event = event_records[result_event_index]
    result_payload = cast(dict[str, Any], result_event.payload)
    result_row = cast(dict[str, Any], result_payload["battle_shock_result"])
    request_row = cast(dict[str, Any], result_row["request"])
    command_state = _command_step_state(state)
    completed_request_id = command_state.completed_battle_shock_test_request_ids[0]

    with pytest.raises(GameLifecycleError, match="requires decision records"):
        command_history.ordered_completed_command_battle_shock_results(
            state=state,
            event_records=event_records,
            decision_records=cast(Any, []),
        )

    def corrupted_command_state(**values: Any) -> CommandStepState:
        corrupted = replace(command_state)
        for name, value in values.items():
            object.__setattr__(corrupted, name, value)
        return corrupted

    state.command_step_state = corrupted_command_state(
        completed_battle_shock_test_request_ids=(completed_request_id, completed_request_id),
    )
    with pytest.raises(GameLifecycleError, match="completed request IDs must be unique"):
        command_history.ordered_completed_command_battle_shock_results(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
        )
    state.command_step_state = corrupted_command_state(
        completed_battle_shock_test_request_ids=("battle-shock:unknown",),
    )
    with pytest.raises(GameLifecycleError, match="completed request is not required"):
        command_history.ordered_completed_command_battle_shock_results(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
        )
    state.command_step_state = command_state

    def with_result_payload(payload: dict[str, Any]) -> tuple[EventRecord, ...]:
        records = list(event_records)
        records[result_event_index] = replace(result_event, payload=payload)
        return tuple(records)

    ignored_result_rows = (
        {**result_payload, "battle_shock_result": None},
        {**result_payload, "battle_shock_result": {**result_row, "request": None}},
        {
            **result_payload,
            "battle_shock_result": {
                **result_row,
                "request": {**request_row, "request_id": 1},
            },
        },
    )
    for payload in ignored_result_rows:
        with pytest.raises(GameLifecycleError, match="completed request prefix"):
            command_history.ordered_completed_command_battle_shock_results(
                state=state,
                event_records=with_result_payload(payload),
                decision_records=decision_records,
            )

    strict_result_payloads = (
        {**result_payload, "phase": BattlePhase.MOVEMENT.value},
        {**result_payload, "game_id": "other-game"},
        {**result_payload, "battle_round": state.battle_round + 1},
        {**result_payload, "active_player_id": "player-b"},
        {**result_payload, "unexpected": True},
        {**result_payload, "auto_passed": 1},
        {**result_payload, "cleared_battle_shocked_unit_ids": None},
        {**result_payload, "cleared_battle_shocked_unit_ids": [unit_id, unit_id]},
        {
            **result_payload,
            "battle_shock_result": {**result_row, "unexpected": True},
        },
    )
    for payload in strict_result_payloads:
        with pytest.raises(GameLifecycleError):
            command_history.ordered_completed_command_battle_shock_results(
                state=state,
                event_records=with_result_payload(payload),
                decision_records=decision_records,
            )

    command_history._validate_historical_snapshot_completion_pairs(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    anchor_index = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "command_step_started"
    )
    snapshot_index = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_step_snapshot_created"
    )
    completion_index = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_step_completed"
    )
    snapshot_event = event_records[snapshot_index]
    snapshot_payload = cast(dict[str, Any], snapshot_event.payload)
    completion_event = event_records[completion_index]
    completion_payload = cast(dict[str, Any], completion_event.payload)

    duplicated_anchor_events = list(event_records)
    duplicated_anchor_events.insert(anchor_index + 1, event_records[anchor_index])
    with pytest.raises(GameLifecycleError, match="anchor is duplicated"):
        command_history._validate_historical_snapshot_completion_pairs(
            state=state,
            event_records=tuple(duplicated_anchor_events),
            decision_records=decision_records,
        )

    def with_snapshot_payload(payload: dict[str, Any]) -> tuple[EventRecord, ...]:
        records = list(event_records)
        records[snapshot_index] = replace(snapshot_event, payload=payload)
        return tuple(records)

    for payload, message in (
        ({**snapshot_payload, "game_id": "other-game"}, "snapshot game drift"),
        (
            {**snapshot_payload, "phase": BattlePhase.MOVEMENT.value},
            "snapshot phase drift",
        ),
        (
            {**snapshot_payload, "battle_shock_candidate_inventory": None},
            "candidate inventory drift",
        ),
        (
            {
                **snapshot_payload,
                "battle_shock_candidate_inventory": [
                    {
                        **cast(
                            list[dict[str, Any]],
                            snapshot_payload["battle_shock_candidate_inventory"],
                        )[0],
                        "unexpected": True,
                    }
                ],
            },
            "candidate payload drift",
        ),
        (
            {
                **snapshot_payload,
                "battle_shock_phase_start_unit_ids": ["missing-unit"],
            },
            "phase-start unit lacks required test",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            command_history._validate_historical_snapshot_completion_pairs(
                state=state,
                event_records=with_snapshot_payload(payload),
                decision_records=decision_records,
            )

    duplicated_snapshot_events = list(event_records)
    duplicated_snapshot_events.insert(
        snapshot_index + 1,
        replace(snapshot_event, event_id=f"{snapshot_event.event_id}:duplicate"),
    )
    with pytest.raises(GameLifecycleError, match="snapshot is duplicated"):
        command_history._validate_historical_snapshot_completion_pairs(
            state=state,
            event_records=tuple(duplicated_snapshot_events),
            decision_records=decision_records,
        )

    completion_results = cast(
        list[dict[str, Any]],
        completion_payload["battle_shock_results"],
    )
    drifted_completion_events = list(event_records)
    drifted_completion_events[completion_index] = replace(
        completion_event,
        payload={
            **completion_payload,
            "battle_shock_results": [
                {**completion_results[0], "unexpected": True},
            ],
        },
    )
    with pytest.raises(GameLifecycleError, match="completion result shape drift"):
        command_history._validate_historical_snapshot_completion_pairs(
            state=state,
            event_records=tuple(drifted_completion_events),
            decision_records=decision_records,
        )

    duplicate_cleared_ids_events = list(event_records)
    duplicate_cleared_ids_events[result_event_index] = replace(
        result_event,
        payload={
            **result_payload,
            "cleared_battle_shocked_unit_ids": [unit_id, unit_id],
        },
    )
    with pytest.raises(GameLifecycleError, match="cleared IDs drift"):
        command_history._validate_historical_snapshot_completion_pairs(
            state=state,
            event_records=tuple(duplicate_cleared_ids_events),
            decision_records=decision_records,
        )

    command_points_not_granted = replace(command_state)
    object.__setattr__(command_points_not_granted, "command_points_granted", False)
    state.command_step_state = command_points_not_granted
    with pytest.raises(GameLifecycleError, match="anchor precedes Core CP gain"):
        command_history._validate_historical_snapshot_completion_pairs(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
        )
    state.command_step_state = command_state

    state.command_step_state = corrupted_command_state(
        completed_battle_shock_test_request_ids=(),
    )
    with pytest.raises(GameLifecycleError, match="request is not completed"):
        command_history.ordered_completed_command_battle_shock_results(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
        )
    state.command_step_state = command_state

    duplicate_result_records = list(event_records)
    duplicate_result_records.insert(result_event_index + 1, result_event)
    with pytest.raises(GameLifecycleError, match="resolved event is duplicated"):
        command_history.ordered_completed_command_battle_shock_results(
            state=state,
            event_records=tuple(duplicate_result_records),
            decision_records=decision_records,
        )

    request_event_index = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request") == request_row
    )
    missing_request_records = list(event_records)
    missing_request_records[request_event_index] = replace(
        missing_request_records[request_event_index],
        payload={},
    )
    with pytest.raises(GameLifecycleError, match="lacks one exact request event"):
        command_history.ordered_completed_command_battle_shock_results(
            state=state,
            event_records=tuple(missing_request_records),
            decision_records=decision_records,
        )

    original_roll_payload = baseline[0].roll_state.original_result.to_payload()
    dice_event_index = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "dice_rolled" and event.payload == original_roll_payload
    )
    missing_dice_records = list(event_records)
    missing_dice_records[dice_event_index] = replace(
        missing_dice_records[dice_event_index],
        payload={},
    )
    with pytest.raises(GameLifecycleError, match="lacks one exact original dice event"):
        command_history.ordered_completed_command_battle_shock_results(
            state=state,
            event_records=tuple(missing_dice_records),
            decision_records=decision_records,
        )


def test_command_battle_shock_runtime_authority_payload_helpers_fail_closed() -> None:
    unit_id = "army-alpha:intercessor-unit-1"
    state = _battle_state(game_id="phase11c-command-runtime-authority-helpers")
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    candidate = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )[0]

    assert command_runtime_authority._candidates([validate_json_value(candidate.to_payload())]) == (
        candidate,
    )
    with pytest.raises(GameLifecycleError, match="payload is invalid"):
        command_runtime_authority._candidates(cast(Any, {}))
    with pytest.raises(GameLifecycleError, match="payload is invalid"):
        command_runtime_authority._candidates(cast(Any, [1]))
    with pytest.raises(GameLifecycleError, match="payload is incomplete"):
        command_runtime_authority._candidates([cast(Any, {})])

    assert command_runtime_authority._object({"value": "ok"}) == {"value": "ok"}
    with pytest.raises(GameLifecycleError, match="must be an object"):
        command_runtime_authority._object(None)
    assert (
        command_runtime_authority._positive_int(
            2,
            field="round",
        )
        == 2
    )
    for positive_int_value in (0, True, "1"):
        with pytest.raises(GameLifecycleError, match="round is invalid"):
            command_runtime_authority._positive_int(
                cast(Any, positive_int_value),
                field="round",
            )
    assert (
        command_runtime_authority._player_id(
            "player-a",
            state=state,
        )
        == "player-a"
    )
    for player_id_value in (None, 1, "missing-player"):
        with pytest.raises(GameLifecycleError, match="active player is invalid"):
            command_runtime_authority._player_id(
                cast(Any, player_id_value),
                state=state,
            )
    assert command_runtime_authority._identifier_list(
        ["a", "b"],
        field="identifiers",
    ) == ("a", "b")
    for identifier_list_value in (None, [1], ["b", "a"], ["a", "a"]):
        with pytest.raises(GameLifecycleError, match="identifiers"):
            command_runtime_authority._identifier_list(
                cast(Any, identifier_list_value),
                field="identifiers",
            )

    assert command_runtime_authority._starting_strength(
        state=state,
        unit_instance_id=unit_id,
    ) == (5, None)
    with pytest.raises(GameLifecycleError, match="starting-strength authority"):
        command_runtime_authority._starting_strength(
            state=state,
            unit_instance_id="missing-unit",
        )

    first = BattleShockForcedTestApplication(
        hook_id="hook-a",
        source_id="source-a",
        unit_instance_ids=("unit-a", "unit-b"),
    )
    second = BattleShockForcedTestApplication(
        hook_id="hook-b",
        source_id="source-b",
        unit_instance_ids=("unit-b",),
    )
    grouped = command_runtime_authority._forced_applications_by_unit_id((first, second))
    assert tuple(grouped) == ("unit-a", "unit-b")
    assert grouped["unit-a"] == (replace(first, unit_instance_ids=("unit-a",)),)
    assert grouped["unit-b"] == (
        replace(first, unit_instance_ids=("unit-b",)),
        replace(second, unit_instance_ids=("unit-b",)),
    )


def test_command_forced_provider_authority_helpers_fail_closed() -> None:
    decisions = DecisionController()
    state = _battle_state(
        game_id="phase11c-command-forced-provider-helpers",
        decisions=decisions,
    )
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    span = TextSpan(text="forced Battle-shock", start=0, end=19)
    forced_rule_effect = RuleEffectSpec(
        kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
        source_span=span,
        parameters=(
            RuleParameter(key="force_battle_shock_below_starting_strength", value=True),
            RuleParameter(key="rules_context", value="battle_shock"),
            RuleParameter(key="status", value="battle_shock_forced_below_starting_strength"),
        ),
    )
    non_forced_rule_effect = RuleEffectSpec(
        kind=RuleEffectKind.MODIFY_DICE_ROLL,
        source_span=span,
        parameters=(RuleParameter(key="delta", value=1),),
    )

    def effect_with(
        *,
        effect_id: str,
        expiration: EffectExpiration,
        effect_payload: Any,
        target_ids: tuple[str, ...] = (unit_id,),
    ) -> PersistingEffect:
        return PersistingEffect(
            effect_id=effect_id,
            source_rule_id="phase11c:forced-provider-source",
            owner_player_id="player-b",
            target_unit_instance_ids=target_ids,
            started_battle_round=1,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=expiration,
            effect_payload=effect_payload,
        )

    forced_effect = effect_with(
        effect_id="phase11c:forced-provider-effect",
        expiration=EffectExpiration.end_battle_round(battle_round=1),
        effect_payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "effect": forced_rule_effect.to_payload(),
        },
    )
    non_forced_effect = effect_with(
        effect_id="phase11c:non-forced-provider-effect",
        expiration=EffectExpiration.end_battle_round(battle_round=1),
        effect_payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "effect": non_forced_rule_effect.to_payload(),
        },
    )

    assert (
        forced_provider_authority._forced_persisting_effect_or_none(
            validate_json_value(forced_effect.to_payload())
        )
        == forced_effect
    )
    assert (
        forced_provider_authority._forced_persisting_effect_or_none(
            validate_json_value(non_forced_effect.to_payload())
        )
        is None
    )
    persisting_effect_values: tuple[JsonValue, ...] = (
        None,
        {},
        validate_json_value(
            effect_with(
                effect_id="phase11c:non-generic-provider-effect",
                expiration=EffectExpiration.end_battle_round(battle_round=1),
                effect_payload=None,
            ).to_payload()
        ),
    )
    for persisting_effect_value in persisting_effect_values:
        assert (
            forced_provider_authority._forced_persisting_effect_or_none(
                cast(Any, persisting_effect_value)
            )
            is None
        )
    missing_rule_payload = cast(
        dict[str, JsonValue],
        validate_json_value(forced_effect.to_payload()),
    )
    missing_rule_payload["effect_payload"] = {"effect_kind": GENERIC_RULE_EFFECT_KIND}
    with pytest.raises(GameLifecycleError, match="generic effect payload is missing"):
        forced_provider_authority._forced_persisting_effect_or_none(
            validate_json_value(missing_rule_payload)
        )
    invalid_rule_payload = cast(
        dict[str, JsonValue],
        validate_json_value(forced_effect.to_payload()),
    )
    invalid_rule_payload["effect_payload"] = {
        "effect_kind": GENERIC_RULE_EFFECT_KIND,
        "effect": {
            "kind": "unsupported",
            "source_span": validate_json_value(span.to_payload()),
            "parameters": [],
        },
    }
    with pytest.raises(GameLifecycleError, match="generic effect payload is invalid"):
        forced_provider_authority._forced_persisting_effect_or_none(
            validate_json_value(invalid_rule_payload)
        )

    split_event = EventRecord(
        event_id="event-forced-provider-split",
        event_type="attached_rules_unit_split_reconciled",
        payload={
            "attached_unit_instance_id": "attached-unit-a",
            "surviving_unit_instance_ids": ["unit-a", "unit-b"],
        },
    )
    attached_effect = replace(
        forced_effect,
        target_unit_instance_ids=("attached-unit-a",),
    )
    assert forced_provider_authority._effect_after_splits(
        effect=attached_effect,
        event_records=(
            EventRecord(event_id="event-ignored", event_type="ignored", payload=None),
            split_event,
        ),
        start_index=0,
        end_index=2,
    ).target_unit_instance_ids == ("unit-a", "unit-b")

    expirations = (
        EffectExpiration.end_of_battle(),
        EffectExpiration.start_phase(
            battle_round=2,
            phase=BattlePhaseKind.COMMAND,
            player_id="player-a",
        ),
        EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.COMMAND,
            player_id="player-a",
        ),
        EffectExpiration.start_turn(battle_round=2, player_id="player-a"),
        EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
        EffectExpiration.start_battle_round(battle_round=2),
        EffectExpiration.end_battle_round(battle_round=1),
    )
    for index, expiration in enumerate(expirations):
        assert isinstance(
            forced_provider_authority._effect_is_active_at_command_snapshot(
                state=state,
                effect=effect_with(
                    effect_id=f"phase11c:expiration-{index}",
                    expiration=expiration,
                    effect_payload=None,
                ),
                battle_round=1,
                active_player_id="player-a",
            ),
            bool,
        )

    invalid_position_state = _battle_state(game_id="phase11c-invalid-forced-position")
    object.__setattr__(invalid_position_state, "turn_order", ("player-b",))
    with pytest.raises(GameLifecycleError, match="snapshot position drifted"):
        forced_provider_authority._effect_is_active_at_command_snapshot(
            state=invalid_position_state,
            effect=forced_effect,
            battle_round=1,
            active_player_id="player-a",
        )
    incomplete_phase_expiration = EffectExpiration.start_phase(
        battle_round=2,
        phase=BattlePhaseKind.COMMAND,
        player_id="player-a",
    )
    object.__setattr__(incomplete_phase_expiration, "battle_round", None)
    with pytest.raises(GameLifecycleError, match="phase expiration is incomplete"):
        forced_provider_authority._effect_is_active_at_command_snapshot(
            state=state,
            effect=replace(forced_effect, expiration=incomplete_phase_expiration),
            battle_round=1,
            active_player_id="player-a",
        )
    incomplete_turn_expiration = EffectExpiration.end_turn(
        battle_round=1,
        player_id="player-a",
    )
    object.__setattr__(incomplete_turn_expiration, "player_id", None)
    with pytest.raises(GameLifecycleError, match="turn expiration is incomplete"):
        forced_provider_authority._effect_is_active_at_command_snapshot(
            state=state,
            effect=replace(forced_effect, expiration=incomplete_turn_expiration),
            battle_round=1,
            active_player_id="player-a",
        )
    incomplete_round_expiration = EffectExpiration.end_battle_round(battle_round=1)
    object.__setattr__(incomplete_round_expiration, "battle_round", None)
    with pytest.raises(GameLifecycleError, match="round expiration is incomplete"):
        forced_provider_authority._effect_is_active_at_command_snapshot(
            state=state,
            effect=replace(forced_effect, expiration=incomplete_round_expiration),
            battle_round=1,
            active_player_id="player-a",
        )
    unsupported_expiration = EffectExpiration.end_of_battle()
    object.__setattr__(unsupported_expiration, "expiration_kind", cast(EffectExpirationKind, "bad"))
    with pytest.raises(GameLifecycleError, match="expiration kind is unsupported"):
        forced_provider_authority._effect_is_active_at_command_snapshot(
            state=state,
            effect=replace(forced_effect, expiration=unsupported_expiration),
            battle_round=1,
            active_player_id="player-a",
        )

    assert forced_provider_authority._dread_tuple(["dismay", "dominion"])
    for dread_value in (None, [1], ["unsupported"]):
        with pytest.raises(GameLifecycleError, match="Harbingers selected"):
            forced_provider_authority._dread_tuple(cast(Any, dread_value))
    rolled = forced_provider_authority._dreads_from_roll(
        dice_values=(4, 4, 6),
        prior_active=(),
    )
    assert tuple(value.value for value in rolled) == ("dismay", "dominion")
    assert not forced_provider_authority._unit_has_harbingers(unit)

    context = historical_battle_shock_context_for_unit(
        state=state,
        decisions=decisions,
        unit_instance_id=unit_id,
        active_player_id="player-a",
    )
    model_ids = tuple(sorted(unit.own_model_ids()))
    assert set(forced_provider_authority._models_by_id(state)) >= set(model_ids)
    assert (
        forced_provider_authority._model_ids_for_component_unit_ids(
            state=state,
            component_unit_instance_ids=(unit_id,),
        )
        == model_ids
    )
    with pytest.raises(GameLifecycleError, match="component identity authority"):
        forced_provider_authority._model_ids_for_component_unit_ids(
            state=state,
            component_unit_instance_ids=("missing-unit",),
        )
    geometries = forced_provider_authority._geometry_models(
        state=state,
        model_ids=model_ids,
        physical_rows=context.physical_models,
    )
    assert tuple(model.model_id for model in geometries) == model_ids
    physical_by_id = forced_provider_authority._physical_by_id(context.physical_models)
    assert set(physical_by_id) >= set(model_ids)
    assert forced_provider_authority._placed_alive(physical_by_id[model_ids[0]])
    assert not forced_provider_authority._placed_alive(None)

    assert (
        forced_provider_authority._unit_for_player(
            state=state,
            player_id="player-a",
            unit_id=unit_id,
        )
        == unit
    )
    for player_id, requested_unit_id in (
        ("missing-player", unit_id),
        ("player-a", "missing-unit"),
    ):
        with pytest.raises(GameLifecycleError, match=r"Catalog forced-test|player_id"):
            forced_provider_authority._unit_for_player(
                state=state,
                player_id=player_id,
                unit_id=requested_unit_id,
            )
    empty_index = AbilityCatalogIndex.from_records(())
    for indexes in ({}, {"player-a": empty_index}):
        with pytest.raises(GameLifecycleError, match="Catalog forced-test"):
            forced_provider_authority._loaded_ability_record(
                ability_indexes_by_player_id=indexes,
                player_id="player-a",
                record_id="missing-record",
            )

    assert forced_provider_authority._object(
        {"value": "ok"},
        context="test",
    ) == {"value": "ok"}
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        forced_provider_authority._object(
            None,
            context="test",
        )
    assert (
        forced_provider_authority._string(
            "value",
            field="field",
        )
        == "value"
    )
    for required_string_value in (None, ""):
        with pytest.raises(GameLifecycleError, match="field is invalid"):
            forced_provider_authority._string(
                cast(Any, required_string_value),
                field="field",
            )
    assert forced_provider_authority._sorted_identifier_list(
        ["a", "b"],
        field="identifiers",
    ) == ("a", "b")
    for sorted_identifier_value in (None, [], [1], ["b", "a"], ["a", "a"]):
        with pytest.raises(GameLifecycleError, match="identifiers"):
            forced_provider_authority._sorted_identifier_list(
                cast(Any, sorted_identifier_value),
                field="identifiers",
            )

    snapshot = EventRecord(
        event_id="event-forced-provider-snapshot",
        event_type="battle_shock_step_snapshot_created",
        payload={},
    )
    invalid_validator_calls = (
        {"battle_shock_hook_registry": cast(BattleShockHookRegistry, object())},
        {"snapshot_index": -1},
        {"battle_round": 0},
        {"active_player_id": "missing-player"},
    )
    for overrides in invalid_validator_calls:
        values: dict[str, Any] = {
            "state": state,
            "event_records": (snapshot,),
            "decision_records": (),
            "snapshot_index": 0,
            "battle_round": 1,
            "active_player_id": "player-a",
            "candidates": (),
            "battle_shock_hook_registry": BattleShockHookRegistry.empty(),
            "ability_indexes_by_player_id": {},
            **overrides,
        }
        with pytest.raises(GameLifecycleError, match="Command forced-test"):
            forced_provider_authority.validate_command_forced_test_applications(**cast(Any, values))

    candidates = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )
    ignored_event = EventRecord("event-forced-provider-ignored", "ignored", None)
    end_snapshot = EventRecord(
        "event-forced-provider-end-snapshot",
        "battle_shock_step_snapshot_created",
        {},
    )
    catalog_values: dict[str, Any] = {
        "state": state,
        "event_records": (ignored_event, end_snapshot),
        "decision_records": (),
        "snapshot_index": 1,
        "battle_round": 1,
        "active_player_id": "player-a",
        "candidates": candidates,
        "physical_rows": context.physical_models,
        "ability_indexes_by_player_id": {},
    }
    assert forced_provider_authority._catalog_forced_target_ids(**catalog_values) == ()
    with pytest.raises(GameLifecycleError, match="effect inventory is invalid"):
        forced_provider_authority._catalog_forced_target_ids(
            **{  # pyright: ignore[reportArgumentType]
                **catalog_values,
                "event_records": (
                    EventRecord(
                        "event-forced-provider-invalid-effects",
                        "catalog_selected_target_effect_selected",
                        {},
                    ),
                    end_snapshot,
                ),
            }
        )
    assert (
        forced_provider_authority._catalog_forced_target_ids(
            **{  # pyright: ignore[reportArgumentType]
                **catalog_values,
                "event_records": (
                    EventRecord(
                        "event-forced-provider-non-forced-effect",
                        "catalog_selected_target_effect_selected",
                        {
                            "persisting_effects": [
                                validate_json_value(non_forced_effect.to_payload())
                            ]
                        },
                    ),
                    end_snapshot,
                ),
            }
        )
        == ()
    )

    selected_payload: dict[str, JsonValue] = {"generic_rule_effect_records": []}
    selected_option = DecisionOption(
        option_id="select",
        label="Select",
        payload=selected_payload,
    )
    selected_request = DecisionRequest(
        request_id="phase11c:forced-provider:selected-request",
        decision_type="phase11c_forced_provider_selected",
        actor_id="player-a",
        payload=None,
        options=(selected_option,),
    )
    selected_result = DecisionResult.for_request(
        result_id="phase11c:forced-provider:selected-result",
        request=selected_request,
        selected_option_id=selected_option.option_id,
    )
    selected_record = DecisionRecord(
        record_id="phase11c:forced-provider:selected-record",
        request=selected_request,
        result=selected_result,
    )
    selected_event = EventRecord(
        "phase11c:forced-provider:selected-event",
        "catalog_selected_target_effect_selected",
        {
            "request_id": selected_request.request_id,
            "result_id": selected_result.result_id,
            "player_id": "player-a",
            "selected_option_id": selected_option.option_id,
        },
    )
    assert (
        forced_provider_authority._expected_catalog_forced_effects(
            state=state,
            event=selected_event,
            record=selected_record,
            ability_indexes_by_player_id={},
            physical_rows=context.physical_models,
        )
        == ()
    )
    actor_drifted_result = replace(selected_result)
    object.__setattr__(actor_drifted_result, "actor_id", "player-b")
    actor_drifted_record = replace(selected_record)
    object.__setattr__(actor_drifted_record, "result", actor_drifted_result)
    effects_drifted_result = replace(selected_result)
    object.__setattr__(effects_drifted_result, "payload", {})
    effects_drifted_record = replace(selected_record)
    object.__setattr__(effects_drifted_record, "result", effects_drifted_result)
    for drifted_record, drifted_event, message in (
        (
            selected_record,
            replace(
                selected_event,
                payload={
                    **cast(dict[str, Any], selected_event.payload),
                    "request_id": "wrong-request",
                },
            ),
            "decision identity drifted",
        ),
        (
            actor_drifted_record,
            selected_event,
            "decision actor drifted",
        ),
        (
            selected_record,
            replace(
                selected_event,
                payload={
                    **cast(dict[str, Any], selected_event.payload),
                    "selected_option_id": "wrong-option",
                },
            ),
            "selected option drifted",
        ),
        (
            effects_drifted_record,
            selected_event,
            "result effects are invalid",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            forced_provider_authority._expected_catalog_forced_effects(
                state=state,
                event=drifted_event,
                record=drifted_record,
                ability_indexes_by_player_id={},
                physical_rows=context.physical_models,
            )

    early_effect_records: tuple[dict[str, JsonValue], ...] = (
        {"immediate_effect_kind": "force_battle_shock_test"},
        {"effect_payload": None},
        {"effect_payload": {}},
        {
            "effect_payload": {
                "effect": {
                    "kind": "unsupported",
                    "source_span": validate_json_value(span.to_payload()),
                    "parameters": [],
                }
            }
        },
        {"effect_payload": {"effect": validate_json_value(non_forced_rule_effect.to_payload())}},
    )
    for effect_index, effect_record in enumerate(early_effect_records):
        if effect_index == 3:
            with pytest.raises(GameLifecycleError, match="RuleIR effect is invalid"):
                forced_provider_authority._catalog_forced_effect_from_record(
                    state=state,
                    event=selected_event,
                    decision_record=selected_record,
                    effect_index=effect_index,
                    effect_record=effect_record,
                    ability_indexes_by_player_id={},
                    physical_rows=context.physical_models,
                )
            continue
        assert (
            forced_provider_authority._catalog_forced_effect_from_record(
                state=state,
                event=selected_event,
                decision_record=selected_record,
                effect_index=effect_index,
                effect_record=effect_record,
                ability_indexes_by_player_id={},
                physical_rows=context.physical_models,
            )
            is None
        )

    for invalid_split in (
        EventRecord("invalid-split-payload", "attached_rules_unit_split_reconciled", None),
        EventRecord(
            "invalid-split-survivors",
            "attached_rules_unit_split_reconciled",
            {
                "attached_unit_instance_id": "attached-unit-a",
                "surviving_unit_instance_ids": None,
            },
        ),
    ):
        with pytest.raises(GameLifecycleError):
            forced_provider_authority._effect_after_splits(
                effect=attached_effect,
                event_records=(invalid_split,),
                start_index=0,
                end_index=1,
            )

    missing_model_row = replace(
        context.physical_models[0],
        model_instance_id="missing-model",
    )
    with pytest.raises(GameLifecycleError, match="model identity authority drifted"):
        forced_provider_authority._geometry_models(
            state=state,
            model_ids=("missing-model",),
            physical_rows=(missing_model_row,),
        )


def test_command_start_authority_helpers_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-command-start-authority-helpers")
    decisions = DecisionController()
    runtime_modifiers = RuntimeModifierRegistry.empty()
    binding = CommandPhaseStartHookBinding(
        hook_id="phase11c:command-start-helper",
        source_id="phase11c:command-start-helper-source",
        handler=lambda _context: None,
    )
    registry = CommandPhaseStartHookRegistry.from_bindings((binding,))
    emitted = EventRecord(
        event_id="event-helper-1",
        event_type="command_start_helper_evidence",
        payload={"value": "ok"},
    )
    disposition = CommandPhaseStartProviderDisposition(
        binding=binding,
        emitted_events=(emitted,),
        state_changed=True,
    )

    inventory = command_start_authority._registry_inventory(registry)
    inventory_row = cast(dict[str, JsonValue], inventory[0])
    assert inventory_row["hook_id"] == binding.hook_id
    assert command_start_authority._registry_fingerprint(
        registry
    ) == command_start_authority._payload_hash(inventory)
    disposition_payload = command_start_authority._provider_dispositions_payload((disposition,))
    disposition_row = cast(dict[str, JsonValue], disposition_payload[0])
    assert disposition_row["emitted_event_ids"] == [emitted.event_id]
    for invalid in (cast(Any, []), (cast(Any, object()),)):
        with pytest.raises(GameLifecycleError, match="dispositions must be typed"):
            command_start_authority._provider_dispositions_payload(invalid)
    reserved_disposition = replace(
        disposition,
        emitted_events=(
            replace(
                emitted,
                event_type=command_start_authority.COMMAND_START_BOUNDARY_COMPLETED_EVENT,
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="reserved authority events"):
        command_start_authority._provider_dispositions_payload((reserved_disposition,))

    common = command_start_authority._authority_common_payload(
        state=state,
        registry=registry,
    )
    assert command_start_authority._validate_authority_common_payload(
        payload=common,
        state=state,
        registry=registry,
    ) == (state.battle_round, "player-a")
    invalid_common_payloads = (
        {**common, "game_id": "forged-game"},
        {**common, "battle_round": 0},
        {**common, "battle_round": True},
        {**common, "active_player_id": ""},
        {**common, "active_player_id": "missing-player"},
        {**common, "phase": BattlePhase.MOVEMENT.value},
        {**common, "provider_registry_fingerprint": "forged"},
        {**common, "provider_binding_inventory": []},
    )
    for payload in invalid_common_payloads:
        with pytest.raises(GameLifecycleError, match="Command-start"):
            command_start_authority._validate_authority_common_payload(
                payload=cast(Any, payload),
                state=state,
                registry=registry,
            )

    valid_shape_payload = {
        **common,
        "provider_binding_inventory": inventory,
        "provider_dispositions": disposition_payload,
    }
    command_start_authority._validate_exact_payload_shape(
        event_type=command_start_authority.COMMAND_START_BOUNDARY_COMPLETED_EVENT,
        payload=cast(Any, valid_shape_payload),
    )
    for event_type, payload in (
        ("unsupported-event", valid_shape_payload),
        (
            command_start_authority.COMMAND_START_BOUNDARY_COMPLETED_EVENT,
            {**valid_shape_payload, "unexpected": True},
        ),
    ):
        with pytest.raises(GameLifecycleError, match="payload shape drifted"):
            command_start_authority._validate_exact_payload_shape(
                event_type=event_type,
                payload=cast(Any, payload),
            )

    assert (
        command_start_authority._binding_from_payload(
            payload={"provider_hook_id": binding.hook_id, "provider_source_id": binding.source_id},
            registry=registry,
        )
        == binding
    )
    with pytest.raises(GameLifecycleError, match="binding identity drifted"):
        command_start_authority._binding_from_payload(
            payload={"provider_hook_id": "missing-hook", "provider_source_id": "missing-source"},
            registry=registry,
        )
    command_start_authority._require_registry_binding(
        registry=registry,
        binding=binding,
    )
    for invalid_binding, requires_effect, requires_result in (
        (cast(Any, object()), False, False),
        (
            CommandPhaseStartHookBinding(
                hook_id="unloaded-hook",
                source_id="unloaded-source",
                handler=lambda _context: None,
            ),
            False,
            False,
        ),
        (binding, True, False),
        (binding, False, True),
    ):
        with pytest.raises(GameLifecycleError, match="Command-start authority"):
            command_start_authority._require_registry_binding(
                registry=registry,
                binding=invalid_binding,
                requires_effect=requires_effect,
                requires_result=requires_result,
            )

    assert command_start_authority._event_payload(emitted) == {"value": "ok"}
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        command_start_authority._event_payload(replace(emitted, payload=None))
    assert (
        command_start_authority._payload_string(
            {"field": "value"},
            "field",
        )
        == "value"
    )
    assert (
        command_start_authority._optional_payload_string(
            {"field": None},
            "field",
        )
        is None
    )
    assert (
        command_start_authority._optional_payload_string(
            {"field": "value"},
            "field",
        )
        == "value"
    )
    for helper, value in (
        (command_start_authority._payload_string, None),
        (command_start_authority._payload_string, ""),
        (command_start_authority._optional_payload_string, 1),
        (command_start_authority._optional_payload_string, ""),
    ):
        with pytest.raises(GameLifecycleError, match="must be a string"):
            helper({"field": cast(Any, value)}, "field")

    assert (
        command_start_authority._exact_event_index(
            (emitted,),
            event_type=emitted.event_type,
            payload=emitted.payload,
        )
        == 0
    )
    for events in ((), (emitted, emitted)):
        with pytest.raises(GameLifecycleError, match="one exact"):
            command_start_authority._exact_event_index(
                events,
                event_type=emitted.event_type,
                payload=emitted.payload,
            )
    anchor = EventRecord(
        event_id="event-anchor",
        event_type="command_step_started",
        payload={"battle_round": 1, "active_player_id": "player-a"},
    )
    assert (
        command_start_authority._command_step_anchor_index(
            (anchor,),
            battle_round=1,
            active_player_id="player-a",
        )
        == 0
    )
    for events in ((), (anchor, anchor)):
        with pytest.raises(GameLifecycleError, match="Core CP anchor"):
            command_start_authority._command_step_anchor_index(
                events,
                battle_round=1,
                active_player_id="player-a",
            )

    assert command_start_authority._current_command_key(state) == (1, "player-a")
    assert command_start_authority._active_player_id(state) == "player-a"
    with pytest.raises(GameLifecycleError, match="CommandStepState"):
        command_start_authority._require_command_state(state)
    command_start_authority._require_empty_pending_queue(
        decisions=decisions,
        context="pending queue must be empty",
    )
    pending = DecisionRequest(
        request_id="command-start-helper-pending",
        decision_type="command-start-helper",
        actor_id="player-a",
        payload=None,
        options=(DecisionOption(option_id="continue", label="Continue"),),
    )
    decisions.request_decision(pending)
    with pytest.raises(GameLifecycleError, match="pending queue must be empty"):
        command_start_authority._require_empty_pending_queue(
            decisions=decisions,
            context="pending queue must be empty",
        )

    command_start_authority._validate_runtime_inputs(
        state=state,
        decisions=DecisionController(),
        registry=registry,
        runtime_modifier_registry=runtime_modifiers,
    )
    invalid_runtime_inputs = (
        {"state": cast(GameState, object())},
        {"decisions": cast(DecisionController, object())},
        {"registry": cast(CommandPhaseStartHookRegistry, object())},
        {"runtime_modifier_registry": cast(RuntimeModifierRegistry, object())},
    )
    for overrides in invalid_runtime_inputs:
        with pytest.raises(GameLifecycleError, match="Command-start boundary"):
            command_start_authority._validate_runtime_inputs(
                state=cast(GameState, overrides.get("state", state)),
                decisions=cast(
                    DecisionController,
                    overrides.get("decisions", DecisionController()),
                ),
                registry=cast(
                    CommandPhaseStartHookRegistry,
                    overrides.get("registry", registry),
                ),
                runtime_modifier_registry=cast(
                    RuntimeModifierRegistry,
                    overrides.get("runtime_modifier_registry", runtime_modifiers),
                ),
            )


def test_command_start_hook_authority_helpers_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-command-start-hook-authority")
    decisions = DecisionController()
    runtime_modifiers = RuntimeModifierRegistry.empty()
    battle_shock_hooks = BattleShockHookRegistry.empty()
    request = DecisionRequest(
        request_id="phase11c-command-start-hook-request",
        decision_type=(
            command_start_hooks.SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
        ),
        actor_id="player-a",
        payload={"value": "ok"},
        options=(DecisionOption(option_id="accept", label="Accept"),),
    )
    result = DecisionResult.for_request(
        result_id="phase11c-command-start-hook-result",
        request=request,
        selected_option_id="accept",
    )

    for effect_context_overrides, message in (
        ({"state": object()}, "state must be GameState"),
        ({"decisions": object()}, "decisions must be DecisionController"),
        ({"runtime_modifier_registry": object()}, "must be a registry"),
    ):
        values: dict[str, Any] = {
            "state": state,
            "decisions": decisions,
            "active_player_id": "player-a",
            "runtime_modifier_registry": runtime_modifiers,
            **effect_context_overrides,
        }
        with pytest.raises(GameLifecycleError, match=message):
            command_start_hooks.CommandPhaseStartEffectContext(**values)

    result_context_values: dict[str, Any] = {
        "state": state,
        "decisions": decisions,
        "request": request,
        "result": result,
        "active_player_id": "player-a",
        "battle_shock_hooks": battle_shock_hooks,
        "runtime_modifier_registry": runtime_modifiers,
        "ability_indexes_by_player_id": {},
    }
    invalid_result_context_overrides: tuple[tuple[dict[str, Any], str], ...] = (
        ({"battle_shock_hooks": object()}, "battle_shock_hooks must be a registry"),
        ({"runtime_modifier_registry": object()}, "must be a registry"),
        ({"ability_indexes_by_player_id": []}, "must be a mapping"),
        (
            {"ability_indexes_by_player_id": {"player-a": object()}},
            "must be AbilityCatalogIndex",
        ),
    )
    for result_context_overrides, message in invalid_result_context_overrides:
        with pytest.raises(GameLifecycleError, match=message):
            command_start_hooks.CommandPhaseStartResultContext(
                **{
                    **result_context_values,
                    **result_context_overrides,
                }
            )

    nested_values: dict[str, Any] = {
        "state": state,
        "decisions": decisions,
        "request": request,
        "result": result,
        "active_player_id": "player-a",
        "battle_shock_hooks": battle_shock_hooks,
        "runtime_modifier_registry": runtime_modifiers,
        "ability_indexes_by_player_id": {},
    }
    with pytest.raises(GameLifecycleError, match="result must be DecisionResult"):
        command_start_hooks.CommandPhaseStartNestedResultContext(
            **{  # pyright: ignore[reportArgumentType]
                **nested_values,
                "result": object(),
            }
        )

    invalid_bindings: tuple[tuple[dict[str, Any], str], ...] = (
        ({"effect_handler": object()}, "effect_handler"),
        ({"nested_result_handler": object()}, "nested_result_handler"),
        ({"nested_pending_authority_validator": object()}, "nested pending"),
        (
            {"completed_battle_shock_authority_validator": object()},
            "completed Battle-shock",
        ),
        (
            {
                "nested_result_handler": lambda _context: False,  # pyright: ignore[reportUnknownLambdaType]
            },
            "require an authority validator",
        ),
    )
    for index, (handlers, message) in enumerate(invalid_bindings):
        with pytest.raises(GameLifecycleError, match=message):
            command_start_hooks.CommandPhaseStartHookBinding(
                hook_id=f"phase11c:hook:invalid-command-start-{index}",
                source_id=f"phase11c:source:invalid-command-start-{index}",
                **handlers,
            )

    binding = CommandPhaseStartHookBinding(
        hook_id="phase11c:hook:command-start-authority",
        source_id="phase11c:source:command-start-authority",
        handler=lambda _context: None,
    )
    event = EventRecord(
        event_id="phase11c:event:command-start-authority",
        event_type="command_start_authority_evidence",
        payload={"value": "ok"},
    )
    invalid_disposition_overrides: tuple[tuple[dict[str, Any], str], ...] = (
        ({"binding": object()}, "provider binding"),
        ({"emitted_events": []}, "must be EventRecords"),
        ({"emitted_events": (object(),)}, "must be EventRecords"),
        ({"state_changed": 1}, "must be a bool"),
        ({"state_changed": True, "emitted_events": ()}, "must emit evidence"),
    )
    for disposition_overrides, message in invalid_disposition_overrides:
        disposition_values: dict[str, Any] = {
            "binding": binding,
            "emitted_events": (event,),
            "state_changed": False,
            **disposition_overrides,
        }
        with pytest.raises(GameLifecycleError, match=message):
            command_start_hooks.CommandPhaseStartProviderDisposition(**disposition_values)

    effect_context = command_start_hooks.CommandPhaseStartEffectContext(
        state=state,
        decisions=decisions,
        active_player_id="player-a",
        runtime_modifier_registry=runtime_modifiers,
    )
    invalid_status_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase11c:hook:invalid-command-start-status",
                source_id="phase11c:source:invalid-command-start-status",
                effect_handler=lambda _context: cast(LifecycleStatus, object()),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return LifecycleStatus"):
        invalid_status_registry.resolve_effects(effect_context)

    result_context = command_start_hooks.CommandPhaseStartResultContext(**result_context_values)
    wrong_type_request = replace(request, decision_type="wrong-command-start-type")
    with pytest.raises(GameLifecycleError, match="decision type drifted"):
        CommandPhaseStartHookRegistry.empty().apply_result(
            replace(result_context, request=wrong_type_request)
        )
    with pytest.raises(GameLifecycleError, match="nested result hooks require context"):
        CommandPhaseStartHookRegistry.empty().apply_nested_result(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="nested pending authority requires context"):
        CommandPhaseStartHookRegistry.empty().binding_for_nested_pending_authority(
            cast(Any, object())
        )
    with pytest.raises(GameLifecycleError, match="Completed Command-start"):
        CommandPhaseStartHookRegistry.empty().validate_completed_battle_shock_authority(
            hook_id="hook",
            source_id="source",
            context=cast(Any, object()),
        )

    pending_context = command_start_hooks.CommandPhaseStartNestedPendingAuthorityContext(
        state=state,
        decisions=decisions,
        request=request,
        active_player_id="player-a",
        battle_shock_hooks=battle_shock_hooks,
        runtime_modifier_registry=runtime_modifiers,
        ability_indexes_by_player_id={},
    )
    non_bool_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase11c:hook:non-bool-pending-authority",
                source_id="phase11c:source:non-bool-pending-authority",
                nested_pending_authority_validator=lambda _context: cast(bool, object()),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return bool"):
        non_bool_registry.binding_for_nested_pending_authority(pending_context)
    validator_groups: tuple[
        tuple[
            Callable[
                [command_start_hooks.CommandPhaseStartNestedPendingAuthorityContext],
                bool,
            ],
            ...,
        ],
        ...,
    ] = (
        (lambda _context: False,),
        (lambda _context: True, lambda _context: True),
    )
    for validators in validator_groups:
        registry = CommandPhaseStartHookRegistry.from_bindings(
            tuple(
                CommandPhaseStartHookBinding(
                    hook_id=f"phase11c:hook:pending-authority-{index}",
                    source_id=f"phase11c:source:pending-authority-{index}",
                    nested_pending_authority_validator=validator,
                )
                for index, validator in enumerate(validators)
            )
        )
        with pytest.raises(GameLifecycleError, match="exactly one source authority"):
            registry.binding_for_nested_pending_authority(pending_context)

    before = command_start_hooks._provider_snapshot(effect_context)
    disposition = command_start_hooks._provider_disposition(
        context=effect_context,
        binding=binding,
        before=before,
    )
    assert not disposition.state_changed
    with pytest.raises(GameLifecycleError, match="cannot record player decisions"):
        command_start_hooks._provider_disposition(
            context=effect_context,
            binding=binding,
            before=(before[0], before[1], -1, before[3]),
        )
    with pytest.raises(GameLifecycleError, match="removed retained events"):
        command_start_hooks._provider_disposition(
            context=effect_context,
            binding=binding,
            before=(before[0], before[1], before[2], before[3] + 1),
        )

    with pytest.raises(GameLifecycleError, match="cannot emit decision records"):
        command_start_hooks._validate_provider_decision_events(
            context=effect_context,
            emitted_events=(replace(event, event_type="decision_recorded"),),
            all_events=(replace(event, event_type="decision_recorded"),),
        )
    orphan = replace(
        event,
        event_type="decision_requested",
        payload=validate_json_value(request.to_payload()),
    )
    with pytest.raises(GameLifecycleError, match="orphaned decision request"):
        command_start_hooks._validate_provider_decision_events(
            context=effect_context,
            emitted_events=(orphan,),
            all_events=(orphan,),
        )

    side_effect_decisions = DecisionController()
    side_effect_context = command_start_hooks.CommandPhaseStartEffectContext(
        state=state,
        decisions=side_effect_decisions,
        active_player_id="player-a",
        runtime_modifier_registry=runtime_modifiers,
    )
    side_effect_before = command_start_hooks._provider_snapshot(side_effect_context)
    side_effect_decisions.event_log.append("unexpected", None)
    with pytest.raises(GameLifecycleError, match="side effect detected"):
        command_start_hooks._require_provider_side_effect_free(
            context=side_effect_context,
            before=side_effect_before,
            error_message="side effect detected",
        )

    request_context = command_start_hooks.CommandPhaseStartRequestContext(
        state=state,
        decisions=DecisionController(),
        active_player_id="player-a",
    )
    with pytest.raises(GameLifecycleError, match="state snapshot is invalid"):
        command_start_hooks._require_request_provider_side_effects(
            context=request_context,
            before=(object(), (), 0, 0),
            request=None,
        )

    active_request = request
    non_active_allowed = replace(
        request,
        request_id="phase11c-command-start-non-active-allowed",
        actor_id="player-b",
        payload={"actor_may_be_non_active": True},
    )
    non_active_denied = replace(
        non_active_allowed,
        request_id="phase11c-command-start-non-active-denied",
        payload=None,
    )
    assert command_start_hooks._sequenced_command_phase_start_emission(
        context=request_context,
        emissions=((active_request, binding), (non_active_allowed, binding)),
    ) == (active_request, binding)
    assert command_start_hooks._sequenced_command_phase_start_emission(
        context=request_context,
        emissions=((non_active_allowed, binding),),
    ) == (non_active_allowed, binding)
    assert (
        command_start_hooks._sequenced_command_phase_start_emission(
            context=request_context,
            emissions=((non_active_denied, binding),),
        )
        is None
    )
    assert (
        command_start_hooks._sequenced_command_phase_start_emission(
            context=request_context,
            emissions=(),
        )
        is None
    )
    assert not command_start_hooks._request_allows_non_active_actor(non_active_denied)

    assert command_start_hooks._validate_ability_index_mapping(
        {"player-a": AbilityCatalogIndex.from_records(())}
    )["player-a"] == AbilityCatalogIndex.from_records(())
    for kwargs, message in (
        ({"state": object()}, "state must be GameState"),
        ({"decisions": object()}, "decisions must be DecisionController"),
        ({"request": object()}, "request must be DecisionRequest"),
        ({"battle_shock_hooks": object()}, "must be a registry"),
        ({"runtime_modifier_registry": object()}, "must be a registry"),
    ):
        nested_common: dict[str, Any] = {
            "state": state,
            "decisions": decisions,
            "request": request,
            "active_player_id": "player-a",
            "battle_shock_hooks": battle_shock_hooks,
            "runtime_modifier_registry": runtime_modifiers,
            **kwargs,
        }
        with pytest.raises(GameLifecycleError, match=message):
            command_start_hooks._validate_nested_context_common(**nested_common)


def test_historical_battle_shock_context_exposes_only_authenticated_facts() -> None:
    decisions = DecisionController()
    state = _battle_state(
        game_id="phase11c-historical-battle-shock-context",
        decisions=decisions,
    )
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    model_id = unit.own_models[0].model_instance_id
    context = historical_battle_shock_context_for_unit(
        state=state,
        decisions=decisions,
        unit_instance_id=unit_id,
        active_player_id="player-a",
    )

    assert context.rules_unit(unit_id).unit_instance_id == unit_id
    assert unit_id in tuple(rules_unit.unit_instance_id for rules_unit in context.all_rules_units())
    assert context.rules_unit_containing_unit(unit_id).unit_instance_id == unit_id
    assert context.army_for_player("player-a").player_id == "player-a"
    assert context.unit_and_army(unit_id)[0] == unit
    assert context.model(model_id) == unit.own_models[0]
    assert context.unit_and_army_for_model(model_id)[0] == unit
    assert context.starting_strength(unit_id).unit_instance_id == unit_id
    assert context.placed_alive_model_ids(unit_id) == tuple(sorted(unit.own_model_ids()))
    assert len(context.geometry_models(unit_id)) == len(unit.own_models)
    assert context.component_placed_alive_model_ids(unit_id) == tuple(sorted(unit.own_model_ids()))
    assert len(context.component_geometry_models(unit_id)) == len(unit.own_models)

    invalid_context_calls: tuple[Callable[[], object], ...] = (
        lambda: context.rules_unit(""),
        lambda: context.rules_unit("missing-unit"),
        lambda: context.rules_unit_containing_unit("missing-unit"),
        lambda: context.army_for_player("missing-player"),
        lambda: context.unit_and_army("missing-unit"),
        lambda: context.model("missing-model"),
        lambda: context.unit_and_army_for_model("missing-model"),
        lambda: context.starting_strength("missing-unit"),
        lambda: context._starting_attached_record("missing-attached-unit"),
    )
    for invalid_call in invalid_context_calls:
        with pytest.raises(GameLifecycleError, match="Historical Battle-shock"):
            invalid_call()

    base = {
        "state": state,
        "event_records": context.event_records,
        "decision_records": context.decision_records,
        "boundary_event_index": context.boundary_event_index,
        "request": context.request,
        "active_player_id": context.active_player_id,
        "phase": context.phase,
        "phase_start_battle_shocked_unit_ids": context.phase_start_battle_shocked_unit_ids,
    }

    def build_context(**overrides: Any) -> Any:
        return historical_battle_shock_authority.historical_battle_shock_authority_context(
            **{  # pyright: ignore[reportArgumentType]
                **base,
                **overrides,
            }
        )

    drifted_player_request = replace(context.request)
    object.__setattr__(drifted_player_request, "player_id", "missing-player")
    invalid_context_builds: tuple[Callable[[], object], ...] = (
        lambda: build_context(state=cast(GameState, object())),
        lambda: build_context(request=cast(BattleShockTestRequest, object())),
        lambda: build_context(request=replace(context.request, game_id="forged-game")),
        lambda: build_context(request=drifted_player_request),
        lambda: build_context(active_player_id="missing-player"),
        lambda: build_context(phase=cast(BattlePhase, "command")),
        lambda: build_context(phase_start_battle_shocked_unit_ids=cast(Any, [])),
        lambda: build_context(
            phase_start_battle_shocked_unit_ids=(unit_id, unit_id),
        ),
    )
    for invalid_build in invalid_context_builds:
        with pytest.raises(GameLifecycleError, match="Historical Battle-shock"):
            invalid_build()


def test_command_battle_shock_result_state_update_contract_fails_closed() -> None:
    state = _battle_state(game_id="phase11c-command-result-state-contract")
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    candidate = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )[0]
    reason = candidate.test_reason
    assert reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
    request = BattleShockTestRequest.for_unit(
        request_id=command_candidates.command_battle_shock_request_id(
            battle_round=state.battle_round,
            active_player_id="player-a",
            unit_instance_id=unit_id,
            reason=reason,
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_id,
        reason=reason,
        leadership_target=6,
        below_half_strength_context=candidate.below_half_strength_context,
    )
    manager = DiceRollManager(state.game_id)
    passed = BattleShockResult.from_roll_state(
        result_id="phase11c-command-result-passed",
        request=request,
        roll_state=manager.roll_fixed(request.spec, [6, 6]),
    )
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c-command-result-failed",
        request=request,
        roll_state=manager.roll_fixed(request.spec, [1, 1]),
    )

    valid_cases: tuple[
        tuple[BattleShockResult, set[str], dict[str, JsonValue], tuple[str, ...]], ...
    ] = (
        (
            passed,
            {unit_id},
            {"state_update": "cleared_battle_shocked", "auto_passed": False},
            (unit_id,),
        ),
        (passed, set(), {"state_update": "not_required", "auto_passed": False}, ()),
        (
            failed,
            {unit_id},
            {"state_update": "already_battle_shocked", "auto_passed": False},
            (),
        ),
        (
            failed,
            set(),
            {"state_update": "recorded_battle_shocked", "auto_passed": False},
            (),
        ),
        (
            failed,
            set(),
            {
                "state_update": "recorded_missing_battle_shocked_descendants",
                "auto_passed": False,
            },
            (),
        ),
    )
    for result, phase_start_ids, payload, cleared_ids in valid_cases:
        command_history._validate_result_state_update(
            state=state,
            command_state_phase_start_ids=phase_start_ids,
            result=result,
            payload=cast(Any, payload),
            cleared_ids=cleared_ids,
        )

    invalid_cases: tuple[
        tuple[BattleShockResult, set[str], dict[str, JsonValue], tuple[str, ...]], ...
    ] = (
        (
            failed,
            set(),
            {"state_update": "recorded_battle_shocked", "auto_passed": True},
            (),
        ),
        (passed, {unit_id}, {"state_update": "not_required", "auto_passed": False}, ()),
        (
            passed,
            {unit_id},
            {"state_update": "cleared_battle_shocked", "auto_passed": False},
            ("missing-unit",),
        ),
        (
            passed,
            set(),
            {"state_update": "cleared_battle_shocked", "auto_passed": False},
            (unit_id,),
        ),
        (
            failed,
            set(),
            {"state_update": "recorded_battle_shocked", "auto_passed": False},
            (unit_id,),
        ),
        (
            failed,
            {unit_id},
            {"state_update": "recorded_battle_shocked", "auto_passed": False},
            (),
        ),
        (failed, set(), {"state_update": "not_required", "auto_passed": False}, ()),
    )
    for result, phase_start_ids, payload, cleared_ids in invalid_cases:
        with pytest.raises(GameLifecycleError, match="Command Battle-shock"):
            command_history._validate_result_state_update(
                state=state,
                command_state_phase_start_ids=phase_start_ids,
                result=result,
                payload=cast(Any, payload),
                cleared_ids=cleared_ids,
            )


def test_battle_shock_event_authority_helpers_fail_closed() -> None:
    game_id = "phase11c-battle-shock-event-authority"
    decisions = DecisionController()
    state = _battle_state(game_id=game_id, decisions=decisions)
    unit_id = "army-alpha:intercessor-unit-1"
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    historical = historical_battle_shock_context_for_unit(
        state=state,
        decisions=decisions,
        unit_instance_id=unit_id,
        active_player_id="player-a",
    )
    config = _config(game_id=game_id)
    armies = tuple(state.army_definitions)

    def bundle(*bindings: BattleShockHookBinding) -> RuntimeContentBundle:
        return RuntimeContentBundle.from_contributions(
            activation=RuntimeContentActivation.from_armies(
                armies=armies,
                catalog=config.army_catalog,
            ),
            armies=armies,
            catalog=config.army_catalog,
            contributions=(
                RuntimeContentContribution(
                    contribution_id=(
                        "phase11c:contribution:battle-shock-event-authority:"
                        + ":".join(binding.hook_id for binding in bindings)
                    ),
                    battle_shock_hook_bindings=bindings,
                ),
            )
            if bindings
            else (),
        )

    empty_bundle = bundle()
    assert battle_event_authority._historical_dice_expression(
        historical=historical,
        runtime_content_bundle=empty_bundle,
    ) == DiceExpression(quantity=2, sides=6)
    assert (
        battle_event_authority._historical_modifier_applications(
            historical=historical,
            runtime_content_bundle=empty_bundle,
        )
        == ()
    )
    assert (
        battle_event_authority._historical_reroll_permission(
            historical=historical,
            runtime_content_bundle=empty_bundle,
        )
        is None
    )

    semantic_request = replace(historical.request, leadership_target=6)
    semantic_values: dict[str, Any] = {
        "historical": historical,
        "prior_events": (),
        "request_index": 0,
        "request_base": {"source_kind": "phase11c_test"},
        "result": BattleShockResult.from_roll_state(
            result_id="phase11c:result:historical-semantics",
            request=semantic_request,
            roll_state=DiceRollManager(game_id).roll_fixed(semantic_request.spec, [6, 6]),
        ),
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND,
        "phase_start_battle_shocked_unit_ids": (),
        "runtime_content_bundle": empty_bundle,
    }
    battle_event_authority._validate_historical_request_semantics(**semantic_values)

    def result_with_request(request: BattleShockTestRequest) -> BattleShockResult:
        value = replace(cast(BattleShockResult, semantic_values["result"]))
        object.__setattr__(value, "request", request)
        return value

    wrong_player_request = replace(semantic_request)
    object.__setattr__(wrong_player_request, "player_id", "player-b")
    wrong_strength_request = replace(semantic_request)
    object.__setattr__(
        wrong_strength_request,
        "below_half_strength_context",
        replace(
            semantic_request.below_half_strength_context,
            current_model_count=(
                semantic_request.below_half_strength_context.current_model_count - 1
            ),
        ),
    )
    placed_ids = frozenset(historical.placed_alive_model_ids(unit_id))
    semantic_invalid_cases = (
        (
            {"result": result_with_request(replace(semantic_request, game_id="other-game"))},
            "occurrence drifted",
        ),
        ({"result": result_with_request(wrong_player_request)}, "owner drifted"),
        (
            {
                "historical": replace(
                    historical,
                    physical_models=tuple(
                        row
                        for row in historical.physical_models
                        if row.model_instance_id not in placed_ids
                    ),
                )
            },
            "not on battlefield",
        ),
        ({"result": result_with_request(wrong_strength_request)}, "strength context drifted"),
        (
            {
                "runtime_content_bundle": replace(
                    empty_bundle,
                    ability_indexes_by_player_id={
                        "player-b": empty_bundle.ability_indexes_by_player_id["player-b"]
                    },
                )
            },
            "lacks loaded Leadership authority",
        ),
        (
            {
                "result": result_with_request(
                    replace(
                        semantic_request,
                        leadership_target=semantic_request.leadership_target + 1,
                    )
                )
            },
            "Leadership lacks exact authority",
        ),
    )
    for overrides, message in semantic_invalid_cases:
        with pytest.raises(GameLifecycleError, match=message):
            battle_event_authority._validate_historical_request_semantics(
                **{  # pyright: ignore[reportArgumentType]
                    **semantic_values,
                    **overrides,
                }
            )

    missing_historical_leadership = RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding(
                modifier_id="phase11c:modifier:live-leadership-only",
                source_id="phase11c:source:live-leadership-only",
                handler=lambda context: context.current_value,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="lacks historical Leadership authority"):
        battle_event_authority._validate_historical_request_semantics(
            **{  # pyright: ignore[reportArgumentType]
                **semantic_values,
                "runtime_content_bundle": replace(
                    empty_bundle,
                    runtime_modifier_registry=missing_historical_leadership,
                ),
            }
        )

    missing_authority = BattleShockHookBinding(
        hook_id="phase11c:hook:missing-historical-authority",
        source_id="phase11c:source:missing-historical-authority",
        dice_expression_handler=lambda _context: None,
    )
    with pytest.raises(GameLifecycleError, match="lacks event-bound historical authority"):
        battle_event_authority._historical_contributions(
            historical=historical,
            runtime_content_bundle=bundle(missing_authority),
        )

    invalid_contribution = BattleShockHookBinding(
        hook_id="phase11c:hook:invalid-historical-contribution",
        source_id="phase11c:source:invalid-historical-contribution",
        outcome_handler=lambda _context: None,
        historical_contribution_handler=lambda _context: cast(
            HistoricalBattleShockContribution,
            object(),
        ),
    )
    with pytest.raises(GameLifecycleError, match="invalid contribution"):
        battle_event_authority._historical_contributions(
            historical=historical,
            runtime_content_bundle=bundle(invalid_contribution),
        )

    modifier = RollModifier(
        modifier_id="phase11c:modifier:historical",
        source_id="phase11c:source:historical-modifier",
        operand=-1,
    )
    permission = RerollPermission(
        source_id="phase11c:source:historical-reroll",
        timing_window="battle_shock_test",
        owning_player_id="player-a",
        eligible_roll_type=historical.request.spec.roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    drifted_contributions = (
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook:drifted-dice",
                source_id="phase11c:source:drifted-dice",
                outcome_handler=lambda _context: None,
                historical_contribution_handler=lambda _context: HistoricalBattleShockContribution(
                    dice_expression=DiceExpression(quantity=3, sides=6)
                ),
            ),
            "dice provider drifted",
        ),
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook:drifted-modifier",
                source_id="phase11c:source:drifted-modifier",
                outcome_handler=lambda _context: None,
                historical_contribution_handler=lambda _context: HistoricalBattleShockContribution(
                    modifiers=(modifier,)
                ),
            ),
            "modifier provider drifted",
        ),
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook:drifted-reroll",
                source_id="phase11c:source:drifted-reroll",
                outcome_handler=lambda _context: None,
                historical_contribution_handler=lambda _context: HistoricalBattleShockContribution(
                    reroll_permission=permission
                ),
            ),
            "reroll provider drifted",
        ),
    )
    for binding, message in drifted_contributions:
        with pytest.raises(GameLifecycleError, match=message):
            battle_event_authority._historical_contributions(
                historical=historical,
                runtime_content_bundle=bundle(binding),
            )

    dice_bindings = tuple(
        BattleShockHookBinding(
            hook_id=f"phase11c:hook:historical-dice-{quantity}",
            source_id=f"phase11c:source:historical-dice-{quantity}",
            dice_expression_handler=cast(
                Any,
                lambda _context, value=quantity: DiceExpression(  # pyright: ignore[reportUnknownLambdaType]
                    quantity=value,
                    sides=6,
                ),
            ),
            historical_contribution_handler=cast(
                Any,
                lambda _context, value=quantity: HistoricalBattleShockContribution(  # pyright: ignore[reportUnknownLambdaType]
                    dice_expression=DiceExpression(quantity=value, sides=6),
                ),
            ),
        )
        for quantity in (3, 2)
    )
    assert battle_event_authority._historical_dice_expression(
        historical=historical,
        runtime_content_bundle=bundle(dice_bindings[0]),
    ) == DiceExpression(quantity=3, sides=6)
    with pytest.raises(GameLifecycleError, match="conflicting overrides"):
        battle_event_authority._historical_dice_expression(
            historical=historical,
            runtime_content_bundle=bundle(*dice_bindings),
        )

    modifier_binding = BattleShockHookBinding(
        hook_id="phase11c:hook:historical-modifier",
        source_id="phase11c:source:historical-modifier",
        modifier_handler=lambda _context: (modifier,),
        historical_contribution_handler=lambda _context: HistoricalBattleShockContribution(
            modifiers=(modifier,)
        ),
    )
    applications = battle_event_authority._historical_modifier_applications(
        historical=historical,
        runtime_content_bundle=bundle(modifier_binding),
    )
    assert applications == (
        BattleShockModifierApplication(
            hook_id=modifier_binding.hook_id,
            source_id=cast(str, modifier.source_id),
            modifiers=(modifier,),
        ),
    )

    reroll_bindings = tuple(
        BattleShockHookBinding(
            hook_id=f"phase11c:hook:historical-reroll-{index}",
            source_id=f"phase11c:source:historical-reroll-{index}",
            reroll_permission_handler=lambda _context: permission,
            historical_contribution_handler=lambda _context: HistoricalBattleShockContribution(
                reroll_permission=permission
            ),
        )
        for index in range(2)
    )
    assert (
        battle_event_authority._historical_reroll_permission(
            historical=historical,
            runtime_content_bundle=bundle(reroll_bindings[0]),
        )
        == permission
    )
    with pytest.raises(GameLifecycleError, match="Multiple historical"):
        battle_event_authority._historical_reroll_permission(
            historical=historical,
            runtime_content_bundle=bundle(*reroll_bindings),
        )

    with pytest.raises(GameLifecycleError, match="dice expression lacks exact"):
        battle_event_authority._validate_historical_request_semantics(
            **{  # pyright: ignore[reportArgumentType]
                **semantic_values,
                "runtime_content_bundle": bundle(dice_bindings[0]),
            }
        )

    candidate = replace(
        command_candidates.command_battle_shock_candidate_inventory(
            state,
            "player-a",
            (),
        )[0],
        is_battle_shocked=True,
        eligibility_reasons=(
            command_candidates.CommandBattleShockEligibilityReason.CURRENTLY_BATTLE_SHOCKED,
        ),
    )
    snapshot = EventRecord(
        event_id="phase11c:event:candidate-authority-snapshot",
        event_type="battle_shock_step_snapshot_created",
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.COMMAND.value,
            "battle_shock_candidate_inventory": [validate_json_value(candidate.to_payload())],
            "battle_shock_phase_start_unit_ids": [],
        },
    )
    battle_event_authority._validate_command_candidate_model_authority(
        prior_events=(snapshot,),
        request_index=1,
        request=historical.request,
        active_player_id="player-a",
        phase_start_battle_shocked_unit_ids=(),
        placed_model_ids=historical.placed_alive_model_ids(unit_id),
    )
    invalid_candidate_calls: tuple[dict[str, Any], ...] = (
        {"request": cast(BattleShockTestRequest, object())},
        {"prior_events": ()},
        {
            "prior_events": (
                replace(
                    snapshot,
                    payload={
                        **cast(dict[str, Any], snapshot.payload),
                        "battle_shock_candidate_inventory": None,
                    },
                ),
            )
        },
        {"phase_start_battle_shocked_unit_ids": (unit_id,)},
    )
    candidate_values: dict[str, Any] = {
        "prior_events": (snapshot,),
        "request_index": 1,
        "request": historical.request,
        "active_player_id": "player-a",
        "phase_start_battle_shocked_unit_ids": (),
        "placed_model_ids": historical.placed_alive_model_ids(unit_id),
    }
    for candidate_overrides in invalid_candidate_calls:
        with pytest.raises(GameLifecycleError, match="Command Battle-shock candidate"):
            battle_event_authority._validate_command_candidate_model_authority(
                **{**candidate_values, **candidate_overrides}
            )

    result = BattleShockResult.from_roll_state(
        result_id="phase11c:result:event-authority",
        request=historical.request,
        roll_state=DiceRollManager(game_id).roll_fixed(historical.request.spec, [6, 6]),
    )
    request_payload = cast(
        dict[str, JsonValue],
        validate_json_value(historical.request.to_payload()),
    )
    request_event = EventRecord(
        event_id="phase11c:event:source-effect-request",
        event_type="battle_shock_test_requested",
        payload={"battle_shock_test_request": request_payload},
    )
    modifier_event = EventRecord(
        event_id="phase11c:event:source-effect-modifiers",
        event_type="battle_shock_modifiers_applied",
        payload={},
    )
    loaded_modifier_values: dict[str, Any] = {
        "event_records": (request_event, modifier_event),
        "decision_records": (),
        "modifier_event_index": 1,
        "request_base": {"source_kind": "command_battle_shock"},
        "result": result,
        "applications": (),
        "historical": historical,
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND,
        "phase_start_battle_shocked_unit_ids": (),
        "runtime_content_bundle": empty_bundle,
    }
    unknown_application = BattleShockModifierApplication(
        hook_id="phase11c:hook:unknown-loaded-modifier",
        source_id=cast(str, modifier.source_id),
        modifiers=(modifier,),
    )
    with pytest.raises(GameLifecycleError, match="lacks loaded runtime authority"):
        battle_event_authority._validate_loaded_modifier_applications(
            **{  # pyright: ignore[reportArgumentType]
                **loaded_modifier_values,
                "applications": (unknown_application,),
            }
        )
    with pytest.raises(GameLifecycleError, match="incomplete or context-invalid"):
        battle_event_authority._validate_loaded_modifier_applications(
            **{  # pyright: ignore[reportArgumentType]
                **loaded_modifier_values,
                "runtime_content_bundle": bundle(modifier_binding),
            }
        )
    source_evidence_binding = BattleShockHookBinding(
        hook_id="phase11c:hook:source-effect-evidence",
        source_id="phase11c:source:source-effect-evidence",
        modifier_handler=lambda _context: (modifier,),
        modifier_source_effect_evidence=True,
    )
    source_evidence_application = BattleShockModifierApplication(
        hook_id=source_evidence_binding.hook_id,
        source_id=source_evidence_binding.source_id,
        modifiers=(
            replace(
                modifier,
                modifier_id="phase11c:modifier:source-effect-evidence",
                source_id=source_evidence_binding.source_id,
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="source-effect applications"):
        battle_event_authority._validate_loaded_modifier_applications(
            **{  # pyright: ignore[reportArgumentType]
                **loaded_modifier_values,
                "applications": (source_evidence_application,),
                "runtime_content_bundle": bundle(source_evidence_binding),
            }
        )
    non_modifier_binding = BattleShockHookBinding(
        hook_id="phase11c:hook:not-a-modifier-provider",
        source_id="phase11c:source:not-a-modifier-provider",
        outcome_handler=lambda _context: None,
    )
    non_modifier_application = BattleShockModifierApplication(
        hook_id=non_modifier_binding.hook_id,
        source_id=non_modifier_binding.source_id,
        modifiers=(
            replace(
                modifier,
                modifier_id="phase11c:modifier:not-a-modifier-provider",
                source_id=non_modifier_binding.source_id,
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="hook authority is ambiguous"):
        battle_event_authority._validate_loaded_modifier_applications(
            **{  # pyright: ignore[reportArgumentType]
                **loaded_modifier_values,
                "applications": (non_modifier_application,),
                "runtime_content_bundle": bundle(non_modifier_binding),
            }
        )
    assert (
        battle_event_authority._expected_source_effect_modifier_applications(
            event_records=(request_event, modifier_event),
            decision_records=(),
            modifier_event_index=1,
            result=result,
        )
        == ()
    )
    for records, boundary, message in (
        ((request_event,), -1, "boundary"),
        ((modifier_event,), 0, "request authority"),
        (
            (
                replace(
                    request_event,
                    payload={
                        "battle_shock_test_request": request_payload,
                        "selected_target_recorded_effects_before_battle_shock": {},
                    },
                ),
                modifier_event,
            ),
            1,
            "effect evidence",
        ),
        (
            (
                replace(
                    request_event,
                    payload={
                        "battle_shock_test_request": request_payload,
                        "selected_target_recorded_effects_before_battle_shock": [],
                    },
                ),
                modifier_event,
            ),
            1,
            "decision is missing",
        ),
        (
            (
                replace(
                    request_event,
                    payload={
                        "battle_shock_test_request": request_payload,
                        "selected_target_recorded_effects_before_battle_shock": [],
                        "selected_target_decision_result": {},
                    },
                ),
                modifier_event,
            ),
            1,
            "decision identity",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_event_authority._expected_source_effect_modifier_applications(
                event_records=records,
                decision_records=(),
                modifier_event_index=boundary,
                result=result,
            )

    source_option = DecisionOption(option_id="select", label="Select")
    source_request = DecisionRequest(
        request_id="phase11c:event-authority:source-request",
        decision_type="phase11c_event_authority_source",
        actor_id="player-a",
        payload=None,
        options=(source_option,),
    )
    source_result = DecisionResult.for_request(
        result_id="phase11c:event-authority:source-result",
        request=source_request,
        selected_option_id=source_option.option_id,
    )
    source_record = DecisionRecord(
        record_id="phase11c:event-authority:source-record",
        request=source_request,
        result=source_result,
    )
    selected_target_modifier = RuleEffectSpec(
        kind=RuleEffectKind.MODIFY_DICE_ROLL,
        source_span=TextSpan(text="Subtract 1 from the test.", start=0, end=25),
        parameters=(
            RuleParameter(key="roll_type", value="battle_shock"),
            RuleParameter(key="target_scope", value="selected_unit"),
            RuleParameter(key="delta", value=-1),
        ),
    )
    source_effect = PersistingEffect(
        effect_id="phase11c:event-authority:selected-target-effect",
        source_rule_id="phase11c:event-authority:selected-target-rule",
        owner_player_id="player-b",
        target_unit_instance_ids=(unit_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "catalog_selected_target": {},
            "effect": validate_json_value(selected_target_modifier.to_payload()),
        },
    )
    source_request_event = EventRecord(
        event_id="phase11c:event-authority:decision-requested",
        event_type="decision_requested",
        payload=validate_json_value(source_request.to_payload()),
    )
    source_record_event = EventRecord(
        event_id="phase11c:event-authority:decision-recorded",
        event_type="decision_recorded",
        payload=validate_json_value(source_record.to_payload()),
    )
    exact_request_event = replace(
        request_event,
        payload={
            "battle_shock_test_request": request_payload,
            "selected_target_recorded_effects_before_battle_shock": [
                validate_json_value(source_effect.to_payload())
            ],
            "selected_target_decision_result": validate_json_value(source_result.to_payload()),
        },
    )
    exact_events = (
        source_request_event,
        source_record_event,
        exact_request_event,
        modifier_event,
    )
    (source_application,) = battle_event_authority._expected_source_effect_modifier_applications(
        event_records=exact_events,
        decision_records=(source_record,),
        modifier_event_index=3,
        result=result,
    )
    assert source_application.source_id == source_effect.source_rule_id
    assert battle_event_authority._has_exact_source_effect_modifier_authority(
        event_records=exact_events,
        decision_records=(source_record,),
        result=result,
        application=source_application,
    )
    wrong_target_effect = replace(
        source_effect,
        effect_id="phase11c:event-authority:wrong-target-effect",
        target_unit_instance_ids=("other-unit",),
    )
    mixed_effect_request = replace(
        exact_request_event,
        payload={
            **cast(dict[str, Any], exact_request_event.payload),
            "selected_target_recorded_effects_before_battle_shock": [
                None,
                validate_json_value(wrong_target_effect.to_payload()),
                validate_json_value(source_effect.to_payload()),
            ],
        },
    )
    assert battle_event_authority._expected_source_effect_modifier_applications(
        event_records=(*exact_events[:2], mixed_effect_request, modifier_event),
        decision_records=(source_record,),
        modifier_event_index=3,
        result=result,
    ) == (source_application,)
    with pytest.raises(GameLifecycleError, match="evidence is duplicated"):
        battle_event_authority._expected_source_effect_modifier_applications(
            event_records=(
                *exact_events[:2],
                replace(
                    exact_request_event,
                    payload={
                        **cast(dict[str, Any], exact_request_event.payload),
                        "selected_target_recorded_effects_before_battle_shock": [
                            validate_json_value(source_effect.to_payload()),
                            validate_json_value(source_effect.to_payload()),
                        ],
                    },
                ),
                modifier_event,
            ),
            decision_records=(source_record,),
            modifier_event_index=3,
            result=result,
        )

    selected_effect_event = EventRecord(
        event_id="phase11c:event-authority:selected-effect",
        event_type="catalog_selected_target_effect_selected",
        payload={
            "persisting_effects": [validate_json_value(source_effect.to_payload())],
            "request_id": source_request.request_id,
            "result_id": source_result.result_id,
        },
    )
    assert battle_event_authority._has_exact_source_effect_modifier_authority(
        event_records=(source_request_event, source_record_event, selected_effect_event),
        decision_records=(source_record,),
        result=result,
        application=source_application,
    )
    assert not battle_event_authority._has_exact_source_effect_modifier_authority(
        event_records=(
            EventRecord("malformed", "ignored", None),
            EventRecord("unrelated", "ignored", {}),
            EventRecord(
                "invalid-effects",
                "catalog_selected_target_effect_selected",
                {"persisting_effects": None},
            ),
            EventRecord(
                "invalid-selected-result",
                "battle_shock_test_requested",
                {
                    "battle_shock_test_request": validate_json_value(request_payload),
                    "selected_target_recorded_effects_before_battle_shock": [],
                    "selected_target_decision_result": None,
                },
            ),
            EventRecord(
                "nonmatching-effects",
                "catalog_selected_target_effect_selected",
                {
                    "persisting_effects": [
                        None,
                        validate_json_value(wrong_target_effect.to_payload()),
                    ],
                    "request_id": source_request.request_id,
                    "result_id": source_result.result_id,
                },
            ),
        ),
        decision_records=(source_record,),
        result=result,
        application=source_application,
    )
    with pytest.raises(GameLifecycleError, match="decision identity is invalid"):
        battle_event_authority._has_exact_source_effect_modifier_authority(
            event_records=(
                EventRecord(
                    "invalid-identity",
                    "catalog_selected_target_effect_selected",
                    {
                        "persisting_effects": [validate_json_value(source_effect.to_payload())],
                        "request_id": None,
                        "result_id": None,
                    },
                ),
            ),
            decision_records=(source_record,),
            result=result,
            application=source_application,
        )

    assert (
        battle_event_authority._generic_rule_effect_parameter(
            {"effect": {"parameters": [{"key": "wanted", "value": 3}]}},
            key="wanted",
        )
        == 3
    )
    assert (
        battle_event_authority._generic_rule_effect_parameter(
            {"effect": {"parameters": []}},
            key="missing",
        )
        is None
    )
    invalid_parameter_payloads: tuple[tuple[JsonValue, str], ...] = (
        ({}, "must be an object"),
        ({"effect": {}}, "parameters are invalid"),
        (
            {
                "effect": {
                    "parameters": [
                        {"key": "duplicate", "value": 1},
                        {"key": "duplicate", "value": 2},
                    ]
                }
            },
            "parameter is duplicated",
        ),
    )
    for payload, message in invalid_parameter_payloads:
        with pytest.raises(GameLifecycleError, match=message):
            battle_event_authority._generic_rule_effect_parameter(
                cast(Any, payload),
                key="duplicate",
            )

    assert battle_event_authority._looks_like_persisting_effect(
        validate_json_value(
            PersistingEffect(
                effect_id="phase11c:event-authority-effect",
                source_rule_id="phase11c:event-authority-source",
                owner_player_id="player-a",
                target_unit_instance_ids=(unit_id,),
                started_battle_round=1,
                started_phase=BattlePhaseKind.COMMAND,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=None,
            ).to_payload()
        )
    )
    assert not battle_event_authority._looks_like_persisting_effect(None)
    assert battle_event_authority._json_object(
        {"value": "ok"},
        context="test",
    ) == {"value": "ok"}
    with pytest.raises(GameLifecycleError, match="must be an object"):
        battle_event_authority._json_object(None, context="test")
    assert (
        battle_event_authority._required_identifier(
            "value",
            context="test",
        )
        == "value"
    )
    for value in (None, ""):
        with pytest.raises(GameLifecycleError, match="must be an identifier"):
            battle_event_authority._required_identifier(
                cast(Any, value),
                context="test",
            )

    runtime_values: dict[str, Any] = {
        "state": state,
        "event_records": (),
        "decision_records": (),
        "runtime_content_bundle": empty_bundle,
    }
    invalid_runtime_overrides: tuple[dict[str, Any], ...] = (
        {"state": object()},
        {"event_records": []},
        {"event_records": (object(),)},
        {"decision_records": []},
        {"decision_records": (object(),)},
    )
    for runtime_overrides in invalid_runtime_overrides:
        with pytest.raises(GameLifecycleError, match="Battle-shock runtime authority"):
            battle_event_authority.validate_battle_shock_runtime_content_authority(
                **{**runtime_values, **runtime_overrides}
            )

    effect = unit_move_completed_hooks.UnitMoveCompletedBattleShockEffect(
        hook_id="phase11c:hook:move-completed",
        source_id="phase11c:source:move-completed",
        source_rule_id="phase11c:rule:move-completed",
        target_unit_instance_id=unit_id,
        target_player_id="player-a",
        trigger_event_id="phase11c:event:charge-move-completed",
        replay_payload={"value": "ok"},
    )
    request_base = unit_move_completed_hooks.unit_move_completed_battle_shock_base_payload(
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id="player-a",
        completed_phase=BattlePhase.CHARGE,
        movement_action="charge_move",
        effect=effect,
    )
    move_request_event = EventRecord(
        event_id="phase11c:event:move-completed-request",
        event_type="battle_shock_test_requested",
        payload={
            **request_base,
            "battle_shock_test_request": validate_json_value(request_payload),
        },
    )
    move_values: dict[str, Any] = {
        "state": state,
        "event_records": (move_request_event,),
        "decision_records": (),
        "request_event_index": 0,
        "request_base": request_base,
        "request": historical.request,
        "active_player_id": "player-a",
        "phase": BattlePhase.CHARGE,
        "phase_start_battle_shocked_unit_ids": (),
        "runtime_content_bundle": empty_bundle,
    }
    move_invalid_cases: tuple[tuple[dict[str, Any], str], ...] = (
        ({"request_event_index": -1}, "index is invalid"),
        ({"request": object()}, "requires a request"),
        ({"active_player_id": ""}, "active player is invalid"),
        ({"phase": "charge"}, "phase is invalid"),
        ({"request_base": {}}, "source schema drifted"),
        (
            {"event_records": (replace(move_request_event, event_type="wrong"),)},
            "request occurrence drifted",
        ),
        (
            {"event_records": (move_request_event, move_request_event)},
            "request occurrence is ambiguous",
        ),
        (
            {
                "request_base": {**request_base, "hook_id": None},
                "event_records": (
                    replace(
                        move_request_event,
                        payload={
                            **request_base,
                            "hook_id": None,
                            "battle_shock_test_request": validate_json_value(request_payload),
                        },
                    ),
                ),
            },
            "source payload is invalid",
        ),
        ({}, "trigger type drifted"),
    )
    for move_overrides, message in move_invalid_cases:
        with pytest.raises(GameLifecycleError, match=message):
            battle_event_authority.validate_unit_move_completed_battle_shock_request_authority(
                **{**move_values, **move_overrides}
            )


def test_battle_shock_source_family_contract_is_exact_and_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-battle-shock-source-family")
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    candidate = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )[0]
    reason = candidate.test_reason
    assert reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
    request = BattleShockTestRequest.for_unit(
        request_id=command_candidates.command_battle_shock_request_id(
            battle_round=state.battle_round,
            active_player_id="player-a",
            unit_instance_id=unit_id,
            reason=reason,
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_id,
        reason=reason,
        leadership_target=6,
        below_half_strength_context=candidate.below_half_strength_context,
    )
    result = BattleShockResult.from_roll_state(
        result_id="phase11c:source-family:result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [6, 6]),
    )
    request_payload = cast(
        dict[str, JsonValue],
        validate_json_value(request.to_payload()),
    )
    command_base: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND.value,
        "source_kind": "command_battle_shock",
    }
    snapshot = EventRecord(
        event_id="phase11c:source-family:snapshot",
        event_type="battle_shock_step_snapshot_created",
        payload={
            **command_base,
            "battle_shock_phase_start_unit_ids": [],
            "battle_shock_candidate_inventory": [validate_json_value(candidate.to_payload())],
        },
    )

    battle_source_authority.validate_battle_shock_source_family_authority(
        event_records=(snapshot,),
        decision_records=(),
        resolved_index=1,
        request_payload=request_payload,
        request_context={**command_base, "battle_shock_test_request": request_payload},
        request_base=command_base,
        result=result,
    )
    assert (
        battle_source_authority._matching_command_snapshots(
            prior_events=(
                EventRecord("ignored", "ignored", {}),
                EventRecord("malformed", "battle_shock_step_snapshot_created", None),
                snapshot,
            ),
            request_payload=request_payload,
            request_base=command_base,
        )
        == 1
    )
    assert not battle_source_authority._command_candidate_inventory_matches_request(
        None,
        request_payload=request_payload,
    )
    assert not battle_source_authority._command_candidate_inventory_matches_request(
        [],
        request_payload={"unit_instance_id": None, "reason": reason.value},
    )
    with pytest.raises(GameLifecycleError, match="payload is malformed"):
        battle_source_authority._command_candidate_inventory_matches_request(
            [None],
            request_payload=request_payload,
        )
    with pytest.raises(GameLifecycleError, match="payload is incomplete"):
        battle_source_authority._command_candidate_inventory_matches_request(
            [{}],
            request_payload=request_payload,
        )
    with pytest.raises(GameLifecycleError, match="identity is duplicated"):
        battle_source_authority._command_candidate_inventory_matches_request(
            [
                validate_json_value(candidate.to_payload()),
                validate_json_value(candidate.to_payload()),
            ],
            request_payload=request_payload,
        )
    with pytest.raises(GameLifecycleError, match="must be an object"):
        battle_source_authority._object(None, "test source")
    assert battle_source_authority._object(
        {"value": "ok"},
        "test source",
    ) == {"value": "ok"}

    invalid_command_calls: tuple[tuple[dict[str, JsonValue], BattleShockResult, str], ...] = (
        ({**command_base, "source_kind": None}, result, "recognized source"),
        ({**command_base, "phase": BattlePhase.MOVEMENT.value}, result, "Command source"),
        ({**command_base, "unexpected": True}, result, "Command source"),
        (
            command_base,
            replace(
                result,
                request=replace(
                    request,
                    reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
                ),
            ),
            "Command source",
        ),
        ({**command_base, "source_kind": "unsupported"}, result, "source kind is unsupported"),
    )
    for invalid_base, invalid_result, message in invalid_command_calls:
        with pytest.raises(GameLifecycleError, match=message):
            battle_source_authority.validate_battle_shock_source_family_authority(
                event_records=(snapshot,),
                decision_records=(),
                resolved_index=1,
                request_payload=request_payload,
                request_context={**invalid_base, "battle_shock_test_request": request_payload},
                request_base=invalid_base,
                result=invalid_result,
            )

    option = DecisionOption(option_id="accept", label="Accept")
    source_request = DecisionRequest(
        request_id="phase11c:source-family:decision",
        decision_type="phase11c_source_family",
        actor_id="player-a",
        payload=None,
        options=(option,),
    )
    source_result = DecisionResult.for_request(
        result_id="phase11c:source-family:decision-result",
        request=source_request,
        selected_option_id=option.option_id,
    )
    source_record = DecisionRecord(
        record_id="phase11c:source-family:decision-record",
        request=source_request,
        result=source_result,
    )
    source_events = (
        EventRecord(
            "source-request",
            "decision_requested",
            validate_json_value(source_request.to_payload()),
        ),
        EventRecord(
            "source-record",
            "decision_recorded",
            validate_json_value(source_record.to_payload()),
        ),
    )
    source_identity: dict[str, JsonValue] = {
        "request_id": source_request.request_id,
        "result_id": source_result.result_id,
    }
    stratagem_request = replace(request, reason=BattleShockTestReason.FORCED_BY_STRATAGEM)
    stratagem_result = BattleShockResult.from_roll_state(
        result_id="phase11c:source-family:stratagem-result",
        request=stratagem_request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(stratagem_request.spec, [6, 6]),
    )
    stratagem_event = EventRecord(
        "stratagem-source",
        "stratagem_used",
        source_identity,
    )
    stratagem_base: dict[str, JsonValue] = {
        **command_base,
        "source_kind": "stratagem_battle_shock",
        "source_stratagem_use": source_identity,
    }
    battle_source_authority.validate_battle_shock_source_family_authority(
        event_records=(*source_events, stratagem_event),
        decision_records=(source_record,),
        resolved_index=3,
        request_payload=cast(
            dict[str, JsonValue],
            validate_json_value(stratagem_request.to_payload()),
        ),
        request_context={
            **stratagem_base,
            "battle_shock_test_request": validate_json_value(stratagem_request.to_payload()),
        },
        request_base=stratagem_base,
        result=stratagem_result,
    )
    with pytest.raises(GameLifecycleError, match="Stratagem source authority"):
        battle_source_authority.validate_battle_shock_source_family_authority(
            event_records=source_events,
            decision_records=(source_record,),
            resolved_index=2,
            request_payload=cast(
                dict[str, JsonValue],
                validate_json_value(stratagem_request.to_payload()),
            ),
            request_context={},
            request_base=stratagem_base,
            result=stratagem_result,
        )
    with pytest.raises(GameLifecycleError, match="decision identity is invalid"):
        battle_source_authority._validate_source_decision_ids(
            event_records=(),
            decision_records=(),
            resolved_index=0,
            source_payload={},
        )

    persisting_record: dict[str, JsonValue] = {
        "source_rule_id": "phase11c:source-family:prefix-rule",
        "owner_player_id": "player-a",
        "target_unit_instance_ids": [unit_id],
        "started_battle_round": state.battle_round,
        "started_phase": BattlePhase.COMMAND.value,
        "expiration": validate_json_value(EffectExpiration.end_of_battle().to_payload()),
        "effect_payload": {"value": "persisted"},
    }
    expected_persisting_record: dict[str, JsonValue] = {
        "effect_id": (
            f"{source_result.result_id}:catalog_post_shoot_hit_target_effect_selected:000"
        ),
        **persisting_record,
    }
    battle_source_authority._validate_selected_target_recorded_prefix(
        event_records=(),
        mutation_index=0,
        decision_record=source_record,
        effect_records=(persisting_record, {}),
        current_effect_index=1,
        recorded_before=(expected_persisting_record,),
    )
    conditional_record: dict[str, JsonValue] = {
        **persisting_record,
        "immediate_effect_condition": "prior_effect_inflicted_mortal_wounds",
    }
    battle_source_authority._validate_selected_target_recorded_prefix(
        event_records=(),
        mutation_index=0,
        decision_record=source_record,
        effect_records=(conditional_record, {}),
        current_effect_index=1,
        recorded_before=(),
    )
    with pytest.raises(GameLifecycleError, match="prefix condition is unsupported"):
        battle_source_authority._validate_selected_target_recorded_prefix(
            event_records=(),
            mutation_index=0,
            decision_record=source_record,
            effect_records=(
                {**persisting_record, "immediate_effect_condition": "unsupported"},
                {},
            ),
            current_effect_index=1,
            recorded_before=(),
        )
    with pytest.raises(GameLifecycleError, match="persisting effect is incomplete"):
        battle_source_authority._validate_selected_target_recorded_prefix(
            event_records=(),
            mutation_index=0,
            decision_record=source_record,
            effect_records=({}, {}),
            current_effect_index=1,
            recorded_before=(),
        )
    with pytest.raises(GameLifecycleError, match="recorded effect prefix drifted"):
        battle_source_authority._validate_selected_target_recorded_prefix(
            event_records=(),
            mutation_index=0,
            decision_record=source_record,
            effect_records=(persisting_record, {}),
            current_effect_index=1,
            recorded_before=(),
        )

    immediate_common: dict[str, JsonValue] = {
        "catalog_record_id": "phase11c:source-family:catalog-record",
        "source_rule_id": "phase11c:source-family:immediate-rule",
        "source_unit_instance_id": "army-alpha:intercessor-unit-2",
        "selection_clause_id": "phase11c:source-family:selection-clause",
        "effect_clause_id": "phase11c:source-family:effect-clause",
        "effect_index": 1,
        "selected_target_unit_instance_id": unit_id,
        "effect_payload": {"value": "immediate"},
    }
    mortal_record: dict[str, JsonValue] = {
        **immediate_common,
        "immediate_effect_kind": "inflict_mortal_wounds",
    }
    mortal_payload: dict[str, JsonValue] = {
        "selected_target_decision_result": validate_json_value(source_result.to_payload()),
        "selected_target_effect_record": mortal_record,
        "wounds_inflicted": 1,
    }
    mortal_event = EventRecord(
        "phase11c:source-family:mortal-event",
        "catalog_selected_target_mortal_wounds_resolved",
        mortal_payload,
    )
    assert battle_source_authority._selected_target_immediate_resolution_events(
        event_records=(
            EventRecord("ignored", "ignored", None),
            EventRecord(
                "wrong-decision",
                "catalog_selected_target_mortal_wounds_resolved",
                {**mortal_payload, "selected_target_decision_result": {}},
            ),
            EventRecord(
                "wrong-effect",
                "catalog_selected_target_mortal_wounds_resolved",
                {**mortal_payload, "selected_target_effect_record": {}},
            ),
            mortal_event,
        ),
        mutation_index=4,
        decision_record=source_record,
        effect_record=mortal_record,
        immediate_kind="inflict_mortal_wounds",
    ) == (mortal_payload,)
    battle_source_authority._validate_selected_target_recorded_prefix(
        event_records=(mortal_event,),
        mutation_index=1,
        decision_record=source_record,
        effect_records=(mortal_record, {}),
        current_effect_index=1,
        recorded_before=(mortal_payload,),
    )
    with pytest.raises(GameLifecycleError, match="immediate-effect authority drifted"):
        battle_source_authority._validate_selected_target_recorded_prefix(
            event_records=(),
            mutation_index=0,
            decision_record=source_record,
            effect_records=(mortal_record, {}),
            current_effect_index=1,
            recorded_before=(),
        )

    battle_shock_record: dict[str, JsonValue] = {
        **immediate_common,
        "immediate_effect_kind": "force_battle_shock_test",
    }
    battle_shock_payload: dict[str, JsonValue] = {
        "selected_target_decision_result": validate_json_value(source_result.to_payload()),
        **immediate_common,
    }
    assert battle_source_authority._selected_target_immediate_resolution_events(
        event_records=(
            EventRecord(
                "wrong-battle-shock-effect",
                "catalog_selected_target_battle_shock_resolved",
                {**battle_shock_payload, "effect_index": 2},
            ),
            EventRecord(
                "battle-shock-effect",
                "catalog_selected_target_battle_shock_resolved",
                battle_shock_payload,
            ),
        ),
        mutation_index=2,
        decision_record=source_record,
        effect_record=battle_shock_record,
        immediate_kind="force_battle_shock_test",
    ) == (battle_shock_payload,)
    with pytest.raises(GameLifecycleError, match="immediate effect kind is unsupported"):
        battle_source_authority._selected_target_immediate_resolution_events(
            event_records=(),
            mutation_index=0,
            decision_record=source_record,
            effect_record={},
            immediate_kind="unsupported",
        )

    invalid_selected_target_sources: tuple[tuple[object, dict[str, JsonValue], str], ...] = (
        (object(), {}, "request is invalid"),
        (request, {}, "source shape drifted"),
        (
            request,
            dict.fromkeys(
                battle_source_authority._SELECTED_TARGET_BASE_KEYS,
                None,
            ),
            "source authority drifted",
        ),
    )
    for invalid_request, invalid_base, message in invalid_selected_target_sources:
        with pytest.raises(GameLifecycleError, match=message):
            battle_source_authority._validate_selected_target_source(
                event_records=(),
                decision_records=(),
                mutation_index=0,
                request=invalid_request,
                base=invalid_base,
            )

    command_start_request = replace(request, reason=BattleShockTestReason.FORCED_BY_ARMY_RULE)
    command_start_result = BattleShockResult.from_roll_state(
        result_id="phase11c:source-family:command-start-result",
        request=command_start_request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(command_start_request.spec, [6, 6]),
    )
    command_start_base: dict[str, JsonValue] = {
        **command_base,
        "source_kind": "command_phase_start_battle_shock",
        "source_faction_rule_state": source_identity,
    }
    battle_source_authority.validate_battle_shock_source_family_authority(
        event_records=source_events,
        decision_records=(source_record,),
        resolved_index=2,
        request_payload=cast(
            dict[str, JsonValue],
            validate_json_value(command_start_request.to_payload()),
        ),
        request_context={
            **command_start_base,
            "battle_shock_test_request": validate_json_value(command_start_request.to_payload()),
        },
        request_base=command_start_base,
        result=command_start_result,
    )
    with pytest.raises(GameLifecycleError, match="Command-start source authority"):
        battle_source_authority.validate_battle_shock_source_family_authority(
            event_records=source_events,
            decision_records=(source_record,),
            resolved_index=2,
            request_payload=cast(
                dict[str, JsonValue],
                validate_json_value(command_start_request.to_payload()),
            ),
            request_context={},
            request_base={**command_start_base, "phase": BattlePhase.MOVEMENT.value},
            result=command_start_result,
        )

    move_base: dict[str, JsonValue] = {
        **command_base,
        "source_kind": "unit_move_completed_battle_shock",
        "trigger_event_id": "phase11c:source-family:move-trigger",
        "movement_action": "charge_move",
        "hook_id": "phase11c:source-family:move-hook",
        "effect_key": "phase11c:source-family:move-effect",
        "source_rule_id": "phase11c:source-family:move-rule",
        "target_unit_instance_id": unit_id,
        "target_player_id": "player-a",
        "replay_payload": {},
    }
    trigger = EventRecord(
        cast(str, move_base["trigger_event_id"]),
        "charge_move_completed",
        {},
    )
    battle_source_authority.validate_battle_shock_source_family_authority(
        event_records=(trigger,),
        decision_records=(),
        resolved_index=1,
        request_payload=request_payload,
        request_context={**move_base, "battle_shock_test_request": request_payload},
        request_base=move_base,
        result=result,
    )
    with pytest.raises(GameLifecycleError, match="move-completed source authority"):
        battle_source_authority.validate_battle_shock_source_family_authority(
            event_records=(),
            decision_records=(),
            resolved_index=0,
            request_payload=request_payload,
            request_context={},
            request_base=move_base,
            result=result,
        )

    permission = RerollPermission(
        source_id="phase11c:source-family:reroll",
        timing_window="battle_shock_test",
        owning_player_id="player-a",
        eligible_roll_type=request.spec.roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    pending_request = DecisionRequest(
        request_id="phase11c:source-family:pending-reroll",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        payload=None,
        options=(option,),
    )
    pending = battle_resolution_authority.PendingBattleShockRerollAuthority(
        decision_request=pending_request,
        test_request=request,
        initial_roll_state=DiceRollState.from_result(result.roll_state.original_result),
        permission=permission,
        source_kind="command_battle_shock",
        base_payload=command_base,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(),
        passed_state_policy=BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
        resolved_event_types=("battle_shock_test_resolved",),
        additional_modifier_applications=(),
    )
    empty_bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=tuple(state.army_definitions),
            catalog=_config(game_id=state.game_id).army_catalog,
        ),
        armies=tuple(state.army_definitions),
        catalog=_config(game_id=state.game_id).army_catalog,
        contributions=(),
    )
    battle_source_authority.validate_pending_battle_shock_source_family_authority(
        state=state,
        event_records=(snapshot,),
        decision_records=(),
        request_event_index=1,
        authority=pending,
        runtime_content_bundle=empty_bundle,
    )
    for invalid_pending, message in (
        (
            replace(pending, base_payload={**command_base, "unexpected": True}),
            "Pending Command Battle-shock source authority drifted",
        ),
        (replace(pending, source_kind="unsupported"), "source kind is unsupported"),
        (replace(pending, resolved_event_types=("wrong",)), "resolved-event inventory"),
        (
            replace(
                pending,
                source_kind="unit_move_completed_battle_shock",
                base_payload=move_base,
                resolved_event_types=(
                    "battle_shock_test_resolved",
                    "unit_move_completed_battle_shock_resolved",
                ),
                additional_modifier_applications=(
                    BattleShockModifierApplication(
                        hook_id="phase11c:source-family:extra-hook",
                        source_id="phase11c:source-family:extra-source",
                        modifiers=(
                            RollModifier(
                                modifier_id="phase11c:source-family:extra-modifier",
                                source_id="phase11c:source-family:extra-source",
                                operand=-1,
                            ),
                        ),
                    ),
                ),
            ),
            "unsupported source applications",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_source_authority.validate_pending_battle_shock_source_family_authority(
                state=state,
                event_records=(snapshot,),
                decision_records=(),
                request_event_index=1,
                authority=invalid_pending,
                runtime_content_bundle=empty_bundle,
            )


def test_section_eight_battle_shock_hook_and_value_boundaries_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-battle-shock-hook-boundaries")
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    request = _battle_shock_request_for_unit(state, unit)
    ability_index = AbilityCatalogIndex.from_records(())

    assert (
        battle_shock_module.battle_shock_leadership_target_for_rules_unit(
            rules_unit,
            current_model_ids=tuple(sorted(unit.own_model_ids())),
            ability_index=ability_index,
            state=None,
        )
        == 6
    )
    leadership_invalid_calls: tuple[Callable[[], object], ...] = (
        lambda: battle_shock_module.battle_shock_leadership_target_for_rules_unit(
            cast(Any, object()),
            current_model_ids=tuple(sorted(unit.own_model_ids())),
            ability_index=ability_index,
            state=None,
        ),
        lambda: battle_shock_module.battle_shock_leadership_target_for_rules_unit(
            rules_unit,
            current_model_ids=tuple(sorted(unit.own_model_ids())),
            ability_index=cast(Any, object()),
            state=None,
        ),
        lambda: battle_shock_module.battle_shock_leadership_target_for_rules_unit(
            rules_unit,
            current_model_ids=(),
            ability_index=ability_index,
            state=None,
        ),
        lambda: battle_shock_module.battle_shock_leadership_target_for_rules_unit(
            rules_unit,
            current_model_ids=("missing-model",),
            ability_index=ability_index,
            state=None,
        ),
    )
    for invalid_call in leadership_invalid_calls:
        with pytest.raises(GameLifecycleError, match="Leadership"):
            invalid_call()

    assert battle_shock_module._battle_shock_dice_expression(None) == DiceExpression(
        quantity=2, sides=6
    )
    for expression in (object(), DiceExpression(quantity=1, sides=6)):
        with pytest.raises(GameLifecycleError, match="dice expression"):
            battle_shock_module._battle_shock_dice_expression(cast(Any, expression))
    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        battle_shock_module._battle_shock_dice_expression_mapping([])
    with pytest.raises(GameLifecycleError, match="dice expression"):
        battle_shock_module._battle_shock_dice_expression_mapping({unit_id: object()})

    starting_records = tuple(state.starting_strength_records)
    assert (
        battle_shock_module._starting_strength_by_unit(
            starting_records,
            player_id="player-a",
        )[unit_id].unit_instance_id
        == unit_id
    )
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        battle_shock_module._starting_strength_by_unit(
            list(starting_records),
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="must contain StartingStrengthRecord"):
        battle_shock_module._starting_strength_by_unit(
            (object(),),
            player_id="player-a",
        )
    player_a_record = next(
        record for record in starting_records if record.unit_instance_id == unit_id
    )
    with pytest.raises(GameLifecycleError, match="duplicate units"):
        battle_shock_module._starting_strength_by_unit(
            (player_a_record, player_a_record),
            player_id="player-a",
        )

    source_modifier = RollModifier(
        modifier_id="phase11c:hook-boundary:modifier",
        source_id="phase11c:hook-boundary:source",
        operand=-1,
    )
    application = BattleShockModifierApplication(
        hook_id="phase11c:hook-boundary:hook",
        source_id=cast(str, source_modifier.source_id),
        modifiers=(source_modifier,),
    )
    application_payload = application.to_payload()
    with pytest.raises(GameLifecycleError, match="payload drifted"):
        battle_hooks.BattleShockModifierApplication.from_payload(
            cast(Any, {**application_payload, "unexpected": True})
        )

    modifier_context = BattleShockModifierContext(
        state=state,
        request=request,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(),
    )
    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        BattleShockRerollPermissionContext(
            state=cast(Any, object()),
            request=request,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="request must be a BattleShockTestRequest"):
        BattleShockRerollPermissionContext(
            state=state,
            request=cast(Any, object()),
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )

    missing_source_registry = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook-boundary:missing-source-hook",
                source_id="phase11c:hook-boundary:missing-source",
                modifier_handler=lambda _context: (
                    RollModifier(
                        modifier_id="phase11c:hook-boundary:missing-source-modifier",
                        operand=-1,
                    ),
                ),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="require source IDs"):
        missing_source_registry.modifier_applications_for(modifier_context)

    reroll_context = BattleShockRerollPermissionContext(
        state=state,
        request=request,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(),
    )
    none_reroll_registry = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook-boundary:none-reroll-hook",
                source_id="phase11c:hook-boundary:none-reroll-source",
                reroll_permission_handler=lambda _context: None,
            ),
        )
    )
    assert none_reroll_registry.reroll_permission_for(reroll_context) is None

    invalid_registry_calls: tuple[Callable[[], object], ...] = (
        lambda: BattleShockHookRegistry.empty().modifier_applications_for(cast(Any, object())),
        lambda: BattleShockHookRegistry.empty().reroll_permission_for(cast(Any, object())),
        lambda: BattleShockHookRegistry.empty().dice_expression_for(cast(Any, object())),
        lambda: BattleShockHookRegistry.empty().forced_test_applications_for(cast(Any, object())),
        lambda: BattleShockHookRegistry.empty().resolve_outcomes(cast(Any, object())),
        lambda: BattleShockHookRegistry.empty().pending_outcome_authority_for(cast(Any, object())),
    )
    for invalid_registry_call in invalid_registry_calls:
        with pytest.raises(GameLifecycleError):
            invalid_registry_call()

    pending_option = DecisionOption(option_id="continue", label="Continue")
    pending_request = DecisionRequest(
        request_id="phase11c:hook-boundary:pending-request",
        decision_type="phase11c_hook_boundary",
        actor_id="player-a",
        payload=None,
        options=(pending_option,),
    )
    outcome_decisions = DecisionController()
    outcome_decisions.event_log.append("battle_shock_test_resolved", {})
    outcome_context = BattleShockPendingOutcomeAuthorityContext(
        state=state,
        decisions=outcome_decisions,
        request=pending_request,
    )
    outcome_result = BattleShockResult.from_roll_state(
        result_id="phase11c:hook-boundary:outcome-result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [6, 6]),
    )
    claim = BattleShockPendingOutcomeAuthority(result=outcome_result, resolved_event_index=0)

    invalid_claim_registry = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook-boundary:invalid-claim-hook",
                source_id="phase11c:hook-boundary:invalid-claim-source",
                outcome_handler=lambda _context: None,
                pending_outcome_authority_validator=lambda _context: cast(
                    BattleShockPendingOutcomeAuthority,
                    object(),
                ),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="typed authority"):
        invalid_claim_registry.pending_outcome_authority_for(outcome_context)

    def mutate_authority_context(context: BattleShockPendingOutcomeAuthorityContext) -> None:
        context.decisions.event_log.append("phase11c_mutated", {})

    mutation_registry = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook-boundary:mutation-hook",
                source_id="phase11c:hook-boundary:mutation-source",
                outcome_handler=lambda _context: None,
                pending_outcome_authority_validator=mutate_authority_context,
            ),
        )
    )
    mutation_decisions = DecisionController.from_payload(outcome_decisions.to_payload())
    with pytest.raises(GameLifecycleError, match="mutated runtime state"):
        mutation_registry.pending_outcome_authority_for(
            replace(outcome_context, decisions=mutation_decisions)
        )

    out_of_bounds_registry = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:hook-boundary:bounds-hook",
                source_id="phase11c:hook-boundary:bounds-source",
                outcome_handler=lambda _context: None,
                pending_outcome_authority_validator=lambda _context: replace(
                    claim,
                    resolved_event_index=99,
                ),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="out of bounds"):
        out_of_bounds_registry.pending_outcome_authority_for(outcome_context)

    multiple_claim_registry = BattleShockHookRegistry.from_bindings(
        tuple(
            BattleShockHookBinding(
                hook_id=f"phase11c:hook-boundary:multiple-hook:{index}",
                source_id=f"phase11c:hook-boundary:multiple-source:{index}",
                outcome_handler=lambda _context: None,
                pending_outcome_authority_validator=lambda _context: claim,
            )
            for index in range(2)
        )
    )
    with pytest.raises(GameLifecycleError, match="multiple loaded authorities"):
        multiple_claim_registry.pending_outcome_authority_for(outcome_context)

    empty_outcome_decisions = DecisionController()
    assert (
        battle_shock_lifecycle_authority._stratagem_battle_shock_outcome_request(
            empty_outcome_decisions
        )
        is None
    )
    unsupported_outcome_decisions = DecisionController()
    unsupported_outcome_decisions.request_decision(pending_request)
    with pytest.raises(GameLifecycleError, match="unsupported decision type"):
        battle_shock_lifecycle_authority._stratagem_battle_shock_outcome_request(
            unsupported_outcome_decisions
        )
    multiple_outcome_decisions = DecisionController.from_payload(
        unsupported_outcome_decisions.to_payload()
    )
    multiple_outcome_decisions.request_decision(
        replace(pending_request, request_id="phase11c:hook-boundary:pending-request-2")
    )
    with pytest.raises(GameLifecycleError, match="queued multiple decisions"):
        battle_shock_lifecycle_authority._stratagem_battle_shock_outcome_request(
            multiple_outcome_decisions
        )

    assert (
        battle_shock_pending_authority._decision_recorded_request_id(
            EventRecord("event-a", "other", None)
        )
        is None
    )
    assert (
        battle_shock_pending_authority._decision_recorded_request_id(
            EventRecord("event-b", "decision_recorded", None)
        )
        is None
    )
    assert (
        battle_shock_pending_authority._decision_recorded_request_id(
            EventRecord("event-c", "decision_recorded", {"request": None})
        )
        is None
    )
    assert (
        battle_shock_pending_authority._decision_recorded_request_id(
            EventRecord(
                "event-d",
                "decision_recorded",
                {"request": {"request_id": "request-a"}},
            )
        )
        == "request-a"
    )


def test_battle_shock_request_and_live_leadership_edges_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-battle-shock-live-edges")
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit,
        starting_strength=state.starting_strength_record_for_unit(unit_id),
        current_model_ids=tuple(sorted(unit.own_model_ids())),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase11c:battle-shock-live-edges:request",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        leadership_target=6,
        below_half_strength_context=context,
    )
    passed = BattleShockResult.from_roll_state(
        result_id="phase11c:battle-shock-live-edges:passed",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [6, 6]),
    )
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c:battle-shock-live-edges:failed",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
    )

    with pytest.raises(GameLifecycleError, match="BelowHalfStrengthContext"):
        replace(
            request,
            below_half_strength_context=cast(BelowHalfStrengthContext, object()),
        )
    with pytest.raises(GameLifecycleError, match="ModifiedRollResult"):
        replace(passed, modified_roll=cast(ModifiedRollResult, object()))
    with pytest.raises(GameLifecycleError, match="requires a BattleShockResult"):
        BattleShockedUnitState.from_result(
            result=cast(BattleShockResult, object()),
            unit=unit,
        )
    for invalid_result, invalid_rules_unit, message in (
        (cast(BattleShockResult, object()), rules_unit, "requires a BattleShockResult"),
        (passed, rules_unit, "Passed Battle-shock"),
        (failed, cast(Any, object()), "requires a RulesUnitView"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            BattleShockedUnitState.from_rules_unit(
                result=invalid_result,
                rules_unit=invalid_rules_unit,
            )
    wrong_identity_request = replace(request)
    object.__setattr__(wrong_identity_request, "unit_instance_id", "missing-unit")
    wrong_identity_result = replace(failed)
    object.__setattr__(wrong_identity_result, "request", wrong_identity_request)
    with pytest.raises(GameLifecycleError, match="canonical rules-unit ID"):
        BattleShockedUnitState.from_rules_unit(
            result=wrong_identity_result,
            rules_unit=rules_unit,
        )
    wrong_owner_request = replace(request)
    object.__setattr__(wrong_owner_request, "player_id", "player-b")
    wrong_owner_result = replace(failed)
    object.__setattr__(wrong_owner_result, "request", wrong_owner_request)
    with pytest.raises(GameLifecycleError, match="owner drift"):
        BattleShockedUnitState.from_rules_unit(
            result=wrong_owner_result,
            rules_unit=rules_unit,
        )

    ability_index = AbilityCatalogIndex.from_records(())
    model_ids = tuple(sorted(unit.own_model_ids()))
    assert (
        battle_shock_module.battle_shock_leadership_target_for_rules_unit(
            rules_unit,
            current_model_ids=model_ids,
            ability_index=ability_index,
            state=state,
        )
        == 6
    )
    leadership_invalid_calls = (
        (
            cast(Any, object()),
            model_ids,
            ability_index,
            "requires a RulesUnitView",
        ),
        (rules_unit, model_ids, cast(Any, object()), "requires an AbilityCatalogIndex"),
        (rules_unit, (), ability_index, "requires current models"),
        (rules_unit, ("missing-model",), ability_index, "model is not in the rules unit"),
    )
    for invalid_unit, invalid_ids, invalid_index, message in leadership_invalid_calls:
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_module.battle_shock_leadership_target_for_rules_unit(
                invalid_unit,
                current_model_ids=invalid_ids,
                ability_index=invalid_index,
                state=state,
            )
    for invalid_unit, invalid_ids, invalid_index, message in (
        (cast(Any, object()), model_ids, ability_index, "requires a UnitInstance"),
        (unit, model_ids, cast(Any, object()), "requires an AbilityCatalogIndex"),
        (unit, (), ability_index, "requires current models"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_module._best_leadership(
                invalid_unit,
                current_model_ids=invalid_ids,
                ability_index=invalid_index,
                state=state,
            )
    with pytest.raises(GameLifecycleError, match="found no models"):
        battle_shock_module._base_leadership(
            unit,
            current_model_ids=("missing-model",),
            ability_index=ability_index,
        )
    with pytest.raises(GameLifecycleError, match="requires a ModelInstance"):
        battle_shock_module._model_leadership(cast(Any, object()))

    for call, message in (
        (
            lambda: battle_shock_module._runtime_modifier_registry(cast(Any, object())),
            "runtime modifier registry is invalid",
        ),
        (
            lambda: battle_shock_module._battle_shock_ability_index(cast(Any, object())),
            "ability_index must be",
        ),
        (
            lambda: battle_shock_module._battle_shock_dice_expression(cast(Any, object())),
            "dice expression must be",
        ),
        (
            lambda: battle_shock_module._battle_shock_dice_expression(
                DiceExpression(quantity=1, sides=6)
            ),
            "must be 2D6 or 3D6",
        ),
        (
            lambda: battle_shock_module._battle_shock_dice_expression_mapping([]),
            "must be a mapping",
        ),
        (
            lambda: battle_shock_module._starting_strength_by_unit(
                [],
                player_id="player-a",
            ),
            "must be a tuple",
        ),
        (
            lambda: battle_shock_module._starting_strength_by_unit(
                (object(),),
                player_id="player-a",
            ),
            "must contain StartingStrengthRecord",
        ),
        (
            lambda: battle_shock_module._validate_identifier_tuple(
                "identifiers",
                ("a", "a"),
            ),
            "must not contain duplicates",
        ),
        (
            lambda: battle_shock_module._validate_positive_int(
                "value",
                True,
            ),
            "must be an integer",
        ),
        (
            lambda: battle_shock_module._validate_positive_int(
                "value",
                0,
            ),
            "must be at least 1",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            call()

    with pytest.raises(GameLifecycleError, match="allow_battle_shocked must be a bool"):
        friendly_stratagem_target_permission(
            player_id="player-a",
            target_player_id="player-a",
            target_unit_instance_id=unit_id,
            battle_shocked_unit_ids=(),
            allow_battle_shocked=cast(Any, 1),
        )

    off_battlefield = _battle_state(game_id="phase11c-battle-shock-request-off-board")
    assert off_battlefield.battlefield_state is not None
    off_battlefield.battlefield_state = off_battlefield.battlefield_state.without_unit_placement(
        unit_id
    )
    army = off_battlefield.army_definition_for_player("player-a")
    assert army is not None
    with pytest.raises(GameLifecycleError, match="eligible off-battlefield"):
        collect_battle_shock_test_requests(
            game_id=off_battlefield.game_id,
            battle_round=off_battlefield.battle_round,
            player_id="player-a",
            army=army,
            battlefield_state=off_battlefield.battlefield_state,
            starting_strength_records=tuple(off_battlefield.starting_strength_records),
            battle_shocked_unit_ids=(unit_id,),
            state=off_battlefield,
        )


def test_precomputed_battle_shock_resolution_contract_edges_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-precomputed-battle-shock-edges")
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    request = _battle_shock_request_for_unit(state, unit)
    result = BattleShockResult.from_roll_state(
        result_id="phase11c:precomputed-battle-shock:result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [6, 6]),
    )
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    base_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND.value,
        "source_kind": "command_battle_shock",
    }
    common_values: dict[str, Any] = {
        "state": state,
        "decisions": decisions,
        "result": result,
        "phase": BattlePhase.COMMAND,
        "auto_passed": False,
        "phase_start_battle_shocked_unit_ids": (),
        "passed_state_policy": BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
        "base_payload": base_payload,
        "resolved_event_types": ("battle_shock_test_resolved",),
        "modifier_applications": (),
    }
    for outcome_overrides, message in (
        ({"state": object()}, "requires GameState"),
        ({"decisions": object()}, "requires decisions"),
        ({"result": object()}, "requires result"),
        ({"auto_passed": 1}, "must be a boolean"),
        (
            {"phase": BattlePhase.MOVEMENT},
            "only valid in the Command phase",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution.record_precomputed_battle_shock_result_events(
                **{  # pyright: ignore[reportArgumentType]
                    **common_values,
                    **outcome_overrides,
                }
            )

    application_a = BattleShockModifierApplication(
        hook_id="phase11c:precomputed:hook-a",
        source_id="phase11c:precomputed:source-a",
        modifiers=(
            RollModifier(
                modifier_id="phase11c:precomputed:modifier-a",
                source_id="phase11c:precomputed:source-a",
                operand=-1,
            ),
        ),
    )
    application_b = BattleShockModifierApplication(
        hook_id="phase11c:precomputed:hook-b",
        source_id="phase11c:precomputed:source-b",
        modifiers=(
            RollModifier(
                modifier_id="phase11c:precomputed:modifier-b",
                source_id="phase11c:precomputed:source-b",
                operand=1,
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="modifiers lack exact application authority"):
        battle_resolution.record_precomputed_battle_shock_result_events(
            **{  # pyright: ignore[reportArgumentType]
                **common_values,
                "modifier_applications": (application_a,),
            }
        )
    invalid_modifier_application_values: tuple[tuple[object, str], ...] = (
        ([], "typed tuple"),
        ((object(),), "typed tuple"),
        ((application_b, application_a), "must be sorted"),
        ((application_a, application_a), "identities are duplicated"),
    )
    for values, message in invalid_modifier_application_values:
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution._validate_modifier_applications(cast(Any, values))

    outcome_values = {
        **common_values,
        "manager": manager,
        "battle_shock_hooks": BattleShockHookRegistry.empty(),
        "active_player_id": "player-a",
    }
    invalid_outcome_overrides: tuple[tuple[dict[str, Any], str], ...] = (
        ({"manager": object()}, "requires dice manager"),
        ({"battle_shock_hooks": object()}, "requires hooks"),
        ({"modifier_applications": (application_a,)}, "modifier authority drifted"),
    )
    for outcome_resolution_overrides, message in invalid_outcome_overrides:
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution.record_precomputed_battle_shock_result_and_outcome_events(
                **{  # pyright: ignore[reportArgumentType]
                    **outcome_values,
                    **outcome_resolution_overrides,
                }
            )

    def drifted_result(**request_changes: Any) -> BattleShockResult:
        forged_request = replace(request)
        for field, value in request_changes.items():
            object.__setattr__(forged_request, field, value)
        forged_result = replace(result)
        object.__setattr__(forged_result, "request", forged_request)
        return forged_result

    context_invalid_cases = (
        (drifted_result(game_id="wrong-game"), base_payload, "game_id drift"),
        (drifted_result(battle_round=2), base_payload, "battle_round drift"),
        (drifted_result(player_id="missing-player"), base_payload, "player_id is unknown"),
        (drifted_result(player_id="player-b"), base_payload, "unit owner drift"),
        (result, {**base_payload, "game_id": "wrong-game"}, "base game_id drift"),
        (result, {**base_payload, "battle_round": 2}, "base battle_round drift"),
        (
            result,
            {**base_payload, "phase": BattlePhase.MOVEMENT.value},
            "base phase drift",
        ),
    )
    for invalid_result, invalid_base, message in context_invalid_cases:
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution._validate_precomputed_result_context(
                state=state,
                result=invalid_result,
                phase=BattlePhase.COMMAND,
                base_payload=invalid_base,
            )

    for value, message in (
        (object(), "must be a string"),
        ("unsupported", "is unsupported"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution._passed_state_policy_from_token(value)
    for call, message in (
        (
            lambda: battle_resolution._payload_object(
                None,
                context="test",
            ),
            "must be an object",
        ),
        (
            lambda: battle_resolution._payload_modifier_applications(
                {},
                key="applications",
            ),
            "missing required key",
        ),
        (
            lambda: battle_resolution._payload_modifier_applications(
                {"applications": None},
                key="applications",
            ),
            "must be an object list",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            call()


def test_battle_shock_pending_reroll_authority_edges_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-pending-reroll-authority-edges")
    unit_id = "army-alpha:intercessor-unit-1"
    request = _battle_shock_request_for_unit(state, _unit_by_id(state, unit_id))
    manager = DiceRollManager(state.game_id)
    initial = DiceRollState.from_result(manager.roll_fixed(request.spec, [1, 1]).original_result)
    permission = RerollPermission(
        source_id="phase11c:pending-reroll-authority",
        timing_window="battle_shock_test",
        owning_player_id="player-a",
        eligible_roll_type=request.spec.roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    base_payload = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND.value,
        "source_kind": "command_battle_shock",
    }
    context: dict[str, Any] = {
        "source_kind": "command_battle_shock",
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": "player-a",
        "battle_shock_test_request": request.to_payload(),
        "battle_shock_roll_state": initial.to_payload(),
        "phase_start_battle_shocked_unit_ids": [],
        "passed_state_policy": BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED.value,
        "base_payload": base_payload,
        "resolved_event_types": ["battle_shock_test_resolved"],
        "additional_modifier_applications": [],
    }
    reroll_request = manager.build_reroll_request(
        initial,
        request_id="phase11c:pending-reroll-authority:request",
        actor_id="player-a",
        permission=permission,
        extra_payload={"battle_shock_context": context},
    )
    parsed = battle_resolution_authority.parse_pending_battle_shock_reroll_authority(reroll_request)
    assert parsed.test_request == request
    assert parsed.initial_roll_state == initial

    def with_context(**changes: Any) -> DecisionRequest:
        payload = cast(dict[str, Any], reroll_request.payload)
        return replace(
            reroll_request,
            payload={
                **payload,
                "battle_shock_context": {**context, **changes},
            },
        )

    different_spec = DiceRollSpec(
        expression=DiceExpression(quantity=3, sides=6),
        reason=request.spec.reason,
        roll_type=request.spec.roll_type,
        actor_id=request.spec.actor_id,
    )
    different_initial = DiceRollState.from_result(
        manager.roll_fixed(different_spec, [1, 1, 1]).original_result
    )
    invalid_requests = (
        (
            with_context(battle_shock_roll_state=different_initial.to_payload()),
            "initial roll state drifted",
        ),
        (with_context(resolved_event_types=[]), "resolved-event inventory drifted"),
        (with_context(passed_state_policy="unsupported"), "state policy is unsupported"),
        (
            with_context(
                base_payload={**base_payload, "active_player_id": "player-b"},
            ),
            "occurrence context drifted",
        ),
        (
            replace(
                reroll_request,
                options=(replace(reroll_request.options[0], label="Drifted"),),
            ),
            "reroll request drifted",
        ),
    )
    for invalid_request, message in invalid_requests:
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution_authority.parse_pending_battle_shock_reroll_authority(invalid_request)

    result = BattleShockResult.from_roll_state(
        result_id="phase11c:pending-reroll-authority:result",
        request=request,
        roll_state=manager.roll_fixed(request.spec, [6, 6]),
    )
    for reason in (
        BattleShockTestReason.BELOW_HALF_STRENGTH,
        BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
    ):
        invalid_reason_request = replace(request, reason=reason)
        invalid_result = replace(result)
        object.__setattr__(invalid_result, "request", invalid_reason_request)
        with pytest.raises(GameLifecycleError, match="lacks predicate authority"):
            battle_resolution_authority._validate_reason_context(invalid_result)

    option = DecisionOption(option_id="decline", label="Decline", payload={"selected_indices": []})
    decision_request = DecisionRequest(
        request_id="phase11c:pending-reroll-authority:actor-request",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        payload=None,
        options=(option,),
    )
    missing_actor_result = DecisionResult.for_request(
        result_id="phase11c:pending-reroll-authority:actor-result",
        request=decision_request,
        selected_option_id=option.option_id,
    )
    missing_actor_record = DecisionRecord(
        record_id="phase11c:pending-reroll-authority:actor-record",
        request=decision_request,
        result=missing_actor_result,
    )
    object.__setattr__(missing_actor_result, "actor_id", None)
    with pytest.raises(GameLifecycleError, match="result actor is missing"):
        battle_resolution_authority._result_actor(missing_actor_record)
    object.__setattr__(missing_actor_result, "actor_id", "player-a")
    assert (
        battle_resolution_authority._reroll_request_payload(
            replace(missing_actor_record, request=replace(decision_request, payload=None))
        )
        is None
    )
    assert (
        battle_resolution_authority._reroll_request_payload(
            replace(
                missing_actor_record,
                request=replace(
                    decision_request,
                    payload={"battle_shock_context": None},
                ),
            )
        )
        is None
    )


def test_battle_shock_resolution_and_state_history_helpers_fail_closed() -> None:
    state = _battle_state(game_id="phase11c-battle-shock-history-helper")
    unit_id = "army-alpha:intercessor-unit-1"
    unit = _unit_by_id(state, unit_id)
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
        starting_strength=state.starting_strength_record_for_unit(unit_id),
        current_model_ids=tuple(sorted(unit.own_model_ids())),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase11c:battle-shock-history-helper-request",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        leadership_target=7,
        below_half_strength_context=context,
    )
    result = BattleShockResult.from_roll_state(
        result_id="phase11c:battle-shock-history-helper-result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [6, 6]),
    )

    option = DecisionOption(
        option_id="reroll",
        label="Reroll",
        payload={"selected_indices": [0, 1]},
    )
    decision_request = DecisionRequest(
        request_id="phase11c:battle-shock-history-reroll-request",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        payload={
            "battle_shock_context": {
                "battle_shock_test_request": validate_json_value(request.to_payload())
            }
        },
        options=(option,),
    )
    decision_result = DecisionResult.for_request(
        result_id="phase11c:battle-shock-history-reroll-result",
        request=decision_request,
        selected_option_id=option.option_id,
    )
    record = DecisionRecord(
        record_id="phase11c:battle-shock-history-reroll-record",
        request=decision_request,
        result=decision_result,
    )
    assert battle_resolution_authority._selected_reroll_indices(record) == (0, 1)
    assert battle_resolution_authority._reroll_request_payload(record) == request.to_payload()
    invalid_reroll_result_payloads: tuple[tuple[JsonValue, str], ...] = (
        (None, "must be an object"),
        ({"selected_indices": None}, "indices are invalid"),
        ({"selected_indices": [0, 0]}, "indices drifted"),
        ({"selected_indices": [-1]}, "indices drifted"),
    )
    for reroll_result_payload, message in invalid_reroll_result_payloads:
        invalid_result = replace(decision_result, payload=reroll_result_payload)
        invalid_record = replace(record)
        object.__setattr__(invalid_record, "result", invalid_result)
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution_authority._selected_reroll_indices(invalid_record)

    assert (
        battle_resolution_authority._passed_state_policy(
            {"passed_state_policy": BattleShockPassedStatePolicy.PRESERVE.value}
        )
        is BattleShockPassedStatePolicy.PRESERVE
    )
    with pytest.raises(GameLifecycleError, match="unsupported"):
        battle_resolution_authority._passed_state_policy({"passed_state_policy": "unsupported"})
    battle_resolution_authority._validate_source_state_policy(
        source_kind="command_battle_shock",
        passed_state_policy=BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED,
    )
    source_policy_cases: tuple[tuple[str, BattleShockPassedStatePolicy, str | None], ...] = (
        ("stratagem_battle_shock", BattleShockPassedStatePolicy.PRESERVE, None),
        ("unsupported", BattleShockPassedStatePolicy.PRESERVE, "source kind is unsupported"),
        (
            "command_battle_shock",
            BattleShockPassedStatePolicy.PRESERVE,
            "policy drifted",
        ),
    )
    for source_kind, policy, policy_message in source_policy_cases:
        if policy_message is None:
            battle_resolution_authority._validate_source_state_policy(
                source_kind=source_kind,
                passed_state_policy=policy,
            )
        else:
            with pytest.raises(GameLifecycleError, match=policy_message):
                battle_resolution_authority._validate_source_state_policy(
                    source_kind=source_kind,
                    passed_state_policy=policy,
                )

    assert battle_resolution_authority._identifier_list(
        ["a", "b"],
        "identifiers",
    ) == ("a", "b")
    assert battle_resolution_authority._identifier_list(
        ["b", "a"],
        "identifiers",
        require_sorted=False,
    ) == ("b", "a")
    for value, message in (
        (None, "is invalid"),
        ([1], "is invalid"),
        (["b", "a"], "drifted"),
        (["a", "a"], "drifted"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution_authority._identifier_list(
                cast(Any, value),
                "identifiers",
            )

    modifier_a = BattleShockModifierApplication(
        hook_id="phase11c:hook:a",
        source_id="phase11c:source:a",
        modifiers=(
            RollModifier(
                modifier_id="phase11c:modifier:a",
                source_id="phase11c:source:a",
                operand=-1,
            ),
        ),
    )
    modifier_b = BattleShockModifierApplication(
        hook_id="phase11c:hook:b",
        source_id="phase11c:source:b",
        modifiers=(
            RollModifier(
                modifier_id="phase11c:modifier:b",
                source_id="phase11c:source:b",
                operand=1,
            ),
        ),
    )
    assert battle_resolution_authority._modifier_application_list(
        [
            validate_json_value(modifier_a.to_payload()),
            validate_json_value(modifier_b.to_payload()),
        ],
        "modifiers",
    ) == (modifier_a, modifier_b)
    invalid_modifier_payloads: tuple[tuple[JsonValue, str], ...] = (
        (None, "is invalid"),
        ([1], "is invalid"),
        (
            [
                validate_json_value(modifier_b.to_payload()),
                validate_json_value(modifier_a.to_payload()),
            ],
            "drifted",
        ),
        (
            [
                validate_json_value(modifier_a.to_payload()),
                validate_json_value(modifier_a.to_payload()),
            ],
            "drifted",
        ),
    )
    for modifier_payload, message in invalid_modifier_payloads:
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution_authority._modifier_application_list(
                modifier_payload,
                "modifiers",
            )

    assert battle_resolution_authority._object(
        {"value": "ok"},
        "test",
    ) == {"value": "ok"}
    assert (
        battle_resolution_authority._identifier(
            "value",
            "test",
        )
        == "value"
    )
    assert battle_resolution_authority._phase(BattlePhase.COMMAND.value) is BattlePhase.COMMAND
    for invalid_call, message in (
        (
            lambda: battle_resolution_authority._object(None, "test"),
            "must be an object",
        ),
        (
            lambda: battle_resolution_authority._identifier("", "test"),
            "must be an identifier",
        ),
        (
            lambda: battle_resolution_authority._phase("unsupported"),
            "phase is unsupported",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            invalid_call()

    invalid_resolution_authority_kwargs: tuple[tuple[dict[str, Any], str], ...] = (
        ({"event_records": []}, "requires event records"),
        ({"event_records": (object(),)}, "requires event records"),
        ({"decision_records": []}, "requires decision records"),
        ({"decision_records": (object(),)}, "requires decision records"),
        ({"resolved_index": -1}, "index is invalid"),
        ({"result": object()}, "requires a result"),
    )
    for kwargs, message in invalid_resolution_authority_kwargs:
        values: dict[str, Any] = {
            "event_records": (EventRecord("event", "battle_shock_test_resolved", {}),),
            "decision_records": (),
            "resolved_index": 0,
            "resolved_payload": {},
            "result": result,
            **kwargs,
        }
        with pytest.raises(GameLifecycleError, match=message):
            battle_resolution_authority.parse_battle_shock_resolution_authority(**values)

    with pytest.raises(GameLifecycleError, match="requires a dice-reroll request"):
        battle_resolution_authority.parse_pending_battle_shock_reroll_authority(cast(Any, request))
    malformed_pending = replace(
        decision_request,
        payload={"battle_shock_context": {}},
    )
    with pytest.raises(GameLifecycleError, match="context shape drifted"):
        battle_resolution_authority.parse_pending_battle_shock_reroll_authority(malformed_pending)

    battle_shock_state_history.validate_battle_shock_state_history(
        state=state,
        event_records=(),
        decision_records=(),
    )
    invalid_state_history_kwargs: tuple[tuple[dict[str, Any], str], ...] = (
        ({"state": object()}, "requires GameState"),
        ({"event_records": []}, "requires event records"),
        ({"event_records": (object(),)}, "requires event records"),
        ({"decision_records": []}, "requires decision records"),
        ({"decision_records": (object(),)}, "requires decision records"),
    )
    for kwargs, message in invalid_state_history_kwargs:
        values = {
            "state": state,
            "event_records": (),
            "decision_records": (),
            **kwargs,
        }
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_state_history.validate_battle_shock_state_history(**values)

    assert (
        battle_shock_state_history.battle_shock_state_authority_before_event(
            state=state,
            event_records=(),
            decision_records=(),
            event_index=0,
        ).battle_shocked_unit_ids
        == ()
    )
    with pytest.raises(GameLifecycleError, match="boundary index is invalid"):
        battle_shock_state_history.battle_shock_state_authority_before_event(
            state=state,
            event_records=(),
            decision_records=(),
            event_index=-1,
        )

    owner_by_unit_id, model_ids_by_unit_id = battle_shock_state_history._historical_unit_inventory(
        state=state
    )
    assert owner_by_unit_id[unit_id] == "player-a"
    assert model_ids_by_unit_id[unit_id] == tuple(unit.own_model_ids())
    assert battle_shock_state_history._starting_attached_records_by_identity(state=state) == {}
    replayed = {
        unit_id: BattleShockedUnitState(
            player_id="player-a",
            unit_instance_id=unit_id,
            model_instance_ids=tuple(unit.own_model_ids()),
            source_result_id="phase11c:battle-shock-state-source",
            battle_round_started=1,
        )
    }
    assert battle_shock_state_history._active_state_ids_for_request(
        unit_instance_id=unit_id,
        replayed_states=replayed,
        attached_by_identity={},
        active_attached_ids=set(),
    ) == {unit_id}
    alive_ids = set(unit.own_model_ids())
    assert battle_shock_state_history._current_state_target_ids_for_request(
        unit_instance_id=unit_id,
        attached_by_identity={},
        active_attached_ids=set(),
        model_ids_by_unit_id=model_ids_by_unit_id,
        alive_model_ids=alive_ids,
    ) == (unit_id,)
    assert (
        battle_shock_state_history._current_state_target_ids_for_request(
            unit_instance_id="missing-unit",
            attached_by_identity={},
            active_attached_ids=set(),
            model_ids_by_unit_id=model_ids_by_unit_id,
            alive_model_ids=alive_ids,
        )
        == ()
    )

    battle_shock_state_history._validate_split_occurrence(
        state=state,
        payload={"battle_round": 1, "phase": None, "active_player_id": None},
    )
    split_occurrence_cases: tuple[tuple[dict[str, JsonValue], str], ...] = (
        ({"battle_round": -1}, "round drifted"),
        ({"battle_round": 1, "phase": "unsupported"}, "phase drifted"),
        (
            {"battle_round": 1, "phase": None, "active_player_id": "missing"},
            "active player drifted",
        ),
    )
    for split_occurrence_payload, message in split_occurrence_cases:
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_state_history._validate_split_occurrence(
                state=state,
                payload=split_occurrence_payload,
            )

    assert battle_shock_state_history._cleared_unit_ids(
        {"cleared_battle_shocked_unit_ids": [unit_id]}
    ) == (unit_id,)
    for value, message in (
        (None, "are invalid"),
        ([1], "are invalid"),
        ([unit_id, unit_id], "drifted"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_state_history._cleared_unit_ids(
                {"cleared_battle_shocked_unit_ids": cast(Any, value)}
            )
    event = EventRecord("phase11c:event:state-history", "state-history", {"value": "ok"})
    assert battle_shock_state_history._event_payload(event) == {"value": "ok"}
    with pytest.raises(GameLifecycleError, match="payload is invalid"):
        battle_shock_state_history._event_payload(replace(event, payload=None))
    assert (
        battle_shock_state_history._payload_string(
            {"field": "value"},
            "field",
        )
        == "value"
    )
    with pytest.raises(GameLifecycleError, match="field is invalid"):
        battle_shock_state_history._payload_string(
            {"field": ""},
            "field",
        )


def test_battle_shock_state_history_attached_split_authority_fail_closed() -> None:
    state, attached_id, bodyguard_id, leader_id = _attached_battle_state_for_split()
    attached = rules_unit_view_by_id(state=state, unit_instance_id=attached_id)
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=attached,
        starting_strength=state.starting_strength_record_for_unit(attached_id),
        current_model_ids=tuple(model.model_instance_id for model in attached.alive_models()),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase11c:state-history-split:request",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=attached_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=context,
    )
    failed = BattleShockResult.from_roll_state(
        result_id="phase11c:state-history-split:request:result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
    )
    source_state = BattleShockedUnitState.from_rules_unit(
        result=failed,
        rules_unit=attached,
    )
    state.record_battle_shock_result(failed)
    split_events = EventLog()
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id, bodyguard_id),
        event_log=split_events,
    )
    assert len(split_events.records) == 2
    split_payload = cast(dict[str, Any], split_events.records[0].payload)
    transfer_payload = cast(dict[str, Any], split_events.records[1].payload)

    authority_state, _, _, _ = _attached_battle_state_for_split()
    owner_by_id, model_ids_by_id = battle_shock_state_history._historical_unit_inventory(
        state=authority_state
    )
    attached_by_id = battle_shock_state_history._starting_attached_records_by_identity(
        state=authority_state
    )
    starting_attached_records = list(authority_state.starting_attached_unit_records)
    collision_record = replace(starting_attached_records[0])
    object.__setattr__(collision_record, "attached_unit_instance_id", bodyguard_id)
    authority_state.starting_attached_unit_records = [collision_record]
    with pytest.raises(GameLifecycleError, match="attached identity collides"):
        battle_shock_state_history._historical_unit_inventory(state=authority_state)
    authority_state.starting_attached_unit_records = [
        starting_attached_records[0],
        starting_attached_records[0],
    ]
    with pytest.raises(GameLifecycleError, match="attached lineage is ambiguous"):
        battle_shock_state_history._starting_attached_records_by_identity(state=authority_state)
    authority_state.starting_attached_unit_records = starting_attached_records
    assert attached_by_id[attached_id] == attached_by_id[bodyguard_id]
    assert attached_by_id[attached_id] == attached_by_id[leader_id]
    assert battle_shock_state_history._active_state_ids_for_request(
        unit_instance_id=bodyguard_id,
        replayed_states={attached_id: source_state},
        attached_by_identity=attached_by_id,
        active_attached_ids={attached_id},
    ) == {attached_id}
    split_replayed = {
        bodyguard_id: replace(
            source_state,
            unit_instance_id=bodyguard_id,
            model_instance_ids=model_ids_by_id[bodyguard_id],
        ),
        leader_id: replace(
            source_state,
            unit_instance_id=leader_id,
            model_instance_ids=model_ids_by_id[leader_id],
        ),
    }
    assert battle_shock_state_history._active_state_ids_for_request(
        unit_instance_id=attached_id,
        replayed_states=split_replayed,
        attached_by_identity=attached_by_id,
        active_attached_ids=set(),
    ) == {bodyguard_id, leader_id}
    assert battle_shock_state_history._active_state_ids_for_request(
        unit_instance_id=bodyguard_id,
        replayed_states=split_replayed,
        attached_by_identity=attached_by_id,
        active_attached_ids=set(),
    ) == {bodyguard_id}
    alive_ids = {
        model.model_instance_id
        for army in authority_state.army_definitions
        for unit in army.units
        for model in unit.own_models
        if model.is_alive
    }
    assert battle_shock_state_history._current_state_target_ids_for_request(
        unit_instance_id=attached_id,
        attached_by_identity=attached_by_id,
        active_attached_ids={attached_id},
        model_ids_by_unit_id=model_ids_by_id,
        alive_model_ids=alive_ids,
    ) == (attached_id,)
    assert set(
        battle_shock_state_history._current_state_target_ids_for_request(
            unit_instance_id=attached_id,
            attached_by_identity=attached_by_id,
            active_attached_ids=set(),
            model_ids_by_unit_id=model_ids_by_id,
            alive_model_ids=alive_ids,
        )
    ) == {bodyguard_id, leader_id}

    active_attached_ids = {attached_id}
    split_identity = battle_shock_state_history._apply_rules_unit_split_event(
        state=authority_state,
        payload=split_payload,
        active_attached_ids=active_attached_ids,
        final_active_attached_ids=set(),
        alive_model_ids=alive_ids,
    )
    assert split_identity == (
        attached_id,
        tuple(split_payload["surviving_unit_instance_ids"]),
    )
    assert not active_attached_ids
    replayed_states = {attached_id: source_state}
    battle_shock_state_history._apply_split_transfer_event(
        state=authority_state,
        payload=transfer_payload,
        replayed_states=replayed_states,
        owner_by_unit_id=owner_by_id,
        model_ids_by_unit_id=model_ids_by_id,
        expected_split=(split_identity[0], split_identity[1], split_payload),
    )
    assert set(replayed_states) == {bodyguard_id, leader_id}

    split_invalid_cases = (
        ({**split_payload, "unexpected": True}, {attached_id}, "payload drifted"),
        ({**split_payload, "player_id": "player-b"}, {attached_id}, "identity drifted"),
        (
            {
                **split_payload,
                "surviving_unit_instance_ids": [bodyguard_id, bodyguard_id],
            },
            {attached_id},
            "survivors drifted",
        ),
    )
    for invalid_payload, active_ids, message in split_invalid_cases:
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_state_history._apply_rules_unit_split_event(
                state=authority_state,
                payload=cast(dict[str, JsonValue], invalid_payload),
                active_attached_ids=active_ids,
                final_active_attached_ids=set(),
                alive_model_ids=alive_ids,
            )

    expected_split = (split_identity[0], split_identity[1], split_payload)
    transfer_invalid_cases: tuple[
        tuple[
            dict[str, Any],
            dict[str, BattleShockedUnitState],
            Any,
            str,
        ],
        ...,
    ] = (
        (
            {**transfer_payload, "unexpected": True},
            {attached_id: source_state},
            expected_split,
            "payload drifted",
        ),
        (
            {**transfer_payload, "player_id": "player-b"},
            {attached_id: source_state},
            expected_split,
            "identity drifted",
        ),
        (
            {**transfer_payload, "successor_battle_shocked_unit_states": None},
            {attached_id: source_state},
            expected_split,
            "state is invalid",
        ),
        (
            transfer_payload,
            {},
            expected_split,
            "source authority drifted",
        ),
        (
            {**transfer_payload, "successor_battle_shocked_unit_states": []},
            {attached_id: source_state},
            expected_split,
            "successor authority drifted",
        ),
    )
    for invalid_payload, replayed, invalid_expected, message in transfer_invalid_cases:
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_state_history._apply_split_transfer_event(
                state=authority_state,
                payload=invalid_payload,
                replayed_states=replayed,
                owner_by_unit_id=owner_by_id,
                model_ids_by_unit_id=model_ids_by_id,
                expected_split=invalid_expected,
            )

    command_state = _battle_state(game_id="phase11c:clear-authority")
    command_unit_id = "army-alpha:intercessor-unit-1"
    command_candidate = replace(
        command_candidates.command_battle_shock_candidate_inventory(
            command_state,
            "player-a",
            (),
        )[0],
        is_battle_shocked=True,
        eligibility_reasons=(
            command_candidates.CommandBattleShockEligibilityReason.CURRENTLY_BATTLE_SHOCKED,
        ),
    )
    command_request = BattleShockTestRequest.for_unit(
        request_id="phase11c:clear-authority:request",
        game_id=command_state.game_id,
        battle_round=command_state.battle_round,
        player_id="player-a",
        unit_instance_id=command_unit_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        leadership_target=6,
        below_half_strength_context=command_candidate.below_half_strength_context,
    )
    command_result = BattleShockResult.from_roll_state(
        result_id="phase11c:clear-authority:request:result",
        request=command_request,
        roll_state=DiceRollManager(command_state.game_id).roll_fixed(command_request.spec, [6, 6]),
    )
    clear_snapshot = EventRecord(
        "phase11c:clear-authority:snapshot",
        "battle_shock_step_snapshot_created",
        {
            "game_id": command_state.game_id,
            "battle_round": command_state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.COMMAND.value,
            "battle_shock_phase_start_unit_ids": [command_unit_id],
            "battle_shock_candidate_inventory": [
                validate_json_value(command_candidate.to_payload())
            ],
        },
    )
    assert battle_shock_state_history._has_command_required_clear_authority(
        event_records=(EventRecord("ignored", "ignored", {}), clear_snapshot),
        resolved_index=2,
        result=command_result,
    )
    with pytest.raises(GameLifecycleError, match="snapshot payload is invalid"):
        battle_shock_state_history._has_command_required_clear_authority(
            event_records=(replace(clear_snapshot, payload=None),),
            resolved_index=1,
            result=command_result,
        )
    with pytest.raises(GameLifecycleError, match="clear authority is invalid"):
        battle_shock_state_history._has_command_required_clear_authority(
            event_records=(
                replace(
                    clear_snapshot,
                    payload={
                        **cast(dict[str, Any], clear_snapshot.payload),
                        "battle_shock_candidate_inventory": None,
                    },
                ),
            ),
            resolved_index=1,
            result=command_result,
        )


@pytest.mark.parametrize(
    "tamper_kind",
    ["add", "delete", "source", "models", "round", "mutation_token"],
)
def test_restore_rejects_battle_shock_state_inventory_tamper(tamper_kind: str) -> None:
    decisions = DecisionController()
    state = _battle_state(decisions=decisions, game_id="phase11c-history-fail-2")
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
    assert battle_shock_rerolls._payload_object(
        {"payload": "ok"},
        context="payload",
    ) == {"payload": "ok"}
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        battle_shock_rerolls._payload_object(
            1,
            context="payload",
        )

    assert (
        battle_shock_rerolls._payload_int(
            cast(Any, {"round": 1}),
            key="round",
        )
        == 1
    )
    with pytest.raises(GameLifecycleError, match="missing required key: round"):
        battle_shock_rerolls._payload_int(
            cast(Any, {}),
            key="round",
        )
    with pytest.raises(GameLifecycleError, match="must be an integer: round"):
        battle_shock_rerolls._payload_int(
            cast(Any, {"round": "1"}),
            key="round",
        )

    assert (
        battle_shock_rerolls._payload_string(
            cast(Any, {"player_id": " player-a "}),
            key="player_id",
        )
        == "player-a"
    )
    with pytest.raises(GameLifecycleError, match="missing required key: player_id"):
        battle_shock_rerolls._payload_string(
            cast(Any, {}),
            key="player_id",
        )
    with pytest.raises(GameLifecycleError, match="must be a string: player_id"):
        battle_shock_rerolls._payload_string(
            cast(Any, {"player_id": 1}),
            key="player_id",
        )
    with pytest.raises(GameLifecycleError, match="cannot be empty: player_id"):
        battle_shock_rerolls._payload_string(
            cast(Any, {"player_id": " "}),
            key="player_id",
        )

    assert battle_shock_rerolls._payload_string_tuple(
        cast(Any, {"unit_ids": [" unit-a ", "unit-b"]}),
        key="unit_ids",
    ) == ("unit-a", "unit-b")
    with pytest.raises(GameLifecycleError, match="missing required key: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(
            cast(Any, {}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="must be a list: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(
            cast(Any, {"unit_ids": "unit-a"}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="list must contain strings: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(
            cast(Any, {"unit_ids": [1]}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="list item is empty: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(
            cast(Any, {"unit_ids": [" "]}),
            key="unit_ids",
        )
    with pytest.raises(GameLifecycleError, match="contains duplicates: unit_ids"):
        battle_shock_rerolls._payload_string_tuple(
            cast(Any, {"unit_ids": ["unit-a", "unit-a"]}),
            key="unit_ids",
        )

    state = _battle_state()
    assert battle_shock_rerolls._active_player_id(state) == "player-a"
    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        battle_shock_rerolls._active_player_id(state)

    state.active_player_id = "player-a"
    state.command_step_state = CommandStepState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    assert battle_shock_rerolls._command_step_state(state) is state.command_step_state
    state.command_step_state = None
    with pytest.raises(GameLifecycleError, match="requires command step state"):
        battle_shock_rerolls._command_step_state(state)


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


def test_command_battle_shock_pending_reroll_context_drift_is_rejected() -> None:
    decisions = DecisionController()
    state = _battle_state(
        game_id="phase11c-command-reroll-context-drift",
        decisions=decisions,
    )
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)

    def reroll_permission(
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        return RerollPermission(
            source_id="phase11c:command-reroll-context-drift",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    hooks = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase11c:command-reroll-context-drift",
                source_id="phase11c:command-reroll-context-drift",
                reroll_permission_handler=reroll_permission,
            ),
        )
    )
    pending = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=hooks,
    ).begin_phase(state=state, decisions=decisions)
    request = _decision_request(pending)
    assert request.decision_type == DICE_REROLL_DECISION_TYPE
    assert (
        battle_shock_rerolls.validate_command_battle_shock_reroll_context(
            state=state,
            decisions=decisions,
            request=request,
            battle_shock_hooks=hooks,
            pending=True,
        ).unit_instance_id
        == unit_id
    )
    payload = cast(dict[str, Any], request.payload)
    context = cast(dict[str, Any], payload["battle_shock_context"])

    def request_with_context(**changes: Any) -> DecisionRequest:
        return replace(
            request,
            payload={
                **payload,
                "battle_shock_context": {**context, **changes},
            },
        )

    request_invalid_cases = (
        (
            replace(request, decision_type="wrong"),
            hooks,
            True,
            "decision type drift",
        ),
        (
            request_with_context(source_kind="wrong"),
            hooks,
            True,
            "source kind drift",
        ),
        (request_with_context(game_id="wrong"), hooks, True, "game_id drift"),
        (request_with_context(battle_round=2), hooks, True, "battle_round drift"),
        (
            request_with_context(phase=BattlePhase.MOVEMENT.value),
            hooks,
            True,
            "phase payload drift",
        ),
        (
            request_with_context(active_player_id="player-b"),
            hooks,
            True,
            "active_player_id drift",
        ),
        (
            request_with_context(base_payload={}),
            hooks,
            True,
            "base payload drift",
        ),
        (
            request_with_context(resolved_event_types=["wrong"]),
            hooks,
            True,
            "resolved event types drift",
        ),
        (
            request_with_context(phase_start_battle_shocked_unit_ids=[unit_id]),
            hooks,
            True,
            "phase-start unit IDs drift",
        ),
        (
            request_with_context(passed_state_policy="preserve"),
            hooks,
            True,
            "passed-state policy drift",
        ),
        (
            replace(request, actor_id="player-b"),
            hooks,
            True,
            "request actor drift",
        ),
        (
            request,
            BattleShockHookRegistry.empty(),
            True,
            "permission is no longer valid",
        ),
        (request, hooks, cast(bool, 1), "pending flag must be a bool"),
        (
            request,
            cast(BattleShockHookRegistry, object()),
            True,
            "requires hook registry",
        ),
    )
    for invalid_request, invalid_hooks, pending_flag, message in request_invalid_cases:
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_rerolls.validate_command_battle_shock_reroll_context(
                state=state,
                decisions=decisions,
                request=invalid_request,
                battle_shock_hooks=invalid_hooks,
                pending=pending_flag,
            )

    original_command_state = _command_step_state(state)
    for field, value, message in (
        ("current_step", CommandPhaseStep.COMMAND, "requires the Battle-shock step"),
        ("active_player_id", "player-b", "active player drift"),
        ("battle_round", 2, "command state round drift"),
        ("battle_shock_step_resolved", True, "step is already resolved"),
    ):
        forged = replace(original_command_state)
        object.__setattr__(forged, field, value)
        state.command_step_state = forged
        with pytest.raises(GameLifecycleError, match=message):
            battle_shock_rerolls.validate_command_battle_shock_reroll_context(
                state=state,
                decisions=decisions,
                request=request,
                battle_shock_hooks=hooks,
                pending=True,
            )
    state.command_step_state = original_command_state

    in_flight = original_command_state.battle_shock_in_flight_test_request
    assert in_flight is not None
    drifted_test_request = replace(in_flight, request_id=f"{in_flight.request_id}:drift")
    with pytest.raises(GameLifecycleError, match="not the in-flight test"):
        battle_shock_rerolls.validate_command_battle_shock_reroll_context(
            state=state,
            decisions=decisions,
            request=request_with_context(
                battle_shock_test_request=drifted_test_request.to_payload(),
            ),
            battle_shock_hooks=hooks,
            pending=True,
        )
    different_spec = DiceRollSpec(
        expression=DiceExpression(quantity=3, sides=6),
        reason=in_flight.spec.reason,
        roll_type=in_flight.spec.roll_type,
        actor_id=in_flight.spec.actor_id,
    )
    different_roll = DiceRollManager(state.game_id).roll_fixed(different_spec, [1, 1, 1])
    with pytest.raises(GameLifecycleError, match="initial roll state drift"):
        battle_shock_rerolls.validate_command_battle_shock_reroll_context(
            state=state,
            decisions=decisions,
            request=request_with_context(battle_shock_roll_state=different_roll.to_payload()),
            battle_shock_hooks=hooks,
            pending=True,
        )
    with pytest.raises(GameLifecycleError, match="request authority drift"):
        battle_shock_rerolls.validate_command_battle_shock_reroll_context(
            state=state,
            decisions=decisions,
            request=replace(
                request,
                options=(replace(request.options[0], label="Drifted"), *request.options[1:]),
            ),
            battle_shock_hooks=hooks,
            pending=True,
        )

    result = DecisionResult.for_request(
        result_id="phase11c:command-reroll-context-drift:result",
        request=request,
        selected_option_id="decline",
    )
    invalid_status = battle_shock_rerolls.invalid_command_battle_shock_reroll_status(
        state=state,
        decisions=decisions,
        request=request_with_context(source_kind="wrong"),
        result=result,
        battle_shock_hooks=hooks,
    )
    assert invalid_status is not None
    assert invalid_status.payload == {"invalid_reason": "command_battle_shock_reroll_context_drift"}

    armies = tuple(state.army_definitions)
    config = _config(game_id=state.game_id)
    runtime_bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=armies,
            catalog=config.army_catalog,
        ),
        armies=armies,
        catalog=config.army_catalog,
        contributions=(
            RuntimeContentContribution(
                contribution_id="phase11c:command-reroll-context-drift:runtime",
                battle_shock_hook_bindings=hooks.bindings,
            ),
        ),
    )
    authority = battle_shock_pending_authority.validate_live_pending_battle_shock_reroll_authority(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        pending_request=request,
        runtime_content_bundle=runtime_bundle,
    )
    assert authority.test_request == in_flight
    lifecycle_payload = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _config=config,
        _runtime_content_bundle=runtime_bundle,
    ).to_payload()
    GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle_payload))),
        runtime_content_bundle=runtime_bundle,
    )
    for tamper_kind in (
        "leadership",
        "dice_expression",
        "strength_context",
        "in_flight_without_request_event",
        "request_event_without_roll_or_pending_reroll",
    ):
        forged_lifecycle = cast(dict[str, Any], deepcopy(lifecycle_payload))
        forged_state = cast(dict[str, Any], forged_lifecycle["state"])
        forged_command = cast(dict[str, Any], forged_state["command_step_state"])
        forged_in_flight = cast(
            dict[str, Any],
            forged_command["battle_shock_in_flight_test_request"],
        )
        if tamper_kind == "leadership":
            forged_in_flight["leadership_target"] = int(forged_in_flight["leadership_target"]) + 1
        elif tamper_kind == "dice_expression":
            expression = cast(
                dict[str, Any],
                cast(dict[str, Any], forged_in_flight["spec"])["expression"],
            )
            expression["quantity"] = 3
        elif tamper_kind == "strength_context":
            strength = cast(dict[str, Any], forged_in_flight["below_half_strength_context"])
            strength["starting_model_count"] = int(strength["starting_model_count"]) + 1
        else:
            forged_decisions = cast(dict[str, Any], forged_lifecycle["decisions"])
            forged_queue = cast(dict[str, Any], forged_decisions["queue"])
            forged_queue["pending_requests"] = []
            events = cast(list[dict[str, Any]], forged_decisions["event_log"])
            filtered = [
                event
                for event in events
                if not (
                    event["event_type"] == "dice_rolled"
                    or (
                        event["event_type"] == "decision_requested"
                        and isinstance(event["payload"], dict)
                        and cast(dict[str, Any], event["payload"]).get("request_id")
                        == request.request_id
                    )
                    or (
                        tamper_kind == "in_flight_without_request_event"
                        and event["event_type"] == "battle_shock_test_requested"
                        and isinstance(event["payload"], dict)
                        and cast(dict[str, Any], event["payload"]).get("battle_shock_test_request")
                        == in_flight.to_payload()
                    )
                )
            ]
            for index, event in enumerate(filtered, start=1):
                event["event_id"] = f"event-{index:06d}"
            forged_decisions["event_log"] = filtered
        with pytest.raises(GameLifecycleError, match="Battle-shock"):
            GameLifecycle.from_payload(
                cast(GameLifecyclePayload, forged_lifecycle),
                runtime_content_bundle=runtime_bundle,
            )

    request_event_index = next(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request") == in_flight.to_payload()
    )
    request_event = decisions.event_log.records[request_event_index]
    duplicated_request_events = list(decisions.event_log.records)
    duplicated_request_events.insert(request_event_index + 1, request_event)
    with pytest.raises(GameLifecycleError, match="request occurrence is ambiguous"):
        battle_shock_pending_authority.validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=tuple(duplicated_request_events),
            decision_records=decisions.records,
            pending_request=request,
            runtime_content_bundle=runtime_bundle,
        )
    drifted_request_events = list(decisions.event_log.records)
    drifted_request_events[request_event_index] = replace(
        request_event,
        payload={**cast(dict[str, Any], request_event.payload), "unexpected": True},
    )
    with pytest.raises(GameLifecycleError, match="request event drifted"):
        battle_shock_pending_authority.validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=tuple(drifted_request_events),
            decision_records=decisions.records,
            pending_request=request,
            runtime_content_bundle=runtime_bundle,
        )
    missing_dice_events = tuple(
        event for event in decisions.event_log.records if event.event_type != "dice_rolled"
    )
    with pytest.raises(GameLifecycleError, match="decision occurrence drifted"):
        battle_shock_pending_authority.validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=missing_dice_events,
            decision_records=decisions.records,
            pending_request=request,
            runtime_content_bundle=runtime_bundle,
        )

    original_active_player_id = state.active_player_id
    state.active_player_id = "player-b"
    with pytest.raises(GameLifecycleError, match="live occurrence drifted"):
        battle_shock_pending_authority.validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_request=request,
            runtime_content_bundle=runtime_bundle,
        )
    state.active_player_id = original_active_player_id

    empty_runtime_bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=armies,
            catalog=config.army_catalog,
        ),
        armies=armies,
        catalog=config.army_catalog,
        contributions=(),
    )
    with pytest.raises(GameLifecycleError, match="reroll permission drifted"):
        battle_shock_pending_authority.validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_request=request,
            runtime_content_bundle=empty_runtime_bundle,
        )

    command_history._validate_pending_reroll_restore_authority(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        pending_decision_requests=(request,),
    )
    with pytest.raises(GameLifecycleError, match="requires pending decision requests"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=cast(Any, [request]),
        )

    state.command_step_state = None
    command_history._validate_pending_reroll_restore_authority(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        pending_decision_requests=(request,),
    )
    state.command_step_state = original_command_state

    resolved_command_state = replace(original_command_state)
    object.__setattr__(resolved_command_state, "battle_shock_step_resolved", True)
    state.command_step_state = resolved_command_state
    with pytest.raises(GameLifecycleError, match="resolved state has pending reroll"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=(request,),
        )
    state.command_step_state = original_command_state

    with pytest.raises(GameLifecycleError, match="pending reroll is ambiguous"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=(
                request,
                replace(request, request_id=f"{request.request_id}:duplicate"),
            ),
        )

    no_in_flight_state = replace(original_command_state)
    object.__setattr__(no_in_flight_state, "battle_shock_in_flight_test_request", None)
    state.command_step_state = no_in_flight_state
    with pytest.raises(GameLifecycleError, match="has no in-flight test"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=(request,),
        )
    state.command_step_state = original_command_state

    with pytest.raises(GameLifecycleError, match="in-flight test requires pending reroll"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=(),
        )
    without_test_request_event = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type != "battle_shock_test_requested"
    )
    with pytest.raises(GameLifecycleError, match="pending reroll state drift"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=without_test_request_event,
            decision_records=decisions.records,
            pending_decision_requests=(request,),
        )
    with pytest.raises(GameLifecycleError, match="pending reroll snapshot drift"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=(
                request_with_context(
                    battle_shock_test_request=drifted_test_request.to_payload(),
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="pending reroll request drift"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=(
                replace(
                    request,
                    options=(
                        replace(request.options[0], label="Drifted"),
                        *request.options[1:],
                    ),
                ),
            ),
        )
    recorded_pending = DecisionRecord(
        record_id="phase11c:command-reroll-context-drift:record",
        request=request,
        result=DecisionResult.for_request(
            result_id="phase11c:command-reroll-context-drift:recorded-result",
            request=request,
            selected_option_id="decline",
        ),
    )
    with pytest.raises(GameLifecycleError, match="pending reroll history drift"):
        command_history._validate_pending_reroll_restore_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=(*decisions.records, recorded_pending),
            pending_decision_requests=(request,),
        )

    resolution_state = GameState.from_payload(_game_state_payload_copy(state))
    resolution_decisions = DecisionController.from_payload(decisions.to_payload())
    resolution_request = resolution_decisions.queue.pending_requests[0]
    resolution_result = DecisionResult.for_request(
        result_id="phase11c:command-reroll-context-drift:declined-result",
        request=resolution_request,
        selected_option_id="decline",
    )
    resolution_decisions.submit_result(resolution_result)
    resolution_handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=hooks,
    )
    resolution_handler.apply_decision(
        state=resolution_state,
        result=resolution_result,
        decisions=resolution_decisions,
    )
    resolution_status = resolution_handler.begin_phase(
        state=resolution_state,
        decisions=resolution_decisions,
    )
    assert resolution_status.status_kind is LifecycleStatusKind.ADVANCED
    resolved_results = command_history.ordered_completed_command_battle_shock_results(
        state=resolution_state,
        event_records=resolution_decisions.event_log.records,
        decision_records=resolution_decisions.records,
    )
    assert len(resolved_results) == 1

    resolved_events = resolution_decisions.event_log.records
    resolved_index = next(
        index
        for index, event in enumerate(resolved_events)
        if event.event_type == "battle_shock_test_resolved"
    )
    original_roll_index = next(
        index
        for index, event in enumerate(resolved_events)
        if event.event_type == "dice_rolled"
        and event.payload == resolved_results[0].roll_state.original_result.to_payload()
    )
    request_index = next(
        index
        for index, event in enumerate(resolved_events)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request")
        == resolved_results[0].request.to_payload()
    )
    reroll_record = resolution_decisions.records[0]

    def validate_reroll_history(
        *,
        event_records: tuple[EventRecord, ...] = resolved_events,
        decision_records: tuple[DecisionRecord, ...] = resolution_decisions.records,
        resolved_event_index: int = resolved_index,
    ) -> DiceRollState:
        return command_history._validated_reroll_decision_history(
            state=resolution_state,
            event_records=event_records,
            decision_records=decision_records,
            segment_start_index=request_index + 1,
            resolved_index=resolved_event_index,
            original_roll_index=original_roll_index,
            result=resolved_results[0],
            battle_round=resolution_state.battle_round,
            active_player_id="player-a",
            phase_start_battle_shocked_unit_ids=(),
        )

    with pytest.raises(GameLifecycleError, match="at most one reroll decision"):
        validate_reroll_history(
            decision_records=(reroll_record, reroll_record),
        )
    with pytest.raises(GameLifecycleError, match="decision authority is missing"):
        validate_reroll_history(decision_records=())
    context_drift_record = replace(reroll_record)
    object.__setattr__(
        context_drift_record,
        "request",
        replace(reroll_record.request, actor_id="player-b"),
    )
    with pytest.raises(GameLifecycleError, match="decision context drift"):
        validate_reroll_history(decision_records=(context_drift_record,))
    with pytest.raises(GameLifecycleError, match="request structure drift"):
        validate_reroll_history(
            decision_records=(
                replace(
                    reroll_record,
                    request=replace(
                        reroll_record.request,
                        options=(
                            replace(reroll_record.request.options[0], label="Drifted"),
                            *reroll_record.request.options[1:],
                        ),
                    ),
                ),
            )
        )
    without_recorded_event = tuple(
        event for event in resolved_events if event.event_type != "decision_recorded"
    )
    with pytest.raises(GameLifecycleError, match="decision closure drift"):
        validate_reroll_history(
            event_records=without_recorded_event,
            resolved_event_index=resolved_index - 1,
        )

    extra_decision_event_records = list(resolved_events)
    extra_decision_event_records.insert(
        resolved_index,
        EventRecord(
            event_id="phase11c:command-reroll-context-drift:extra-decision",
            event_type="decision_requested",
            payload={},
        ),
    )
    with pytest.raises(GameLifecycleError, match="decision events are ambiguous"):
        validate_reroll_history(
            event_records=tuple(extra_decision_event_records),
            resolved_event_index=resolved_index + 1,
        )

    def record_with_result_payload(value: Any) -> DecisionRecord:
        corrupted = replace(reroll_record)
        object.__setattr__(
            corrupted,
            "result",
            replace(reroll_record.result, payload=value),
        )
        return corrupted

    selected_record = record_with_result_payload({"selected_indices": [0]})
    selected_events = tuple(
        replace(event, payload=validate_json_value(selected_record.to_payload()))
        if event.event_type == "decision_recorded"
        else event
        for event in resolved_events
    )
    with pytest.raises(GameLifecycleError, match="declined reroll selected dice"):
        validate_reroll_history(
            event_records=selected_events,
            decision_records=(selected_record,),
        )
    without_decline_event = tuple(
        event for event in resolved_events if event.event_type != "dice_reroll_declined"
    )
    with pytest.raises(GameLifecycleError, match="reroll decline authority drift"):
        validate_reroll_history(event_records=without_decline_event)

    assert not command_history._record_targets_battle_shock_request(
        record=replace(
            reroll_record,
            request=replace(reroll_record.request, payload=None),
        ),
        result=resolved_results[0],
    )
    request_payload = cast(dict[str, Any], reroll_record.request.payload)
    assert not command_history._record_targets_battle_shock_request(
        record=replace(
            reroll_record,
            request=replace(
                reroll_record.request,
                payload={**request_payload, "battle_shock_context": None},
            ),
        ),
        result=resolved_results[0],
    )
    with pytest.raises(GameLifecycleError, match="result payload drift"):
        command_history._selected_reroll_indices(record_with_result_payload(None))
    with pytest.raises(GameLifecycleError, match="selected indices drift"):
        command_history._selected_reroll_indices(
            record_with_result_payload({"selected_indices": [True]})
        )

    wrong_owner_request = replace(in_flight)
    object.__setattr__(wrong_owner_request, "player_id", "player-b")
    wrong_owner_authority = replace(authority)
    object.__setattr__(wrong_owner_authority, "test_request", wrong_owner_request)
    with pytest.raises(GameLifecycleError, match="target owner drifted"):
        battle_shock_pending_authority._expected_live_test_request(
            state=state,
            authority=wrong_owner_authority,
            runtime_content_bundle=runtime_bundle,
        )

    unplaced_state = GameState.from_payload(_game_state_payload_copy(state))
    assert unplaced_state.battlefield_state is not None
    unplaced_state.battlefield_state = unplaced_state.battlefield_state.without_unit_placement(
        unit_id
    )
    with pytest.raises(GameLifecycleError, match="no longer placed"):
        battle_shock_pending_authority._expected_live_test_request(
            state=unplaced_state,
            authority=authority,
            runtime_content_bundle=runtime_bundle,
        )
    with pytest.raises(GameLifecycleError, match="lacks ability authority"):
        battle_shock_pending_authority._expected_live_test_request(
            state=state,
            authority=authority,
            runtime_content_bundle=replace(
                runtime_bundle,
                ability_indexes_by_player_id={
                    "player-b": runtime_bundle.ability_indexes_by_player_id["player-b"]
                },
            ),
        )

    invalid_live_status = (
        battle_shock_pending_authority.invalid_live_pending_battle_shock_reroll_status(
            state=state,
            decisions=decisions,
            pending_request=request,
            result=replace(result, selected_option_id="missing-option"),
            runtime_content_bundle=runtime_bundle,
        )
    )
    assert invalid_live_status is not None
    assert invalid_live_status.payload == {"invalid_reason": "battle_shock_reroll_authority_drift"}

    _remove_first_models(state, unit_instance_id=unit_id, count=1)
    with pytest.raises(GameLifecycleError, match="request semantics drifted"):
        battle_shock_pending_authority.validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_request=request,
            runtime_content_bundle=runtime_bundle,
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

    state = _battle_state(game_id="phase11c-command-step-validation")
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    inventory = command_candidates.command_battle_shock_candidate_inventory(
        state,
        "player-a",
        (),
    )
    candidate = next(item for item in inventory if item.unit_instance_id == unit_id)
    reason = candidate.test_reason
    assert reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
    request = BattleShockTestRequest.for_unit(
        request_id=command_candidates.command_battle_shock_request_id(
            battle_round=state.battle_round,
            active_player_id="player-a",
            unit_instance_id=unit_id,
            reason=reason,
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_id,
        reason=reason,
        leadership_target=6,
        below_half_strength_context=candidate.below_half_strength_context,
    )

    with pytest.raises(GameLifecycleError, match="phase-start units must be deterministic"):
        CommandStepState(
            battle_round=1,
            active_player_id="player-a",
            battle_shock_phase_start_unit_ids=("unit-b", "unit-a"),
        )
    with pytest.raises(GameLifecycleError, match="before synchronous hooks resolve"):
        CommandStepState(
            battle_round=1,
            active_player_id="player-a",
            command_phase_start_boundary_resolved=True,
        )
    with pytest.raises(GameLifecycleError, match="immutable eligibility snapshot"):
        command_state.enter_battle_shock_step()

    battle_step = command_state.enter_battle_shock_step(
        phase_start_battle_shocked_unit_ids=(),
        candidate_inventory=inventory,
    )
    assert battle_step.enter_battle_shock_step() == battle_step
    with pytest.raises(GameLifecycleError, match="phase-start unit IDs drifted"):
        battle_step.enter_battle_shock_step(
            phase_start_battle_shocked_unit_ids=("other-unit",),
        )
    with pytest.raises(GameLifecycleError, match="candidate inventory drifted"):
        battle_step.enter_battle_shock_step(candidate_inventory=())
    with pytest.raises(GameLifecycleError, match="candidate order requires Battle-shock step"):
        command_state.with_battle_shock_candidate_order((unit_id,))
    ordered_battle_step = battle_step.with_battle_shock_candidate_order((unit_id,))
    with pytest.raises(GameLifecycleError, match="candidate order was already resolved"):
        ordered_battle_step.with_battle_shock_candidate_order((unit_id,))
    with pytest.raises(GameLifecycleError, match="in-flight test requires Battle-shock step"):
        command_state.with_in_flight_battle_shock_test_request(request)

    with pytest.raises(GameLifecycleError, match="candidate order resolves"):
        battle_step.with_in_flight_battle_shock_test_request(request)
    in_flight = ordered_battle_step.with_in_flight_battle_shock_test_request(request)
    with pytest.raises(GameLifecycleError, match="already in flight"):
        in_flight.with_in_flight_battle_shock_test_request(request)
    with pytest.raises(GameLifecycleError, match="completion requires Battle-shock step"):
        command_state.with_completed_battle_shock_test_request(request.request_id)
    with pytest.raises(GameLifecycleError, match="not the in-flight request"):
        battle_step.with_completed_battle_shock_test_request(request.request_id)
    with pytest.raises(GameLifecycleError, match="not the in-flight request"):
        in_flight.with_completed_battle_shock_test_request("wrong-request")

    completed = in_flight.with_completed_battle_shock_test_request(request.request_id)
    duplicate_completion = replace(completed)
    object.__setattr__(duplicate_completion, "battle_shock_in_flight_test_request", request)
    with pytest.raises(GameLifecycleError, match="already completed"):
        duplicate_completion.with_completed_battle_shock_test_request(request.request_id)
    with pytest.raises(GameLifecycleError, match="resolution requires Battle-shock step"):
        command_state.with_battle_shock_step_resolved()
    resolved = completed.with_battle_shock_step_resolved()
    with pytest.raises(GameLifecycleError, match="step is already resolved"):
        resolved.with_completed_battle_shock_test_request(request.request_id)
    with pytest.raises(GameLifecycleError, match="already resolved"):
        resolved.with_battle_shock_step_resolved()

    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        command_points_module._validate_transaction_tuple(
            "transactions",
            [],
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="must contain CommandPointTransaction"):
        command_points_module._validate_transaction_tuple(
            "transactions",
            (object(),),
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="must be a BattleShockTestRequest"):
        command_points_module._validate_optional_battle_shock_test_request(
            object(),
            battle_round=1,
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        command_points_module._validate_optional_battle_shock_test_request(
            replace(request, battle_round=2),
            battle_round=1,
            active_player_id="player-a",
        )
    wrong_player_request = replace(request)
    object.__setattr__(wrong_player_request, "player_id", "player-b")
    with pytest.raises(GameLifecycleError, match="active player drift"):
        command_points_module._validate_optional_battle_shock_test_request(
            wrong_player_request,
            battle_round=1,
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        command_points_module._validate_identifier_tuple("identifiers", [])
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        command_points_module._validate_identifier_tuple("identifiers", ("unit-a", "unit-a"))
    with pytest.raises(GameLifecycleError, match="must be an integer"):
        command_points_module._validate_positive_int("value", "1")
    with pytest.raises(GameLifecycleError, match="must be at least 1"):
        command_points_module._validate_positive_int("value", 0)
    with pytest.raises(GameLifecycleError, match="must be an integer"):
        command_points_module._validate_non_zero_int("value", "1")
    with pytest.raises(GameLifecycleError, match="must not be zero"):
        command_points_module._validate_non_zero_int("value", 0)
    with pytest.raises(GameLifecycleError, match="must be an integer"):
        command_points_module._validate_non_negative_int("value", "1")
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        command_points_module._validate_non_negative_int("value", -1)
    with pytest.raises(GameLifecycleError, match="must be a bool"):
        command_points_module._validate_bool("value", 1)

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


def test_command_phase_section_eight_private_boundaries_fail_closed() -> None:
    invalid_handler_values: tuple[dict[str, Any], ...] = (
        {"stratagem_index": object()},
        {"stratagem_cost_modifier_registry": object()},
        {"battle_shock_hooks": object()},
        {"command_phase_start_hooks": object()},
        {"runtime_modifier_registry": object()},
        {"ability_indexes_by_player_id": []},
        {"ability_indexes_by_player_id": {"": AbilityCatalogIndex.from_records(())}},
        {"ability_indexes_by_player_id": {"player-a": object()}},
    )
    for overrides in invalid_handler_values:
        with pytest.raises(GameLifecycleError):
            CommandPhaseHandler(**cast(Any, overrides))

    assert (
        command_phase_module._validate_player_id(
            "player_id",
            "player-a",
        )
        == "player-a"
    )
    assert command_phase_module._validate_ability_index_mapping(
        {"player-a": AbilityCatalogIndex.from_records(())}
    )["player-a"] == AbilityCatalogIndex.from_records(())
    assert command_phase_module._ability_index_for_player(
        {},
        player_id="player-a",
    ) == AbilityCatalogIndex.from_records(())
    assert command_phase_module._decision_payload_object({"value": "ok"}) == {"value": "ok"}
    assert (
        command_phase_module._payload_int(
            {"value": 1},
            key="value",
        )
        == 1
    )
    assert not command_phase_module._payload_optional_bool(
        {},
        key="value",
    )
    assert (
        command_phase_module._payload_string(
            {"value": " player-a "},
            key="value",
        )
        == "player-a"
    )

    invalid_helper_calls = (
        lambda: command_phase_module._validate_player_id("", "player-a"),
        lambda: command_phase_module._validate_player_id("player_id", ""),
        lambda: command_phase_module._validate_ability_index_mapping([]),
        lambda: command_phase_module._validate_ability_index_mapping({"player-a": object()}),
        lambda: command_phase_module._ability_index_for_player([], player_id="player-a"),
        lambda: command_phase_module._ability_index_for_player(
            {"player-a": object()}, player_id="player-a"
        ),
        lambda: command_phase_module._decision_payload_object(None),
        lambda: command_phase_module._payload_int({}, key="value"),
        lambda: command_phase_module._payload_int({"value": True}, key="value"),
        lambda: command_phase_module._payload_optional_bool({"value": 1}, key="value"),
        lambda: command_phase_module._payload_string({}, key="value"),
        lambda: command_phase_module._payload_string({"value": 1}, key="value"),
        lambda: command_phase_module._payload_string({"value": ""}, key="value"),
    )
    for invalid_call in invalid_helper_calls:
        with pytest.raises(GameLifecycleError):
            invalid_call()

    inactive_state = _battle_state(game_id="phase11c-command-private-inactive")
    inactive_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="active player"):
        command_phase_module._active_player_id(inactive_state)

    missing_state = _battle_state(game_id="phase11c-command-private-missing-step")
    missing_state.command_step_state = None
    with pytest.raises(GameLifecycleError, match="requires CommandStepState"):
        command_phase_module._command_step_state(missing_state)

    missing_battlefield = _battle_state(game_id="phase11c-command-private-battlefield")
    missing_battlefield.battlefield_state = None
    missing_battlefield.command_step_state = CommandStepState.start(
        battle_round=missing_battlefield.battle_round,
        active_player_id="player-a",
    )
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        command_phase_module._resolve_battle_shock_step(
            state=missing_battlefield,
            decisions=DecisionController(),
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_index=AbilityCatalogIndex.from_records(()),
        )
    with pytest.raises(GameLifecycleError, match="support requires battlefield state"):
        command_phase_module._unsupported_command_battle_shock_candidate_status(
            state=missing_battlefield,
        )

    missing_army = _battle_state(game_id="phase11c-command-private-army")
    missing_army.army_definitions = []
    with pytest.raises(GameLifecycleError, match="active player's army"):
        command_phase_module._resolve_battle_shock_step(
            state=missing_army,
            decisions=DecisionController(),
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_index=AbilityCatalogIndex.from_records(()),
        )

    auto_pass_state = _battle_state(game_id="phase11c-command-private-auto-pass")
    unit_id = "army-alpha:intercessor-unit-1"
    for index, payload in enumerate(
        (
            None,
            {"effect_kind": "unrelated"},
            {"effect_kind": "battle_shock_auto_pass"},
            {"effect_kind": "battle_shock_auto_pass"},
        )
    ):
        auto_pass_state.record_persisting_effect(
            PersistingEffect(
                effect_id=f"phase11c:command-private:auto-pass:{index}",
                source_rule_id=f"phase11c:command-private:auto-pass-source:{index}",
                owner_player_id="player-a",
                target_unit_instance_ids=(unit_id,),
                started_battle_round=1,
                started_phase=BattlePhase.COMMAND,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=cast(Any, payload),
            )
        )
    with pytest.raises(GameLifecycleError, match="Multiple Battle-shock auto-pass"):
        command_phase_module._battle_shock_auto_pass_effect(
            state=auto_pass_state,
            unit_instance_id=unit_id,
        )

    one_candidate_state = _battle_state(game_id="phase11c-command-private-trivial-order")
    _remove_first_models(one_candidate_state, unit_instance_id=unit_id, count=3)
    inventory = command_candidates.command_battle_shock_candidate_inventory(
        one_candidate_state,
        "player-a",
        (),
    )
    battle_step = (
        CommandStepState.start(battle_round=1, active_player_id="player-a")
        .with_command_phase_start_synchronous_hooks_resolved()
        .with_command_phase_start_boundary_resolved()
        .with_command_points_granted()
        .enter_battle_shock_step(
            phase_start_battle_shocked_unit_ids=(),
            candidate_inventory=inventory,
        )
    )
    one_candidate_state.command_step_state = battle_step
    assert (
        command_phase_module._resolve_command_battle_shock_candidate_order(
            state=one_candidate_state,
            decisions=DecisionController(),
        )
        is None
    )
    assert _command_step_state(one_candidate_state).battle_shock_candidate_order_unit_ids == (
        unit_id,
    )

    two_unit_selections = (
        _default_unit_selection("intercessor-unit-1"),
        _default_unit_selection("intercessor-unit-2"),
    )
    sequencing_state = _battle_state(
        game_id="phase11c-command-private-sequencing",
        player_a_units=two_unit_selections,
    )
    for candidate_unit_id in (
        "army-alpha:intercessor-unit-1",
        "army-alpha:intercessor-unit-2",
    ):
        _remove_first_models(sequencing_state, unit_instance_id=candidate_unit_id, count=3)
    sequencing_decisions = DecisionController()
    waiting = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(())
    ).begin_phase(state=sequencing_state, decisions=sequencing_decisions)
    sequencing_request = _decision_request(waiting)
    assert sequencing_request.decision_type == SEQUENCING_DECISION_TYPE
    candidate_order_status = command_phase_module._resolve_command_battle_shock_candidate_order(
        state=sequencing_state,
        decisions=sequencing_decisions,
    )
    assert candidate_order_status is not None
    assert candidate_order_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION

    ambiguous = DecisionController.from_payload(sequencing_decisions.to_payload())
    ambiguous.request_decision(
        replace(sequencing_request, request_id="phase11c:sequencing:second-pending")
    )
    with pytest.raises(GameLifecycleError, match="pending queue is ambiguous"):
        command_phase_module._resolve_command_battle_shock_candidate_order(
            state=sequencing_state,
            decisions=ambiguous,
        )

    drifted_pending = DecisionController.from_payload(sequencing_decisions.to_payload())
    drifted_pending.queue._pending_requests[0] = replace(
        sequencing_request,
        payload={"sequencing_conflict": {}},
    )
    with pytest.raises(GameLifecycleError, match="pending request drifted"):
        command_phase_module._resolve_command_battle_shock_candidate_order(
            state=sequencing_state,
            decisions=drifted_pending,
        )

    malformed_event = DecisionController.from_payload(sequencing_decisions.to_payload())
    malformed_event.event_log.append("sequencing_next_participant_selected", None)
    with pytest.raises(GameLifecycleError, match="payload is malformed"):
        command_phase_module._resolve_command_battle_shock_candidate_order(
            state=sequencing_state,
            decisions=malformed_event,
        )

    sequencing_result = DecisionResult.for_request(
        result_id="phase11c:sequencing:result",
        request=sequencing_request,
        selected_option_id=sequencing_request.options[0].option_id,
    )
    sequencing_record = sequencing_decisions.submit_result(sequencing_result)
    sequencing = sequencing_module.apply_select_next_sequencing_participant_from_request(
        request=sequencing_record.request,
        result=sequencing_record.result,
    )
    sequencing_decisions.event_log.append(
        "sequencing_next_participant_selected", sequencing.to_payload()
    )
    duplicated = DecisionController.from_payload(sequencing_decisions.to_payload())
    duplicated.event_log.append("sequencing_next_participant_selected", sequencing.to_payload())
    with pytest.raises(GameLifecycleError, match="selection prefix drifted"):
        command_phase_module._resolve_command_battle_shock_candidate_order(
            state=sequencing_state,
            decisions=duplicated,
        )

    missing_record = DecisionController.from_payload(sequencing_decisions.to_payload())
    missing_record._records.clear()
    with pytest.raises(GameLifecycleError, match="lacks one decision record"):
        command_phase_module._resolve_command_battle_shock_candidate_order(
            state=sequencing_state,
            decisions=missing_record,
        )

    sequencing_events = sequencing_decisions.event_log.records
    sequencing_event_index = next(
        index
        for index, event in enumerate(sequencing_events)
        if event.event_type == "sequencing_next_participant_selected"
    )
    snapshot_index = next(
        index
        for index, event in enumerate(sequencing_events)
        if event.event_type == "battle_shock_step_snapshot_created"
    )
    sequencing_command_state = _command_step_state(sequencing_state)
    sequencing_candidates = tuple(
        candidate
        for candidate in sequencing_command_state.battle_shock_candidate_inventory
        if candidate.test_reason is not None
    )
    ordered_unit_ids = (
        sequencing.selected_participant_id.removeprefix("command-battle-shock-test:"),
        next(
            participant_id.removeprefix("command-battle-shock-test:")
            for participant_id in sequencing.remaining_participant_ids
            if participant_id != sequencing.selected_participant_id
        ),
    )
    command_history._validate_historical_candidate_order(
        state=sequencing_state,
        event_records=sequencing_events,
        decision_records=sequencing_decisions.records,
        snapshot_index=snapshot_index,
        completion_index=len(sequencing_events) + 1,
        battle_round=sequencing_state.battle_round,
        active_player_id="player-a",
        candidates=sequencing_candidates,
        ordered_unit_ids=ordered_unit_ids,
    )
    command_history._validate_historical_sequencing_request(
        state=sequencing_state,
        request=sequencing_request,
        battle_round=sequencing_state.battle_round,
        active_player_id="player-a",
        candidates=sequencing_candidates,
    )

    with pytest.raises(GameLifecycleError, match="sequencing payload is malformed"):
        command_history._validate_historical_candidate_order(
            state=sequencing_state,
            event_records=(EventRecord("malformed", "sequencing_next_participant_selected", None),),
            decision_records=(),
            snapshot_index=-1,
            completion_index=1,
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
            ordered_unit_ids=ordered_unit_ids,
        )
    with pytest.raises(GameLifecycleError, match="sequencing order drifted"):
        command_history._validate_historical_candidate_order(
            state=sequencing_state,
            event_records=(),
            decision_records=(),
            snapshot_index=-1,
            completion_index=1,
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
            ordered_unit_ids=ordered_unit_ids,
        )
    with pytest.raises(GameLifecycleError, match="sequencing escaped its step"):
        command_history._validate_historical_candidate_order(
            state=sequencing_state,
            event_records=sequencing_events,
            decision_records=sequencing_decisions.records,
            snapshot_index=sequencing_event_index,
            completion_index=len(sequencing_events) + 1,
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
            ordered_unit_ids=ordered_unit_ids,
        )
    with pytest.raises(GameLifecycleError, match="lacks a decision record"):
        command_history._validate_historical_candidate_order(
            state=sequencing_state,
            event_records=sequencing_events,
            decision_records=(),
            snapshot_index=snapshot_index,
            completion_index=len(sequencing_events) + 1,
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
            ordered_unit_ids=ordered_unit_ids,
        )

    one_candidate = sequencing_candidates[:1]
    with pytest.raises(GameLifecycleError, match="trivial order drifted"):
        command_history._validate_historical_candidate_order(
            state=sequencing_state,
            event_records=(),
            decision_records=(),
            snapshot_index=-1,
            completion_index=1,
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=one_candidate,
            ordered_unit_ids=(),
        )

    with pytest.raises(GameLifecycleError, match="sequencing request drifted"):
        command_history._validate_historical_sequencing_request(
            state=sequencing_state,
            request=replace(sequencing_request, actor_id="player-b"),
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
        )
    context_drift_payload = cast(
        dict[str, Any],
        json.loads(json.dumps(sequencing_request.payload)),
    )
    cast(dict[str, Any], context_drift_payload["sequencing_conflict"])["game_id"] = "other-game"
    with pytest.raises(GameLifecycleError, match="sequencing context drifted"):
        command_history._validate_historical_sequencing_request(
            state=sequencing_state,
            request=replace(sequencing_request, payload=context_drift_payload),
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
        )
    participant_drift_payload = cast(
        dict[str, Any],
        json.loads(json.dumps(sequencing_request.payload)),
    )
    participant_drift_payload["participants"] = []
    with pytest.raises(GameLifecycleError, match="sequencing participants drifted"):
        command_history._validate_historical_sequencing_request(
            state=sequencing_state,
            request=replace(sequencing_request, payload=participant_drift_payload),
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
        )
    with pytest.raises(GameLifecycleError, match="request payload drifted"):
        command_history._validate_historical_sequencing_request(
            state=sequencing_state,
            request=replace(
                sequencing_request,
                options=(replace(sequencing_request.options[0], label="Drifted"),),
            ),
            battle_round=sequencing_state.battle_round,
            active_player_id="player-a",
            candidates=sequencing_candidates,
        )

    command_history._validate_pending_candidate_order_restore_authority(
        state=sequencing_state,
        pending_decision_requests=(sequencing_request,),
    )
    with pytest.raises(GameLifecycleError, match="pending sequencing authority drifted"):
        command_history._validate_pending_candidate_order_restore_authority(
            state=sequencing_state,
            pending_decision_requests=(),
        )
    ordered_command_state = replace(sequencing_command_state)
    object.__setattr__(
        ordered_command_state,
        "battle_shock_candidate_order_unit_ids",
        ordered_unit_ids,
    )
    sequencing_state.command_step_state = ordered_command_state
    with pytest.raises(GameLifecycleError, match="excess sequencing request"):
        command_history._validate_pending_candidate_order_restore_authority(
            state=sequencing_state,
            pending_decision_requests=(sequencing_request,),
        )


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
