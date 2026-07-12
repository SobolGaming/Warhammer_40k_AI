from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import (
    DiceRollResult,
    DiceRollState,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine import attack_sequence_hazardous, battle_shock_resolution
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequenceStep
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockHookRegistry,
    BattleShockRerollPermissionContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
    apply_catalog_selected_target_battle_shock_reroll_decision,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockEffect,
    UnitMoveCompletedBattleShockHookBinding,
    UnitMoveCompletedBattleShockHookRegistry,
    UnitMoveCompletedContext,
    apply_unit_move_completed_battle_shock_reroll_decision,
    resolve_unit_move_completed_battle_shock_hooks,
)
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def test_post_shoot_forced_battle_shock_reroll_pauses_and_resumes() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _compiled_record(
        record_id="record:selected-target:post-shoot-battle-shock-reroll",
        raw_text=(
            "In your Shooting phase, after this model has shot, select one enemy unit that "
            "was hit by one or more of those attacks. That unit must take a Battle-shock test."
        ),
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
    )
    ability_indexes_by_player_id = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army, target_army),
    )
    sequence = _successful_shooting_sequence(
        source_army=source_army,
        source_unit=source_unit,
        target_army=target_army,
        target_unit=target_unit,
    )
    decisions = DecisionController()
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    status = runtime.attack_sequence_completed_bindings()[0].handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=sequence,
            attack_sequence_completed_event_id="event:post-shoot-battle-shock-reroll:completed",
        )
    )
    assert status is not None
    target_request = decisions.queue.peek_next()
    target_result = DecisionResult.for_request(
        result_id="result:selected-target:post-shoot-battle-shock-reroll",
        request=target_request,
        selected_option_id=target_request.options[0].option_id,
    )
    decisions.submit_result(target_result)

    observed_phases: list[BattlePhase] = []

    def reroll_permission(
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        observed_phases.append(context.phase)
        return RerollPermission(
            source_id="test:skull-altar:battle-shock-reroll",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="test:skull-altar:battle-shock-reroll",
                source_id="test:skull-altar:battle-shock-reroll",
                reroll_permission_handler=reroll_permission,
            ),
        )
    )
    apply_status = apply_catalog_post_shoot_hit_target_effect_result(
        state=state,
        decisions=decisions,
        result=target_result,
        battle_shock_hooks=battle_shock_hooks,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ability_indexes_by_player_id=ability_indexes_by_player_id,
    )

    assert apply_status is not None
    assert apply_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    reroll_request = decisions.queue.peek_next()
    assert apply_status.decision_request == reroll_request
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert reroll_request.actor_id == target_army.player_id
    assert observed_phases == [BattlePhase.SHOOTING]
    pending_event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert "battle_shock_test_requested" in pending_event_types
    assert "battle_shock_test_resolved" not in pending_event_types

    reroll_result = DecisionResult.for_request(
        result_id="result:selected-target:battle-shock-reroll-declined",
        request=reroll_request,
        selected_option_id="decline",
    )
    decisions.submit_result(reroll_result)
    resume_status = apply_catalog_selected_target_battle_shock_reroll_decision(
        state=state,
        decisions=decisions,
        result=reroll_result,
        battle_shock_hooks=battle_shock_hooks,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ability_indexes_by_player_id=ability_indexes_by_player_id,
    )

    assert resume_status is None
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert "dice_reroll_declined" in event_types
    assert "battle_shock_test_resolved" in event_types
    assert "catalog_selected_target_battle_shock_resolved" in event_types
    assert CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT in event_types
    assert event_types.index("battle_shock_test_resolved") < event_types.index(
        CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT
    )


def test_battle_shock_resolution_result_rejects_invalid_shapes() -> None:
    with pytest.raises(GameLifecycleError, match="resolved or pending"):
        battle_shock_resolution.BattleShockResolutionResult(
            resolved_payload=None,
            pending_status=None,
        )

    with pytest.raises(GameLifecycleError, match="resolved or pending"):
        battle_shock_resolution.BattleShockResolutionResult(
            resolved_payload={},
            pending_status=LifecycleStatus.advanced(stage=GameLifecycleStage.BATTLE),
        )

    with pytest.raises(GameLifecycleError, match="pending status"):
        battle_shock_resolution.BattleShockResolutionResult(
            resolved_payload=None,
            pending_status=cast(LifecycleStatus, object()),
        )


def test_battle_shock_resolution_payload_helpers_fail_fast() -> None:
    assert (
        battle_shock_resolution._battle_phase_from_token(  # pyright: ignore[reportPrivateUsage]
            BattlePhase.CHARGE.value
        )
        is BattlePhase.CHARGE
    )

    helper_failures = (
        lambda: battle_shock_resolution._payload_object(  # pyright: ignore[reportPrivateUsage]
            "bad",
            context="Decision payload",
        ),
        lambda: battle_shock_resolution._payload_json_object(  # pyright: ignore[reportPrivateUsage]
            {},
            key="missing",
        ),
        lambda: battle_shock_resolution._payload_int(  # pyright: ignore[reportPrivateUsage]
            {},
            key="missing",
        ),
        lambda: battle_shock_resolution._payload_int(  # pyright: ignore[reportPrivateUsage]
            {"value": "bad"},
            key="value",
        ),
        lambda: battle_shock_resolution._payload_string(  # pyright: ignore[reportPrivateUsage]
            {},
            key="missing",
        ),
        lambda: battle_shock_resolution._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
            {},
            key="missing",
        ),
        lambda: battle_shock_resolution._payload_string_tuple(  # pyright: ignore[reportPrivateUsage]
            {"value": "bad"},
            key="value",
        ),
        lambda: battle_shock_resolution._battle_phase_from_token(  # pyright: ignore[reportPrivateUsage]
            object()
        ),
        lambda: battle_shock_resolution._battle_phase_from_token(  # pyright: ignore[reportPrivateUsage]
            "not-a-phase"
        ),
        lambda: battle_shock_resolution._validate_json_object(  # pyright: ignore[reportPrivateUsage]
            "field",
            "bad",
        ),
        lambda: battle_shock_resolution._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
            "field",
            ["not-a-tuple"],
        ),
        lambda: battle_shock_resolution._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
            "field",
            ("duplicate", "duplicate"),
        ),
    )

    for helper_failure in helper_failures:
        with pytest.raises(GameLifecycleError):
            helper_failure()

    inactive_state = _basic_battle_shock_resolution_inputs()[0]
    inactive_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="active player"):
        battle_shock_resolution._active_player_id(inactive_state)  # pyright: ignore[reportPrivateUsage]


def test_battle_shock_resolution_resolves_without_reroll_permission() -> None:
    state, decisions, manager, request, roll_state = _basic_battle_shock_resolution_inputs()

    resolution = battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        request=request,
        roll_state=roll_state,
        active_player_id="player-a",
        phase=BattlePhase.SHOOTING,
        phase_start_battle_shocked_unit_ids=(),
        source_kind="test-source",
        base_payload={"source_id": "test:no-reroll-resolution"},
        resolved_event_types=("test_battle_shock_resolved",),
        pending_phase_body_status="test_pending",
    )

    assert resolution.pending_status is None
    assert resolution.resolved_payload is not None
    assert resolution.resolved_payload["state_update"] == "recorded_battle_shocked"
    assert request.unit_instance_id in state.battle_shocked_unit_ids


def test_battle_shock_resolution_resolve_validates_runtime_inputs() -> None:
    state, decisions, manager, request, roll_state = _basic_battle_shock_resolution_inputs()

    with pytest.raises(GameLifecycleError, match="GameState"):
        battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
            state=cast(GameState, object()),
            decisions=decisions,
            manager=manager,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            request=request,
            roll_state=roll_state,
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
            phase_start_battle_shocked_unit_ids=(),
            source_kind="test-source",
            base_payload={},
            resolved_event_types=("test_battle_shock_resolved",),
            pending_phase_body_status="test_pending",
        )

    with pytest.raises(GameLifecycleError, match="DecisionController"):
        battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
            state=state,
            decisions=cast(DecisionController, object()),
            manager=manager,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            request=request,
            roll_state=roll_state,
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
            phase_start_battle_shocked_unit_ids=(),
            source_kind="test-source",
            base_payload={},
            resolved_event_types=("test_battle_shock_resolved",),
            pending_phase_body_status="test_pending",
        )

    with pytest.raises(GameLifecycleError, match="DiceRollManager"):
        battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
            state=state,
            decisions=decisions,
            manager=cast(DiceRollManager, object()),
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            request=request,
            roll_state=roll_state,
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
            phase_start_battle_shocked_unit_ids=(),
            source_kind="test-source",
            base_payload={},
            resolved_event_types=("test_battle_shock_resolved",),
            pending_phase_body_status="test_pending",
        )

    with pytest.raises(GameLifecycleError, match="Battle-shock hooks"):
        battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
            state=state,
            decisions=decisions,
            manager=manager,
            battle_shock_hooks=cast(BattleShockHookRegistry, object()),
            request=request,
            roll_state=roll_state,
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
            phase_start_battle_shocked_unit_ids=(),
            source_kind="test-source",
            base_payload={},
            resolved_event_types=("test_battle_shock_resolved",),
            pending_phase_body_status="test_pending",
        )

    with pytest.raises(GameLifecycleError, match="test request"):
        battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
            state=state,
            decisions=decisions,
            manager=manager,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            request=cast(BattleShockTestRequest, object()),
            roll_state=roll_state,
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
            phase_start_battle_shocked_unit_ids=(),
            source_kind="test-source",
            base_payload={},
            resolved_event_types=("test_battle_shock_resolved",),
            pending_phase_body_status="test_pending",
        )

    with pytest.raises(GameLifecycleError, match="dice roll state"):
        battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
            state=state,
            decisions=decisions,
            manager=manager,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            request=request,
            roll_state=cast(DiceRollState, object()),
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
            phase_start_battle_shocked_unit_ids=(),
            source_kind="test-source",
            base_payload={},
            resolved_event_types=("test_battle_shock_resolved",),
            pending_phase_body_status="test_pending",
        )


def test_battle_shock_reroll_resolution_apply_validates_runtime_inputs() -> None:
    state, decisions, _manager, _request, _roll_state = _basic_battle_shock_resolution_inputs()
    request = DecisionRequest(
        request_id="request:apply-validation",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-b",
        payload={},
        options=(DecisionOption(option_id="decline", label="decline"),),
    )
    result = DecisionResult.for_request(
        result_id="result:apply-validation",
        request=request,
        selected_option_id="decline",
    )

    with pytest.raises(GameLifecycleError, match="GameState"):
        battle_shock_resolution.apply_battle_shock_reroll_resolution_decision(
            state=cast(GameState, object()),
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            expected_source_kind="test-source",
        )

    with pytest.raises(GameLifecycleError, match="DecisionController"):
        battle_shock_resolution.apply_battle_shock_reroll_resolution_decision(
            state=state,
            decisions=cast(DecisionController, object()),
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            expected_source_kind="test-source",
        )

    with pytest.raises(GameLifecycleError, match="DecisionResult"):
        battle_shock_resolution.apply_battle_shock_reroll_resolution_decision(
            state=state,
            decisions=decisions,
            result=cast(DecisionResult, object()),
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            expected_source_kind="test-source",
        )

    with pytest.raises(GameLifecycleError, match="Battle-shock hooks"):
        battle_shock_resolution.apply_battle_shock_reroll_resolution_decision(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=cast(BattleShockHookRegistry, object()),
            expected_source_kind="test-source",
        )

    setup_state = _basic_battle_shock_resolution_inputs()[0]
    setup_state.stage = GameLifecycleStage.SETUP
    with pytest.raises(GameLifecycleError, match="during battle"):
        battle_shock_resolution.apply_battle_shock_reroll_resolution_decision(
            state=setup_state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            expected_source_kind="test-source",
        )

    phase_less_state = _basic_battle_shock_resolution_inputs()[0]
    phase_less_state.battle_phase_index = None
    with pytest.raises(GameLifecycleError, match="current battle phase"):
        battle_shock_resolution.apply_battle_shock_reroll_resolution_decision(
            state=phase_less_state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            expected_source_kind="test-source",
        )


def test_battle_shock_reroll_request_detection_rejects_non_matching_payloads() -> None:
    non_reroll_request = DecisionRequest(
        request_id="request:non-reroll",
        decision_type="test_decision",
        actor_id="player-a",
        payload={},
        options=(DecisionOption(option_id="accept", label="accept"),),
    )
    assert not battle_shock_resolution.is_battle_shock_reroll_request(
        non_reroll_request,
        source_kind="expected-source",
    )

    reroll_without_context = DecisionRequest(
        request_id="request:reroll-without-context",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        payload={},
        options=(DecisionOption(option_id="decline", label="decline"),),
    )
    assert not battle_shock_resolution.is_battle_shock_reroll_request(
        reroll_without_context,
        source_kind="expected-source",
    )

    reroll_with_other_context = DecisionRequest(
        request_id="request:reroll-other-context",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        payload={
            battle_shock_resolution.BATTLE_SHOCK_REROLL_CONTEXT_KEY: {
                battle_shock_resolution.BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY: "other-source"
            }
        },
        options=(DecisionOption(option_id="decline", label="decline"),),
    )
    assert not battle_shock_resolution.is_battle_shock_reroll_request(
        reroll_with_other_context,
        source_kind="expected-source",
    )

    with pytest.raises(GameLifecycleError, match="DecisionRequest"):
        battle_shock_resolution.is_battle_shock_reroll_request(
            cast(DecisionRequest, object()),
            source_kind="expected-source",
        )


def test_battle_shock_resolution_records_failed_state_updates() -> None:
    source_army, target_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_army.units[0],
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    request = _battle_shock_test_request(
        state=state,
        army=target_army,
        unit=target_unit,
        request_id="request:failed-battle-shock-recorded",
    )
    payload = battle_shock_resolution.record_battle_shock_result_and_outcome_events(
        state=state,
        decisions=DecisionController(),
        manager=DiceRollManager(state.game_id),
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        request=request,
        roll_state=_fixed_battle_shock_roll_state(
            request=request,
            roll_id="roll:failed-battle-shock-recorded",
            values=(1, 1),
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=(),
        base_payload={"source_id": "test:failed-battle-shock-recorded"},
        resolved_event_types=("test_battle_shock_resolved",),
    )

    resolved_payload = cast(dict[str, JsonValue], payload)
    assert resolved_payload["state_update"] == "recorded_battle_shocked"
    assert target_unit.unit_instance_id in state.battle_shocked_unit_ids

    already_shocked_state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_army.units[0],
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    already_shocked_request = _battle_shock_test_request(
        state=already_shocked_state,
        army=target_army,
        unit=target_unit,
        request_id="request:failed-battle-shock-already-shocked",
    )
    already_payload = battle_shock_resolution.record_battle_shock_result_and_outcome_events(
        state=already_shocked_state,
        decisions=DecisionController(),
        manager=DiceRollManager(already_shocked_state.game_id),
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        request=already_shocked_request,
        roll_state=_fixed_battle_shock_roll_state(
            request=already_shocked_request,
            roll_id="roll:failed-battle-shock-already-shocked",
            values=(1, 1),
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=(target_unit.unit_instance_id,),
        base_payload={"source_id": "test:failed-battle-shock-already-shocked"},
        resolved_event_types=("test_battle_shock_resolved",),
    )

    already_resolved_payload = cast(dict[str, JsonValue], already_payload)
    assert already_resolved_payload["state_update"] == "already_battle_shocked"
    assert target_unit.unit_instance_id not in already_shocked_state.battle_shocked_unit_ids


def test_fortification_cover_keyword_ignores_destroyed_blocker_model() -> None:
    source_army, target_army = _mustered_core_armies()
    fortification_unit = replace(
        _unit_with_dead_models(source_army.units[0]),
        keywords=tuple(sorted((*source_army.units[0].keywords, "FORTIFICATION"))),
    )
    source_army = replace(source_army, units=(fortification_unit,))
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=fortification_unit,
            source_x=15.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )

    assert not attack_sequence_hazardous._model_owner_unit_has_keyword(  # pyright: ignore[reportPrivateUsage]
        state=state,
        model_instance_id=fortification_unit.own_models[0].model_instance_id,
        keyword="FORTIFICATION",
    )


def test_charge_end_forced_battle_shock_reroll_pauses_and_resumes() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=10.4,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.CHARGE,
    )
    decisions = DecisionController()
    trigger_event = decisions.event_log.append(
        "charge_move_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "unit_instance_id": source_unit.unit_instance_id,
            "active_player_id": source_army.player_id,
            "movement_phase_action": "charge_move",
        },
    )

    def move_completed_handler(
        context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedBattleShockEffect, ...]:
        return (
            UnitMoveCompletedBattleShockEffect(
                hook_id="test:charge-end:battle-shock",
                source_id="test:charge-end:battle-shock",
                source_rule_id="source:test:charge-end:battle-shock",
                target_unit_instance_id=target_unit.unit_instance_id,
                target_player_id=target_army.player_id,
                trigger_event_id=context.trigger_event_id,
            ),
        )

    observed_phases: list[BattlePhase] = []

    def reroll_permission(
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        observed_phases.append(context.phase)
        return RerollPermission(
            source_id="test:charge-end:battle-shock-reroll",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="test:charge-end:battle-shock-reroll",
                source_id="test:charge-end:battle-shock-reroll",
                reroll_permission_handler=reroll_permission,
            ),
        )
    )
    status = resolve_unit_move_completed_battle_shock_hooks(
        state=state,
        decisions=decisions,
        registry=UnitMoveCompletedBattleShockHookRegistry.from_bindings(
            (
                UnitMoveCompletedBattleShockHookBinding(
                    hook_id="test:charge-end:battle-shock",
                    source_id="test:charge-end:battle-shock",
                    handler=move_completed_handler,
                ),
            )
        ),
        battle_shock_hooks=battle_shock_hooks,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        event_type="charge_move_completed",
        movement_actions=("charge_move",),
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records(()),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
    )

    assert trigger_event.event_id == "event-000001"
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    reroll_request = decisions.queue.peek_next()
    assert status.decision_request == reroll_request
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert observed_phases == [BattlePhase.CHARGE]

    reroll_result = DecisionResult.for_request(
        result_id="result:charge-end:battle-shock-reroll-declined",
        request=reroll_request,
        selected_option_id="decline",
    )
    decisions.submit_result(reroll_result)
    resume_status = apply_unit_move_completed_battle_shock_reroll_decision(
        state=state,
        decisions=decisions,
        result=reroll_result,
        battle_shock_hooks=battle_shock_hooks,
    )

    assert resume_status is None
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert "dice_reroll_declined" in event_types
    assert "battle_shock_test_resolved" in event_types
    assert "unit_move_completed_battle_shock_resolved" in event_types


def test_fortification_cover_ignores_destroyed_attacker_placements() -> None:
    source_army, target_army = _mustered_core_armies()
    attacker_unit = _unit_with_dead_models(source_army.units[0])
    fortification_unit_id = f"{source_army.units[0].unit_instance_id}:fortification"
    fortification_unit = _copy_unit_with_ids(
        source_army.units[0],
        unit_instance_id=fortification_unit_id,
        model_prefix=f"{fortification_unit_id}:model",
    )
    fortification_unit = replace(
        fortification_unit,
        keywords=tuple(sorted((*fortification_unit.keywords, "FORTIFICATION"))),
    )
    source_army = replace(source_army, units=(attacker_unit, fortification_unit))
    target_unit = target_army.units[0]
    battlefield = BattlefieldRuntimeState(
        battlefield_id="dead-attacker-fortification-cover",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=source_army.army_id,
                player_id=source_army.player_id,
                unit_placements=(
                    _unit_placement_for_test(
                        army=source_army,
                        unit=attacker_unit,
                        model_xs=_model_xs_for_unit(unit=attacker_unit, start_x=10.0),
                    ),
                    _unit_placement_for_test(
                        army=source_army,
                        unit=fortification_unit,
                        model_xs=_model_xs_for_unit(unit=fortification_unit, start_x=15.0),
                    ),
                ),
            ),
            _placed_army(
                army=target_army,
                unit=target_unit,
                model_xs=_model_xs_for_unit(unit=target_unit, start_x=20.0),
            ),
        ),
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    scenario = BattlefieldScenario(
        armies=(source_army, target_army),
        battlefield_state=battlefield,
    )
    target_model = target_unit.own_models[0]
    target_placement = battlefield.model_placement_by_id(target_model.model_instance_id)
    fortification_model = fortification_unit.own_models[0]
    fortification_placement = battlefield.model_placement_by_id(
        fortification_model.model_instance_id
    )
    profile = _first_catalog_weapon_profile()
    pool = RangedAttackPool(
        attacker_model_instance_id=attacker_unit.own_models[0].model_instance_id,
        wargear_id="dead-attacker-fortification-cover-wargear",
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target_unit.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_unit.own_model_ids(),
        target_in_range_model_ids=target_unit.own_model_ids(),
    )

    cover = attack_sequence_hazardous._fortification_cover_for_allocated_model(  # pyright: ignore[reportPrivateUsage]
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        scenario=scenario,
        pool=pool,
        allocated_model_id=target_model.model_instance_id,
        attacking_unit_id=attacker_unit.unit_instance_id,
        target_geometry=geometry_model_for_placement(
            model=target_model,
            placement=target_placement,
        ),
        terrain_features=(),
        terrain_volumes=(),
        dynamic_blockers=(
            geometry_model_for_placement(
                model=fortification_model,
                placement=fortification_placement,
            ),
        ),
    )

    assert cover is None


def _compiled_record(
    *,
    record_id: str,
    raw_text: str,
    source_unit: UnitInstance,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    source_text = RuleSourceText.from_raw(
        source_id=f"source:{record_id}",
        raw_text=raw_text,
    )
    rule_ir = compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return _ability_record(
        record_id=record_id,
        rule_ir=rule_ir,
        trigger_kind=trigger_kind,
        datasheet_id=source_unit.datasheet_id,
    )


def _ability_record(
    *,
    record_id: str,
    rule_ir: RuleIR,
    trigger_kind: TimingTriggerKind,
    datasheet_id: str,
) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=record_id,
        definition=AbilityDefinition(
            ability_id=f"{record_id}:ability",
            name="Skull Altar Runtime Regression",
            source_id=rule_ir.source_id,
            when_descriptor="Source-backed regression timing.",
            effect_descriptor="Source-backed regression effect.",
            restrictions_descriptor="Source-backed regression restrictions.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": cast(JsonValue, rule_ir.to_payload())}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _mustered_core_armies() -> tuple[ArmyDefinition, ArmyDefinition]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-b", army_id="army-beta"),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
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
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=f"{army_id}-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _successful_shooting_sequence(
    *,
    source_army: ArmyDefinition,
    source_unit: UnitInstance,
    target_army: ArmyDefinition,
    target_unit: UnitInstance,
) -> AttackSequence:
    del target_army
    profile = _first_catalog_weapon_profile()
    return AttackSequence(
        sequence_id="attack-sequence:post-shoot-battle-shock-reroll",
        attacker_player_id=source_army.player_id,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            RangedAttackPool(
                attacker_model_instance_id=source_unit.own_models[0].model_instance_id,
                wargear_id="post-shoot-battle-shock-reroll-wargear",
                weapon_profile_id=profile.profile_id,
                weapon_profile=profile,
                target_unit_instance_id=target_unit.unit_instance_id,
                shooting_type=ShootingType.NORMAL,
                attacks=1,
                target_visible_model_ids=target_unit.own_model_ids(),
                target_in_range_model_ids=target_unit.own_model_ids(),
            ),
        ),
    )


def _basic_battle_shock_resolution_inputs() -> tuple[
    GameState,
    DecisionController,
    DiceRollManager,
    BattleShockTestRequest,
    DiceRollState,
]:
    source_army, target_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_army.units[0],
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    request = _battle_shock_test_request(
        state=state,
        army=target_army,
        unit=target_unit,
        request_id="request:basic-battle-shock-resolution",
    )
    roll_state = _fixed_battle_shock_roll_state(
        request=request,
        roll_id="roll:basic-battle-shock-resolution",
        values=(1, 1),
    )
    decisions = DecisionController()
    return (
        state,
        decisions,
        DiceRollManager(state.game_id, event_log=decisions.event_log),
        request,
        roll_state,
    )


def _battle_shock_test_request(
    *,
    state: GameState,
    army: ArmyDefinition,
    unit: UnitInstance,
    request_id: str,
) -> BattleShockTestRequest:
    starting_strength = StartingStrengthRecord.from_unit(
        player_id=army.player_id,
        unit=unit,
    )
    return BattleShockTestRequest.for_unit(
        request_id=request_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=12,
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id=army.player_id,
            unit=unit,
            starting_strength=starting_strength,
            current_model_ids=unit.own_model_ids(),
        ),
    )


def _fixed_battle_shock_roll_state(
    *,
    request: BattleShockTestRequest,
    roll_id: str,
    values: tuple[int, int],
) -> DiceRollState:
    return DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id=roll_id,
            spec=request.spec,
            values=values,
            source="fixed",
        )
    )


def _first_catalog_weapon_profile() -> WeaponProfile:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    for wargear in catalog.wargear:
        if wargear.weapon_profiles:
            return wargear.weapon_profiles[0]
    raise AssertionError("Canonical catalog must contain a weapon profile.")


def _battlefield_for_units(
    *,
    source_army: ArmyDefinition,
    source_unit: UnitInstance,
    source_x: float,
    target_army: ArmyDefinition,
    target_unit: UnitInstance,
    target_x: float,
) -> BattlefieldRuntimeState:
    return BattlefieldRuntimeState(
        battlefield_id="skull-altar-runtime-regression-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            _placed_army(
                army=source_army,
                unit=source_unit,
                model_xs=_model_xs_for_unit(unit=source_unit, start_x=source_x),
            ),
            _placed_army(
                army=target_army,
                unit=target_unit,
                model_xs=_model_xs_for_unit(unit=target_unit, start_x=target_x),
            ),
        ),
    )


def _placed_army(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    model_xs: tuple[float, ...],
) -> PlacedArmy:
    return PlacedArmy(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_placements=(_unit_placement_for_test(army=army, unit=unit, model_xs=model_xs),),
    )


def _unit_placement_for_test(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    model_xs: tuple[float, ...],
) -> UnitPlacement:
    if len(model_xs) != len(unit.own_models):
        raise AssertionError("Test battlefield model positions must match unit models.")
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x=model_xs[index], y=10.0),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _model_xs_for_unit(*, unit: UnitInstance, start_x: float) -> tuple[float, ...]:
    return tuple(start_x + (index * 2.0) for index, _model in enumerate(unit.own_models))


def _state_with_battlefield(
    *,
    armies: tuple[ArmyDefinition, ...],
    battlefield: BattlefieldRuntimeState,
    active_player_id: str,
    phase: BattlePhase,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    return GameState(
        game_id="skull-altar-runtime-regressions-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
        player_ids=tuple(army.player_id for army in armies),
        turn_order=tuple(army.player_id for army in armies),
        tactical_secondary_draw_count=2,
        army_definitions=list(armies),
        battlefield_state=battlefield,
    )


def _unit_with_dead_models(unit: UnitInstance) -> UnitInstance:
    return replace(
        unit,
        own_models=tuple(replace(model, wounds_remaining=0) for model in unit.own_models),
    )


def _copy_unit_with_ids(
    unit: UnitInstance,
    *,
    unit_instance_id: str,
    model_prefix: str,
) -> UnitInstance:
    return replace(
        unit,
        unit_instance_id=unit_instance_id,
        own_models=tuple(
            replace(model, model_instance_id=f"{model_prefix}:{index:02d}")
            for index, model in enumerate(unit.own_models)
        ),
    )
