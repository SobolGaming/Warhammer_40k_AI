from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _complete_setup_through_gate,  # pyright: ignore[reportPrivateUsage]
    _default_unit_selection,  # pyright: ignore[reportPrivateUsage]
)
from tests.unit.test_phase15d_fight_resolution import (
    _melee_fixture,  # pyright: ignore[reportPrivateUsage]
    _melee_proposal,  # pyright: ignore[reportPrivateUsage]
    _melee_request,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule,
)
from warhammer40k_core.engine.fight_resolution import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    melee_attack_sequence_from_proposal,
)
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
    WargearSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.phases.charge import (
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargePhaseHandler,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

WORLD_EATERS_DATASHEET_ID = "phase17g-world-eaters-berzerkers"
WORLD_EATERS_UNIT_ID = "army-alpha:berzerkers"
ENEMY_UNIT_ID = "army-beta:enemy-unit"
ICON_OF_KHORNE_WARGEAR_ID = "icon-of-khorne"
ICON_OF_KHORNE_OPTION_ID = "world-eaters-icon-of-khorne"


def test_lifecycle_requests_world_eaters_blessings_and_records_effect() -> None:
    lifecycle = _battle_ready_lifecycle()
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"

    summary_payload = _runtime_content_bundle(lifecycle).to_summary_payload()
    assert army_rule.HOOK_ID in summary_payload["battle_round_start_hook_ids"]
    assert (
        army_rule.UNBRIDLED_BLOODLUST_CHARGE_MODIFIER_ID
        in summary_payload["charge_roll_modifier_ids"]
    )
    assert (
        army_rule.RAGE_FUELLED_INVIGORATION_HOOK_ID
        in summary_payload["fight_activation_ability_hook_ids"]
    )
    assert (
        f"{army_rule.HOOK_ID}:weapon-profile-keywords"
        in summary_payload["weapon_profile_modifier_ids"]
    )

    selected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-world-eaters-select-unbridled",
            request=request,
            selected_option_id="world_eaters:blessings:unbridled_bloodlust",
        )
    )

    assert selected.decision_request is not None
    assert lifecycle.state is not None
    assert army_rule.active_blessings_for_player(lifecycle.state, player_id="player-a") == (
        army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,
    )
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(lifecycle.state.to_payload())))
    )
    assert restored.to_payload() == lifecycle.state.to_payload()


def test_no_blessing_selection_is_not_requested_twice_in_same_round() -> None:
    lifecycle = _battle_ready_lifecycle()
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE

    selected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-world-eaters-select-none",
            request=request,
            selected_option_id="world_eaters:blessings:none",
        )
    )

    assert selected.decision_request is not None
    assert selected.decision_request.decision_type != (
        SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
    )
    assert lifecycle.state is not None
    assert army_rule.active_blessings_for_player(lifecycle.state, player_id="player-a") == ()


def test_blessings_selection_result_validation_paths_are_fail_fast() -> None:
    state = _battle_ready_state()
    decisions = DecisionController()
    options = army_rule.blessings_selection_options(
        player_id="player-a",
        battle_round=state.battle_round,
        dice_values=(1, 1, 2, 2, 3, 3, 4, 4),
        bloodshed_points=0,
    )

    wrong_decision_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type="phase17g-other-decision",
        actor_id="player-a",
        payload=validate_json_value({"hook_id": army_rule.HOOK_ID}),
        options=options,
    )
    wrong_decision_result = DecisionResult.for_request(
        result_id="phase17g-world-eaters-wrong-decision",
        request=wrong_decision_request,
        selected_option_id="world_eaters:blessings:unbridled_bloodlust",
    )
    assert not army_rule.apply_blessings_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_decision_request,
            result=wrong_decision_result,
        )
    )

    wrong_hook_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"hook_id": "phase17g-other-hook"}),
        options=options,
    )
    wrong_hook_result = DecisionResult.for_request(
        result_id="phase17g-world-eaters-wrong-hook",
        request=wrong_hook_request,
        selected_option_id="world_eaters:blessings:unbridled_bloodlust",
    )
    assert not army_rule.apply_blessings_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_hook_request,
            result=wrong_hook_result,
        )
    )

    actorless_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id=None,
        payload=validate_json_value({"hook_id": army_rule.HOOK_ID}),
        options=options,
    )
    actorless_result = DecisionResult.for_request(
        result_id="phase17g-world-eaters-no-actor",
        request=actorless_request,
        selected_option_id="world_eaters:blessings:unbridled_bloodlust",
    )
    with pytest.raises(GameLifecycleError, match="selection requires an actor"):
        army_rule.apply_blessings_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=actorless_request,
                result=actorless_result,
            )
        )

    non_world_eaters_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id="player-b",
        payload=validate_json_value({"hook_id": army_rule.HOOK_ID}),
        options=options,
    )
    non_world_eaters_result = DecisionResult.for_request(
        result_id="phase17g-world-eaters-wrong-actor",
        request=non_world_eaters_request,
        selected_option_id="world_eaters:blessings:unbridled_bloodlust",
    )
    with pytest.raises(GameLifecycleError, match="actor does not own World Eaters"):
        army_rule.apply_blessings_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=non_world_eaters_request,
                result=non_world_eaters_result,
            )
        )

    _record_active_blessings(
        state,
        blessings=(army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,),
    )
    duplicate_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"hook_id": army_rule.HOOK_ID}),
        options=options,
    )
    duplicate_result = DecisionResult.for_request(
        result_id="phase17g-world-eaters-duplicate-selection",
        request=duplicate_request,
        selected_option_id="world_eaters:blessings:unbridled_bloodlust",
    )
    with pytest.raises(GameLifecycleError, match="already recorded"):
        army_rule.apply_blessings_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=duplicate_request,
                result=duplicate_result,
            )
        )


def test_blessings_options_require_matching_disjoint_dice() -> None:
    no_warp_options = army_rule.blessings_selection_options(
        player_id="player-a",
        battle_round=1,
        dice_values=(5, 6, 1, 1, 1, 1, 1, 1),
        bloodshed_points=0,
    )
    assert all("warp_blades" not in option.option_id for option in no_warp_options)

    options = army_rule.blessings_selection_options(
        player_id="player-a",
        battle_round=1,
        dice_values=(6, 6, 5, 5, 2, 2, 1, 1),
        bloodshed_points=0,
    )
    option = next(
        item
        for item in options
        if item.option_id == "world_eaters:blessings:warp_blades+decapitating_strikes"
    )
    payload = cast(dict[str, JsonValue], option.payload)
    consumed = cast(dict[str, JsonValue], payload["consumed_dice_by_blessing_id"])
    assert consumed["warp_blades"] == [2, 3]
    assert consumed["decapitating_strikes"] == [0, 1]


def test_battle_round_start_hook_registry_validates_and_dispatches() -> None:
    state = _battle_ready_state()
    decisions = DecisionController()
    context = BattleRoundStartRequestContext(state=state, decisions=decisions)
    request = _dummy_battle_round_request(state)

    request_binding = BattleRoundStartHookBinding(
        hook_id="phase17g-test:request",
        source_id="phase17g-test:source",
        request_handler=lambda _context: request,
    )
    no_request_binding = BattleRoundStartHookBinding(
        hook_id="phase17g-test:no-request",
        source_id="phase17g-test:source",
        result_handler=lambda _context: False,
    )
    registry = BattleRoundStartHookRegistry.from_bindings((request_binding, no_request_binding))

    assert BattleRoundStartHookRegistry.empty().all_bindings() == ()
    assert registry.all_bindings() == (no_request_binding, request_binding)
    assert registry.next_request_for(context) == request
    assert (
        BattleRoundStartHookRegistry.from_bindings((no_request_binding,)).next_request_for(context)
        is None
    )

    result = DecisionResult.for_request(
        result_id="phase17g-battle-round-hooks-result",
        request=request,
        selected_option_id="phase17g-battle-round-hooks-option",
    )
    result_context = BattleRoundStartResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )

    def _bad_request_handler(_context: BattleRoundStartRequestContext) -> DecisionRequest | None:
        return cast(DecisionRequest, object())

    def _bad_result_handler(_context: BattleRoundStartResultContext) -> bool:
        return cast(bool, "handled")

    result_registry = BattleRoundStartHookRegistry.from_bindings(
        (
            BattleRoundStartHookBinding(
                hook_id="phase17g-test:false-result",
                source_id="phase17g-test:source",
                result_handler=lambda _context: False,
            ),
            BattleRoundStartHookBinding(
                hook_id="phase17g-test:true-result",
                source_id="phase17g-test:source",
                result_handler=lambda _context: True,
            ),
        )
    )

    assert result_registry.apply_result(result_context)
    assert not BattleRoundStartHookRegistry.from_bindings((request_binding,)).apply_result(
        result_context
    )

    with pytest.raises(GameLifecycleError, match="request hooks require a context"):
        registry.next_request_for(cast(BattleRoundStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="result hooks require a context"):
        registry.apply_result(cast(BattleRoundStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="return DecisionRequest or None"):
        BattleRoundStartHookRegistry.from_bindings(
            (
                BattleRoundStartHookBinding(
                    hook_id="phase17g-test:bad-request",
                    source_id="phase17g-test:source",
                    request_handler=_bad_request_handler,
                ),
            )
        ).next_request_for(context)
    with pytest.raises(GameLifecycleError, match="multiple simultaneous requests"):
        BattleRoundStartHookRegistry.from_bindings(
            (
                request_binding,
                BattleRoundStartHookBinding(
                    hook_id="phase17g-test:request-two",
                    source_id="phase17g-test:source",
                    request_handler=lambda _context: request,
                ),
            )
        ).next_request_for(context)
    with pytest.raises(GameLifecycleError, match="result handlers must return bool"):
        BattleRoundStartHookRegistry.from_bindings(
            (
                BattleRoundStartHookBinding(
                    hook_id="phase17g-test:bad-result",
                    source_id="phase17g-test:source",
                    result_handler=_bad_result_handler,
                ),
            )
        ).apply_result(result_context)
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        BattleRoundStartHookRegistry.from_bindings(
            (
                BattleRoundStartHookBinding(
                    hook_id="phase17g-test:true-one",
                    source_id="phase17g-test:source",
                    result_handler=lambda _context: True,
                ),
                BattleRoundStartHookBinding(
                    hook_id="phase17g-test:true-two",
                    source_id="phase17g-test:source",
                    result_handler=lambda _context: True,
                ),
            )
        ).apply_result(result_context)


def test_battle_round_start_hook_dataclasses_reject_malformed_inputs() -> None:
    state = _battle_ready_state()
    decisions = DecisionController()
    request = _dummy_battle_round_request(state)
    result = DecisionResult.for_request(
        result_id="phase17g-battle-round-hooks-malformed-result",
        request=request,
        selected_option_id="phase17g-battle-round-hooks-option",
    )

    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        BattleRoundStartRequestContext(
            state=cast(GameState, object()),
            decisions=decisions,
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        BattleRoundStartRequestContext(
            state=state,
            decisions=cast(DecisionController, object()),
        )
    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        BattleRoundStartResultContext(
            state=cast(GameState, object()),
            decisions=decisions,
            request=request,
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        BattleRoundStartResultContext(
            state=state,
            decisions=cast(DecisionController, object()),
            request=request,
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="request must be DecisionRequest"):
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=cast(DecisionRequest, object()),
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="result must be DecisionResult"):
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=cast(DecisionResult, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires a handler"):
        BattleRoundStartHookBinding(hook_id="phase17g-test:empty", source_id="source")
    with pytest.raises(GameLifecycleError, match="hook_id must be a string"):
        BattleRoundStartHookBinding(
            hook_id=cast(str, object()),
            source_id="source",
            request_handler=lambda _context: None,
        )
    with pytest.raises(GameLifecycleError, match="source_id must not be empty"):
        BattleRoundStartHookBinding(
            hook_id="phase17g-test:blank-source",
            source_id=" ",
            request_handler=lambda _context: None,
        )
    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        BattleRoundStartHookBinding(
            hook_id="phase17g-test:bad-request-handler",
            source_id="source",
            request_handler=cast(
                Callable[[BattleRoundStartRequestContext], DecisionRequest | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        BattleRoundStartHookBinding(
            hook_id="phase17g-test:bad-result-handler",
            source_id="source",
            result_handler=cast(Callable[[BattleRoundStartResultContext], bool], object()),
        )

    valid_binding = BattleRoundStartHookBinding(
        hook_id="phase17g-test:valid",
        source_id="source",
        request_handler=lambda _context: None,
    )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        BattleRoundStartHookRegistry(
            bindings=cast(tuple[BattleRoundStartHookBinding, ...], [valid_binding])
        )
    with pytest.raises(GameLifecycleError, match="must contain BattleRoundStartHookBinding"):
        BattleRoundStartHookRegistry(
            bindings=cast(tuple[BattleRoundStartHookBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        BattleRoundStartHookRegistry(
            bindings=(
                valid_binding,
                BattleRoundStartHookBinding(
                    hook_id="phase17g-test:valid",
                    source_id="source-two",
                    request_handler=lambda _context: None,
                ),
            )
        )


def test_battle_round_start_context_requires_start_of_first_turn() -> None:
    decisions = DecisionController()

    setup_state = _cloned_battle_ready_state()
    setup_state.stage = GameLifecycleStage.SETUP
    with pytest.raises(GameLifecycleError, match="require battle stage"):
        BattleRoundStartRequestContext(state=setup_state, decisions=decisions)

    movement_state = _state_at_phase(_battle_ready_state(), BattlePhase.MOVEMENT)
    with pytest.raises(GameLifecycleError, match="require Command phase"):
        BattleRoundStartRequestContext(state=movement_state, decisions=decisions)

    later_command_state = _cloned_battle_ready_state()
    later_command_state.battle_phase_sequence = (BattlePhase.MOVEMENT, BattlePhase.COMMAND)
    later_command_state.battle_phase_index = 1
    with pytest.raises(GameLifecycleError, match="require first battle phase"):
        BattleRoundStartRequestContext(state=later_command_state, decisions=decisions)

    no_turn_order_state = _cloned_battle_ready_state()
    no_turn_order_state.turn_order = ()
    with pytest.raises(GameLifecycleError, match="require turn order"):
        BattleRoundStartRequestContext(state=no_turn_order_state, decisions=decisions)

    wrong_active_state = _cloned_battle_ready_state()
    wrong_active_state.active_player_id = "player-b"
    with pytest.raises(GameLifecycleError, match="require first player turn"):
        BattleRoundStartRequestContext(state=wrong_active_state, decisions=decisions)


def test_unbridled_bloodlust_charge_modifier_uses_runtime_registry() -> None:
    state = _battle_ready_state()
    _record_active_blessings(
        state,
        blessings=(army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,),
    )
    registry = RuntimeModifierRegistry.from_bindings(
        charge_roll_modifier_bindings=(
            army_rule.runtime_contribution().charge_roll_modifier_bindings
        ),
    )

    modifiers = registry.charge_roll_modifiers(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=WORLD_EATERS_UNIT_ID,
            current_roll_modifiers=(),
        )
    )

    assert len(modifiers) == 1
    assert modifiers[0].source_id == army_rule.SOURCE_RULE_ID
    assert modifiers[0].operand == 1

    assert (
        army_rule.unbridled_bloodlust_charge_roll_modifier(
            ChargeRollModifierContext(
                state=state,
                unit_instance_id=WORLD_EATERS_UNIT_ID,
                current_roll_modifiers=modifiers,
            )
        )
        == modifiers
    )


def test_unbridled_bloodlust_charge_modifier_reaches_charge_phase_consumer() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    _record_active_blessings(
        state,
        blessings=(army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,),
    )
    state.replace_battlefield_state(
        _battlefield_with_unit_origins(
            state,
            world_eaters_origin=Pose.at(10.0, 20.0),
            enemy_origin=Pose.at(24.0, 20.0, facing_degrees=180.0),
        )
    )
    charge_state = _state_at_phase(state, BattlePhase.CHARGE)
    bundle = _runtime_content_bundle(lifecycle)
    decisions = DecisionController()
    handler = ChargePhaseHandler(
        ruleset_descriptor=_world_eaters_config().ruleset_descriptor,
        ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )

    status = handler.begin_phase(state=charge_state, decisions=decisions)
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert WORLD_EATERS_UNIT_ID in {option.option_id for option in request.options}
    result = DecisionResult.for_request(
        result_id="phase17g-world-eaters-charge-consumer",
        request=request,
        selected_option_id=WORLD_EATERS_UNIT_ID,
    )
    decisions.submit_result(result)

    handler.apply_decision(state=charge_state, result=result, decisions=decisions)
    roll_result = _charge_roll_result_from_event(decisions, "charge_roll_resolved")

    assert [modifier.operand for modifier in roll_result.request.roll_modifiers] == [1]
    assert [modifier.source_id for modifier in roll_result.request.roll_modifiers] == [
        army_rule.SOURCE_RULE_ID
    ]


def test_blessings_weapon_profile_modifier_adds_melee_keywords() -> None:
    state = _battle_ready_state()
    _record_active_blessings(
        state,
        blessings=(
            army_rule.BlessingOfKhorne.MARTIAL_EXCELLENCE,
            army_rule.BlessingOfKhorne.WARP_BLADES,
            army_rule.BlessingOfKhorne.DECAPITATING_STRIKES,
        ),
    )
    attacking_unit = _unit_by_id(state, WORLD_EATERS_UNIT_ID)
    registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=(
            army_rule.runtime_contribution().weapon_profile_modifier_bindings
        ),
    )

    profile = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=WORLD_EATERS_UNIT_ID,
            attacker_model_instance_id=attacking_unit.own_models[0].model_instance_id,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_melee_profile(),
        )
    )

    assert WeaponKeyword.SUSTAINED_HITS in profile.keywords
    assert WeaponKeyword.LETHAL_HITS in profile.keywords
    assert WeaponKeyword.DEVASTATING_WOUNDS in profile.keywords
    assert {ability.ability_kind.value for ability in profile.abilities} == {
        "devastating_wounds",
        "lethal_hits",
        "sustained_hits",
    }

    command_profile = army_rule.blessings_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.COMMAND,
            attacking_unit_instance_id=WORLD_EATERS_UNIT_ID,
            attacker_model_instance_id=attacking_unit.own_models[0].model_instance_id,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_melee_profile(),
        )
    )
    assert command_profile == _melee_profile()

    ranged_profile = replace(_melee_profile(), range_profile=RangeProfile.distance(12))
    assert (
        army_rule.blessings_weapon_profile_modifier(
            WeaponProfileModifierContext(
                state=state,
                source_phase=BattlePhase.FIGHT,
                attacking_unit_instance_id=WORLD_EATERS_UNIT_ID,
                attacker_model_instance_id=attacking_unit.own_models[0].model_instance_id,
                target_unit_instance_id=ENEMY_UNIT_ID,
                weapon_profile=ranged_profile,
            )
        )
        == ranged_profile
    )

    assert army_rule.active_blessings_for_unit(state, unit_instance_id=ENEMY_UNIT_ID) == ()


def test_blessings_weapon_profile_modifier_reaches_melee_sequence_consumer() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture()
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
            ),
        ),
    )
    state = _world_eaters_state_for_melee_fixture(
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    _record_active_blessings(
        state,
        blessings=(
            army_rule.BlessingOfKhorne.MARTIAL_EXCELLENCE,
            army_rule.BlessingOfKhorne.WARP_BLADES,
        ),
        unit_instance_id=attacker.unit_instance_id,
    )
    registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=(
            army_rule.runtime_contribution().weapon_profile_modifier_bindings
        ),
    )

    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase17g-world-eaters-melee-sequence"),
        sequence_id="phase17g-world-eaters-melee-sequence",
        state=state,
        runtime_modifier_registry=registry,
    )
    profile = sequence.attack_pools[0].weapon_profile

    assert WeaponKeyword.SUSTAINED_HITS in profile.keywords
    assert WeaponKeyword.LETHAL_HITS in profile.keywords
    assert {ability.ability_kind.value for ability in profile.abilities} >= {
        "lethal_hits",
        "sustained_hits",
    }


def test_icon_of_khorne_bloodshed_points_require_live_bearer() -> None:
    live_state = _battle_ready_state()
    live_decisions = DecisionController()
    _destroy_enemy_unit(
        state=live_state,
        decisions=live_decisions,
        attacking_unit_id=WORLD_EATERS_UNIT_ID,
    )

    assert (
        army_rule.bloodshed_points_available(
            live_state,
            event_log=live_decisions.event_log,
            player_id="player-a",
        )
        == 1
    )

    destroyed_state = _battle_ready_state()
    destroyed_decisions = DecisionController()
    icon_bearer_id = _icon_bearer_model_id(destroyed_state)
    _remove_models(destroyed_state, (icon_bearer_id,))
    _append_model_destroyed_event(
        state=destroyed_state,
        decisions=destroyed_decisions,
        destroying_player_id="player-b",
        attacking_unit_id=ENEMY_UNIT_ID,
        target_unit_id=WORLD_EATERS_UNIT_ID,
        model_instance_id=icon_bearer_id,
        event_suffix="icon-bearer",
    )
    _destroy_enemy_unit(
        state=destroyed_state,
        decisions=destroyed_decisions,
        attacking_unit_id=WORLD_EATERS_UNIT_ID,
    )

    assert (
        army_rule.bloodshed_points_available(
            destroyed_state,
            event_log=destroyed_decisions.event_log,
            player_id="player-a",
        )
        == 0
    )


def test_bloodshed_points_add_blessings_roll_dice() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    _destroy_enemy_unit(
        state=state,
        decisions=lifecycle.decision_controller,
        attacking_unit_id=WORLD_EATERS_UNIT_ID,
    )

    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["bloodshed_points_spent"] == 1
    assert len(cast(list[JsonValue], payload["dice_values"])) == 9


def test_bloodshed_points_require_world_eaters_and_battlefield() -> None:
    state = _battle_ready_state()

    assert (
        army_rule.bloodshed_points_available(
            state,
            event_log=DecisionController().event_log,
            player_id="player-b",
        )
        == 0
    )

    state_without_battlefield = _cloned_battle_ready_state()
    state_without_battlefield.battlefield_state = None
    assert (
        army_rule.bloodshed_points_available(
            state_without_battlefield,
            event_log=DecisionController().event_log,
            player_id="player-a",
        )
        == 0
    )


def test_total_carnage_selection_registers_optional_triggered_fight_on_death() -> None:
    state = _battle_ready_state()
    decisions = DecisionController()
    options = army_rule.blessings_selection_options(
        player_id="player-a",
        battle_round=state.battle_round,
        dice_values=(3, 3, 1, 1, 1, 1, 1, 1),
        bloodshed_points=0,
    )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"hook_id": army_rule.HOOK_ID}),
        options=options,
    )
    result = DecisionResult.for_request(
        result_id="phase17g-total-carnage-result",
        request=request,
        selected_option_id="world_eaters:blessings:total_carnage",
    )

    handled = army_rule.apply_blessings_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert handled
    assert army_rule.active_blessings_for_player(state, player_id="player-a") == (
        army_rule.BlessingOfKhorne.TOTAL_CARNAGE,
    )
    unit = _unit_by_id(state, WORLD_EATERS_UNIT_ID)
    for model in unit.alive_own_models():
        sources = state.destruction_reaction_sources_for_model(
            model_instance_id=model.model_instance_id
        )
        assert len(sources) == 1
        source = sources[0]
        assert source.optional
        assert source.source_id.startswith(army_rule.TOTAL_CARNAGE_HOOK_ID)
        payload = cast(dict[str, JsonValue], source.payload)
        assert payload["trigger_roll_threshold"] == army_rule.TOTAL_CARNAGE_TRIGGER_THRESHOLD
        assert payload["requires_destroyed_by_melee_attack"] is True
        assert payload["requires_not_fought_this_phase"] is True


def test_world_eaters_army_rule_fail_fast_edges_are_explicit() -> None:
    state = _battle_ready_state()

    with pytest.raises(GameLifecycleError, match="dice recipe count must be positive"):
        army_rule.DiceRecipe(count=0, min_value=1)
    with pytest.raises(GameLifecycleError, match="dice recipe min_value must be 1-6"):
        army_rule.DiceRecipe(count=1, min_value=7)
    with pytest.raises(GameLifecycleError, match="definition blessing drift"):
        army_rule.BlessingDefinition(
            blessing=cast(army_rule.BlessingOfKhorne, "unbridled_bloodlust"),
            label="Unbridled Bloodlust",
            recipes=(army_rule.DiceRecipe(count=2, min_value=1),),
            effect_summary="summary",
        )
    with pytest.raises(GameLifecycleError, match="definition label must be non-empty"):
        army_rule.BlessingDefinition(
            blessing=army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,
            label=" ",
            recipes=(army_rule.DiceRecipe(count=2, min_value=1),),
            effect_summary="summary",
        )
    with pytest.raises(GameLifecycleError, match="definition requires recipes"):
        army_rule.BlessingDefinition(
            blessing=army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,
            label="Unbridled Bloodlust",
            recipes=(),
            effect_summary="summary",
        )
    with pytest.raises(GameLifecycleError, match="recipes must be DiceRecipe"):
        army_rule.BlessingDefinition(
            blessing=army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,
            label="Unbridled Bloodlust",
            recipes=cast(tuple[army_rule.DiceRecipe, ...], (object(),)),
            effect_summary="summary",
        )
    with pytest.raises(GameLifecycleError, match="effect summary must be non-empty"):
        army_rule.BlessingDefinition(
            blessing=army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,
            label="Unbridled Bloodlust",
            recipes=(army_rule.DiceRecipe(count=2, min_value=1),),
            effect_summary=" ",
        )
    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.blessings_selection_request(cast(BattleRoundStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_blessings_selection_result(cast(BattleRoundStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        army_rule.unbridled_bloodlust_charge_roll_modifier(
            cast(ChargeRollModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="requires context"):
        army_rule.blessings_weapon_profile_modifier(cast(WeaponProfileModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        army_rule.active_blessings_for_player(cast(GameState, object()), player_id="player-a")
    with pytest.raises(GameLifecycleError, match="requires EventLog"):
        army_rule.bloodshed_points_available(
            state,
            event_log=cast(EventLog, object()),
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id was not found"):
        army_rule.unit_has_active_blessing(
            state,
            unit_instance_id="missing-unit",
            blessing=army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,
        )
    with pytest.raises(GameLifecycleError, match="options require positive battle_round"):
        army_rule.blessings_selection_options(
            player_id="player-a",
            battle_round=0,
            dice_values=(1, 1, 1, 1, 1, 1, 1, 1),
            bloodshed_points=0,
        )
    with pytest.raises(GameLifecycleError, match="bloodshed_points must be non-negative"):
        army_rule.blessings_selection_options(
            player_id="player-a",
            battle_round=1,
            dice_values=(1, 1, 1, 1, 1, 1, 1, 1),
            bloodshed_points=-1,
        )


def test_active_blessing_lookup_rejects_duplicate_active_effects() -> None:
    state = _battle_ready_state()
    _record_active_blessings(
        state,
        blessings=(army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST,),
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{army_rule.HOOK_ID}:player-a:round-01:duplicate-active-blessings",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=(WORLD_EATERS_UNIT_ID,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=validate_json_value(
                {
                    "effect_kind": army_rule.BLESSINGS_OF_KHORNE_EFFECT_KIND,
                    "battle_round": state.battle_round,
                    "selected_blessing_ids": [army_rule.BlessingOfKhorne.TOTAL_CARNAGE.value],
                }
            ),
        )
    )

    with pytest.raises(GameLifecycleError, match="multiple active effects"):
        army_rule.active_blessings_for_player(state, player_id="player-a")


def _world_eaters_config() -> GameConfig:
    catalog = _world_eaters_catalog()
    return GameConfig(
        game_id="phase17g-world-eaters-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-world-eaters-test",
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
                    faction_id=army_rule.WORLD_EATERS_FACTION_ID,
                    detachment_ids=("berzerker-warband",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="berzerkers",
                        datasheet_id=WORLD_EATERS_DATASHEET_ID,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                        wargear_selections=(
                            WargearSelection(
                                option_id=ICON_OF_KHORNE_OPTION_ID,
                                model_profile_id="core-intercessor-like",
                                wargear_ids=(ICON_OF_KHORNE_WARGEAR_ID,),
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
        mission_setup=_mission_setup(),
    )


def _world_eaters_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, _world_eaters_datasheet(base_datasheet)),
        wargear=(
            *base_catalog.wargear,
            Wargear(
                wargear_id=ICON_OF_KHORNE_WARGEAR_ID,
                name="Icon of Khorne",
                source_ids=(army_rule.ICON_OF_KHORNE_RULE_UPDATE_SOURCE,),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.WORLD_EATERS_FACTION_ID,
                name="World Eaters",
                faction_keywords=("World Eaters",),
                source_ids=("gw-11e-world-eaters-faction-pack-2026-06:faction:world-eaters",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="berzerker-warband",
                name="Berzerker Warband",
                faction_id=army_rule.WORLD_EATERS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(WORLD_EATERS_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-world-eaters-faction-pack-2026-06:detachment:berzerker-warband",
                ),
            ),
        ),
    )


def _world_eaters_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=WORLD_EATERS_DATASHEET_ID,
        name="Khorne Berzerkers",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Battleline"),
            faction_keywords=("World Eaters",),
        ),
        wargear_options=(
            *base_datasheet.wargear_options,
            DatasheetWargearOption(
                option_id=ICON_OF_KHORNE_OPTION_ID,
                model_profile_id="core-intercessor-like",
                default_wargear_ids=(),
                allowed_wargear_ids=(ICON_OF_KHORNE_WARGEAR_ID,),
                max_selections=1,
                source_ids=(army_rule.ICON_OF_KHORNE_RULE_UPDATE_SOURCE,),
                effects=(
                    DatasheetWargearOptionEffect(
                        kind=WargearOptionEffectKind.ADD_WARGEAR,
                        wargear_id=ICON_OF_KHORNE_WARGEAR_ID,
                        model_count=1,
                        wargear_count=1,
                    ),
                ),
            ),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:world-eaters:khorne-berzerkers",),
    )


def _battle_ready_lifecycle() -> GameLifecycle:
    config = _world_eaters_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-world-eaters-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(state=state, config=config)
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _battle_ready_state() -> GameState:
    return _require_state(_battle_ready_lifecycle())


def _cloned_battle_ready_state() -> GameState:
    return GameState.from_payload(_battle_ready_state().to_payload())


def _dummy_battle_round_request(state: GameState) -> DecisionRequest:
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"hook_id": "phase17g-test:dummy-battle-round-hook"}),
        options=(
            DecisionOption(
                option_id="phase17g-battle-round-hooks-option",
                label="Dummy Battle Round Hook",
                payload=validate_json_value({"selected": True}),
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _record_active_blessings(
    state: GameState,
    *,
    blessings: tuple[army_rule.BlessingOfKhorne, ...],
    unit_instance_id: str = WORLD_EATERS_UNIT_ID,
    player_id: str = "player-a",
) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{army_rule.HOOK_ID}:{player_id}:round-01:test-active-blessings",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id=player_id,
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=validate_json_value(
                {
                    "effect_kind": army_rule.BLESSINGS_OF_KHORNE_EFFECT_KIND,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "player_id": player_id,
                    "faction_id": army_rule.WORLD_EATERS_FACTION_ID,
                    "source_rule_id": army_rule.SOURCE_RULE_ID,
                    "hook_id": army_rule.HOOK_ID,
                    "selected_blessing_ids": [blessing.value for blessing in blessings],
                    "selected_blessing_labels": _blessing_labels(blessings),
                    "selected_option_id": "phase17g-test",
                    "request_id": "phase17g-test-request",
                    "result_id": "phase17g-test-result",
                    "dice_values": [6, 6, 5, 5, 4, 4, 3, 3],
                    "consumed_dice_by_blessing_id": {},
                    "bloodshed_points_spent": 0,
                    "rules_update_sources": [army_rule.UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE],
                }
            ),
        )
    )


def _world_eaters_state_for_melee_fixture(
    *,
    ruleset: RulesetDescriptor,
    scenario: BattlefieldScenario,
    attacker: UnitInstance,
) -> GameState:
    world_eaters_attacker = replace(
        attacker,
        faction_keywords=(army_rule.WORLD_EATERS_FACTION_KEYWORD,),
    )
    armies = (
        replace(scenario.armies[0], units=(world_eaters_attacker,)),
        scenario.armies[1],
    )
    return GameState(
        game_id="phase17g-world-eaters-melee-state",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(ruleset.battle_phase_sequence.phases).index(BattlePhase.FIGHT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=list(armies),
        battlefield_state=scenario.battlefield_state,
    )


def _melee_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-world-eaters-chainblade",
        name="Chainblade",
        range_profile=RangeProfile.melee(),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
    )


def _destroy_enemy_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    attacking_unit_id: str,
) -> None:
    enemy = _unit_by_id(state, ENEMY_UNIT_ID)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy.own_models)
    _remove_models(state, destroyed_model_ids)
    for index, model_id in enumerate(destroyed_model_ids, start=1):
        _append_model_destroyed_event(
            state=state,
            decisions=decisions,
            destroying_player_id="player-a",
            attacking_unit_id=attacking_unit_id,
            target_unit_id=ENEMY_UNIT_ID,
            model_instance_id=model_id,
            event_suffix=f"enemy-{index:02d}",
        )


def _append_model_destroyed_event(
    *,
    state: GameState,
    decisions: DecisionController,
    destroying_player_id: str,
    attacking_unit_id: str,
    target_unit_id: str,
    model_instance_id: str,
    event_suffix: str,
) -> None:
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires battle phase")
    decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": phase.value,
            "destroying_player_id": destroying_player_id,
            "attacking_unit_instance_id": attacking_unit_id,
            "target_unit_instance_id": target_unit_id,
            "model_instance_id": model_instance_id,
            "damage_kind": "normal",
            "damage_event_id": f"phase17g-world-eaters-damage-{event_suffix}",
            "destroyed_model_rules_triggered": True,
        },
    )


def _remove_models(state: GameState, model_instance_ids: tuple[str, ...]) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield")
    state.replace_battlefield_state(state.battlefield_state.with_removed_models(model_instance_ids))


def _state_at_phase(state: GameState, phase: BattlePhase) -> GameState:
    phase_state = GameState.from_payload(state.to_payload())
    while phase_state.current_battle_phase is not phase:
        if phase_state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        phase_state.advance_to_next_battle_phase()
    return phase_state


def _battlefield_with_unit_origins(
    state: GameState,
    *,
    world_eaters_origin: Pose,
    enemy_origin: Pose,
) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield")
    battlefield = state.battlefield_state
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            unit=_unit_by_id(state, WORLD_EATERS_UNIT_ID),
            player_id="player-a",
            origin=world_eaters_origin,
        )
    )
    return battlefield.with_unit_placement(
        _unit_placement_at(
            unit=_unit_by_id(state, ENEMY_UNIT_ID),
            player_id="player-b",
            origin=enemy_origin,
        )
    )


def _unit_placement_at(
    *,
    unit: UnitInstance,
    player_id: str,
    origin: Pose,
) -> UnitPlacement:
    army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(
                unit.own_models,
                _compact_unit_poses(origin=origin, model_count=len(unit.own_models)),
                strict=True,
            )
        ),
    )


def _compact_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _charge_roll_result_from_event(
    decisions: DecisionController,
    event_type: str,
) -> ChargeRollResult:
    for event in reversed(decisions.event_log.records):
        if event.event_type != event_type:
            continue
        payload = cast(dict[str, object], event.payload)
        return ChargeRollResult.from_payload(cast(ChargeRollResultPayload, payload["roll_result"]))
    raise AssertionError(f"missing event type {event_type}")


def _icon_bearer_model_id(state: GameState) -> str:
    unit = _unit_by_id(state, WORLD_EATERS_UNIT_ID)
    for model in unit.own_models:
        if ICON_OF_KHORNE_WARGEAR_ID in model.wargear_ids:
            return model.model_instance_id
    raise AssertionError("test unit requires Icon of Khorne bearer")


def _blessing_labels(
    blessings: tuple[army_rule.BlessingOfKhorne, ...],
) -> list[str]:
    return [
        blessing.value.replace("_", " ").title().replace("Fuelled", "fuelled")
        for blessing in blessings
    ]


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _require_state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    if state is None:
        raise AssertionError("lifecycle must be started")
    return state


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()
