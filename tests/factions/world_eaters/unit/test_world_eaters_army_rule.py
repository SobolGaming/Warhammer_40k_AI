from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.factions.world_eaters.world_eaters_helpers import (
    ENEMY_UNIT_ID,
    WORLD_EATERS_UNIT_ID,
    _advance_to_player_b_fight,
    _attack_pool_for_world_eaters_test,
    _battle_ready_lifecycle,
    _battle_ready_state,
    _battlefield_with_unit_origins,
    _charge_roll_result_from_event,
    _cloned_battle_ready_state,
    _dummy_battle_round_request,
    _event_payloads,
    _fixed_roll_result,
    _melee_profile,
    _record_active_blessings,
    _record_total_carnage_selection,
    _remove_models,
    _require_state,
    _runtime_content_bundle,
    _state_at_phase,
    _unit_by_id,
    _world_eaters_config,
    _world_eaters_state_for_melee_fixture,
)
from tests.phase15d_fight_resolution_helpers import (
    melee_fixture,
    melee_proposal,
    melee_request,
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import (
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.damage_allocation import SELECT_DESTRUCTION_REACTION_DECISION_TYPE
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule,
)
from warhammer40k_core.engine.fight_resolution import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    melee_attack_sequence_from_proposal,
)
from warhammer40k_core.engine.game_state import (
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.phases.charge import (
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargePhaseHandler,
)
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.geometry.pose import Pose


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


def test_battle_round_start_hook_registry_discovers_before_rolling_or_allocating() -> None:
    state = _battle_ready_state()
    decisions = DecisionController()
    context = BattleRoundStartRequestContext(state=state, decisions=decisions)
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )
    before = (state.to_payload(), decisions.to_payload())
    candidates = registry.candidates_for(context)
    assert len(candidates) == 1
    assert candidates[0].participant.player_id == "player-a"
    assert (state.to_payload(), decisions.to_payload()) == before
    request = registry.next_request_for(context)
    assert request is not None
    assert request.actor_id == "player-a"
    assert (
        len([event for event in decisions.event_log.records if event.event_type == "dice_rolled"])
        == 1
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="order36-blessings-result",
        request=request,
        selected_option_id="world_eaters:blessings:none",
    )
    decisions.submit_result(result)
    assert registry.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    assert registry.next_request_for(context) is None
    assert (
        len([event for event in decisions.event_log.records if event.event_type == "dice_rolled"])
        == 1
    )
    with pytest.raises(GameLifecycleError, match="request hooks require a context"):
        registry.next_request_for(cast(BattleRoundStartRequestContext, object()))


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
    handler.begin_phase(state=charge_state, decisions=decisions)
    roll_result = _charge_roll_result_from_event(decisions, "charge_roll_resolved")

    assert [modifier.operand for modifier in roll_result.request.roll_modifiers] == [1]
    assert [modifier.source_id for modifier in roll_result.request.roll_modifiers] == [
        army_rule.SOURCE_RULE_ID
    ]

    assert roll_result.value == roll_result.roll_state.current_total + 1
    assert roll_result.movement_budget.maximum_distance_inches == float(roll_result.value)


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
    catalog, ruleset, scenario, attacker, target_a, _target_b = melee_fixture()
    request = melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = melee_proposal(
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

    decisions = DecisionController()
    one_attack = AttackSequence.start(
        sequence_id="world-eaters-blessings-observable-hit",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        source_phase=BattlePhase.FIGHT,
        attack_pools=(replace(sequence.attack_pools[0], attacks=1),),
    )
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=profile.profile_id,
        attack_context_id=f"{one_attack.sequence_id}:pool-001:attack-001",
        attacker_player_id="player-a",
    )
    remaining, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset,
        attack_sequence=one_attack,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "world-eaters-blessings-observable-hit",
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="world-eaters-critical-hit", spec=hit_spec, value=6),
            ),
        ),
        runtime_modifier_registry=registry,
    )
    steps = _event_payloads(decisions, "attack_sequence_step")
    hit_steps = [step for step in steps if step["step"] == "hit"]
    assert hit_steps
    hit = cast(dict[str, JsonValue], hit_steps[0]["payload"])
    assert hit["critical"] is True
    assert hit["generated_hits"] == 2
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_lethal_hit_wound"
    assert {option.option_id for option in status.decision_request.options} == {
        "auto-wound",
        "roll-to-wound",
    }
    assert not any(step["step"] == "wound" for step in steps)


def test_total_carnage_selection_registers_optional_triggered_fight_on_death() -> None:
    state = _battle_ready_state()
    decisions = DecisionController()
    _record_total_carnage_selection(state=state, decisions=decisions)

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
        requirement = cast(dict[str, JsonValue], payload["requires_active_persisting_effect"])
        assert requirement["effect_kind"] == army_rule.BLESSINGS_OF_KHORNE_EFFECT_KIND
        assert requirement["selected_blessing_id"] == army_rule.BlessingOfKhorne.TOTAL_CARNAGE.value


def test_total_carnage_current_round_source_opens_reaction_window() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    decisions = lifecycle.decision_controller
    _record_total_carnage_selection(state=state, decisions=decisions)
    defender = _unit_by_id(state, WORLD_EATERS_UNIT_ID)
    defender_model = defender.own_models[0]
    source = state.destruction_reaction_sources_for_model(
        model_instance_id=defender_model.model_instance_id
    )[0]

    _advance_to_player_b_fight(state, battle_round=1)

    assert state.battle_round == 1
    assert state.active_player_id == "player-b"
    assert state.current_battle_phase is BattlePhase.FIGHT
    _remove_models(
        state,
        tuple(
            model.model_instance_id
            for model in defender.own_models
            if model.model_instance_id != defender_model.model_instance_id
        ),
    )
    attacker = _unit_by_id(state, ENEMY_UNIT_ID)
    weapon_profile = replace(
        _melee_profile(),
        profile_id="phase17g-current-total-carnage-killing-blow",
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        damage_profile=DamageProfile.fixed(defender_model.current_wounds),
    )
    sequence_id = "phase17g-current-total-carnage"
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-b",
        attacking_unit_instance_id=attacker.unit_instance_id,
        source_phase=BattlePhase.FIGHT,
        attack_pools=(
            _attack_pool_for_world_eaters_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-b",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-b",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-a",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    trigger_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Destruction reaction trigger",
        roll_type="world_eaters_total_carnage",
        actor_id="player-a",
    )

    _remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_world_eaters_config().ruleset_descriptor,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase17g-current-total-carnage",
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase17g-current-total-carnage-hit",
                    spec=hit_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase17g-current-total-carnage-wound",
                    spec=wound_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase17g-current-total-carnage-save",
                    spec=save_spec,
                    value=1,
                ),
                _fixed_roll_result(
                    roll_id="phase17g-current-total-carnage-trigger",
                    spec=trigger_spec,
                    value=army_rule.TOTAL_CARNAGE_TRIGGER_THRESHOLD,
                ),
            ),
        ),
    )

    assert allocated_ids == (defender_model.model_instance_id,)
    assert status is not None
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} >= {source.source_id}
    rolled = _event_payloads(decisions, "fight_on_death_retention_trigger_resolved")
    opened = _event_payloads(decisions, "fight_on_death_retention_opened")
    assert len(rolled) == 1
    assert len(opened) == 1
    assert rolled[0]["triggered"] is True
    assert rolled[0]["applicable"] is True
    assert cast(dict[str, JsonValue], rolled[0]["source"])["source_id"] == source.source_id
    assert _event_payloads(decisions, "destruction_reaction_trigger_not_applicable") == ()


def test_total_carnage_stale_source_does_not_trigger_after_blessing_expires() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    decisions = lifecycle.decision_controller
    _record_total_carnage_selection(state=state, decisions=decisions)
    defender = _unit_by_id(state, WORLD_EATERS_UNIT_ID)
    defender_model = defender.own_models[0]
    assert state.destruction_reaction_sources_for_model(
        model_instance_id=defender_model.model_instance_id
    )

    _advance_to_player_b_fight(state, battle_round=2)

    assert state.battle_round == 2
    assert state.active_player_id == "player-b"
    assert state.current_battle_phase is BattlePhase.FIGHT
    assert not any(
        effect.source_rule_id == army_rule.SOURCE_RULE_ID for effect in state.persisting_effects
    )
    assert state.destruction_reaction_sources_for_model(
        model_instance_id=defender_model.model_instance_id
    )

    _remove_models(
        state,
        tuple(
            model.model_instance_id
            for model in defender.own_models
            if model.model_instance_id != defender_model.model_instance_id
        ),
    )
    attacker = _unit_by_id(state, ENEMY_UNIT_ID)
    weapon_profile = replace(
        _melee_profile(),
        profile_id="phase17g-stale-total-carnage-killing-blow",
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        damage_profile=DamageProfile.fixed(defender_model.current_wounds),
    )
    sequence_id = "phase17g-stale-total-carnage"
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-b",
        attacking_unit_instance_id=attacker.unit_instance_id,
        source_phase=BattlePhase.FIGHT,
        attack_pools=(
            _attack_pool_for_world_eaters_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-b",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-b",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-a",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_world_eaters_config().ruleset_descriptor,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase17g-stale-total-carnage",
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase17g-stale-total-carnage-hit",
                    spec=hit_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase17g-stale-total-carnage-wound",
                    spec=wound_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase17g-stale-total-carnage-save",
                    spec=save_spec,
                    value=1,
                ),
            ),
        ),
    )

    not_applicable = _event_payloads(decisions, "fight_on_death_retention_trigger_resolved")
    assert remaining_sequence is None
    assert allocated_ids == (defender_model.model_instance_id,)
    assert status is None
    assert decisions.queue.pending_requests == ()
    assert _event_payloads(decisions, "destruction_reaction_trigger_rolled") == ()
    assert _event_payloads(decisions, "destruction_reaction_window_opened") == ()
    assert len(not_applicable) == 1
    assert not_applicable[0]["applicable"] is False
    assert not_applicable[0]["trigger_roll"] is None
    assert not_applicable[0]["triggered"] is False
    selected_source = cast(dict[str, JsonValue], not_applicable[0]["source"])
    descriptor = cast(dict[str, JsonValue], selected_source["payload"])
    assert cast(str, selected_source["source_id"]).startswith(army_rule.TOTAL_CARNAGE_HOOK_ID)
    assert descriptor["battle_round"] == 1


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
    with pytest.raises(GameLifecycleError, match="unit_instance_id is unknown"):
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
