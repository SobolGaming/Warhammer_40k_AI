from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    ruleset,
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DamagedEffectDefinition, DamagedEffectKind
from warhammer40k_core.core.dice import (
    DiceRollResult,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
    army_rule,
)
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    AdvanceRollModifierContext,
    ChargeRollModifierContext,
    MovementBudgetModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def test_battle_round_start_gains_miracle_die_once_for_adepta_army() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    decisions = DecisionController()
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )

    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert request is None
    pool = army_rule.miracle_dice_pool(state, player_id="player-a")
    assert len(pool) == 1
    assert 1 <= pool[0].value <= 6
    assert pool[0].roll_state.original_result.spec.roll_type == (
        army_rule.MIRACLE_DIE_GAIN_ROLL_TYPE
    )
    assert pool[0].roll_state.original_result.spec.reroll_forbidden_rule_ids == (
        army_rule.SOURCE_RULE_ID,
    )
    payload = _last_event_payload(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT)
    assert payload["player_id"] == "player-a"
    assert payload["trigger"] == army_rule.BATTLE_ROUND_START_TRIGGER
    assert _dice_roll_count(decisions) == 1

    second_request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert second_request is None
    assert len(army_rule.miracle_dice_pool(state, player_id="player-a")) == 1
    assert _dice_roll_count(decisions) == 1


def test_battle_round_start_ignores_non_adepta_armies() -> None:
    state = battle_state()
    decisions = DecisionController()
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )

    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert request is None
    assert army_rule.miracle_dice_pool(state, player_id="player-a") == ()
    assert _event_payloads(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT) == ()


def test_destroyed_adepta_sororitas_unit_gains_miracle_die_for_owner() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-b")
    target_unit = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    destroyed_event = _append_destroyed_model_event(
        state=state,
        decisions=decisions,
        destroying_player_id="player-a",
        target_unit=target_unit,
    )
    context = UnitDestroyedContext(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.SHOOTING,
        model_destroyed_event_id=destroyed_event.event_id,
        model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
        destroying_player_id="player-a",
        destroyed_unit_instance_id=target_unit.unit_instance_id,
        destroyed_player_id="player-b",
    )

    army_rule.resolve_adepta_sororitas_unit_destroyed(context)

    pool = army_rule.miracle_dice_pool(state, player_id="player-b")
    assert len(pool) == 1
    assert army_rule.miracle_dice_pool(state, player_id="player-a") == ()
    payload = _last_event_payload(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT)
    assert payload["player_id"] == "player-b"
    assert payload["trigger"] == army_rule.UNIT_DESTROYED_TRIGGER
    source_context = cast(dict[str, JsonValue], payload["source_context"])
    assert source_context["destroyed_unit_instance_id"] == target_unit.unit_instance_id
    assert source_context["model_destroyed_event_id"] == destroyed_event.event_id

    army_rule.resolve_adepta_sororitas_unit_destroyed(context)

    assert len(army_rule.miracle_dice_pool(state, player_id="player-b")) == 1


def test_destroyed_non_adepta_unit_in_adepta_army_does_not_gain_miracle_die() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(
        state,
        player_id="player-b",
        faction_keywords=("AGENTS OF THE IMPERIUM",),
    )
    target_unit = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    destroyed_event = _append_destroyed_model_event(
        state=state,
        decisions=decisions,
        destroying_player_id="player-a",
        target_unit=target_unit,
    )

    army_rule.resolve_adepta_sororitas_unit_destroyed(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        )
    )

    assert army_rule.miracle_dice_pool(state, player_id="player-b") == ()
    assert _event_payloads(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT) == ()


def test_miracle_die_pool_spend_and_game_state_payload_round_trip() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    decisions = DecisionController()
    die = army_rule.gain_miracle_die(
        state,
        decisions,
        player_id="player-a",
        trigger=army_rule.BATTLE_ROUND_START_TRIGGER,
        source_id="phase17g-adepta-test:manual-gain",
        source_context={"test": "manual"},
    )
    assert die is not None

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit = _unit_for_player(state, player_id="player-a")
    spent = army_rule.spend_miracle_die(
        state,
        decisions,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        miracle_die_id=die.miracle_die_id,
        source_id="phase17g-adepta-test:manual-spend",
        source_context={"test": "manual"},
    )
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )

    assert spent == die
    assert army_rule.miracle_dice_pool(state, player_id="player-a") == ()
    assert army_rule.miracle_dice_pool(restored, player_id="player-a") == ()
    payload = _last_event_payload(decisions, army_rule.MIRACLE_DIE_SPENT_EVENT)
    miracle_die_payload = cast(dict[str, JsonValue], payload["miracle_die"])
    assert miracle_die_payload["miracle_die_id"] == die.miracle_die_id
    assert payload["phase"] == BattlePhase.SHOOTING.value

    with pytest.raises(GameLifecycleError, match="not available"):
        army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            miracle_die_id=die.miracle_die_id,
            source_id="phase17g-adepta-test:manual-spend-again",
            source_context={"test": "manual"},
        )


def test_triumph_relics_damaged_profile_limits_selection_to_one() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    triumph = _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=6)
    decisions = DecisionController()

    request = _next_triumph_relics_request(state=state, decisions=decisions)

    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["source_unit_instance_id"] == triumph.unit_instance_id
    assert payload["max_selections"] == 1
    assert payload["baseline_max_selections"] == 2
    assert payload["damaged_profile_active"] is True
    for option in request.options:
        option_payload = cast(dict[str, JsonValue], option.payload)
        selected = cast(list[str], option_payload["selected_relic_ids"])
        assert len(selected) <= 1

    _apply_triumph_relics_selection(
        state=state,
        decisions=decisions,
        request=request,
        selected_relics=(army_rule.TriumphRelic.FIERY_HEART,),
    )

    assert army_rule.active_triumph_relics_for_unit(
        state,
        player_id="player-a",
        unit_instance_id=triumph.unit_instance_id,
    ) == (army_rule.TriumphRelic.FIERY_HEART,)
    assert (
        _last_event_payload(decisions, army_rule.TRIUMPH_RELICS_SELECTED_EVENT)[
            "damaged_profile_active"
        ]
        is True
    )


def test_triumph_relics_apply_fiery_heart_and_bloody_rose_modifiers() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    triumph = _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=7)
    target = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    request = _next_triumph_relics_request(state=state, decisions=decisions)
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["max_selections"] == 2
    assert payload["damaged_profile_active"] is False

    _apply_triumph_relics_selection(
        state=state,
        decisions=decisions,
        request=request,
        selected_relics=(
            army_rule.TriumphRelic.FIERY_HEART,
            army_rule.TriumphRelic.PETALS_OF_THE_BLOODY_ROSE,
        ),
    )

    model = triumph.own_models[0]
    moved = army_rule.triumph_fiery_heart_movement_modifier(
        MovementBudgetModifierContext(
            state=state,
            unit_instance_id=triumph.unit_instance_id,
            model_instance_id=model.model_instance_id,
            base_movement_inches=6.0,
            current_movement_inches=6.0,
        )
    )
    charge_modifiers = army_rule.triumph_fiery_heart_charge_modifier(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=triumph.unit_instance_id,
            current_roll_modifiers=(),
        )
    )
    advance_modifiers = army_rule.triumph_fiery_heart_advance_modifier(
        AdvanceRollModifierContext(
            state=state,
            unit_instance_id=triumph.unit_instance_id,
            current_roll_modifiers=(),
        )
    )
    melee_profile = _weapon_profile("triumph-test-melee", melee=True, armor_penetration=0)
    modified_profile = army_rule.triumph_bloody_rose_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=triumph.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=melee_profile,
        )
    )

    assert moved == 8.0
    assert tuple(modifier.operand for modifier in advance_modifiers) == (1,)
    assert tuple(modifier.operand for modifier in charge_modifiers) == (1,)
    assert modified_profile.armor_penetration.final == -1
    assert modified_profile.source_ids != melee_profile.source_ids


def test_triumph_relics_ebon_chalice_raises_acts_limit_and_icon_syncs_fnp() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    triumph = _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=7)
    decisions = DecisionController()
    request = _next_triumph_relics_request(state=state, decisions=decisions)
    _apply_triumph_relics_selection(
        state=state,
        decisions=decisions,
        request=request,
        selected_relics=(
            army_rule.TriumphRelic.SIMULACRUM_OF_THE_EBON_CHALICE,
            army_rule.TriumphRelic.ICON_OF_THE_VALOROUS_HEART,
        ),
    )

    assert (
        army_rule.acts_of_faith_phase_limit_for_unit(
            state,
            player_id="player-a",
            unit_instance_id=triumph.unit_instance_id,
        )
        == 2
    )
    assert tuple(
        source.threshold
        for source in state.feel_no_pain_sources_for_model(
            model_instance_id=triumph.own_models[0].model_instance_id,
        )
    ) == (6,)

    dice = list(army_rule.miracle_dice_pool(state, player_id="player-a"))
    for index in range(2):
        die = army_rule.gain_miracle_die(
            state,
            decisions,
            player_id="player-a",
            trigger=army_rule.BATTLE_ROUND_START_TRIGGER,
            source_id=f"phase17g-adepta-test:triumph-extra-gain-{index}",
            source_context={"test": "triumph"},
        )
        assert die is not None
        dice.append(die)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)

    for index, die in enumerate(dice[:2], start=1):
        army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            unit_instance_id=triumph.unit_instance_id,
            miracle_die_id=die.miracle_die_id,
            source_id=f"phase17g-adepta-test:triumph-spend-{index}",
            source_context={"test": "triumph"},
        )

    with pytest.raises(GameLifecycleError, match="phase limit"):
        army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            unit_instance_id=triumph.unit_instance_id,
            miracle_die_id=dice[2].miracle_die_id,
            source_id="phase17g-adepta-test:triumph-spend-3",
            source_context={"test": "triumph"},
        )


def test_triumph_relics_censer_and_argent_shroud_expose_reroll_support() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    triumph = _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=7)
    decisions = DecisionController()
    request = _next_triumph_relics_request(state=state, decisions=decisions)
    _apply_triumph_relics_selection(
        state=state,
        decisions=decisions,
        request=request,
        selected_relics=(
            army_rule.TriumphRelic.CENSER_OF_THE_SACRED_ROSE,
            army_rule.TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD,
        ),
    )

    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=triumph.unit_instance_id,
        roll_type="battle_shock_roll",
        timing_window="battle_shock_test",
    )
    argent_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=triumph.unit_instance_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        attack_kind="ranged",
    )
    melee_argent_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=triumph.unit_instance_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        attack_kind="melee",
    )
    ranged_profile = _weapon_profile("triumph-test-ranged", melee=False, armor_penetration=0)
    melee_profile = _weapon_profile("triumph-test-melee", melee=True, armor_penetration=0)

    assert permission_context is not None
    assert permission_context.source_payload["relic_id"] == (
        army_rule.TriumphRelic.CENSER_OF_THE_SACRED_ROSE.value
    )
    assert argent_context is not None
    assert argent_context.source_payload["relic_id"] == (
        army_rule.TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD.value
    )
    assert argent_context.source_payload["conditional_wound_reroll"] == {
        "reroll_unmodified_values": [1]
    }
    assert melee_argent_context is None
    assert army_rule.triumph_argent_shroud_wound_reroll_values(
        state,
        player_id="player-a",
        unit_instance_id=triumph.unit_instance_id,
        weapon_profile=ranged_profile,
    ) == (1,)
    assert (
        army_rule.triumph_argent_shroud_wound_reroll_values(
            state,
            player_id="player-a",
            unit_instance_id=triumph.unit_instance_id,
            weapon_profile=melee_profile,
        )
        == ()
    )


def test_triumph_argent_shroud_attack_sequence_requests_ranged_wound_reroll_only() -> None:
    ranged_request = _source_backed_argent_shroud_attack_reroll_request(
        source_phase=BattlePhase.SHOOTING,
        melee=False,
    )
    assert ranged_request is not None
    assert ranged_request.decision_type == DICE_REROLL_DECISION_TYPE
    payload = cast(dict[str, object], ranged_request.payload)
    permission_payload = cast(dict[str, object], payload["permission"])
    attack_context = cast(dict[str, object], payload["attack_context"])
    source_payload = cast(dict[str, object], attack_context["source_payload"])

    assert payload["roll_type"] == "attack_sequence.wound"
    assert payload["current_values"] == [1]
    assert tuple(option.option_id for option in ranged_request.options) == ("decline", "reroll:0")
    assert permission_payload["timing_window"] == "attack_sequence.wound"
    assert permission_payload["eligible_roll_type"] == "attack_sequence.wound"
    assert permission_payload["component_selection_policy"] == "component_selection"
    assert permission_payload["allowed_component_selections"] == [[0]]
    assert (
        source_payload["relic_id"] == army_rule.TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD.value
    )
    assert source_payload["attack_kind"] == "ranged"
    assert source_payload["conditional_wound_reroll"] == {"reroll_unmodified_values": [1]}

    assert (
        _source_backed_argent_shroud_attack_reroll_request(
            source_phase=BattlePhase.FIGHT,
            melee=True,
        )
        is None
    )


def test_triumph_relic_public_apis_noop_without_active_selection() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    triumph = _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=7)
    target = _unit_for_player(state, player_id="player-b")
    model = triumph.own_models[0]
    existing_modifier = RollModifier(
        modifier_id="phase17g-adepta-existing-modifier",
        source_id="phase17g-adepta-test:existing",
        operand=2,
    )
    ranged_profile = _weapon_profile("triumph-test-ranged", melee=False, armor_penetration=0)
    melee_profile = _weapon_profile("triumph-test-melee", melee=True, armor_penetration=0)

    assert (
        army_rule.active_triumph_relics_for_unit(
            state,
            player_id="player-a",
            unit_instance_id=triumph.unit_instance_id,
        )
        == ()
    )
    assert (
        army_rule.acts_of_faith_phase_limit_for_unit(
            state,
            player_id="player-a",
            unit_instance_id=triumph.unit_instance_id,
        )
        == 1
    )
    assert (
        army_rule.triumph_fiery_heart_movement_modifier(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id=triumph.unit_instance_id,
                model_instance_id=model.model_instance_id,
                base_movement_inches=6.0,
                current_movement_inches=6.0,
            )
        )
        == 6.0
    )
    assert army_rule.triumph_fiery_heart_advance_modifier(
        AdvanceRollModifierContext(
            state=state,
            unit_instance_id=triumph.unit_instance_id,
            current_roll_modifiers=(existing_modifier,),
        )
    ) == (existing_modifier,)
    assert army_rule.triumph_fiery_heart_charge_modifier(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=triumph.unit_instance_id,
            current_roll_modifiers=(existing_modifier,),
        )
    ) == (existing_modifier,)
    assert (
        army_rule.triumph_bloody_rose_weapon_profile_modifier(
            WeaponProfileModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=triumph.unit_instance_id,
                attacker_model_instance_id=model.model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                weapon_profile=melee_profile,
            )
        )
        == melee_profile
    )
    assert (
        army_rule.triumph_bloody_rose_weapon_profile_modifier(
            WeaponProfileModifierContext(
                state=state,
                source_phase=BattlePhase.FIGHT,
                attacking_unit_instance_id=triumph.unit_instance_id,
                attacker_model_instance_id=model.model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                weapon_profile=ranged_profile,
            )
        )
        == ranged_profile
    )
    assert (
        army_rule.triumph_argent_shroud_wound_reroll_values(
            state,
            player_id="player-a",
            unit_instance_id=triumph.unit_instance_id,
            weapon_profile=ranged_profile,
        )
        == ()
    )


def test_triumph_relic_public_apis_fail_fast_on_drift() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    unit = _unit_for_player(state, player_id="player-a")
    other_player_unit = _unit_for_player(state, player_id="player-b")
    ranged_profile = _weapon_profile("triumph-test-ranged", melee=False, armor_penetration=0)

    with pytest.raises(GameLifecycleError, match="player drift"):
        army_rule.acts_of_faith_phase_limit_for_unit(
            state,
            player_id="player-a",
            unit_instance_id=other_player_unit.unit_instance_id,
        )

    non_adepta_state = battle_state()
    non_adepta_unit = _unit_for_player(non_adepta_state, player_id="player-a")
    with pytest.raises(GameLifecycleError, match="requires Adepta Sororitas"):
        army_rule.acts_of_faith_phase_limit_for_unit(
            non_adepta_state,
            player_id="player-a",
            unit_instance_id=non_adepta_unit.unit_instance_id,
        )

    non_adepta_unit_state = battle_state()
    _mark_player_as_adepta_sororitas(
        non_adepta_unit_state,
        player_id="player-a",
        faction_keywords=("imperium",),
    )
    non_adepta_keyword_unit = _unit_for_player(non_adepta_unit_state, player_id="player-a")
    with pytest.raises(GameLifecycleError, match="requires an Adepta Sororitas unit"):
        army_rule.acts_of_faith_phase_limit_for_unit(
            non_adepta_unit_state,
            player_id="player-a",
            unit_instance_id=non_adepta_keyword_unit.unit_instance_id,
        )

    with pytest.raises(GameLifecycleError, match="WeaponProfile"):
        army_rule.triumph_argent_shroud_wound_reroll_values(
            state,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            weapon_profile=cast(WeaponProfile, object()),
        )
    with pytest.raises(GameLifecycleError, match="player drift"):
        army_rule.triumph_argent_shroud_wound_reroll_values(
            state,
            player_id="player-b",
            unit_instance_id=unit.unit_instance_id,
            weapon_profile=ranged_profile,
        )
    assert (
        army_rule.triumph_argent_shroud_wound_reroll_values(
            non_adepta_state,
            player_id="player-a",
            unit_instance_id=non_adepta_unit.unit_instance_id,
            weapon_profile=ranged_profile,
        )
        == ()
    )
    assert (
        army_rule.triumph_argent_shroud_wound_reroll_values(
            non_adepta_unit_state,
            player_id="player-a",
            unit_instance_id=non_adepta_keyword_unit.unit_instance_id,
            weapon_profile=ranged_profile,
        )
        == ()
    )


def test_triumph_modifier_handlers_fail_fast_on_invalid_contexts() -> None:
    with pytest.raises(GameLifecycleError, match="movement modifier requires context"):
        army_rule.triumph_fiery_heart_movement_modifier(
            cast(MovementBudgetModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="advance modifier requires context"):
        army_rule.triumph_fiery_heart_advance_modifier(cast(AdvanceRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="charge modifier requires context"):
        army_rule.triumph_fiery_heart_charge_modifier(cast(ChargeRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="weapon modifier requires context"):
        army_rule.triumph_bloody_rose_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )


def test_triumph_modifiers_ignore_non_adepta_armies_and_units() -> None:
    def assert_modifiers_noop(state: GameState, unit: UnitInstance) -> None:
        target = _unit_for_player(state, player_id="player-b")
        model = unit.own_models[0]
        existing_modifier = RollModifier(
            modifier_id=f"phase17g-adepta-existing:{unit.unit_instance_id}",
            source_id="phase17g-adepta-test:existing",
            operand=2,
        )
        profile = _weapon_profile(
            f"triumph-test-melee:{unit.unit_instance_id}",
            melee=True,
            armor_penetration=0,
        )

        assert (
            army_rule.triumph_fiery_heart_movement_modifier(
                MovementBudgetModifierContext(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    base_movement_inches=6.0,
                    current_movement_inches=6.0,
                )
            )
            == 6.0
        )
        assert army_rule.triumph_fiery_heart_advance_modifier(
            AdvanceRollModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                current_roll_modifiers=(existing_modifier,),
            )
        ) == (existing_modifier,)
        assert army_rule.triumph_fiery_heart_charge_modifier(
            ChargeRollModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                current_roll_modifiers=(existing_modifier,),
            )
        ) == (existing_modifier,)
        assert (
            army_rule.triumph_bloody_rose_weapon_profile_modifier(
                WeaponProfileModifierContext(
                    state=state,
                    source_phase=BattlePhase.FIGHT,
                    attacking_unit_instance_id=unit.unit_instance_id,
                    attacker_model_instance_id=model.model_instance_id,
                    target_unit_instance_id=target.unit_instance_id,
                    weapon_profile=profile,
                )
            )
            == profile
        )
        assert (
            army_rule.triumph_argent_shroud_wound_reroll_values(
                state,
                player_id="player-a",
                unit_instance_id=unit.unit_instance_id,
                weapon_profile=_weapon_profile(
                    f"triumph-test-ranged:{unit.unit_instance_id}",
                    melee=False,
                    armor_penetration=0,
                ),
            )
            == ()
        )

    non_adepta_state = battle_state()
    assert_modifiers_noop(
        non_adepta_state, _unit_for_player(non_adepta_state, player_id="player-a")
    )

    non_adepta_unit_state = battle_state()
    _mark_player_as_adepta_sororitas(
        non_adepta_unit_state,
        player_id="player-a",
        faction_keywords=("imperium",),
    )
    assert_modifiers_noop(
        non_adepta_unit_state,
        _unit_for_player(non_adepta_unit_state, player_id="player-a"),
    )


def test_triumph_feel_no_pain_sync_requires_adepta_and_clears_inactive_sources() -> None:
    non_adepta_state = battle_state()
    with pytest.raises(GameLifecycleError, match="requires Adepta Sororitas"):
        army_rule.sync_triumph_relic_feel_no_pain_sources(
            non_adepta_state,
            player_id="player-a",
        )

    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    unit = _unit_for_player(state, player_id="player-a")
    model = unit.own_models[0]
    state.record_model_feel_no_pain_sources(
        model_instance_id=model.model_instance_id,
        sources=(
            FeelNoPainSource(
                source_id=f"{army_rule.TRIUMPH_RELICS_FEEL_NO_PAIN_SOURCE_PREFIX}:stale",
                threshold=6,
            ),
        ),
    )

    army_rule.sync_triumph_relic_feel_no_pain_sources(state, player_id="player-a")

    assert state.feel_no_pain_sources_for_model(model_instance_id=model.model_instance_id) == ()


@pytest.mark.parametrize(
    ("payload_update", "message"),
    [
        ({"game_id": "phase17g-adepta-drift-game"}, "game_id drift"),
        ({"battle_round": 2}, "battle_round drift"),
        ({"phase": BattlePhase.MOVEMENT.value}, "phase drift"),
        ({"active_player_id": "player-b"}, "active player drift"),
        ({"source_model_instance_id": "phase17g-adepta-drift-model"}, "source model drift"),
        ({"damaged_effect_id": "phase17g-adepta-drift-damaged"}, "DAMAGED effect drift"),
        ({"damaged_profile_active": False}, "DAMAGED active drift"),
        ({"max_selections": 2}, "max selection drift"),
        ({"baseline_max_selections": 3}, "baseline selection drift"),
        ({"available_relic_ids": [army_rule.TriumphRelic.FIERY_HEART.value]}, "available relic"),
    ],
)
def test_triumph_relics_selection_rejects_stale_request_drift(
    payload_update: dict[str, JsonValue],
    message: str,
) -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=6)
    decisions = DecisionController()
    request = _next_triumph_relics_request(state=state, decisions=decisions)
    drifted_request = replace(
        request,
        payload={
            **cast(dict[str, JsonValue], request.payload),
            **payload_update,
        },
    )
    result = DecisionResult.for_request(
        result_id=f"phase17g-adepta-triumph-drift:{message.replace(' ', '-')}",
        request=drifted_request,
        selected_option_id="triumph-relics-none",
    )
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )

    with pytest.raises(GameLifecycleError, match=message):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=drifted_request,
                result=result,
            )
        )


def test_triumph_relics_selection_rejects_result_drift_and_duplicate_resolution() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=7)
    decisions = DecisionController()
    request = _next_triumph_relics_request(state=state, decisions=decisions)
    result = DecisionResult.for_request(
        result_id="phase17g-adepta-triumph-result-drift",
        request=request,
        selected_option_id="triumph-relics-none",
    )
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )
    invalid_results: tuple[tuple[DecisionResult, str], ...] = (
        (replace(result, actor_id=None), "requires an actor"),
        (replace(result, actor_id="player-b"), "actor drift"),
        (replace(result, selected_option_id="phase17g-adepta-missing-option"), "not available"),
        (replace(result, payload={}), "payload drift"),
    )

    for invalid_result, message in invalid_results:
        with pytest.raises(GameLifecycleError, match=message):
            registry.apply_result(
                BattleRoundStartResultContext(
                    state=state,
                    decisions=decisions,
                    request=request,
                    result=invalid_result,
                )
            )

    assert registry.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    with pytest.raises(GameLifecycleError, match="selection already exists"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )


def test_source_backed_reroll_conditional_payloads_fail_fast() -> None:
    def state_with_effect(source_payload: JsonValue) -> tuple[GameState, UnitInstance]:
        state = battle_state()
        unit = _unit_for_player(state, player_id="player-a")
        state.record_persisting_effect(
            PersistingEffect(
                effect_id="phase17g-adepta-source-backed-reroll-effect",
                source_rule_id="phase17g-adepta-source-backed-reroll",
                owner_player_id="player-a",
                target_unit_instance_ids=(unit.unit_instance_id,),
                started_battle_round=state.battle_round,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=source_backed_reroll_permission_effect_payload(
                    target_unit_instance_ids=(unit.unit_instance_id,),
                    permission=RerollPermission(
                        source_id="phase17g-adepta-source-backed-reroll",
                        timing_window="attack_sequence.wound",
                        owning_player_id="player-a",
                        eligible_roll_type="wound_roll",
                        component_selection_policy=(RerollComponentSelectionPolicy.WHOLE_ROLL),
                    ),
                    source_payload=source_payload,
                ),
            )
        )
        return state, unit

    def query(
        state: GameState,
        unit: UnitInstance,
        *,
        attack_kind: str | None = "ranged",
        target_unit_instance_id: str | None = None,
    ) -> object:
        return source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            roll_type="wound_roll",
            timing_window="attack_sequence.wound",
            attack_kind=attack_kind,
            target_unit_instance_id=target_unit_instance_id,
        )

    def query_with_effect(
        source_payload: JsonValue,
        *,
        attack_kind: str | None = "ranged",
        target_unit_instance_id: str | None = None,
    ) -> object:
        state, unit = state_with_effect(source_payload)
        return query(
            state,
            unit,
            attack_kind=attack_kind,
            target_unit_instance_id=target_unit_instance_id,
        )

    with pytest.raises(GameLifecycleError, match="attack_kind"):
        query_with_effect({"attack_kind": ""})
    with pytest.raises(GameLifecycleError, match="aura_source_unit_instance_id"):
        query_with_effect({"aura_range_inches": 6.0}, attack_kind=None)
    with pytest.raises(GameLifecycleError, match="aura_range_inches"):
        query_with_effect(
            {
                "aura_source_unit_instance_id": "phase17g-adepta-source-unit",
                "aura_range_inches": "six",
            },
            attack_kind=None,
        )
    with pytest.raises(GameLifecycleError, match="aura_range_inches"):
        query_with_effect(
            {
                "aura_source_unit_instance_id": "phase17g-adepta-source-unit",
                "aura_range_inches": 0,
            },
            attack_kind=None,
        )
    with pytest.raises(GameLifecycleError, match="unsupported attack_kind"):
        query_with_effect({}, attack_kind="psychic")
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        source_backed_reroll_permission_context_for_unit(
            state=object(),
            player_id="player-a",
            unit_instance_id="phase17g-adepta-unit",
            roll_type="wound_roll",
            timing_window="attack_sequence.wound",
        )

    state, unit = state_with_effect({"attack_kind": "melee"})
    assert query(state, unit, attack_kind="ranged") is None
    state, unit = state_with_effect({"target_unit_instance_id": "phase17g-adepta-other-target"})
    assert query(state, unit, target_unit_instance_id=unit.unit_instance_id) is None
    state, unit = state_with_effect(
        {
            "aura_source_unit_instance_id": "phase17g-adepta-missing-source",
            "aura_range_inches": 6.0,
        }
    )
    assert query(state, unit, attack_kind=None) is None

    state, unit = state_with_effect(
        {
            "aura_source_unit_instance_id": unit.unit_instance_id,
            "aura_range_inches": 6.0,
        }
    )
    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="battlefield_state"):
        query(state, unit, attack_kind=None)


def test_acts_of_faith_runtime_contribution_exposes_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert (
        army_rule.CONTRIBUTION_ID == "warhammer_40000_11th:adepta_sororitas:army_rule:acts_of_faith"
    )
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert tuple(binding.hook_id for binding in contribution.battle_round_start_hook_bindings) == (
        army_rule.BATTLE_ROUND_START_HOOK_ID,
        army_rule.TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
    )
    assert tuple(binding.hook_id for binding in contribution.unit_destroyed_hook_bindings) == (
        army_rule.UNIT_DESTROYED_HOOK_ID,
    )
    assert tuple(
        binding.modifier_id for binding in contribution.movement_budget_modifier_bindings
    ) == (army_rule.TRIUMPH_FIERY_HEART_MOVEMENT_MODIFIER_ID,)
    assert tuple(
        binding.modifier_id for binding in contribution.advance_roll_modifier_bindings
    ) == (army_rule.TRIUMPH_FIERY_HEART_ADVANCE_MODIFIER_ID,)
    assert tuple(binding.modifier_id for binding in contribution.charge_roll_modifier_bindings) == (
        army_rule.TRIUMPH_FIERY_HEART_CHARGE_MODIFIER_ID,
    )
    assert tuple(
        binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings
    ) == (army_rule.TRIUMPH_BLOODY_ROSE_WEAPON_PROFILE_MODIFIER_ID,)


def test_acts_of_faith_handlers_fail_fast_on_malformed_inputs() -> None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    decisions = DecisionController()

    invalid_cases: tuple[Callable[[], object], ...] = (
        lambda: army_rule.resolve_battle_round_start(
            cast(BattleRoundStartRequestContext, object())
        ),
        lambda: army_rule.resolve_adepta_sororitas_unit_destroyed(
            cast(UnitDestroyedContext, object())
        ),
        lambda: army_rule.gain_miracle_die(
            cast(GameState, object()),
            decisions,
            player_id="player-a",
            trigger=army_rule.BATTLE_ROUND_START_TRIGGER,
            source_id="phase17g-adepta-test:invalid-state",
            source_context={},
        ),
        lambda: army_rule.gain_miracle_die(
            state,
            decisions,
            player_id="player-a",
            trigger="unsupported_trigger",
            source_id="phase17g-adepta-test:invalid-trigger",
            source_context={},
        ),
        lambda: army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            unit_instance_id=_unit_for_player(state, player_id="player-a").unit_instance_id,
            miracle_die_id="missing-die",
            source_id="phase17g-adepta-test:missing-spend",
            source_context={},
        ),
    )
    for invalid_case in invalid_cases:
        with pytest.raises(GameLifecycleError):
            invalid_case()


def _mark_player_as_adepta_sororitas(
    state: GameState,
    *,
    player_id: str,
    faction_keywords: tuple[str, ...] = (army_rule.ADEPTA_SORORITAS_FACTION_KEYWORD,),
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.ADEPTA_SORORITAS_FACTION_ID,
                ),
                units=tuple(
                    replace(
                        unit,
                        faction_keywords=faction_keywords,
                    )
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _make_first_unit_triumph(
    state: GameState,
    *,
    player_id: str,
    wounds_remaining: int,
) -> UnitInstance:
    source_unit = _unit_for_player(state, player_id=player_id)
    updated_models = tuple(
        replace(
            model,
            datasheet_id=army_rule.TRIUMPH_OF_SAINT_KATHERINE_DATASHEET_ID,
            starting_wounds=18,
            wounds_remaining=wounds_remaining if index == 0 else 0,
        )
        for index, model in enumerate(source_unit.own_models)
    )
    triumph = replace(
        source_unit,
        datasheet_id=army_rule.TRIUMPH_OF_SAINT_KATHERINE_DATASHEET_ID,
        name="Triumph Of Saint Katherine",
        own_models=updated_models,
        damaged_effects=(
            DamagedEffectDefinition(
                damaged_effect_id="wahapedia:000002063:damaged:relics-selection-limit",
                model_profile_id=None,
                wounds_min=1,
                wounds_max=6,
                effect_kind=DamagedEffectKind.ABILITY_SELECTION_LIMIT,
                max_selections=1,
                baseline_max_selections=2,
                selection_group=army_rule.TRIUMPH_RELICS_SELECTION_GROUP,
                source_id=army_rule.TRIUMPH_RELICS_DAMAGED_SOURCE_RULE_ID,
            ),
        ),
    )
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    triumph if unit.unit_instance_id == source_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies
    return triumph


def _next_triumph_relics_request(
    *,
    state: GameState,
    decisions: DecisionController,
) -> DecisionRequest:
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("Expected Relics of the Matriarchs request.")
    return request


def _apply_triumph_relics_selection(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    selected_relics: tuple[army_rule.TriumphRelic, ...],
) -> None:
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )
    option_id = _triumph_option_id(request, selected_relics=selected_relics)
    result = DecisionResult.for_request(
        result_id=f"phase17g-adepta-triumph:{option_id}:result",
        request=request,
        selected_option_id=option_id,
    )
    handled = registry.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    assert handled


def _triumph_option_id(
    request: DecisionRequest,
    *,
    selected_relics: tuple[army_rule.TriumphRelic, ...],
) -> str:
    selected_ids = [relic.value for relic in selected_relics]
    for option in request.options:
        payload = cast(dict[str, JsonValue], option.payload)
        if payload["selected_relic_ids"] == selected_ids:
            return option.option_id
    raise AssertionError(f"Missing Triumph relic option {selected_ids}.")


def _source_backed_argent_shroud_attack_reroll_request(
    *,
    source_phase: BattlePhase,
    melee: bool,
) -> DecisionRequest | None:
    state = battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    triumph = _make_first_unit_triumph(state, player_id="player-a", wounds_remaining=7)
    defender = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    request = _next_triumph_relics_request(state=state, decisions=decisions)
    _apply_triumph_relics_selection(
        state=state,
        decisions=decisions,
        request=request,
        selected_relics=(army_rule.TriumphRelic.SIMULACRUM_OF_THE_ARGENT_SHROUD,),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(source_phase)
    weapon_profile = _weapon_profile(
        f"phase17g-adepta-argent-{source_phase.value}",
        melee=melee,
        armor_penetration=0,
    )
    attack_pool = _attack_pool_for_triumph_test(
        attacker=triumph,
        defender=defender,
        weapon_profile=weapon_profile,
    )
    sequence_id = f"phase17g-adepta-argent-{source_phase.value}"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    attack_sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=triumph.unit_instance_id,
        source_phase=source_phase,
        attack_pools=(attack_pool,),
    )
    _remaining_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            state.game_id,
            event_log=decisions.event_log,
            injected_results=(
                DiceRollResult.from_values(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    values=(4,),
                    source="fixed",
                ),
                DiceRollResult.from_values(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    values=(1,),
                    source="fixed",
                ),
            ),
        ),
    )
    assert allocated_model_ids == ()
    if status is None:
        return None
    decision_request = status.decision_request
    if decision_request is None:
        raise AssertionError("Expected a source-backed wound reroll request.")
    return decision_request


def _attack_pool_for_triumph_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
) -> RangedAttackPool:
    defender_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=f"{weapon_profile.profile_id}:wargear",
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=defender_model_ids,
        target_in_range_model_ids=defender_model_ids,
    )


def _weapon_profile(
    profile_id: str,
    *,
    melee: bool,
    armor_penetration: int,
) -> WeaponProfile:
    return WeaponProfile(
        profile_id=profile_id,
        name=profile_id,
        range_profile=RangeProfile.melee() if melee else RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(
            Characteristic.WEAPON_SKILL if melee else Characteristic.BALLISTIC_SKILL,
            3,
        ),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(
            Characteristic.ARMOR_PENETRATION,
            armor_penetration,
        ),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g-adepta-test:weapon-profile",),
    )


def _append_destroyed_model_event(
    *,
    state: GameState,
    decisions: DecisionController,
    destroying_player_id: str,
    target_unit: UnitInstance,
) -> EventRecord:
    return decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "destroying_player_id": destroying_player_id,
            "target_unit_instance_id": target_unit.unit_instance_id,
            "model_instance_id": target_unit.own_models[-1].model_instance_id,
        },
    )


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _last_event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    events = _event_payloads(decisions, event_type)
    if not events:
        raise AssertionError(f"Missing event {event_type}.")
    return events[-1]


def _dice_roll_count(decisions: DecisionController) -> int:
    return sum(1 for event in decisions.event_log.records if event.event_type == "dice_rolled")
