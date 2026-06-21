from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state_with_center_objective_positions,  # pyright: ignore[reportPrivateUsage]
    _default_unit_selection,  # pyright: ignore[reportPrivateUsage]
    _remove_first_models,  # pyright: ignore[reportPrivateUsage]
    _unit_by_id,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceRollResult, DiceRollSpec
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceStep,
    _target_unit_toughness,  # pyright: ignore[reportPrivateUsage]
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationHookBinding,
    BattleFormationHookRegistry,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    collect_battle_shock_test_requests,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierBinding,
    SaveOptionModifierContext,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveOption,
    save_options_for_model,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

DEATH_GUARD_TEST_DATASHEET_ID = "phase17g-death-guard-plague-marine"
DEATH_GUARD_UNIT_ID = "army-alpha:intercessor-unit-1"
ENEMY_UNIT_ID = "army-beta:intercessor-unit-3"


def test_lifecycle_requests_death_guard_plague_selection_and_records_state() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_death_guard_config())
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    summary_payload = _runtime_content_bundle(lifecycle).to_summary_payload()
    assert army_rule.HOOK_ID in summary_payload["battle_formation_hook_ids"]
    assert f"{army_rule.HOOK_ID}:toughness" in summary_payload["unit_characteristic_modifier_ids"]
    assert f"{army_rule.HOOK_ID}:leadership" in summary_payload["unit_characteristic_modifier_ids"]
    assert f"{army_rule.HOOK_ID}:melee-hit-roll" in summary_payload["hit_roll_modifier_ids"]
    assert f"{army_rule.HOOK_ID}:armour-save-option" in summary_payload["save_option_modifier_ids"]
    assert f"{army_rule.HOOK_ID}:movement-budget" in summary_payload["movement_budget_modifier_ids"]
    assert (
        f"{army_rule.HOOK_ID}:objective-control"
        in summary_payload["objective_control_modifier_ids"]
    )

    selected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-death-guard-select-skullsquirm",
            request=request,
            selected_option_id=(
                f"death_guard:nurgles_gift:{army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT.value}"
            ),
        )
    )

    assert selected.decision_request is not None
    assert selected.decision_request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE
    assert lifecycle.state is not None
    states = lifecycle.state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
    )
    assert len(states) == 1
    assert states[0].source_rule_id == army_rule.SOURCE_RULE_ID
    assert (
        army_rule.selected_plague_for_player(
            lifecycle.state,
            player_id="player-a",
        )
        is army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT
    )
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(lifecycle.state.to_payload())))
    )
    assert restored.to_payload() == lifecycle.state.to_payload()


def test_lifecycle_rejects_death_guard_plague_selection_drift_before_mutation() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_death_guard_config())
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    option_id = f"death_guard:nurgles_gift:{army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT.value}"
    option = request.option_by_id(option_id)

    actor_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-death-guard-wrong-actor",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id="player-b",
            selected_option_id=option.option_id,
            payload=option.payload,
        )
    )

    assert actor_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(actor_drift.payload, dict)
    assert actor_drift.payload["invalid_reason"] == "invalid_faction_rule_setup_option_result"
    assert actor_drift.payload["field"] == "actor_id"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert lifecycle.state is not None
    assert (
        lifecycle.state.faction_rule_states_for_player(
            player_id="player-a",
            state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
        )
        == ()
    )

    drifted_payload = dict(cast(dict[str, object], option.payload))
    drifted_payload["plague_id"] = army_rule.NurglesGiftPlague.RATTLEJOINT_AGUE.value
    payload_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-death-guard-payload-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=validate_json_value(drifted_payload),
        )
    )

    assert payload_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(payload_drift.payload, dict)
    assert payload_drift.payload["invalid_reason"] == "invalid_faction_rule_setup_option_result"
    assert payload_drift.payload["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert (
        lifecycle.state.faction_rule_states_for_player(
            player_id="player-a",
            state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
        )
        == ()
    )


def test_battle_formation_hook_registry_enforces_single_request_and_handler() -> None:
    config = _death_guard_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    assert lifecycle.state is not None
    request_context = BattleFormationRequestContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
    )

    registry = BattleFormationHookRegistry.from_bindings(
        (
            BattleFormationHookBinding(
                hook_id="phase17g:test-hook-a",
                source_id="phase17g:test-source-a",
                request_handler=lambda context: _test_battle_formation_request(
                    context=context,
                    hook_id="phase17g:test-hook-a",
                ),
            ),
            BattleFormationHookBinding(
                hook_id="phase17g:test-hook-b",
                source_id="phase17g:test-source-b",
                request_handler=lambda context: _test_battle_formation_request(
                    context=context,
                    hook_id="phase17g:test-hook-b",
                ),
            ),
        )
    )

    with pytest.raises(GameLifecycleError, match="multiple simultaneous requests"):
        registry.next_request_for(request_context)

    result = DecisionResult.for_request(
        result_id="phase17g-battle-formation-hook-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    result_context = BattleFormationResultContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
        request=request,
        result=result,
    )
    assert (
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:false-handler",
                    source_id="phase17g:false-source",
                    result_handler=lambda context: False,
                ),
            )
        ).apply_result(result_context)
        is False
    )

    multiple_handlers = BattleFormationHookRegistry.from_bindings(
        (
            BattleFormationHookBinding(
                hook_id="phase17g:true-handler-a",
                source_id="phase17g:true-source-a",
                result_handler=lambda context: True,
            ),
            BattleFormationHookBinding(
                hook_id="phase17g:true-handler-b",
                source_id="phase17g:true-source-b",
                result_handler=lambda context: True,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        multiple_handlers.apply_result(result_context)


def test_runtime_modifier_registry_applies_generic_surfaces_deterministically() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    unit = _unit_by_id(state, DEATH_GUARD_UNIT_ID)
    model_id = unit.own_models[0].model_instance_id
    save_option = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=0,
    )
    call_order: list[str] = []

    def unit_characteristic_first(context: UnitCharacteristicModifierContext) -> int:
        call_order.append("unit-characteristic:first")
        assert context.base_value == 4
        assert context.current_value == 4
        return context.current_value - 1

    def unit_characteristic_second(context: UnitCharacteristicModifierContext) -> int:
        call_order.append("unit-characteristic:second")
        assert context.base_value == 4
        assert context.current_value == 3
        return context.current_value * 2

    def hit_roll_first(context: HitRollModifierContext) -> int:
        call_order.append("hit-roll:first")
        assert context.attacker_model_instance_id == model_id
        return 1

    def hit_roll_second(context: HitRollModifierContext) -> int:
        call_order.append("hit-roll:second")
        assert context.source_phase is BattlePhase.FIGHT
        return -3

    def wound_roll_first(context: WoundRollModifierContext) -> int:
        call_order.append("wound-roll:first")
        assert context.strength == 5
        assert context.toughness == 4
        return 1

    def wound_roll_second(context: WoundRollModifierContext) -> int:
        call_order.append("wound-roll:second")
        assert context.target_unit_instance_id == ENEMY_UNIT_ID
        return -2

    def save_option_first(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
        call_order.append("save-option:first")
        option = context.save_options[0]
        return (
            replace(
                option,
                target_number=option.target_number + 1,
                source_rule_ids=(*option.source_rule_ids, "runtime:first-save"),
            ),
        )

    def save_option_second(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
        call_order.append("save-option:second")
        option = context.save_options[0]
        assert option.target_number == 4
        return (
            replace(
                option,
                target_number=option.target_number + 1,
                source_rule_ids=(*option.source_rule_ids, "runtime:second-save"),
            ),
        )

    def movement_first(context: MovementBudgetModifierContext) -> float:
        call_order.append("movement:first")
        assert context.current_movement_inches == 6.0
        return 5.0

    def movement_second(context: MovementBudgetModifierContext) -> float:
        call_order.append("movement:second")
        assert context.current_movement_inches == 5.0
        return 4.5

    def objective_control_first(context: ObjectiveControlModifierContext) -> int:
        call_order.append("objective-control:first")
        assert context.current_objective_control == 3
        return 2

    def objective_control_second(context: ObjectiveControlModifierContext) -> int:
        call_order.append("objective-control:second")
        assert context.current_objective_control == 2
        return 1

    registry = RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding(
                modifier_id="runtime:unit-characteristic-second",
                source_id="runtime:source-unit-characteristic-second",
                handler=unit_characteristic_second,
            ),
            UnitCharacteristicModifierBinding(
                modifier_id="runtime:unit-characteristic-first",
                source_id="runtime:source-unit-characteristic-first",
                handler=unit_characteristic_first,
            ),
        ),
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                modifier_id="runtime:hit-roll-second",
                source_id="runtime:source-hit-roll-second",
                handler=hit_roll_second,
            ),
            HitRollModifierBinding(
                modifier_id="runtime:hit-roll-first",
                source_id="runtime:source-hit-roll-first",
                handler=hit_roll_first,
            ),
        ),
        wound_roll_modifier_bindings=(
            WoundRollModifierBinding(
                modifier_id="runtime:wound-roll-second",
                source_id="runtime:source-wound-roll-second",
                handler=wound_roll_second,
            ),
            WoundRollModifierBinding(
                modifier_id="runtime:wound-roll-first",
                source_id="runtime:source-wound-roll-first",
                handler=wound_roll_first,
            ),
        ),
        save_option_modifier_bindings=(
            SaveOptionModifierBinding(
                modifier_id="runtime:save-option-second",
                source_id="runtime:source-save-option-second",
                handler=save_option_second,
            ),
            SaveOptionModifierBinding(
                modifier_id="runtime:save-option-first",
                source_id="runtime:source-save-option-first",
                handler=save_option_first,
            ),
        ),
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding(
                modifier_id="runtime:movement-second",
                source_id="runtime:source-movement-second",
                handler=movement_second,
            ),
            MovementBudgetModifierBinding(
                modifier_id="runtime:movement-first",
                source_id="runtime:source-movement-first",
                handler=movement_first,
            ),
        ),
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id="runtime:objective-control-second",
                source_id="runtime:source-objective-control-second",
                handler=objective_control_second,
            ),
            ObjectiveControlModifierBinding(
                modifier_id="runtime:objective-control-first",
                source_id="runtime:source-objective-control-first",
                handler=objective_control_first,
            ),
        ),
    )

    assert [binding.modifier_id for binding in registry.all_hit_roll_bindings()] == [
        "runtime:hit-roll-first",
        "runtime:hit-roll-second",
    ]
    assert [binding.modifier_id for binding in registry.all_wound_roll_bindings()] == [
        "runtime:wound-roll-first",
        "runtime:wound-roll-second",
    ]
    assert (
        registry.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                characteristic=cast(Characteristic, Characteristic.TOUGHNESS.value),
                base_value=4,
                current_value=4,
            )
        )
        == 6
    )
    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=unit.unit_instance_id,
                attacker_model_instance_id=model_id,
                target_unit_instance_id=ENEMY_UNIT_ID,
                weapon_profile=_first_weapon_profile_for_unit(unit),
                source_phase=cast(BattlePhase, BattlePhase.FIGHT.value),
            )
        )
        == -2
    )
    assert (
        registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=unit.unit_instance_id,
                attacker_model_instance_id=model_id,
                target_unit_instance_id=ENEMY_UNIT_ID,
                weapon_profile=_first_weapon_profile_for_unit(unit),
                strength=5,
                toughness=4,
            )
        )
        == -1
    )
    assert registry.modified_save_options(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            save_options=(save_option,),
        )
    ) == (
        replace(
            save_option,
            target_number=5,
            source_rule_ids=("runtime:first-save", "runtime:second-save"),
        ),
    )
    assert (
        registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                base_movement_inches=6,
                current_movement_inches=6,
            )
        )
        == 4.5
    )
    assert (
        registry.modified_objective_control(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                base_objective_control=3,
                current_objective_control=3,
            )
        )
        == 1
    )
    assert call_order == [
        "unit-characteristic:first",
        "unit-characteristic:second",
        "hit-roll:first",
        "hit-roll:second",
        "wound-roll:first",
        "wound-roll:second",
        "save-option:first",
        "save-option:second",
        "movement:first",
        "movement:second",
        "objective-control:first",
        "objective-control:second",
    ]


def test_runtime_modifier_registry_rejects_duplicate_ids_and_bad_handler_results() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    unit = _unit_by_id(state, DEATH_GUARD_UNIT_ID)
    model_id = unit.own_models[0].model_instance_id

    valid_binding = HitRollModifierBinding(
        modifier_id="runtime:duplicate-hit-roll",
        source_id="runtime:duplicate-source",
        handler=lambda _context: 0,
    )
    with pytest.raises(GameLifecycleError, match="modifier IDs must be unique"):
        RuntimeModifierRegistry.from_bindings(
            hit_roll_modifier_bindings=(valid_binding, valid_binding)
        )

    bad_binding = MovementBudgetModifierBinding(
        modifier_id="runtime:bad-movement",
        source_id="runtime:bad-movement-source",
        handler=lambda _context: -1.0,
    )
    bad_registry = RuntimeModifierRegistry.from_bindings(
        movement_budget_modifier_bindings=(bad_binding,)
    )
    with pytest.raises(GameLifecycleError, match="runtime:bad-movement returned movement"):
        bad_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_id,
                base_movement_inches=6,
                current_movement_inches=6,
            )
        )


def test_runtime_modifier_registry_rejects_invalid_context_and_binding_shapes() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    unit = _unit_by_id(state, DEATH_GUARD_UNIT_ID)
    model_id = unit.own_models[0].model_instance_id
    invalid_state = cast(GameState, object())
    registry = RuntimeModifierRegistry.empty()

    with pytest.raises(GameLifecycleError, match="Unit characteristic modifier state"):
        UnitCharacteristicModifierContext(
            state=invalid_state,
            unit_instance_id=unit.unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=4,
            current_value=4,
        )
    with pytest.raises(GameLifecycleError, match="Hit roll modifier state"):
        HitRollModifierContext(
            state=invalid_state,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=model_id,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_first_weapon_profile_for_unit(unit),
            source_phase=BattlePhase.FIGHT,
        )
    with pytest.raises(GameLifecycleError, match="Wound roll modifier state"):
        WoundRollModifierContext(
            state=invalid_state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=model_id,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_first_weapon_profile_for_unit(unit),
            strength=5,
            toughness=4,
        )
    with pytest.raises(GameLifecycleError, match="Save option modifier state"):
        SaveOptionModifierContext(
            state=invalid_state,
            target_unit_instance_id=unit.unit_instance_id,
            save_options=(),
        )
    with pytest.raises(GameLifecycleError, match="Movement budget modifier state"):
        MovementBudgetModifierContext(
            state=invalid_state,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model_id,
            base_movement_inches=6,
            current_movement_inches=6,
        )
    with pytest.raises(GameLifecycleError, match="Objective Control modifier state"):
        ObjectiveControlModifierContext(
            state=invalid_state,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model_id,
            base_objective_control=2,
            current_objective_control=2,
        )

    with pytest.raises(GameLifecycleError, match="Unit characteristic modifiers require"):
        registry.modified_unit_characteristic(cast(UnitCharacteristicModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Hit roll modifiers require"):
        registry.hit_roll_modifier(cast(HitRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Wound roll modifiers require"):
        registry.wound_roll_modifier(cast(WoundRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Save option modifiers require"):
        registry.modified_save_options(cast(SaveOptionModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Movement budget modifiers require"):
        registry.modified_movement_inches(cast(MovementBudgetModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Objective Control modifiers require"):
        registry.modified_objective_control(cast(ObjectiveControlModifierContext, object()))

    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        RuntimeModifierRegistry(
            hit_roll_modifier_bindings=cast(tuple[HitRollModifierBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="must contain HitRollModifierBinding"):
        RuntimeModifierRegistry(
            hit_roll_modifier_bindings=cast(tuple[HitRollModifierBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        HitRollModifierBinding(
            modifier_id="runtime:bad-handler",
            source_id="runtime:bad-handler-source",
            handler=cast(Callable[[HitRollModifierContext], int], object()),
        )
    with pytest.raises(GameLifecycleError, match="modifier_id must not be empty"):
        HitRollModifierBinding(
            modifier_id=" ",
            source_id="runtime:bad-id-source",
            handler=lambda _context: 0,
        )

    with pytest.raises(GameLifecycleError, match="save_options must be a tuple"):
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            save_options=cast(tuple[SaveOption, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="save_options must contain SaveOption"):
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            save_options=cast(tuple[SaveOption, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="must be a Characteristic"):
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            characteristic=cast(Characteristic, object()),
            base_value=4,
            current_value=4,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported runtime modifier characteristic"):
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            characteristic=cast(Characteristic, "invalid-characteristic"),
            base_value=4,
            current_value=4,
        )
    with pytest.raises(GameLifecycleError, match="must be a BattlePhase"):
        HitRollModifierContext(
            state=state,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=model_id,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_first_weapon_profile_for_unit(unit),
            source_phase=cast(BattlePhase, object()),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported runtime modifier BattlePhase"):
        HitRollModifierContext(
            state=state,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=model_id,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_first_weapon_profile_for_unit(unit),
            source_phase=cast(BattlePhase, "invalid-phase"),
        )
    with pytest.raises(GameLifecycleError, match="base_movement_inches must be numeric"):
        MovementBudgetModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model_id,
            base_movement_inches=cast(float, object()),
            current_movement_inches=6,
        )
    with pytest.raises(GameLifecycleError, match="base_value must not be negative"):
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=-1,
            current_value=4,
        )
    with pytest.raises(GameLifecycleError, match="current_value must be an int"):
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=4,
            current_value=cast(int, 1.25),
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id must be a string"):
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=cast(str, object()),
            characteristic=Characteristic.TOUGHNESS,
            base_value=4,
            current_value=4,
        )


def test_battle_formation_hook_registry_rejects_invalid_shapes() -> None:
    config = _death_guard_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = _advance_through_secondary_choices(lifecycle)
    request = status.decision_request
    assert request is not None
    assert lifecycle.state is not None
    request_context = BattleFormationRequestContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    result_context = BattleFormationResultContext(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        config=config,
        request=request,
        result=DecisionResult.for_request(
            result_id="phase17g-invalid-shape-result",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
    )

    with pytest.raises(GameLifecycleError, match="requires a handler"):
        BattleFormationHookBinding(hook_id="phase17g:no-handler", source_id="phase17g:source")
    with pytest.raises(GameLifecycleError, match="hook_id must be a string"):
        BattleFormationHookBinding(
            hook_id=cast(str, object()),
            source_id="phase17g:source",
            request_handler=lambda context: None,
        )
    with pytest.raises(GameLifecycleError, match="source_id must not be empty"):
        BattleFormationHookBinding(
            hook_id="phase17g:empty-source",
            source_id=" ",
            request_handler=lambda context: None,
        )
    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        BattleFormationHookBinding(
            hook_id="phase17g:bad-request-handler",
            source_id="phase17g:source",
            request_handler=cast(
                Callable[[BattleFormationRequestContext], DecisionRequest | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        BattleFormationHookBinding(
            hook_id="phase17g:bad-result-handler",
            source_id="phase17g:source",
            result_handler=cast(Callable[[BattleFormationResultContext], bool], object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        BattleFormationHookRegistry(bindings=cast(tuple[BattleFormationHookBinding, ...], object()))
    with pytest.raises(GameLifecycleError, match="must contain BattleFormationHookBinding"):
        BattleFormationHookRegistry(bindings=(cast(BattleFormationHookBinding, object()),))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:duplicate",
                    source_id="phase17g:source-a",
                    request_handler=lambda context: None,
                ),
                BattleFormationHookBinding(
                    hook_id="phase17g:duplicate",
                    source_id="phase17g:source-b",
                    request_handler=lambda context: None,
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="request hooks require a context"):
        BattleFormationHookRegistry.empty().next_request_for(
            cast(BattleFormationRequestContext, object())
        )
    assert (
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:none-request",
                    source_id="phase17g:source",
                    request_handler=lambda context: None,
                ),
            )
        ).next_request_for(request_context)
        is None
    )
    with pytest.raises(GameLifecycleError, match="DecisionRequest or None"):
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:bad-request",
                    source_id="phase17g:source",
                    request_handler=_bad_battle_formation_request_handler,
                ),
            )
        ).next_request_for(request_context)

    with pytest.raises(GameLifecycleError, match="result hooks require a context"):
        BattleFormationHookRegistry.empty().apply_result(
            cast(BattleFormationResultContext, object())
        )
    with pytest.raises(GameLifecycleError, match="handlers must return bool"):
        BattleFormationHookRegistry.from_bindings(
            (
                BattleFormationHookBinding(
                    hook_id="phase17g:bad-result",
                    source_id="phase17g:source",
                    result_handler=_bad_battle_formation_result_handler,
                ),
            )
        ).apply_result(result_context)


def test_faction_rule_state_validation_rejects_invalid_and_duplicate_records() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    stored = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
    )[0]

    with pytest.raises(GameLifecycleError, match="must be FactionRuleState"):
        state.record_faction_rule_state(cast(FactionRuleState, object()))
    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_faction_rule_state(stored)
    with pytest.raises(GameLifecycleError, match="player_id"):
        state.faction_rule_states_for_player(player_id="missing-player")
    with pytest.raises(GameLifecycleError, match="setup_step"):
        FactionRuleState.from_payload(
            {
                "state_id": "phase17g-invalid-step",
                "player_id": "player-a",
                "faction_id": army_rule.DEATH_GUARD_FACTION_ID,
                "source_rule_id": army_rule.SOURCE_RULE_ID,
                "state_kind": army_rule.NURGLES_GIFT_STATE_KIND,
                "setup_step": "not-a-step",
                "request_id": "phase17g-request",
                "result_id": "phase17g-result",
                "payload": {},
            }
        )


def test_contagion_range_caps_after_modifiers_per_11th_update() -> None:
    assert army_rule.contagion_range_inches(battle_round=1) == 3.0
    assert army_rule.contagion_range_inches(battle_round=2) == 6.0
    assert army_rule.contagion_range_inches(battle_round=3) == 9.0
    assert army_rule.contagion_range_inches(battle_round=3, modifier_inches=6.0) == 12.0


def test_nurgles_gift_requires_live_placed_death_guard_model_in_contagion_range() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)

    assert army_rule.afflicting_death_guard_player_ids(
        state,
        target_unit_instance_id=ENEMY_UNIT_ID,
    ) == ("player-a",)

    _remove_first_models(state, unit_instance_id=DEATH_GUARD_UNIT_ID, count=1)

    assert (
        army_rule.afflicting_death_guard_player_ids(
            state,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
        == ()
    )


def test_nurgles_gift_afflicted_units_have_minus_one_toughness() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.RATTLEJOINT_AGUE)

    assert (
        _target_unit_toughness(
            state=state,
            target_unit_instance_id=ENEMY_UNIT_ID,
            runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
        )
        == 3
    )
    assert (
        army_rule.nurgles_gift_modified_toughness(
            state=state,
            target_unit_instance_id=ENEMY_UNIT_ID,
            base_toughness=4,
        )
        == 3
    )


def test_skullsquirm_blight_only_modifies_afflicted_melee_hit_rolls() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    enemy_model_id = _unit_by_id(state, ENEMY_UNIT_ID).own_models[0].model_instance_id

    assert (
        army_rule.nurgles_gift_hit_roll_modifier(
            state=state,
            attacker_model_instance_id=enemy_model_id,
            source_phase=BattlePhase.FIGHT,
        )
        == -1
    )
    assert (
        army_rule.nurgles_gift_hit_roll_modifier(
            state=state,
            attacker_model_instance_id=enemy_model_id,
            source_phase=BattlePhase.SHOOTING,
        )
        == 0
    )


def test_rattlejoint_ague_worsens_afflicted_armour_save_option() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.RATTLEJOINT_AGUE)
    enemy_model = _unit_by_id(state, ENEMY_UNIT_ID).own_models[0]
    base_options = save_options_for_model(model=enemy_model, armor_penetration=0)

    modified = army_rule.nurgles_gift_modified_save_options(
        state=state,
        target_unit_instance_id=ENEMY_UNIT_ID,
        save_options=base_options,
    )

    base_armour = next(option for option in base_options if option.save_kind is SaveKind.ARMOUR)
    modified_armour = next(option for option in modified if option.save_kind is SaveKind.ARMOUR)
    assert modified_armour.characteristic_target_number == (
        base_armour.characteristic_target_number + 1
    )
    assert modified_armour.target_number == base_armour.target_number + 1
    assert army_rule.SOURCE_RULE_ID in modified_armour.source_rule_ids


def test_scabrous_soulrot_movement_consumer_rejects_path_over_modified_budget() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SCABROUS_SOULROT)
    scenario = _scenario_from_state(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(ENEMY_UNIT_ID)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        state=state,
        path_witness=_full_unit_straight_line_witness(
            unit_placement=unit_placement,
            delta_x=6.0,
            delta_y=0.0,
        ),
        runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
    )

    violation_codes = {
        violation.violation_code
        for result in resolution.path_validation_results
        for violation in result.violations
    }
    model_movements = cast(list[dict[str, object]], resolution.movement_payload["model_movements"])

    assert not resolution.is_valid
    assert "movement_distance_exceeded" in violation_codes
    assert {movement["movement_inches"] for movement in model_movements} == {5.0}
    assert {movement["base_movement_inches"] for movement in model_movements} == {5.0}


def test_scabrous_soulrot_objective_control_consumer_uses_reduced_oc() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SCABROUS_SOULROT)

    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
        )
    )

    enemy_contributions = tuple(
        contribution
        for result in record.results
        for contribution in result.contributors
        if contribution.unit_instance_id == ENEMY_UNIT_ID
    )

    assert enemy_contributions
    assert {contribution.objective_control for contribution in enemy_contributions} == {1}
    assert {contribution.effective_objective_control for contribution in enemy_contributions} == {1}


def test_skullsquirm_blight_attack_sequence_consumes_melee_hit_modifier_only() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SKULLSQUIRM_BLIGHT)
    attacker = _unit_by_id(state, ENEMY_UNIT_ID)
    defender = _unit_by_id(state, DEATH_GUARD_UNIT_ID)

    melee_hit = _single_attack_hit_payload(
        state=state,
        attacker=attacker,
        defender=defender,
        source_phase=BattlePhase.FIGHT,
        sequence_id="phase17g-skullsquirm-melee-hit",
        hit_roll=3,
    )
    shooting_hit = _single_attack_hit_payload(
        state=state,
        attacker=attacker,
        defender=defender,
        source_phase=BattlePhase.SHOOTING,
        sequence_id="phase17g-skullsquirm-shooting-hit",
        hit_roll=3,
    )

    assert melee_hit["modifier"] == -1
    assert melee_hit["capped_modifier"] == -1
    assert melee_hit["final_roll"] == 2
    assert melee_hit["successful"] is False
    assert shooting_hit["modifier"] == 0
    assert shooting_hit["capped_modifier"] == 0
    assert shooting_hit["final_roll"] == 3
    assert shooting_hit["successful"] is True


def test_rattlejoint_ague_attack_sequence_worsens_armour_save_option() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.RATTLEJOINT_AGUE)
    attacker = _unit_by_id(state, DEATH_GUARD_UNIT_ID)
    defender = _unit_by_id(state, ENEMY_UNIT_ID)
    defender_model = defender.own_models[2]
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        tuple(
            model.model_instance_id
            for model in defender.own_models
            if model.model_instance_id != defender_model.model_instance_id
        )
    )

    save_payload = _single_attack_save_payload(
        state=state,
        attacker=attacker,
        defender=defender,
        defender_model_id=defender_model.model_instance_id,
        sequence_id="phase17g-rattlejoint-save",
        save_roll=3,
    )
    option = cast(dict[str, object], save_payload["option"])
    save_options = cast(list[dict[str, object]], save_payload["save_options"])

    assert save_payload["save_kind"] == SaveKind.ARMOUR.value
    assert save_payload["target_number"] == 4
    assert save_payload["unmodified_roll"] == 3
    assert save_payload["final_roll"] == 3
    assert save_payload["successful"] is False
    assert option["target_number"] == 4
    assert save_options[0]["target_number"] == 4


def test_scabrous_soulrot_worsens_afflicted_move_leadership_and_oc() -> None:
    state = _death_guard_battle_state(army_rule.NurglesGiftPlague.SCABROUS_SOULROT)
    enemy_unit = _unit_by_id(state, ENEMY_UNIT_ID)
    enemy_model = enemy_unit.own_models[0]

    assert (
        army_rule.nurgles_gift_modified_movement_inches(
            state=state,
            unit_instance_id=ENEMY_UNIT_ID,
            base_movement_inches=6.0,
        )
        == 5.0
    )
    assert (
        army_rule.nurgles_gift_modified_objective_control(
            state=state,
            unit_instance_id=ENEMY_UNIT_ID,
            base_objective_control=2,
        )
        == 1
    )
    assert (
        army_rule.nurgles_gift_modified_objective_control(
            state=state,
            unit_instance_id=ENEMY_UNIT_ID,
            base_objective_control=1,
        )
        == 1
    )

    _remove_first_models(state, unit_instance_id=ENEMY_UNIT_ID, count=3)
    assert state.battlefield_state is not None
    enemy_army = state.army_definition_for_player("player-b")
    assert enemy_army is not None
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        army=enemy_army,
        battlefield_state=state.battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
        state=state,
        ability_index=AbilityCatalogIndex.from_records(()),
        runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
    )

    assert len(requests) == 1
    assert requests[0].reason is BattleShockTestReason.BELOW_HALF_STRENGTH
    assert requests[0].leadership_target == (
        enemy_model.characteristic(Characteristic.LEADERSHIP).final + 1
    )


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    if state.battlefield_state is None:
        raise AssertionError("Death Guard test state requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _full_unit_straight_line_witness(
    *,
    unit_placement: UnitPlacement,
    delta_x: float,
    delta_y: float,
) -> PathWitness:
    model_paths: list[tuple[str, Pose, Pose]] = []
    for placement in unit_placement.model_placements:
        model_paths.append(
            (
                placement.model_instance_id,
                placement.pose,
                Pose.at(
                    x=placement.pose.position.x + delta_x,
                    y=placement.pose.position.y + delta_y,
                    z=placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                ),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(model_paths))


def _death_guard_runtime_modifier_registry() -> RuntimeModifierRegistry:
    contribution = army_rule.runtime_contribution()
    return RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=contribution.unit_characteristic_modifier_bindings,
        hit_roll_modifier_bindings=contribution.hit_roll_modifier_bindings,
        save_option_modifier_bindings=contribution.save_option_modifier_bindings,
        movement_budget_modifier_bindings=contribution.movement_budget_modifier_bindings,
        objective_control_modifier_bindings=contribution.objective_control_modifier_bindings,
    )


def _single_attack_hit_payload(
    *,
    state: GameState,
    attacker: UnitInstance,
    defender: UnitInstance,
    source_phase: BattlePhase,
    sequence_id: str,
    hit_roll: int,
) -> dict[str, object]:
    weapon_profile = replace(
        _first_weapon_profile_for_unit(attacker),
        profile_id=f"{sequence_id}:weapon",
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    decisions = DecisionController()
    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id=attacker_player_id(attacker),
            attacking_unit_instance_id=attacker.unit_instance_id,
            source_phase=source_phase,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id(attacker),
                    ),
                    value=hit_roll,
                ),
            ),
        ),
        runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
    )
    hit_event = _attack_step_payload(
        _event_payloads(decisions, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    return cast(dict[str, object], hit_event["payload"])


def _single_attack_save_payload(
    *,
    state: GameState,
    attacker: UnitInstance,
    defender: UnitInstance,
    defender_model_id: str,
    sequence_id: str,
    save_roll: int,
) -> dict[str, object]:
    weapon_profile = replace(
        _first_weapon_profile_for_unit(attacker),
        profile_id=f"{sequence_id}:weapon",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    decisions = DecisionController()
    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id=attacker_player_id(attacker),
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    target_model_ids=(defender_model_id,),
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id(attacker),
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id(attacker),
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id=defender_player_id(defender),
                        allocated_model_id=defender_model_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=save_roll,
                ),
            ),
        ),
        runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
    )
    save_event = _attack_step_payload(
        _event_payloads(decisions, "attack_sequence_step"),
        AttackSequenceStep.SAVE,
    )
    return cast(dict[str, object], save_event["payload"])


def _attack_pool_for_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
    target_model_ids: tuple[str, ...] | None = None,
) -> RangedAttackPool:
    defender_model_ids = (
        tuple(model.model_instance_id for model in defender.own_models)
        if target_model_ids is None
        else target_model_ids
    )
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=defender_model_ids,
        target_in_range_model_ids=defender_model_ids,
    )


def _first_weapon_profile_for_unit(unit: UnitInstance) -> WeaponProfile:
    wargear_id = unit.wargear_selections[0].wargear_ids[0]
    for wargear in _death_guard_catalog().wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"Missing test wargear {wargear_id}.")


def _fixed_roll_result(
    *,
    roll_id: str,
    spec: DiceRollSpec,
    value: int,
) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=roll_id,
        spec=spec,
        values=(value,),
        source="fixed",
    )


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _attack_step_payload(
    events: tuple[dict[str, object], ...],
    step: AttackSequenceStep,
) -> dict[str, object]:
    for event in events:
        if event["step"] == step.value:
            return event
    raise AssertionError(f"Missing attack sequence step {step.value}.")


def attacker_player_id(unit: UnitInstance) -> str:
    if unit.unit_instance_id.startswith("army-alpha:"):
        return "player-a"
    if unit.unit_instance_id.startswith("army-beta:"):
        return "player-b"
    raise AssertionError(f"Unknown attacker unit owner for {unit.unit_instance_id}.")


def defender_player_id(unit: UnitInstance) -> str:
    return attacker_player_id(unit)


def _death_guard_battle_state(plague: army_rule.NurglesGiftPlague) -> GameState:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((2.0, -3.0), (2.0, -1.5), (2.0, 0.0), (2.0, 1.5), (2.0, 3.0)),
    )
    _mark_player_as_death_guard(state, player_id="player-a")
    _record_plague_selection(state, player_id="player-a", plague=plague)
    return state


def _mark_player_as_death_guard(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(replace(unit, faction_keywords=("Death Guard",)))
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                ),
                units=tuple(updated_units),
            )
        )
    state.army_definitions = updated_armies


def _record_plague_selection(
    state: GameState,
    *,
    player_id: str,
    plague: army_rule.NurglesGiftPlague,
) -> None:
    state.record_faction_rule_state(
        FactionRuleState(
            state_id=f"{army_rule.HOOK_ID}:{player_id}:plague-selection",
            player_id=player_id,
            faction_id=army_rule.DEATH_GUARD_FACTION_ID,
            source_rule_id=army_rule.SOURCE_RULE_ID,
            state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="phase17g-death-guard-test-request",
            result_id=f"phase17g-death-guard-test-result:{plague.value}",
            payload={
                "plague_id": plague.value,
                "hook_id": army_rule.HOOK_ID,
            },
        )
    )


def _test_battle_formation_request(
    *,
    context: BattleFormationRequestContext,
    hook_id: str,
) -> DecisionRequest:
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={
            "hook_id": hook_id,
            "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
        },
        options=(
            DecisionOption(
                option_id=f"{hook_id}:option",
                label=hook_id,
                payload={"hook_id": hook_id},
            ),
        ),
    )


def _bad_battle_formation_request_handler(
    context: BattleFormationRequestContext,
) -> DecisionRequest | None:
    assert type(context) is BattleFormationRequestContext
    return cast(DecisionRequest, object())


def _bad_battle_formation_result_handler(context: BattleFormationResultContext) -> bool:
    assert type(context) is BattleFormationResultContext
    return cast(bool, "yes")


def _advance_through_secondary_choices(lifecycle: GameLifecycle) -> LifecycleStatus:
    status = lifecycle.advance_until_decision_or_terminal()
    for result_id in (
        "phase17g-death-guard-secondary-player-a",
        "phase17g-death-guard-secondary-player-b",
    ):
        request = status.decision_request
        assert request is not None
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=result_id,
                request=request,
                selected_option_id="fixed:assassination:bring_it_down",
            )
        )
    return status


def _death_guard_config() -> GameConfig:
    catalog = _death_guard_catalog()
    return GameConfig(
        game_id="phase17g-death-guard-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-death-guard-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                    detachment_ids=("plague-company",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="plague-marine",
                        datasheet_id=DEATH_GUARD_TEST_DATASHEET_ID,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                ),
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
                unit_selections=(_default_unit_selection("enemy-unit"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _death_guard_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    death_guard_datasheet = _death_guard_datasheet(base_datasheet)
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, death_guard_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                name="Death Guard",
                faction_keywords=("Death Guard",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:death-guard",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="plague-company",
                name="Plague Company",
                faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(DEATH_GUARD_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:death-guard:plague-company",
                ),
            ),
        ),
    )


def _death_guard_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=DEATH_GUARD_TEST_DATASHEET_ID,
        name="Plague Marine",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Battleline"),
            faction_keywords=("Death Guard",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:death-guard:plague-marine",),
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()
