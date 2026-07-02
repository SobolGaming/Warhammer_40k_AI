from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
    _center_marker_definition,  # pyright: ignore[reportPrivateUsage]
    _remove_first_models,  # pyright: ignore[reportPrivateUsage]
    _unit_by_id,  # pyright: ignore[reportPrivateUsage]
    _with_model_offsets,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestContext,
    BattleShockHookRegistry,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
    army_rule,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)


def test_harbingers_selection_records_persistent_dread_state() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    registry = _battle_round_start_hooks()

    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert "chaos_knights:harbingers_of_dread:despair" in {
        option.option_id for option in request.options
    }

    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-select-despair",
        request=request,
        selected_option_id="chaos_knights:harbingers_of_dread:despair",
    )
    assert registry.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert army_rule.active_dread_abilities_for_player(state, player_id="player-a") == (
        army_rule.DreadAbility.DEATHLY_TERROR,
        army_rule.DreadAbility.DESPAIR,
    )
    selected_payload = _event_payload(decisions, "chaos_knights_harbingers_of_dread_selected")
    assert selected_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert selected_payload["selected_dread_ability_ids"] == ["despair"]
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()


def test_harbingers_roll_selection_records_engine_owned_dice() -> None:
    state = _battle_state()
    state.game_id = "phase17g-chaos-knights-roll-selection"
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("expected Harbingers selection request")

    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-roll",
        request=request,
        selected_option_id=army_rule.ROLL_SELECTION_OPTION_ID,
    )
    assert registry.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    selected_payload = _event_payload(decisions, "chaos_knights_harbingers_of_dread_selected")
    dice_values = cast(list[int], selected_payload["dice_values"])
    selected_ids = cast(list[str], selected_payload["selected_dread_ability_ids"])
    assert selected_payload["selection_mode"] == "roll_2d6"
    assert len(dice_values) == 2
    assert all(type(value) is int and 1 <= value <= 6 for value in dice_values)
    assert set(selected_ids) <= {ability.value for ability in army_rule.ROLLABLE_DREAD_ABILITIES}
    assert len(set(selected_ids)) == len(selected_ids)


def test_harbingers_rejects_stale_selection_after_active_dread_drift() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("expected Harbingers selection request")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DESPAIR,),
        battle_round=3,
    )
    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-stale-selection",
        request=request,
        selected_option_id="chaos_knights:harbingers_of_dread:doom",
    )

    with pytest.raises(GameLifecycleError, match="active ability drift"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )


def test_harbingers_selection_request_suppresses_unavailable_states() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    registry = _battle_round_start_hooks()

    state.battle_round = 2
    assert (
        registry.next_request_for(BattleRoundStartRequestContext(state=state, decisions=decisions))
        is None
    )

    state.battle_round = 1
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DESPAIR,),
    )
    assert (
        registry.next_request_for(BattleRoundStartRequestContext(state=state, decisions=decisions))
        is None
    )

    exhausted_state = _battle_state()
    exhausted_state.battle_round = 5
    _mark_player_as_chaos_knights(exhausted_state, player_id="player-a")
    _record_harbingers_selection(
        exhausted_state,
        player_id="player-a",
        selected=army_rule.ROLLABLE_DREAD_ABILITIES,
        battle_round=3,
    )
    assert (
        registry.next_request_for(
            BattleRoundStartRequestContext(state=exhausted_state, decisions=decisions)
        )
        is None
    )

    no_harbingers_units_state = _battle_state()
    _mark_player_faction_only_as_chaos_knights(
        no_harbingers_units_state,
        player_id="player-a",
    )
    assert (
        registry.next_request_for(
            BattleRoundStartRequestContext(state=no_harbingers_units_state, decisions=decisions)
        )
        is None
    )


def test_harbingers_selection_result_rejects_invalid_contexts_and_payloads() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("expected Harbingers selection request")
    selected_option_id = "chaos_knights:harbingers_of_dread:despair"
    option = request.option_by_id(selected_option_id)

    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_harbingers_selection_result(cast(BattleRoundStartResultContext, object()))

    wrong_type_request = replace(request, decision_type="not_harbingers")
    wrong_type_result = DecisionResult(
        result_id="phase17g-chaos-knights-wrong-type",
        request_id=wrong_type_request.request_id,
        decision_type=wrong_type_request.decision_type,
        actor_id=wrong_type_request.actor_id,
        selected_option_id=option.option_id,
        payload=option.payload,
    )
    assert not army_rule.apply_harbingers_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_type_request,
            result=wrong_type_result,
        )
    )

    request_payload = cast(dict[str, JsonValue], request.payload)
    wrong_hook_request = replace(request, payload={**request_payload, "hook_id": "other-hook"})
    wrong_hook_result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-wrong-hook",
        request=wrong_hook_request,
        selected_option_id=selected_option_id,
    )
    assert not army_rule.apply_harbingers_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_hook_request,
            result=wrong_hook_result,
        )
    )

    missing_actor_result = DecisionResult(
        result_id="phase17g-chaos-knights-missing-actor",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=None,
        selected_option_id=selected_option_id,
        payload=option.payload,
    )
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=missing_actor_result,
            )
        )

    wrong_actor_result = DecisionResult(
        result_id="phase17g-chaos-knights-wrong-actor",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id="player-b",
        selected_option_id=selected_option_id,
        payload=option.payload,
    )
    with pytest.raises(GameLifecycleError, match="does not own Chaos Knights"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=wrong_actor_result,
            )
        )

    missing_option_result = DecisionResult(
        result_id="phase17g-chaos-knights-missing-option",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="chaos_knights:harbingers_of_dread:not-available",
        payload=option.payload,
    )
    with pytest.raises(GameLifecycleError, match="selected option is not available"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=missing_option_result,
            )
        )

    drifted_result = DecisionResult(
        result_id="phase17g-chaos-knights-payload-drift",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=selected_option_id,
        payload={**cast(dict[str, JsonValue], option.payload), "selection_mode": "roll_2d6"},
    )
    with pytest.raises(GameLifecycleError, match="selected option payload drift"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=drifted_result,
            )
        )

    unsupported_payload = {
        **cast(dict[str, JsonValue], option.payload),
        "selection_mode": "unsupported",
    }
    unsupported_request = replace(
        request,
        options=(
            DecisionOption(
                option_id=selected_option_id,
                label="Unsupported",
                payload=unsupported_payload,
            ),
        ),
    )
    unsupported_result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-unsupported-mode",
        request=unsupported_request,
        selected_option_id=selected_option_id,
    )
    with pytest.raises(GameLifecycleError, match="selection mode is unsupported"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=unsupported_request,
                result=unsupported_result,
            )
        )


def test_harbingers_selection_result_rejects_round_replay_and_request_drift() -> None:
    round_state, round_decisions, round_request = _harbingers_selection_request_for_test()
    round_result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-round-drift",
        request=round_request,
        selected_option_id="chaos_knights:harbingers_of_dread:despair",
    )
    round_state.battle_round = 2
    with pytest.raises(GameLifecycleError, match="not available this round"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=round_state,
                decisions=round_decisions,
                request=round_request,
                result=round_result,
            )
        )

    replay_state, replay_decisions, replay_request = _harbingers_selection_request_for_test()
    replay_result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-replay",
        request=replay_request,
        selected_option_id="chaos_knights:harbingers_of_dread:despair",
    )
    _record_harbingers_selection(
        replay_state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DOOM,),
    )
    with pytest.raises(GameLifecycleError, match="already recorded this round"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=replay_state,
                decisions=replay_decisions,
                request=replay_request,
                result=replay_result,
            )
        )

    game_state, game_decisions, game_request = _harbingers_selection_request_for_test()
    game_result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-game-drift",
        request=game_request,
        selected_option_id="chaos_knights:harbingers_of_dread:despair",
    )
    game_state.game_id = "phase17g-chaos-knights-drifted-game"
    with pytest.raises(GameLifecycleError, match="game_id drift"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=game_state,
                decisions=game_decisions,
                request=game_request,
                result=game_result,
            )
        )

    battle_round_state, battle_round_decisions, battle_round_request = (
        _harbingers_selection_request_for_test()
    )
    battle_round_result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-battle-round-drift",
        request=battle_round_request,
        selected_option_id="chaos_knights:harbingers_of_dread:despair",
    )
    battle_round_state.battle_round = 3
    with pytest.raises(GameLifecycleError, match="battle_round drift"):
        army_rule.apply_harbingers_selection_result(
            BattleRoundStartResultContext(
                state=battle_round_state,
                decisions=battle_round_decisions,
                request=battle_round_request,
                result=battle_round_result,
            )
        )


def test_harbingers_public_handlers_fail_fast_for_invalid_inputs() -> None:
    with pytest.raises(GameLifecycleError, match="ability drift"):
        army_rule.DreadAbilityDefinition(
            ability=cast(army_rule.DreadAbility, "despair"),
            label="Despair",
            effect_summary="Invalid ability type",
        )
    with pytest.raises(GameLifecycleError, match="label must be non-empty"):
        army_rule.DreadAbilityDefinition(
            ability=army_rule.DreadAbility.DESPAIR,
            label="",
            effect_summary="Invalid label",
        )
    with pytest.raises(GameLifecycleError, match="summary must be non-empty"):
        army_rule.DreadAbilityDefinition(
            ability=army_rule.DreadAbility.DESPAIR,
            label="Despair",
            effect_summary="",
        )
    with pytest.raises(GameLifecycleError, match="D6 face"):
        army_rule.DreadAbilityDefinition(
            ability=army_rule.DreadAbility.DESPAIR,
            label="Despair",
            effect_summary="Invalid roll",
            roll_result=7,
        )
    with pytest.raises(GameLifecycleError, match="is_aura must be a bool"):
        army_rule.DreadAbilityDefinition(
            ability=army_rule.DreadAbility.DESPAIR,
            label="Despair",
            effect_summary="Invalid aura flag",
            is_aura=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.harbingers_selection_request(cast(BattleRoundStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="result actor check requires context"):
        army_rule.result_actor_is_missing(cast(BattleRoundStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="Leadership modifier requires context"):
        army_rule.harbingers_leadership_modifier(cast(UnitCharacteristicModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Darkness hit modifier requires context"):
        army_rule.harbingers_darkness_hit_roll_modifier(cast(HitRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Doom wound modifier requires context"):
        army_rule.harbingers_doom_wound_roll_modifier(cast(WoundRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="forced tests require context"):
        army_rule.harbingers_forced_battle_shock_unit_ids(
            cast(BattleShockForcedTestContext, object())
        )
    with pytest.raises(GameLifecycleError, match="Battle-shock outcome requires context"):
        army_rule.resolve_harbingers_battle_shock_outcome(cast(BattleShockOutcomeContext, object()))
    with pytest.raises(GameLifecycleError, match="roll values must be D6 results"):
        army_rule._dread_abilities_from_dice_values(  # pyright: ignore[reportPrivateUsage]
            (7,),
            active=(army_rule.DreadAbility.DEATHLY_TERROR,),
        )


def test_harbingers_rejects_invalid_persisted_dread_states() -> None:
    deathly_state = _battle_state()
    _mark_player_as_chaos_knights(deathly_state, player_id="player-a")
    _record_harbingers_selection(
        deathly_state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DEATHLY_TERROR,),
    )
    with pytest.raises(GameLifecycleError, match="Deathly Terror must not be selected"):
        army_rule.active_dread_abilities_for_player(deathly_state, player_id="player-a")

    duplicate_ability_state = _battle_state()
    _mark_player_as_chaos_knights(duplicate_ability_state, player_id="player-a")
    _record_harbingers_selection(
        duplicate_ability_state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DESPAIR,),
        battle_round=1,
    )
    _record_harbingers_selection(
        duplicate_ability_state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DESPAIR,),
        battle_round=3,
    )
    with pytest.raises(GameLifecycleError, match="active lookup found duplicates"):
        army_rule.active_dread_abilities_for_player(
            duplicate_ability_state,
            player_id="player-a",
        )

    duplicate_round_state = _battle_state()
    _mark_player_as_chaos_knights(duplicate_round_state, player_id="player-a")
    _record_harbingers_selection(
        duplicate_round_state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DESPAIR,),
        battle_round=1,
    )
    first_round_state = duplicate_round_state.faction_rule_states[-1]
    first_round_payload = cast(dict[str, JsonValue], first_round_state.payload)
    duplicate_round_state.record_faction_rule_state(
        replace(
            first_round_state,
            state_id=f"{first_round_state.state_id}:duplicate",
            result_id=f"{first_round_state.result_id}:duplicate",
            payload=validate_json_value(
                {
                    **first_round_payload,
                    "selected_dread_ability_ids": [army_rule.DreadAbility.DOOM.value],
                    "selected_dread_ability_labels": ["Doom"],
                }
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="duplicate battle-round states"):
        army_rule.active_dread_abilities_for_player(duplicate_round_state, player_id="player-a")

    with pytest.raises(GameLifecycleError, match="manual selection requires one ability"):
        army_rule._validate_manual_selection(  # pyright: ignore[reportPrivateUsage]
            selected=(),
            active=(army_rule.DreadAbility.DEATHLY_TERROR,),
        )
    with pytest.raises(GameLifecycleError, match="cannot select Deathly Terror"):
        army_rule._validate_manual_selection(  # pyright: ignore[reportPrivateUsage]
            selected=(army_rule.DreadAbility.DEATHLY_TERROR,),
            active=(),
        )
    with pytest.raises(GameLifecycleError, match="ability is already active"):
        army_rule._validate_manual_selection(  # pyright: ignore[reportPrivateUsage]
            selected=(army_rule.DreadAbility.DESPAIR,),
            active=(army_rule.DreadAbility.DESPAIR,),
        )


def test_dismay_forces_below_starting_enemy_battle_shock_test() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DISMAY,),
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=1)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    requested_payload = _event_payload(decisions, "battle_shock_test_requested")
    request_payload = cast(dict[str, JsonValue], requested_payload["battle_shock_test_request"])
    assert request_payload["unit_instance_id"] == target_unit_id
    assert request_payload["reason"] == "below_starting_strength_forced"


def test_delirium_applies_mortal_wounds_after_failed_battle_shock() -> None:
    state = _battle_state()
    state.game_id = "phase17g-chaos-knights-delirium"
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DELIRIUM,),
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    _replace_unit_leadership(state, unit_instance_id=target_unit_id, leadership=13)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    starting_wounds = sum(
        model.wounds_remaining for model in _unit_by_id(state, target_unit_id).own_models
    )
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    delirium_payload = _event_payload(decisions, "chaos_knights_delirium_mortal_wounds_applied")
    assert delirium_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    application = cast(dict[str, JsonValue], delirium_payload["mortal_wound_application"])
    assert application["mortal_wounds"] in (1, 2, 3)
    final_wounds = sum(
        model.wounds_remaining for model in _unit_by_id(state, target_unit_id).own_models
    )
    assert final_wounds < starting_wounds


def test_delirium_reports_unsupported_when_mortal_wound_fnp_requires_choice() -> None:
    state = _battle_state()
    state.game_id = "phase17g-chaos-knights-delirium-fnp"
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DELIRIUM,),
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    _replace_unit_leadership(state, unit_instance_id=target_unit_id, leadership=13)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    target_unit = _unit_by_id(state, target_unit_id)
    fnp_model = next(model for model in target_unit.own_models if model.is_alive)
    state.record_model_feel_no_pain_sources(
        model_instance_id=fnp_model.model_instance_id,
        sources=(FeelNoPainSource(source_id="phase17g-chaos-knights-fnp", threshold=5),),
        decline_allowed=True,
    )
    starting_wounds = sum(model.wounds_remaining for model in target_unit.own_models)
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    unsupported_payload = _event_payload(decisions, "chaos_knights_delirium_unsupported")
    assert (
        unsupported_payload["unsupported_reason"] == "mortal_wound_feel_no_pain_requires_decision"
    )
    final_wounds = sum(
        model.wounds_remaining for model in _unit_by_id(state, target_unit_id).own_models
    )
    assert final_wounds == starting_wounds


def test_deathly_terror_and_despair_worsen_enemy_leadership_in_aura() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DESPAIR,),
    )
    target_unit_id = "army-beta:intercessor-unit-3"
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    registry = _runtime_modifier_registry()

    modified = registry.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=target_unit_id,
            characteristic=Characteristic.LEADERSHIP,
            base_value=7,
            current_value=7,
        )
    )

    assert modified == 9


def test_doom_and_darkness_runtime_modifiers_apply_to_enemy_attacks() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(
            army_rule.DreadAbility.DOOM,
            army_rule.DreadAbility.DARKNESS,
        ),
    )
    target_unit_id = "army-beta:intercessor-unit-3"
    state.battle_shocked_unit_ids = [target_unit_id]
    registry = _runtime_modifier_registry()
    profile = _weapon_profile()

    wound_modifier = registry.wound_roll_modifier(
        WoundRollModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id="army-alpha:intercessor-unit-1",
            attacker_model_instance_id="army-alpha:intercessor-unit-1:model-1",
            target_unit_instance_id=target_unit_id,
            weapon_profile=profile,
            strength=4,
            toughness=4,
        )
    )
    hit_modifier = registry.hit_roll_modifier(
        HitRollModifierContext(
            state=state,
            attacking_unit_instance_id=target_unit_id,
            attacker_model_instance_id="army-beta:intercessor-unit-3:model-1",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
            weapon_profile=profile,
            source_phase=BattlePhase.SHOOTING,
        )
    )

    assert wound_modifier == 1
    assert hit_modifier == -1


def test_harbingers_modifiers_return_neutral_outside_required_contexts() -> None:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(
            army_rule.DreadAbility.DOOM,
            army_rule.DreadAbility.DARKNESS,
        ),
    )
    target_unit_id = "army-beta:intercessor-unit-3"
    state.battle_shocked_unit_ids = [target_unit_id]
    registry = _runtime_modifier_registry()
    profile = _weapon_profile()

    assert (
        registry.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=target_unit_id,
                characteristic=Characteristic.TOUGHNESS,
                base_value=4,
                current_value=4,
            )
        )
        == 4
    )
    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=target_unit_id,
                attacker_model_instance_id="army-beta:intercessor-unit-3:model-1",
                target_unit_instance_id="army-alpha:intercessor-unit-1",
                weapon_profile=profile,
                source_phase=BattlePhase.FIGHT,
            )
        )
        == 0
    )
    assert (
        registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id="army-beta:intercessor-unit-3",
                attacker_model_instance_id="army-beta:intercessor-unit-3:model-1",
                target_unit_instance_id=target_unit_id,
                weapon_profile=profile,
                strength=4,
                toughness=4,
            )
        )
        == 0
    )
    assert not army_rule.unit_has_active_dread(
        state,
        unit_instance_id="army-beta:intercessor-unit-3",
        dread=army_rule.DreadAbility.DOOM,
    )


def test_chaos_knights_army_rule_uses_phase17f_execution_source_id() -> None:
    record = _chaos_knights_army_rule_execution_record()
    contribution = army_rule.runtime_contribution()

    assert record.execution_id == army_rule.SOURCE_RULE_ID
    assert contribution.contribution_id == army_rule.HOOK_ID
    assert contribution.contribution_id == record.handler_id
    assert contribution.battle_round_start_hook_bindings[0].source_id == record.execution_id
    assert contribution.battle_shock_hook_bindings[0].source_id == record.execution_id
    assert contribution.unit_characteristic_modifier_bindings[0].source_id == record.execution_id
    assert contribution.hit_roll_modifier_bindings[0].source_id == record.execution_id
    assert contribution.wound_roll_modifier_bindings[0].source_id == record.execution_id


def _battle_round_start_hooks() -> BattleRoundStartHookRegistry:
    contribution = army_rule.runtime_contribution()
    return BattleRoundStartHookRegistry.from_bindings(contribution.battle_round_start_hook_bindings)


def _battle_shock_hooks() -> BattleShockHookRegistry:
    contribution = army_rule.runtime_contribution()
    return BattleShockHookRegistry.from_bindings(contribution.battle_shock_hook_bindings)


def _runtime_modifier_registry() -> RuntimeModifierRegistry:
    contribution = army_rule.runtime_contribution()
    return RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=contribution.unit_characteristic_modifier_bindings,
        hit_roll_modifier_bindings=contribution.hit_roll_modifier_bindings,
        wound_roll_modifier_bindings=contribution.wound_roll_modifier_bindings,
    )


def _chaos_knights_army_rule_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == army_rule.CHAOS_KNIGHTS_FACTION_ID
        and record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
    )
    if len(records) != 1:
        raise AssertionError("expected one Chaos Knights army-rule execution record")
    return records[0]


def _harbingers_selection_request_for_test() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
]:
    state = _battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    request = _battle_round_start_hooks().next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("expected Harbingers selection request")
    return state, decisions, request


def _mark_player_as_chaos_knights(state: GameState, *, player_id: str) -> None:
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
                    faction_id=army_rule.CHAOS_KNIGHTS_FACTION_ID,
                ),
                units=tuple(_chaos_knights_unit(unit) for unit in army.units),
            )
        )
    state.army_definitions = updated_armies


def _mark_player_faction_only_as_chaos_knights(state: GameState, *, player_id: str) -> None:
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
                    faction_id=army_rule.CHAOS_KNIGHTS_FACTION_ID,
                ),
            )
        )
    state.army_definitions = updated_armies


def _chaos_knights_unit(unit: UnitInstance) -> UnitInstance:
    return replace(unit, faction_keywords=("CHAOS KNIGHTS",))


def _record_harbingers_selection(
    state: GameState,
    *,
    player_id: str,
    selected: tuple[army_rule.DreadAbility, ...],
    battle_round: int | None = None,
) -> None:
    selected_round = state.battle_round if battle_round is None else battle_round
    state.record_faction_rule_state(
        FactionRuleState(
            state_id=f"phase17g-chaos-knights:{player_id}:round-{selected_round:02d}",
            player_id=player_id,
            faction_id=army_rule.CHAOS_KNIGHTS_FACTION_ID,
            source_rule_id=army_rule.SOURCE_RULE_ID,
            state_kind=army_rule.HARBINGERS_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id=f"phase17g-chaos-knights:{player_id}:request:{selected_round:02d}",
            result_id=f"phase17g-chaos-knights:{player_id}:result:{selected_round:02d}",
            payload=validate_json_value(
                {
                    "selection_kind": army_rule.HARBINGERS_SELECTION_KIND,
                    "effect_kind": army_rule.HARBINGERS_EFFECT_KIND,
                    "selection_mode": "test_fixture",
                    "selected_option_id": "phase17g:test-fixture",
                    "game_id": state.game_id,
                    "battle_round": selected_round,
                    "phase": BattlePhase.COMMAND.value,
                    "player_id": player_id,
                    "faction_id": army_rule.CHAOS_KNIGHTS_FACTION_ID,
                    "source_rule_id": army_rule.SOURCE_RULE_ID,
                    "hook_id": army_rule.HOOK_ID,
                    "selected_dread_ability_ids": [ability.value for ability in selected],
                    "selected_dread_ability_labels": [
                        army_rule._DEFINITIONS_BY_DREAD[ability].label  # pyright: ignore[reportPrivateUsage]
                        for ability in selected
                    ],
                    "dice_values": [],
                    "roll_state": None,
                    "rules_update_sources": [army_rule.DARKNESS_RULE_UPDATE_SOURCE],
                }
            ),
        )
    )


def _place_units_near_center(
    state: GameState,
    *,
    source_unit_id: str,
    target_unit_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = _center_marker_definition(state)
    source = state.battlefield_state.unit_placement_by_id(source_unit_id)
    target = state.battlefield_state.unit_placement_by_id(target_unit_id)
    battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(source, marker, offsets=((0.0, 0.0),))
    )
    battlefield_state = battlefield_state.with_unit_placement(
        _with_model_offsets(target, marker, offsets=((1.0, 0.0),))
    )
    state.battlefield_state = battlefield_state


def _replace_unit_leadership(
    state: GameState,
    *,
    unit_instance_id: str,
    leadership: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        _replace_model_leadership(model, leadership=leadership)
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _replace_model_leadership(model: ModelInstance, *, leadership: int) -> ModelInstance:
    return replace(
        model,
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.LEADERSHIP, leadership)
            if value.characteristic is Characteristic.LEADERSHIP
            else value
            for value in model.characteristics
        ),
    )


def _weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-chaos-knights-test-weapon",
        name="Test Weapon",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:test:chaos-knights:weapon",),
    )


def _event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")
