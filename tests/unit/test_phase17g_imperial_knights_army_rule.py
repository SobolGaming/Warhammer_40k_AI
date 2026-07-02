from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
    _battle_state_with_center_objective_positions,  # pyright: ignore[reportPrivateUsage]
    _config,  # pyright: ignore[reportPrivateUsage]
    _default_unit_selection,  # pyright: ignore[reportPrivateUsage]
    _setup_state_at_declare_battle_formations,  # pyright: ignore[reportPrivateUsage]
    _unit_by_id,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainResult,
    CommandPointGainResultPayload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpirationBoundary, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventContext,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.imperial_knights import (
    army_rule,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedEffectGrant,
    FightUnitSelectedHookBinding,
    FightUnitSelectedHookRegistry,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    MovementBudgetModifierContext,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import ShootingUnitSelectedContext
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_for_unit,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

IMPERIAL_KNIGHTS_UNIT_ID = "army-alpha:intercessor-unit-1"
BONDSMAN_ARMIGER_UNIT_ID = "army-alpha:intercessor-unit-2"
BONDSMAN_TEST_ABILITY_ID = "phase17g-imperial-knights-paladins-duty"
ENEMY_UNIT_ID = "army-beta:intercessor-unit-3"


def test_code_chivalric_setup_selection_records_replay_safe_oath() -> None:
    config = _config()
    state = _setup_state_at_declare_battle_formations(config)
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _mark_enemy_unit_as_character(state, player_id="player-b")
    decisions = DecisionController()

    request = army_rule.code_chivalric_oath_request(
        BattleFormationRequestContext(state=state, decisions=decisions, config=config)
    )

    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    option = _oath_option(
        request,
        deed=army_rule.CodeChivalricDeed.LAY_LOW_THE_TYRANT,
        quality=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED,
    )
    result = DecisionResult.for_request(
        result_id="phase17g-imperial-knights-oath-result",
        request=request,
        selected_option_id=option.option_id,
    )

    handled = army_rule.apply_code_chivalric_oath_result(
        BattleFormationResultContext(
            state=state,
            decisions=decisions,
            config=config,
            request=request,
            result=result,
        )
    )

    assert handled is True
    assert (
        army_rule.selected_deed_for_player(state, player_id="player-a")
        is army_rule.CodeChivalricDeed.LAY_LOW_THE_TYRANT
    )
    assert (
        army_rule.selected_quality_for_player(state, player_id="player-a")
        is army_rule.CodeChivalricQuality.LEGACY_UNSULLIED
    )
    oath_state = army_rule.selected_oath_state_for_player(state, player_id="player-a")
    assert oath_state is not None
    oath_payload = cast(dict[str, JsonValue], oath_state.payload)
    assert oath_payload["lay_low_target_model_instance_id"] is not None
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()


def test_code_chivalric_random_oath_rolls_engine_dice_and_rewards_three_cp() -> None:
    config = _config()
    state = _setup_state_at_declare_battle_formations(config)
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _mark_enemy_unit_as_character(state, player_id="player-b")
    decisions = DecisionController()
    request = army_rule.code_chivalric_oath_request(
        BattleFormationRequestContext(state=state, decisions=decisions, config=config)
    )

    assert request is not None
    option = _random_oath_option(request)
    result = DecisionResult.for_request(
        result_id="phase17g-imperial-knights-random-oath-result",
        request=request,
        selected_option_id=option.option_id,
    )

    handled = army_rule.apply_code_chivalric_oath_result(
        BattleFormationResultContext(
            state=state,
            decisions=decisions,
            config=config,
            request=request,
            result=result,
        )
    )

    assert handled is True
    oath_state = army_rule.selected_oath_state_for_player(state, player_id="player-a")
    assert oath_state is not None
    payload = cast(dict[str, JsonValue], oath_state.payload)
    assert payload["deed_selection_mode"] == army_rule.OathSelectionMode.ROLL_D6.value
    assert payload["quality_selection_mode"] == army_rule.OathSelectionMode.ROLL_D6.value
    assert payload["deed_roll"] is not None
    assert payload["quality_roll"] is not None
    assert payload["random_selection"] is True
    assert payload["command_point_reward_amount"] == 3


def test_bondsman_command_phase_application_records_model_effect_until_next_own_turn() -> None:
    state = _bondsman_battle_state()
    decisions = DecisionController()
    request = army_rule.bondsman_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )

    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    option = _bondsman_apply_option(request)
    option_payload = _json_object(option.payload)
    target_model_id = _json_string(option_payload, "target_armiger_model_instance_id")
    result = DecisionResult.for_request(
        result_id="phase17g-imperial-knights-bondsman-application-result",
        request=request,
        selected_option_id=option.option_id,
    )

    handled = army_rule.apply_bondsman_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            active_player_id="player-a",
        )
    )

    assert handled is True
    assert army_rule.model_is_affected_by_bondsman(
        state,
        model_instance_id=target_model_id,
    )
    assert (
        army_rule.active_bondsman_ability_id_for_model(
            state,
            model_instance_id=target_model_id,
        )
        == BONDSMAN_TEST_ABILITY_ID
    )
    bondsman_states = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.BONDSMAN_APPLIED_STATE_KIND,
    )
    assert len(bondsman_states) == 1
    bondsman_effects = tuple(
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == army_rule.BONDSMAN_SOURCE_RULE_ID
    )
    assert len(bondsman_effects) == 1
    effect_payload = _json_object(bondsman_effects[0].effect_payload)
    assert effect_payload["target_armiger_model_instance_id"] == target_model_id
    assert effect_payload["bondsman_ability_id"] == BONDSMAN_TEST_ABILITY_ID
    assert effect_payload["expires_at_battle_round"] == state.battle_round + 1
    assert _event_records_of_type(decisions, army_rule.BONDSMAN_APPLIED_EVENT)
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()

    next_request = army_rule.bondsman_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )

    assert next_request is not None
    assert all(
        _json_object(candidate.payload).get("target_armiger_model_instance_id") != target_model_id
        for candidate in next_request.options
        if candidate.option_id != army_rule.BONDSMAN_DONE_OPTION_ID
    )
    expired = state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_start(
            battle_round=state.battle_round + 1,
            player_id="player-a",
        )
    )
    assert expired == bondsman_effects
    assert not army_rule.model_is_affected_by_bondsman(
        state,
        model_instance_id=target_model_id,
    )


def test_bondsman_done_option_suppresses_only_current_command_phase() -> None:
    state = _bondsman_battle_state()
    decisions = DecisionController()
    request = army_rule.bondsman_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17g-imperial-knights-bondsman-done-result",
        request=request,
        selected_option_id=army_rule.BONDSMAN_DONE_OPTION_ID,
    )

    handled = army_rule.apply_bondsman_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            active_player_id="player-a",
        )
    )

    assert handled is True
    assert not state.persisting_effects
    assert _event_records_of_type(decisions, army_rule.BONDSMAN_DONE_EVENT)
    assert (
        army_rule.bondsman_request(
            CommandPhaseStartRequestContext(
                state=state,
                decisions=decisions,
                active_player_id="player-a",
            )
        )
        is None
    )
    state.battle_round += 1
    assert (
        army_rule.bondsman_request(
            CommandPhaseStartRequestContext(
                state=state,
                decisions=decisions,
                active_player_id="player-a",
            )
        )
        is not None
    )


def test_bondsman_requires_friendly_armiger_target_within_twelve_inches() -> None:
    decisions = DecisionController()
    without_armiger = _bondsman_battle_state(target_is_armiger=False)
    assert (
        army_rule.bondsman_request(
            CommandPhaseStartRequestContext(
                state=without_armiger,
                decisions=decisions,
                active_player_id="player-a",
            )
        )
        is None
    )

    out_of_range = _bondsman_battle_state(target_is_armiger=True, target_x=40.0)
    assert (
        army_rule.bondsman_request(
            CommandPhaseStartRequestContext(
                state=out_of_range,
                decisions=decisions,
                active_player_id="player-a",
            )
        )
        is None
    )


def test_bondsman_rejects_drifted_selection_before_mutation() -> None:
    state = _bondsman_battle_state()
    decisions = DecisionController()
    request = army_rule.bondsman_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )
    assert request is not None
    option = _bondsman_apply_option(request)
    result = DecisionResult.for_request(
        result_id="phase17g-imperial-knights-bondsman-drift-result",
        request=request,
        selected_option_id=option.option_id,
    )
    _place_unit_line(
        state,
        unit_instance_id=BONDSMAN_ARMIGER_UNIT_ID,
        start_x=40.0,
        y=10.0,
    )

    with pytest.raises(GameLifecycleError, match="Bondsman selection is no longer eligible"):
        army_rule.apply_bondsman_result(
            CommandPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
                active_player_id="player-a",
            )
        )

    assert not state.persisting_effects
    assert not state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.BONDSMAN_APPLIED_STATE_KIND,
    )


def test_code_chivalric_lay_low_honours_army_from_destroyed_character_model() -> None:
    config = _config()
    state = _battle_state()
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _mark_enemy_unit_as_character(state, player_id="player-b")
    enemy = _unit_by_id(state, ENEMY_UNIT_ID)
    target_model_id = enemy.own_models[0].model_instance_id
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.LAY_LOW_THE_TYRANT,
        quality=army_rule.CodeChivalricQuality.MARTIAL_VALOUR,
        target_model_id=target_model_id,
        target_unit_id=ENEMY_UNIT_ID,
    )
    _set_current_phase(state, BattlePhase.FIGHT, active_player_id="player-b")
    decisions = DecisionController()
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "destroying_player_id": "player-a",
            "attacking_unit_instance_id": IMPERIAL_KNIGHTS_UNIT_ID,
            "target_unit_instance_id": ENEMY_UNIT_ID,
            "model_instance_id": target_model_id,
            "damage_kind": "normal",
            "damage_event_id": "phase17g-imperial-knights-lay-low-damage",
            "destroyed_model_rules_triggered": True,
        },
    )

    result = army_rule.resolve_code_chivalric_end_turn(
        _runtime_event_context(
            state=state,
            decisions=decisions,
            config=config,
            trigger_kind=TimingTriggerKind.END_TURN,
            active_player_id="player-b",
            event_suffix="lay-low",
        )
    )

    assert result.status.value == "applied"
    assert army_rule.army_is_honoured(state, player_id="player-a")
    fulfilled = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.CODE_CHIVALRIC_FULFILLED_STATE_KIND,
    )[0]
    payload = cast(dict[str, JsonValue], fulfilled.payload)
    evidence = cast(dict[str, JsonValue], payload["evidence"])
    assert evidence["model_destroyed_event_id"] == destroyed_event.event_id
    gain_payload = cast(CommandPointGainResultPayload, payload["command_point_gain"])
    assert CommandPointGainResult.from_payload(gain_payload).applied_amount == 2


def test_code_chivalric_reclaim_honours_army_at_opponent_turn_end() -> None:
    config = _config()
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0), (-2.0, 0.0)),
        player_b_offsets=((10.0, 10.0),),
    )
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED,
    )
    assert state.battlefield_state is not None
    enemy_model_ids = _unit_by_id(state, ENEMY_UNIT_ID).own_model_ids()
    state.replace_battlefield_state(state.battlefield_state.with_removed_models(enemy_model_ids))
    _set_current_phase(state, BattlePhase.FIGHT, active_player_id="player-b")

    result = army_rule.resolve_code_chivalric_end_turn(
        _runtime_event_context(
            state=state,
            decisions=DecisionController(),
            config=config,
            trigger_kind=TimingTriggerKind.END_TURN,
            active_player_id="player-b",
            event_suffix="reclaim",
        )
    )

    replay_payload = cast(dict[str, JsonValue], result.replay_payload)
    assert replay_payload["resolution"] == "oath_fulfilled"
    fulfilled = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.CODE_CHIVALRIC_FULFILLED_STATE_KIND,
    )[0]
    fulfilled_payload = cast(dict[str, JsonValue], fulfilled.payload)
    evidence = cast(dict[str, JsonValue], fulfilled_payload["evidence"])
    assert evidence["deed_completion_kind"] == army_rule.CodeChivalricDeed.RECLAIM_THE_REALM.value
    assert evidence["player_controlled_objective_count"] == 1
    assert evidence["opponent_controlled_objective_count"] == 0
    assert army_rule.army_is_honoured(state, player_id="player-a")


def test_code_chivalric_tally_uses_updated_threshold_and_returned_destroyed_units() -> None:
    config = _config()
    state = _battle_state()
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.REAP_A_GREAT_TALLY,
        quality=army_rule.CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    )
    _set_current_phase(state, BattlePhase.FIGHT, active_player_id="player-b")
    decisions = DecisionController()

    _record_enemy_unit_destroyed(
        state=state,
        decisions=decisions,
        model_destroyed_event_id_suffix="first-destruction",
    )
    army_rule.resolve_code_chivalric_end_battle_round(
        _runtime_event_context(
            state=state,
            decisions=decisions,
            config=config,
            trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
            active_player_id=None,
            event_suffix="one-destroyed-unit",
        )
    )

    assert not army_rule.army_is_honoured(state, player_id="player-a")

    _record_enemy_unit_destroyed(
        state=state,
        decisions=decisions,
        model_destroyed_event_id_suffix="returned-unit-destroyed-again",
    )
    army_rule.resolve_code_chivalric_end_battle_round(
        _runtime_event_context(
            state=state,
            decisions=decisions,
            config=config,
            trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
            active_player_id=None,
            event_suffix="two-destroyed-units",
        )
    )

    assert army_rule.army_is_honoured(state, player_id="player-a")
    fulfilled = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.CODE_CHIVALRIC_FULFILLED_STATE_KIND,
    )
    assert len(fulfilled) == 1
    payload = cast(dict[str, JsonValue], fulfilled[0].payload)
    evidence = cast(dict[str, JsonValue], payload["evidence"])
    assert evidence["battle_round_number"] == 1
    assert evidence["enemy_units_destroyed_this_battle_round"] == 2
    gain_payload = cast(CommandPointGainResultPayload, payload["command_point_gain"])
    gain = CommandPointGainResult.from_payload(gain_payload)
    assert gain.applied_amount == 2
    assert gain.transaction is not None
    assert gain.transaction.cap_exempt is True


def test_code_chivalric_tally_counts_current_phase_unit_completion_evidence() -> None:
    config = _config()
    state = _battle_state()
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.REAP_A_GREAT_TALLY,
        quality=army_rule.CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    )
    _set_current_phase(state, BattlePhase.FIGHT, active_player_id="player-b")
    decisions = DecisionController()
    _record_enemy_unit_destroyed(
        state=state,
        decisions=decisions,
        model_destroyed_event_id_suffix="recorded-hook-destruction",
    )
    enemy = _unit_by_id(state, ENEMY_UNIT_ID)
    model_id = enemy.own_models[0].model_instance_id
    decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "destroying_player_id": "player-a",
            "attacking_unit_instance_id": IMPERIAL_KNIGHTS_UNIT_ID,
            "target_unit_instance_id": ENEMY_UNIT_ID,
            "model_instance_id": model_id,
            "damage_kind": "normal",
            "damage_event_id": "phase17g-imperial-knights-current-phase-damage",
            "destroyed_model_rules_triggered": True,
        },
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(enemy.own_model_ids())
    )

    army_rule.resolve_code_chivalric_end_battle_round(
        _runtime_event_context(
            state=state,
            decisions=decisions,
            config=config,
            trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
            active_player_id=None,
            event_suffix="current-phase-destruction",
        )
    )

    assert army_rule.army_is_honoured(state, player_id="player-a")


def test_code_chivalric_eager_and_legacy_quality_modifiers() -> None:
    eager_state = _battle_state()
    _mark_player_as_imperial_knights(eager_state, player_id="player-a")
    _record_oath(
        eager_state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    )

    movement = army_rule.code_chivalric_eager_movement_modifier(
        MovementBudgetModifierContext(
            state=eager_state,
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            model_instance_id=_unit_by_id(eager_state, IMPERIAL_KNIGHTS_UNIT_ID)
            .own_models[0]
            .model_instance_id,
            base_movement_inches=10.0,
            current_movement_inches=10.0,
        )
    )
    charge_modifiers = army_rule.code_chivalric_eager_charge_modifier(
        ChargeRollModifierContext(
            state=eager_state,
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            current_roll_modifiers=(),
        )
    )

    assert movement == 12.0
    assert len(charge_modifiers) == 1
    assert charge_modifiers[0].operand == 1

    legacy_state = _battle_state()
    _mark_player_as_imperial_knights(legacy_state, player_id="player-a")
    _record_oath(
        legacy_state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED,
    )
    legacy_unit = _unit_by_id(legacy_state, IMPERIAL_KNIGHTS_UNIT_ID)
    legacy_model_id = legacy_unit.own_models[0].model_instance_id

    objective_control = army_rule.code_chivalric_legacy_objective_control_modifier(
        ObjectiveControlModifierContext(
            state=legacy_state,
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            model_instance_id=legacy_model_id,
            base_objective_control=2,
            current_objective_control=2,
        )
    )
    leadership = army_rule.code_chivalric_legacy_leadership_modifier(
        UnitCharacteristicModifierContext(
            state=legacy_state,
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            characteristic=Characteristic.LEADERSHIP,
            base_value=7,
            current_value=7,
        )
    )

    assert objective_control == 4
    assert leadership == 6


def test_code_chivalric_modifiers_noop_without_matching_quality_or_characteristic() -> None:
    state = _battle_state()
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.MARTIAL_VALOUR,
    )
    model_id = _unit_by_id(state, IMPERIAL_KNIGHTS_UNIT_ID).own_models[0].model_instance_id

    assert army_rule.selected_deed_for_player(_battle_state(), player_id="player-a") is None
    assert army_rule.selected_quality_for_player(_battle_state(), player_id="player-a") is None
    assert (
        army_rule.unit_has_code_chivalric_quality(
            _battle_state(),
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            quality=army_rule.CodeChivalricQuality.MARTIAL_VALOUR,
        )
        is False
    )
    assert (
        army_rule.code_chivalric_eager_movement_modifier(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
                model_instance_id=model_id,
                base_movement_inches=10.0,
                current_movement_inches=10.0,
            )
        )
        == 10.0
    )
    assert (
        army_rule.code_chivalric_eager_charge_modifier(
            ChargeRollModifierContext(
                state=state,
                unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
                current_roll_modifiers=(),
            )
        )
        == ()
    )
    assert (
        army_rule.code_chivalric_legacy_objective_control_modifier(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
                model_instance_id=model_id,
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 2
    )
    assert (
        army_rule.code_chivalric_legacy_leadership_modifier(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
                characteristic=Characteristic.MOVEMENT,
                base_value=7,
                current_value=7,
            )
        )
        == 7
    )
    non_martial_state = _battle_state()
    _mark_player_as_imperial_knights(non_martial_state, player_id="player-a")
    _record_oath(
        non_martial_state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    )
    _set_current_phase(non_martial_state, BattlePhase.SHOOTING, active_player_id="player-a")
    assert (
        army_rule.code_chivalric_martial_valour_shooting_grants(
            ShootingUnitSelectedContext(
                state=non_martial_state,
                player_id="player-a",
                battle_round=non_martial_state.battle_round,
                unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
                request_id="phase17g-imperial-knights-noop-shoot-request",
                result_id="phase17g-imperial-knights-noop-shoot-result",
            )
        )
        == ()
    )
    _set_current_phase(non_martial_state, BattlePhase.FIGHT, active_player_id="player-a")
    assert (
        army_rule.code_chivalric_martial_valour_fight_grants(
            FightUnitSelectedContext(
                state=non_martial_state,
                player_id="player-a",
                battle_round=non_martial_state.battle_round,
                unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
                fight_type="normal",
                ordering_band="remaining_combats",
                request_id="phase17g-imperial-knights-noop-fight-request",
                result_id="phase17g-imperial-knights-noop-fight-result",
            )
        )
        == ()
    )


def test_code_chivalric_martial_valour_grants_hit_and_wound_rerolls() -> None:
    state = _battle_state()
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.MARTIAL_VALOUR,
    )
    _set_current_phase(state, BattlePhase.SHOOTING, active_player_id="player-a")

    grants = army_rule.code_chivalric_martial_valour_shooting_grants(
        ShootingUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            request_id="phase17g-imperial-knights-shooting-request",
            result_id="phase17g-imperial-knights-shooting-result",
        )
    )
    for grant in grants:
        state.record_persisting_effect(grant.persisting_effect)

    assert len(grants) == 2
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
        )
        is not None
    )
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
        )
        is not None
    )


def test_code_chivalric_martial_valour_fight_grants_hit_and_wound_rerolls() -> None:
    state = _battle_state()
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.MARTIAL_VALOUR,
    )
    _set_current_phase(state, BattlePhase.FIGHT, active_player_id="player-a")

    grants = army_rule.code_chivalric_martial_valour_fight_grants(
        FightUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            fight_type="normal",
            ordering_band="remaining_combats",
            request_id="phase17g-imperial-knights-fight-request",
            result_id="phase17g-imperial-knights-fight-result",
        )
    )
    for grant in grants:
        state.record_persisting_effect(grant.persisting_effect)

    assert len(grants) == 2
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
        )
        is not None
    )
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
        )
        is not None
    )


def test_code_chivalric_fight_effect_registry_is_fail_fast() -> None:
    state = _battle_state()
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.MARTIAL_VALOUR,
    )
    _set_current_phase(state, BattlePhase.FIGHT, active_player_id="player-a")
    context = FightUnitSelectedContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
        fight_type="normal",
        ordering_band="remaining_combats",
        request_id="phase17g-imperial-knights-registry-fight-request",
        result_id="phase17g-imperial-knights-registry-fight-result",
    )
    valid_grant = army_rule.code_chivalric_martial_valour_fight_grants(context)[0]

    def valid_handler(_: FightUnitSelectedContext) -> tuple[FightUnitSelectedEffectGrant, ...]:
        return (valid_grant,)

    binding = FightUnitSelectedHookBinding(
        hook_id=valid_grant.hook_id,
        source_id=valid_grant.source_id,
        handler=valid_handler,
    )

    assert FightUnitSelectedHookRegistry.from_bindings((binding,)).grants_for(context) == (
        valid_grant,
    )
    assert valid_grant.to_payload()["unit_instance_id"] == IMPERIAL_KNIGHTS_UNIT_ID

    with pytest.raises(GameLifecycleError, match="persisting_effect"):
        FightUnitSelectedEffectGrant(
            hook_id="phase17g-imperial-knights-bad-effect",
            source_id=army_rule.SOURCE_RULE_ID,
            unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
            persisting_effect=cast(PersistingEffect, object()),
        )
    with pytest.raises(GameLifecycleError, match="source_id"):
        replace(valid_grant, source_id="phase17g-imperial-knights-source-drift")
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        FightUnitSelectedHookBinding(
            hook_id="phase17g-imperial-knights-bad-handler",
            source_id=army_rule.SOURCE_RULE_ID,
            handler=cast(
                Callable[
                    [FightUnitSelectedContext],
                    tuple[FightUnitSelectedEffectGrant, ...],
                ],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        FightUnitSelectedHookRegistry(bindings=cast(tuple[FightUnitSelectedHookBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="must contain FightUnitSelectedHookBinding"):
        FightUnitSelectedHookRegistry.from_bindings(
            cast(tuple[FightUnitSelectedHookBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        FightUnitSelectedHookRegistry.from_bindings((binding, binding))

    def list_handler(
        _: FightUnitSelectedContext,
    ) -> tuple[FightUnitSelectedEffectGrant, ...]:
        return cast(tuple[FightUnitSelectedEffectGrant, ...], [valid_grant])

    with pytest.raises(GameLifecycleError, match="must return a tuple"):
        FightUnitSelectedHookRegistry.from_bindings(
            (
                FightUnitSelectedHookBinding(
                    hook_id="phase17g-imperial-knights-list-handler",
                    source_id=valid_grant.source_id,
                    handler=list_handler,
                ),
            )
        ).grants_for(context)

    def object_handler(
        _: FightUnitSelectedContext,
    ) -> tuple[FightUnitSelectedEffectGrant, ...]:
        return cast(tuple[FightUnitSelectedEffectGrant, ...], (object(),))

    with pytest.raises(GameLifecycleError, match="FightUnitSelectedEffectGrant values"):
        FightUnitSelectedHookRegistry.from_bindings(
            (
                FightUnitSelectedHookBinding(
                    hook_id="phase17g-imperial-knights-object-handler",
                    source_id=valid_grant.source_id,
                    handler=object_handler,
                ),
            )
        ).grants_for(context)

    hook_drift_grant = replace(
        valid_grant,
        hook_id="phase17g-imperial-knights-hook-drift",
    )

    def hook_drift_handler(
        _: FightUnitSelectedContext,
    ) -> tuple[FightUnitSelectedEffectGrant, ...]:
        return (hook_drift_grant,)

    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        FightUnitSelectedHookRegistry.from_bindings(
            (
                FightUnitSelectedHookBinding(
                    hook_id=valid_grant.hook_id,
                    source_id=valid_grant.source_id,
                    handler=hook_drift_handler,
                ),
            )
        ).grants_for(context)

    source_drift_binding = FightUnitSelectedHookBinding(
        hook_id=valid_grant.hook_id,
        source_id="phase17g-imperial-knights-source-drift-binding",
        handler=valid_handler,
    )
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        FightUnitSelectedHookRegistry.from_bindings((source_drift_binding,)).grants_for(context)


def test_code_chivalric_unit_destroyed_hook_ignores_non_knights_and_duplicates() -> None:
    state = _battle_state()
    decisions = DecisionController()
    _set_current_phase(state, BattlePhase.FIGHT, active_player_id="player-b")
    _record_enemy_unit_destroyed(
        state=state,
        decisions=decisions,
        model_destroyed_event_id_suffix="non-knight-destruction",
    )
    assert not _event_records_of_type(decisions, army_rule.CODE_CHIVALRIC_ENEMY_DESTROYED_EVENT)

    _mark_player_as_imperial_knights(state, player_id="player-a")
    destroyed_event = _record_enemy_unit_destroyed(
        state=state,
        decisions=decisions,
        model_destroyed_event_id_suffix="knight-destruction",
    )
    count_after_first_record = len(
        _event_records_of_type(decisions, army_rule.CODE_CHIVALRIC_ENEMY_DESTROYED_EVENT)
    )
    army_rule.record_code_chivalric_enemy_unit_destroyed(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=ENEMY_UNIT_ID,
            destroyed_player_id="player-b",
        )
    )

    assert count_after_first_record == 1
    assert (
        len(_event_records_of_type(decisions, army_rule.CODE_CHIVALRIC_ENEMY_DESTROYED_EVENT)) == 1
    )


def test_code_chivalric_runtime_timing_reports_ignored_no_oath_and_already_honoured() -> None:
    config = _config()
    decisions = DecisionController()
    ignored_state = _battle_state()
    _mark_player_as_imperial_knights(ignored_state, player_id="player-a")
    ignored = army_rule.resolve_code_chivalric_end_turn(
        _runtime_event_context(
            state=ignored_state,
            decisions=decisions,
            config=config,
            trigger_kind=TimingTriggerKind.END_TURN,
            active_player_id="player-a",
            event_suffix="ignored",
            player_id="player-b",
        )
    )
    ignored_payload = cast(dict[str, JsonValue], ignored.replay_payload)
    assert ignored_payload["resolution"] == "ignored_non_imperial_knights_player"

    no_oath_state = _battle_state()
    _mark_player_as_imperial_knights(no_oath_state, player_id="player-a")
    no_oath = army_rule.resolve_code_chivalric_end_turn(
        _runtime_event_context(
            state=no_oath_state,
            decisions=DecisionController(),
            config=config,
            trigger_kind=TimingTriggerKind.END_TURN,
            active_player_id="player-a",
            event_suffix="no-oath",
        )
    )
    no_oath_payload = cast(dict[str, JsonValue], no_oath.replay_payload)
    assert no_oath_payload["resolution"] == "no_selected_oath"

    honoured_state = _battle_state()
    _mark_player_as_imperial_knights(honoured_state, player_id="player-a")
    _record_oath(
        honoured_state,
        deed=army_rule.CodeChivalricDeed.REAP_A_GREAT_TALLY,
        quality=army_rule.CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    )
    _record_honoured(honoured_state)
    already_honoured = army_rule.resolve_code_chivalric_end_battle_round(
        _runtime_event_context(
            state=honoured_state,
            decisions=DecisionController(),
            config=config,
            trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
            active_player_id=None,
            event_suffix="already-honoured",
        )
    )
    already_honoured_payload = cast(dict[str, JsonValue], already_honoured.replay_payload)
    assert already_honoured_payload["resolution"] == "already_honoured"


def test_code_chivalric_invalid_payloads_fail_fast_before_mutation() -> None:
    config = _config()
    state = _setup_state_at_declare_battle_formations(config)
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _mark_enemy_unit_as_character(state, player_id="player-b")
    decisions = DecisionController()
    request = army_rule.code_chivalric_oath_request(
        BattleFormationRequestContext(state=state, decisions=decisions, config=config)
    )

    assert request is not None
    option = _oath_option(
        request,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED,
    )
    drifted_payload = dict(cast(dict[str, JsonValue], option.payload))
    drifted_payload["submission_kind"] = "wrong_kind"
    result = replace(
        DecisionResult.for_request(
            result_id="phase17g-imperial-knights-drifted-oath-result",
            request=request,
            selected_option_id=option.option_id,
        ),
        payload=drifted_payload,
    )

    with pytest.raises(DecisionError, match="payload must match"):
        army_rule.apply_code_chivalric_oath_result(
            BattleFormationResultContext(
                state=state,
                decisions=decisions,
                config=config,
                request=request,
                result=result,
            )
        )
    assert army_rule.selected_oath_state_for_player(state, player_id="player-a") is None


def test_code_chivalric_setup_result_rejects_wrong_contexts_before_mutation() -> None:
    config = _config()
    state = _setup_state_at_declare_battle_formations(config)
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _mark_enemy_unit_as_character(state, player_id="player-b")
    decisions = DecisionController()

    other_request, other_result = _manual_oath_request_result(
        state=state,
        actor_id="player-a",
        decision_type="other_decision",
        request_hook_id=army_rule.SETUP_HOOK_ID,
        payload_hook_id=army_rule.SETUP_HOOK_ID,
        deed_id=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM.value,
        quality_id=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED.value,
    )
    assert (
        army_rule.apply_code_chivalric_oath_result(
            BattleFormationResultContext(
                state=state,
                decisions=decisions,
                config=config,
                request=other_request,
                result=other_result,
            )
        )
        is False
    )

    wrong_hook_request, wrong_hook_result = _manual_oath_request_result(
        state=state,
        actor_id="player-a",
        decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
        request_hook_id="wrong-hook",
        payload_hook_id=army_rule.SETUP_HOOK_ID,
        deed_id=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM.value,
        quality_id=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED.value,
    )
    assert (
        army_rule.apply_code_chivalric_oath_result(
            BattleFormationResultContext(
                state=state,
                decisions=decisions,
                config=config,
                request=wrong_hook_request,
                result=wrong_hook_result,
            )
        )
        is False
    )

    actorless_request, actorless_result = _manual_oath_request_result(
        state=state,
        actor_id=None,
        decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
        request_hook_id=army_rule.SETUP_HOOK_ID,
        payload_hook_id=army_rule.SETUP_HOOK_ID,
        deed_id=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM.value,
        quality_id=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED.value,
    )
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        army_rule.apply_code_chivalric_oath_result(
            BattleFormationResultContext(
                state=state,
                decisions=decisions,
                config=config,
                request=actorless_request,
                result=actorless_result,
            )
        )

    non_knight_request, non_knight_result = _manual_oath_request_result(
        state=state,
        actor_id="player-b",
        decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
        request_hook_id=army_rule.SETUP_HOOK_ID,
        payload_hook_id=army_rule.SETUP_HOOK_ID,
        deed_id=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM.value,
        quality_id=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED.value,
    )
    with pytest.raises(GameLifecycleError, match="does not own Imperial Knights"):
        army_rule.apply_code_chivalric_oath_result(
            BattleFormationResultContext(
                state=state,
                decisions=decisions,
                config=config,
                request=non_knight_request,
                result=non_knight_result,
            )
        )

    _record_oath(
        state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED,
    )
    duplicate_request, duplicate_result = _manual_oath_request_result(
        state=state,
        actor_id="player-a",
        decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
        request_hook_id=army_rule.SETUP_HOOK_ID,
        payload_hook_id=army_rule.SETUP_HOOK_ID,
        deed_id=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM.value,
        quality_id=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED.value,
    )
    with pytest.raises(GameLifecycleError, match="already selected"):
        army_rule.apply_code_chivalric_oath_result(
            BattleFormationResultContext(
                state=state,
                decisions=decisions,
                config=config,
                request=duplicate_request,
                result=duplicate_result,
            )
        )


def test_code_chivalric_unfinished_deeds_report_without_mutation() -> None:
    config = _config()
    lay_low_state = _battle_state()
    _mark_player_as_imperial_knights(lay_low_state, player_id="player-a")
    _mark_enemy_unit_as_character(lay_low_state, player_id="player-b")
    target_model_id = _unit_by_id(lay_low_state, ENEMY_UNIT_ID).own_models[0].model_instance_id
    _record_oath(
        lay_low_state,
        deed=army_rule.CodeChivalricDeed.LAY_LOW_THE_TYRANT,
        quality=army_rule.CodeChivalricQuality.MARTIAL_VALOUR,
        target_model_id=target_model_id,
        target_unit_id=ENEMY_UNIT_ID,
    )
    _set_current_phase(lay_low_state, BattlePhase.FIGHT, active_player_id="player-b")
    lay_low_result = army_rule.resolve_code_chivalric_end_turn(
        _runtime_event_context(
            state=lay_low_state,
            decisions=DecisionController(),
            config=config,
            trigger_kind=TimingTriggerKind.END_TURN,
            active_player_id="player-b",
            event_suffix="lay-low-unfinished",
        )
    )
    lay_low_payload = cast(dict[str, JsonValue], lay_low_result.replay_payload)
    assert lay_low_payload["resolution"] == "deed_not_completed"

    reclaim_state = _battle_state()
    _mark_player_as_imperial_knights(reclaim_state, player_id="player-a")
    _record_oath(
        reclaim_state,
        deed=army_rule.CodeChivalricDeed.RECLAIM_THE_REALM,
        quality=army_rule.CodeChivalricQuality.LEGACY_UNSULLIED,
    )
    _set_current_phase(reclaim_state, BattlePhase.FIGHT, active_player_id="player-a")
    reclaim_result = army_rule.resolve_code_chivalric_end_turn(
        _runtime_event_context(
            state=reclaim_state,
            decisions=DecisionController(),
            config=config,
            trigger_kind=TimingTriggerKind.END_TURN,
            active_player_id="player-a",
            event_suffix="reclaim-own-turn",
        )
    )
    reclaim_payload = cast(dict[str, JsonValue], reclaim_result.replay_payload)
    assert reclaim_payload["resolution"] == "deed_not_completed"

    tally_state = _battle_state()
    _mark_player_as_imperial_knights(tally_state, player_id="player-a")
    _record_oath(
        tally_state,
        deed=army_rule.CodeChivalricDeed.REAP_A_GREAT_TALLY,
        quality=army_rule.CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    )
    _set_current_phase(tally_state, BattlePhase.FIGHT, active_player_id="player-b")
    tally_result = army_rule.resolve_code_chivalric_end_turn(
        _runtime_event_context(
            state=tally_state,
            decisions=DecisionController(),
            config=config,
            trigger_kind=TimingTriggerKind.END_TURN,
            active_player_id="player-b",
            event_suffix="tally-wrong-trigger",
        )
    )
    tally_payload = cast(dict[str, JsonValue], tally_result.replay_payload)
    assert tally_payload["resolution"] == "deed_not_completed"


def test_code_chivalric_public_handlers_fail_fast_for_wrong_context_types() -> None:
    invalid_object = object()
    with pytest.raises(GameLifecycleError, match="request context"):
        army_rule.code_chivalric_oath_request(cast(BattleFormationRequestContext, invalid_object))
    with pytest.raises(GameLifecycleError, match="result context"):
        army_rule.apply_code_chivalric_oath_result(
            cast(BattleFormationResultContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="Bondsman requires request context"):
        army_rule.bondsman_request(cast(CommandPhaseStartRequestContext, invalid_object))
    with pytest.raises(GameLifecycleError, match="Bondsman requires result context"):
        army_rule.apply_bondsman_result(cast(CommandPhaseStartResultContext, invalid_object))
    with pytest.raises(GameLifecycleError, match="unit-destroyed hook"):
        army_rule.record_code_chivalric_enemy_unit_destroyed(
            cast(UnitDestroyedContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="end-turn handler"):
        army_rule.resolve_code_chivalric_end_turn(cast(RuntimeContentEventContext, invalid_object))
    with pytest.raises(GameLifecycleError, match="end-battle-round handler"):
        army_rule.resolve_code_chivalric_end_battle_round(
            cast(RuntimeContentEventContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="movement modifier"):
        army_rule.code_chivalric_eager_movement_modifier(
            cast(MovementBudgetModifierContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="charge modifier"):
        army_rule.code_chivalric_eager_charge_modifier(
            cast(ChargeRollModifierContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="OC modifier"):
        army_rule.code_chivalric_legacy_objective_control_modifier(
            cast(ObjectiveControlModifierContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="Leadership modifier"):
        army_rule.code_chivalric_legacy_leadership_modifier(
            cast(UnitCharacteristicModifierContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="shooting grant"):
        army_rule.code_chivalric_martial_valour_shooting_grants(
            cast(ShootingUnitSelectedContext, invalid_object)
        )
    with pytest.raises(GameLifecycleError, match="fight grant"):
        army_rule.code_chivalric_martial_valour_fight_grants(
            cast(FightUnitSelectedContext, invalid_object)
        )


def test_code_chivalric_token_and_payload_validators_are_fail_fast() -> None:
    deed_from_d6 = cast(
        Callable[[int], army_rule.CodeChivalricDeed],
        army_rule._deed_from_d6,  # pyright: ignore[reportPrivateUsage]
    )
    quality_from_d6 = cast(
        Callable[[int], army_rule.CodeChivalricQuality],
        army_rule._quality_from_d6,  # pyright: ignore[reportPrivateUsage]
    )
    deed_from_token = cast(
        Callable[[object], army_rule.CodeChivalricDeed],
        army_rule._deed_from_token,  # pyright: ignore[reportPrivateUsage]
    )
    quality_from_token = cast(
        Callable[[object], army_rule.CodeChivalricQuality],
        army_rule._quality_from_token,  # pyright: ignore[reportPrivateUsage]
    )
    selection_mode_from_token = cast(
        Callable[[object], army_rule.OathSelectionMode],
        army_rule._selection_mode_from_token,  # pyright: ignore[reportPrivateUsage]
    )
    payload_object = cast(
        Callable[[JsonValue], dict[str, JsonValue]],
        army_rule._payload_object,  # pyright: ignore[reportPrivateUsage]
    )
    payload_string = cast(
        Callable[..., str],
        army_rule._payload_string,  # pyright: ignore[reportPrivateUsage]
    )
    payload_optional_string = cast(
        Callable[..., str | None],
        army_rule._payload_optional_string,  # pyright: ignore[reportPrivateUsage]
    )
    payload_int = cast(
        Callable[..., int],
        army_rule._payload_int,  # pyright: ignore[reportPrivateUsage]
    )
    validate_identifier = cast(
        Callable[[str, object], str],
        army_rule._validate_identifier,  # pyright: ignore[reportPrivateUsage]
    )
    active_player_id = cast(
        Callable[[GameState], str],
        army_rule._active_player_id,  # pyright: ignore[reportPrivateUsage]
    )
    validate_game_state = cast(
        Callable[[object], GameState],
        army_rule._validate_game_state,  # pyright: ignore[reportPrivateUsage]
    )
    event_with_source_id_exists = cast(
        Callable[..., bool],
        army_rule._event_with_source_id_exists,  # pyright: ignore[reportPrivateUsage]
    )

    assert deed_from_d6(1) is army_rule.CodeChivalricDeed.LAY_LOW_THE_TYRANT
    assert deed_from_d6(3) is army_rule.CodeChivalricDeed.RECLAIM_THE_REALM
    assert deed_from_d6(6) is army_rule.CodeChivalricDeed.REAP_A_GREAT_TALLY
    assert quality_from_d6(1) is army_rule.CodeChivalricQuality.MARTIAL_VALOUR
    assert quality_from_d6(3) is army_rule.CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE
    assert quality_from_d6(6) is army_rule.CodeChivalricQuality.LEGACY_UNSULLIED
    assert (
        deed_from_token(army_rule.CodeChivalricDeed.RECLAIM_THE_REALM)
        is army_rule.CodeChivalricDeed.RECLAIM_THE_REALM
    )
    assert (
        quality_from_token(army_rule.CodeChivalricQuality.LEGACY_UNSULLIED)
        is army_rule.CodeChivalricQuality.LEGACY_UNSULLIED
    )
    assert (
        selection_mode_from_token(army_rule.OathSelectionMode.SELECTED)
        is army_rule.OathSelectionMode.SELECTED
    )
    assert payload_object({"key": "value"}) == {"key": "value"}
    assert payload_string({"key": "value"}, key="key") == "value"
    assert payload_optional_string({"key": None}, key="key") is None
    assert payload_int({"key": 3}, key="key") == 3
    assert validate_identifier("field", " value ") == "value"

    decisions = DecisionController()
    decisions.event_log.append("other", None)
    decisions.event_log.append("matched", {"source_rule_id": "source:matched"})
    assert event_with_source_id_exists(decisions.event_log, source_id="source:matched") is True
    assert event_with_source_id_exists(decisions.event_log, source_id="source:missing") is False

    inactive_state = _battle_state()
    inactive_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="active player"):
        active_player_id(inactive_state)
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        validate_game_state(object())
    with pytest.raises(GameLifecycleError, match="D6 value"):
        deed_from_d6(7)
    with pytest.raises(GameLifecycleError, match="D6 value"):
        quality_from_d6(0)
    with pytest.raises(GameLifecycleError, match="deed token"):
        deed_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported Code Chivalric deed"):
        deed_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="quality token"):
        quality_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported Code Chivalric quality"):
        quality_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="selection mode"):
        selection_mode_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported Code Chivalric selection mode"):
        selection_mode_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        payload_object(None)
    with pytest.raises(GameLifecycleError, match="payload missing missing"):
        payload_string({}, key="missing")
    with pytest.raises(GameLifecycleError, match="must be a string"):
        payload_string({"key": 1}, key="key")
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        payload_string({"key": " "}, key="key")
    with pytest.raises(GameLifecycleError, match="payload missing missing"):
        payload_optional_string({}, key="missing")
    with pytest.raises(GameLifecycleError, match="must be a string"):
        payload_optional_string({"key": 1}, key="key")
    with pytest.raises(GameLifecycleError, match="payload missing missing"):
        payload_int({}, key="missing")
    with pytest.raises(GameLifecycleError, match="must be an int"):
        payload_int({"key": "1"}, key="key")


def _manual_oath_request_result(
    *,
    state: GameState,
    actor_id: str | None,
    decision_type: str,
    request_hook_id: str,
    payload_hook_id: str,
    deed_id: str | None,
    quality_id: str | None,
) -> tuple[DecisionRequest, DecisionResult]:
    player_id = "player-a" if actor_id is None else actor_id
    payload = validate_json_value(
        {
            "submission_kind": army_rule.CODE_CHIVALRIC_SELECTION_KIND,
            "player_id": player_id,
            "source_rule_id": army_rule.SOURCE_RULE_ID,
            "hook_id": payload_hook_id,
            "deed_selection_mode": army_rule.OathSelectionMode.SELECTED.value,
            "deed_id": deed_id,
            "quality_selection_mode": army_rule.OathSelectionMode.SELECTED.value,
            "quality_id": quality_id,
            "lay_low_target_model_instance_id": None,
            "lay_low_target_unit_instance_id": None,
        }
    )
    request_id = state.next_decision_request_id()
    request = DecisionRequest(
        request_id=request_id,
        decision_type=decision_type,
        actor_id=actor_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "player_id": player_id,
                "faction_id": army_rule.IMPERIAL_KNIGHTS_FACTION_ID,
                "source_rule_id": army_rule.SOURCE_RULE_ID,
                "hook_id": request_hook_id,
                "state_kind": army_rule.CODE_CHIVALRIC_STATE_KIND,
                "submission_kind": army_rule.CODE_CHIVALRIC_SELECTION_KIND,
            }
        ),
        options=(
            DecisionOption(
                option_id=f"{request_id}:option",
                label="Manual Code Chivalric oath",
                payload=payload,
            ),
        ),
    )
    result = DecisionResult.for_request(
        result_id=f"{request_id}:result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    return request, result


def _oath_option(
    request: DecisionRequest,
    *,
    deed: army_rule.CodeChivalricDeed,
    quality: army_rule.CodeChivalricQuality,
) -> DecisionOption:
    for option in request.options:
        payload = cast(dict[str, JsonValue], option.payload)
        if payload.get("deed_id") == deed.value and payload.get("quality_id") == quality.value:
            return option
    raise AssertionError("missing Code Chivalric oath option")


def _random_oath_option(request: DecisionRequest) -> DecisionOption:
    for option in request.options:
        payload = cast(dict[str, JsonValue], option.payload)
        if (
            payload.get("deed_selection_mode") == army_rule.OathSelectionMode.ROLL_D6.value
            and payload.get("quality_selection_mode") == army_rule.OathSelectionMode.ROLL_D6.value
        ):
            return option
    raise AssertionError("missing random Code Chivalric oath option")


def _bondsman_apply_option(request: DecisionRequest) -> DecisionOption:
    for option in request.options:
        payload = _json_object(option.payload)
        if payload.get("selected_bondsman_option") == "apply":
            return option
    raise AssertionError("missing Bondsman application option")


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        pytest.fail("expected JSON object")
    return value


def _json_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise AssertionError(f"expected JSON string at {key}")
    return value


def _mark_player_as_imperial_knights(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_units = tuple(
            replace(unit, faction_keywords=(army_rule.IMPERIAL_KNIGHTS_FACTION_KEYWORD,))
            for unit in army.units
        )
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.IMPERIAL_KNIGHTS_FACTION_ID,
                ),
                units=updated_units,
            )
        )
    state.army_definitions = updated_armies


def _bondsman_battle_state(
    *,
    target_is_armiger: bool = True,
    target_x: float = 16.0,
) -> GameState:
    state = _battle_state(
        player_a_units=(
            _default_unit_selection("intercessor-unit-1"),
            _default_unit_selection("intercessor-unit-2"),
        ),
    )
    _mark_player_as_imperial_knights(state, player_id="player-a")
    _mark_bondsman_source_and_armiger_target(state, target_is_armiger=target_is_armiger)
    _place_unit_line(
        state,
        unit_instance_id=IMPERIAL_KNIGHTS_UNIT_ID,
        start_x=10.0,
        y=10.0,
    )
    _place_unit_line(
        state,
        unit_instance_id=BONDSMAN_ARMIGER_UNIT_ID,
        start_x=target_x,
        y=10.0,
    )
    _set_current_phase(state, BattlePhase.COMMAND, active_player_id="player-a")
    return state


def _bondsman_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=BONDSMAN_TEST_ABILITY_ID,
        name="Paladin's Duty (Bondsman)",
        source_id="phase17g:imperial-knights:paladins-duty",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        parameter_tokens=("bondsman",),
        effect_description=(
            "While a model is affected by this ability, weapons equipped by that model "
            "have the LETHAL HITS ability, and melee weapons equipped by that model "
            "have the LANCE ability."
        ),
    )


def _mark_bondsman_source_and_armiger_target(
    state: GameState,
    *,
    target_is_armiger: bool,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            datasheet_abilities = unit.datasheet_abilities
            keywords = unit.keywords
            if unit.unit_instance_id == IMPERIAL_KNIGHTS_UNIT_ID:
                datasheet_abilities = (*unit.datasheet_abilities, _bondsman_ability())
            if unit.unit_instance_id == BONDSMAN_ARMIGER_UNIT_ID and target_is_armiger:
                keywords = _with_unique_keyword(unit.keywords, army_rule.ARMIGER_KEYWORD)
            updated_units.append(
                replace(
                    unit,
                    keywords=keywords,
                    datasheet_abilities=datasheet_abilities,
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _place_unit_line(
    state: GameState,
    *,
    unit_instance_id: str,
    start_x: float,
    y: float,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    placements = tuple(
        placement.with_pose(
            Pose.at(
                start_x + float(index),
                y,
                placement.pose.position.z,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
        for index, placement in enumerate(unit_placement.model_placements)
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(placements)
    )


def _with_unique_keyword(keywords: tuple[str, ...], keyword: str) -> tuple[str, ...]:
    return tuple(sorted({*keywords, keyword}))


def _mark_enemy_unit_as_character(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(
                replace(unit, keywords=tuple(sorted({*unit.keywords, "CHARACTER"})))
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _record_oath(
    state: GameState,
    *,
    deed: army_rule.CodeChivalricDeed,
    quality: army_rule.CodeChivalricQuality,
    target_model_id: str | None = None,
    target_unit_id: str | None = None,
    reward_amount: int = 2,
) -> None:
    state.record_faction_rule_state(
        FactionRuleState(
            state_id=f"phase17g-test:imperial-knights:oath:{deed.value}:{quality.value}",
            player_id="player-a",
            faction_id=army_rule.IMPERIAL_KNIGHTS_FACTION_ID,
            source_rule_id=army_rule.SOURCE_RULE_ID,
            state_kind=army_rule.CODE_CHIVALRIC_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="phase17g-test:imperial-knights:oath-request",
            result_id="phase17g-test:imperial-knights:oath-result",
            payload={
                "selection_kind": army_rule.CODE_CHIVALRIC_SELECTION_KIND,
                "effect_kind": army_rule.CODE_CHIVALRIC_EFFECT_KIND,
                "game_id": state.game_id,
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "player_id": "player-a",
                "faction_id": army_rule.IMPERIAL_KNIGHTS_FACTION_ID,
                "source_rule_id": army_rule.SOURCE_RULE_ID,
                "hook_id": army_rule.SETUP_HOOK_ID,
                "selected_option_id": "phase17g-test:imperial-knights:oath-option",
                "deed_selection_mode": army_rule.OathSelectionMode.SELECTED.value,
                "selected_deed_id": deed.value,
                "selected_deed_label": deed.value,
                "deed_roll": None,
                "quality_selection_mode": army_rule.OathSelectionMode.SELECTED.value,
                "selected_quality_id": quality.value,
                "selected_quality_label": quality.value,
                "quality_roll": None,
                "lay_low_target_model_instance_id": target_model_id,
                "lay_low_target_unit_instance_id": target_unit_id,
                "random_selection": False,
                "command_point_reward_amount": reward_amount,
                "rules_update_sources": [army_rule.RULE_UPDATE_SOURCE],
            },
        )
    )


def _record_honoured(state: GameState) -> None:
    state.record_faction_rule_state(
        FactionRuleState(
            state_id="phase17g-test:imperial-knights:fulfilled",
            player_id="player-a",
            faction_id=army_rule.IMPERIAL_KNIGHTS_FACTION_ID,
            source_rule_id=army_rule.SOURCE_RULE_ID,
            state_kind=army_rule.CODE_CHIVALRIC_FULFILLED_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="phase17g-test:imperial-knights:fulfilled-request",
            result_id="phase17g-test:imperial-knights:fulfilled-result",
            payload={
                "effect_kind": army_rule.CODE_CHIVALRIC_EFFECT_KIND,
                "player_id": "player-a",
                "source_rule_id": army_rule.SOURCE_RULE_ID,
                "deed_id": army_rule.CodeChivalricDeed.REAP_A_GREAT_TALLY.value,
            },
        )
    )


def _record_enemy_unit_destroyed(
    *,
    state: GameState,
    decisions: DecisionController,
    model_destroyed_event_id_suffix: str,
) -> EventRecord:
    enemy = _unit_by_id(state, ENEMY_UNIT_ID)
    model = enemy.own_models[0]
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "destroying_player_id": "player-a",
            "attacking_unit_instance_id": IMPERIAL_KNIGHTS_UNIT_ID,
            "target_unit_instance_id": ENEMY_UNIT_ID,
            "model_instance_id": model.model_instance_id,
            "damage_kind": "normal",
            "damage_event_id": f"phase17g-imperial-knights:{model_destroyed_event_id_suffix}",
            "destroyed_model_rules_triggered": True,
        },
    )
    army_rule.record_code_chivalric_enemy_unit_destroyed(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=ENEMY_UNIT_ID,
            destroyed_player_id="player-b",
        )
    )
    return destroyed_event


def _event_records_of_type(
    decisions: DecisionController,
    event_type: str,
) -> tuple[EventRecord, ...]:
    return tuple(
        record for record in decisions.event_log.records if record.event_type == event_type
    )


def _runtime_event_context(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
    trigger_kind: TimingTriggerKind,
    active_player_id: str | None,
    event_suffix: str,
    player_id: str = "player-a",
) -> RuntimeContentEventContext:
    return RuntimeContentEventContext(
        event=RuntimeContentEvent(
            event_id=f"phase17g-imperial-knights-runtime-event:{event_suffix}",
            game_id=state.game_id,
            player_id=player_id,
            battle_round=state.battle_round,
            trigger_kind=trigger_kind,
            phase=None,
            active_player_id=active_player_id,
            event_payload={"event_suffix": event_suffix},
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.from_bindings(
            objective_control_modifier_bindings=(
                army_rule.runtime_contribution().objective_control_modifier_bindings
            ),
        ),
    )


def _set_current_phase(
    state: GameState,
    phase: BattlePhase,
    *,
    active_player_id: str,
) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.active_player_id = active_player_id
