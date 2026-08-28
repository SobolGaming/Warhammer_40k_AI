from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.battle_shock_historical_helpers import historical_battle_shock_context_for_unit
from tests.phase11c_command_phase_helpers import (
    battle_state,
    center_marker_definition,
    default_unit_selection,
    remove_first_models,
    unit_by_id,
    unit_selection,
    with_model_offsets,
)
from tests.setup_completion_helpers import record_current_battlefield_placements_for_fixture

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine import (
    battle_shock_resolution,
)
from warhammer40k_core.engine import (
    command_battle_shock_forced_provider_authority as forced_provider_authority,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestApplication,
    BattleShockForcedTestContext,
    BattleShockHookRegistry,
    BattleShockOutcomeContext,
    BattleShockPendingOutcomeAuthorityContext,
)
from warhammer40k_core.engine.command_battle_shock_candidates import (
    CommandBattleShockCandidate,
    CommandBattleShockCandidatePayload,
    CommandBattleShockEligibilityReason,
)
from warhammer40k_core.engine.command_battle_shock_forced_provider_authority import (
    validate_command_forced_test_applications,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
    army_rule,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookRegistry,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
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
    state = battle_state()
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


def test_harbingers_historical_leadership_recomputes_from_event_bound_aura() -> None:
    state = battle_state(game_id="phase17g-chaos-knights-historical-harbingers")
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("expected Harbingers selection request")
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-historical-despair",
        request=request,
        selected_option_id="chaos_knights:harbingers_of_dread:despair",
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
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id="army-beta:intercessor-unit-3",
    )
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    assert state.active_player_id is not None
    context = historical_battle_shock_context_for_unit(
        state=state,
        decisions=decisions,
        unit_instance_id="army-beta:intercessor-unit-3",
        active_player_id=state.active_player_id,
    )

    assert army_rule.historical_harbingers_leadership(context, 7) == 9
    with pytest.raises(GameLifecycleError, match="historical authority requires"):
        army_rule.historical_harbingers_leadership(cast(Any, object()), 7)


def test_harbingers_roll_selection_records_engine_owned_dice() -> None:
    state = battle_state()
    state.game_id = "phase17g-chaos-knights-roll-selection"
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("expected Harbingers selection request")
    decisions.request_decision(request)

    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-roll",
        request=request,
        selected_option_id=army_rule.ROLL_SELECTION_OPTION_ID,
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

    selected_payload = _event_payload(decisions, "chaos_knights_harbingers_of_dread_selected")
    dice_values = cast(list[int], selected_payload["dice_values"])
    selected_ids = cast(list[str], selected_payload["selected_dread_ability_ids"])
    assert selected_payload["selection_mode"] == "roll_2d6"
    assert len(dice_values) == 2
    assert all(type(value) is int and 1 <= value <= 6 for value in dice_values)
    assert set(selected_ids) <= {ability.value for ability in army_rule.ROLLABLE_DREAD_ABILITIES}
    assert len(set(selected_ids)) == len(selected_ids)
    historical = forced_provider_authority.historical_harbingers_abilities(
        state=state,
        event_records=tuple(decisions.event_log.records),
        decision_records=decisions.records,
        snapshot_index=len(decisions.event_log.records),
    )
    assert historical["player-a"] == army_rule.active_dread_abilities_for_player(
        state,
        player_id="player-a",
    )


def test_harbingers_rejects_stale_selection_after_active_dread_drift() -> None:
    state = battle_state()
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
    state = battle_state()
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

    exhausted_state = battle_state()
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

    no_harbingers_units_state = battle_state()
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
    state = battle_state()
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
    deathly_state = battle_state()
    _mark_player_as_chaos_knights(deathly_state, player_id="player-a")
    _record_harbingers_selection(
        deathly_state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DEATHLY_TERROR,),
    )
    with pytest.raises(GameLifecycleError, match="Deathly Terror must not be selected"):
        army_rule.active_dread_abilities_for_player(deathly_state, player_id="player-a")

    duplicate_ability_state = battle_state()
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

    duplicate_round_state = battle_state()
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
    state = battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DISMAY,),
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    remove_first_models(state, unit_instance_id=target_unit_id, count=1)
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


@pytest.mark.parametrize("tamper", ["deletion", "insertion", "hook", "source"])
def test_command_restore_rejects_harbingers_forced_application_drift(tamper: str) -> None:
    state = battle_state(
        game_id=f"phase17g-chaos-knights-forced-authority-{tamper}",
        player_b_units=(
            default_unit_selection("near-unit"),
            default_unit_selection("far-unit"),
        ),
    )
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    battle_round_hooks = _battle_round_start_hooks()
    selection_request = battle_round_hooks.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if selection_request is None:
        raise AssertionError("expected Harbingers selection request")
    queued = decisions.request_decision(selection_request)
    selection_result = DecisionResult.for_request(
        result_id=f"phase17g-chaos-knights-select-dismay-{tamper}",
        request=queued,
        selected_option_id="chaos_knights:harbingers_of_dread:dismay",
    )
    decisions.submit_result(selection_result)
    assert battle_round_hooks.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=queued,
            result=selection_result,
        )
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:near-unit"
    remove_first_models(state, unit_instance_id=target_unit_id, count=1)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    assert state.battlefield_state is not None
    marker = center_marker_definition(state)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            state.battlefield_state.unit_placement_by_id("army-beta:far-unit"),
            marker,
            offsets=((20.0, 0.0), (20.4, 0.0), (20.8, 0.0), (21.2, 0.0), (21.6, 0.0)),
        )
    )
    CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_battle_shock_hooks(),
    ).begin_phase(state=state, decisions=decisions)
    snapshot_index, snapshot = next(
        (index, event)
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "battle_shock_step_snapshot_created"
    )
    assert isinstance(snapshot.payload, dict)
    raw_candidates = snapshot.payload["battle_shock_candidate_inventory"]
    assert isinstance(raw_candidates, list)
    candidates = tuple(
        CommandBattleShockCandidate.from_payload(
            cast(CommandBattleShockCandidatePayload, candidate)
        )
        for candidate in raw_candidates
        if isinstance(candidate, dict)
    )
    ability_indexes = {
        "player-a": AbilityCatalogIndex.from_records(()),
        "player-b": AbilityCatalogIndex.from_records(()),
    }
    validate_command_forced_test_applications(
        state=state,
        event_records=tuple(decisions.event_log.records),
        decision_records=decisions.records,
        snapshot_index=snapshot_index,
        battle_round=1,
        active_player_id="player-b",
        candidates=candidates,
        battle_shock_hook_registry=_battle_shock_hooks(),
        ability_indexes_by_player_id=ability_indexes,
    )
    forced_index = next(
        index for index, candidate in enumerate(candidates) if candidate.forced_test_applications
    )
    forced_candidate = candidates[forced_index]
    application = forced_candidate.forced_test_applications[0]
    if tamper == "deletion":
        replacement = replace(
            forced_candidate,
            eligibility_reasons=tuple(
                reason
                for reason in forced_candidate.eligibility_reasons
                if reason is not CommandBattleShockEligibilityReason.BELOW_STARTING_STRENGTH_FORCED
            ),
            forced_test_applications=(),
        )
    elif tamper in {"hook", "source"}:
        replacement = replace(
            forced_candidate,
            forced_test_applications=(
                BattleShockForcedTestApplication(
                    hook_id=f"{application.hook_id}:forged"
                    if tamper == "hook"
                    else application.hook_id,
                    source_id=f"{application.source_id}:forged"
                    if tamper == "source"
                    else application.source_id,
                    unit_instance_ids=(forced_candidate.unit_instance_id,),
                ),
            ),
        )
    else:
        unforced_index = next(
            index
            for index, candidate in enumerate(candidates)
            if not candidate.forced_test_applications
        )
        forced_index = unforced_index
        unforced = candidates[unforced_index]
        forged_context = replace(
            unforced.below_half_strength_context,
            current_model_count=unforced.below_half_strength_context.starting_model_count - 1,
        )
        replacement = replace(
            unforced,
            below_half_strength_context=forged_context,
            eligibility_reasons=(
                *unforced.eligibility_reasons,
                CommandBattleShockEligibilityReason.BELOW_STARTING_STRENGTH_FORCED,
            ),
            forced_test_applications=(
                BattleShockForcedTestApplication(
                    hook_id=application.hook_id,
                    source_id=application.source_id,
                    unit_instance_ids=(unforced.unit_instance_id,),
                ),
            ),
        )
    tampered = tuple(
        replacement if index == forced_index else candidate
        for index, candidate in enumerate(candidates)
    )

    with pytest.raises(GameLifecycleError, match="forced-test applications drifted"):
        validate_command_forced_test_applications(
            state=state,
            event_records=tuple(decisions.event_log.records),
            decision_records=decisions.records,
            snapshot_index=snapshot_index,
            battle_round=1,
            active_player_id="player-b",
            candidates=tampered,
            battle_shock_hook_registry=_battle_shock_hooks(),
            ability_indexes_by_player_id=ability_indexes,
        )


def test_delirium_applies_mortal_wounds_after_failed_battle_shock() -> None:
    state = battle_state(game_id="phase17g-chaos-knights-delirium")
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(army_rule.DreadAbility.DELIRIUM,),
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    _replace_unit_leadership(state, unit_instance_id=target_unit_id, leadership=13)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    starting_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
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
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )
    assert final_wounds < starting_wounds


def test_harbingers_uses_attached_rules_unit_identity_for_forced_test_and_outcome() -> None:
    state = battle_state(
        game_id="phase17g-chaos-knights-attached-battle-shock",
        player_b_units=(
            default_unit_selection("bodyguard-unit"),
            unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_b_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )
    _mark_player_as_chaos_knights(state, player_id="player-a")
    _record_harbingers_selection(
        state,
        player_id="player-a",
        selected=(
            army_rule.DreadAbility.DISMAY,
            army_rule.DreadAbility.DELIRIUM,
        ),
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_army = state.army_definition_for_player("player-b")
    assert target_army is not None
    formation = target_army.attached_units[0]
    attached_id = formation.attached_unit_instance_id
    bodyguard_id = formation.bodyguard_unit_instance_id
    leader_id = formation.leader_unit_instance_ids[0]
    remove_first_models(state, unit_instance_id=bodyguard_id, count=4)
    _replace_unit_leadership(state, unit_instance_id=bodyguard_id, leadership=13)
    _replace_unit_leadership(state, unit_instance_id=leader_id, leadership=13)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=bodyguard_id,
    )
    starting_wounds = sum(
        model.wounds_remaining
        for unit_id in (bodyguard_id, leader_id)
        for model in unit_by_id(state, unit_id).own_models
    )
    decisions = DecisionController()

    completed = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_battle_shock_hooks(),
    ).begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    requested = _event_payload(decisions, "battle_shock_test_requested")
    request_payload = cast(dict[str, JsonValue], requested["battle_shock_test_request"])
    assert request_payload["unit_instance_id"] == attached_id
    assert request_payload["reason"] == "below_starting_strength_forced"
    delirium = _event_payload(decisions, "chaos_knights_delirium_mortal_wounds_applied")
    assert delirium["target_unit_instance_id"] == attached_id
    application = cast(dict[str, JsonValue], delirium["mortal_wound_application"])
    assert application["target_unit_instance_id"] == attached_id
    final_wounds = sum(
        model.wounds_remaining
        for unit_id in (bodyguard_id, leader_id)
        for model in unit_by_id(state, unit_id).own_models
    )
    assert final_wounds < starting_wounds


def test_harbingers_source_geometry_does_not_expand_to_attached_bodyguards() -> None:
    source_bodyguard_id = "army-alpha:dread-bodyguard"
    source_leader_id = "army-alpha:dread-leader"
    target_unit_id = "army-beta:intercessor-unit-3"
    state = battle_state(
        game_id="phase17g-chaos-knights-attached-source-geometry",
        player_a_units=(
            default_unit_selection("dread-bodyguard"),
            unit_selection(
                unit_selection_id="dread-leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="dread-leader",
                bodyguard_unit_selection_id="dread-bodyguard",
            ),
        ),
    )
    _mark_player_faction_only_as_chaos_knights(state, player_id="player-a")
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(unit, faction_keywords=(army_rule.CHAOS_KNIGHTS_FACTION_KEYWORD,))
                if unit.unit_instance_id == source_leader_id
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            state.battlefield_state.unit_placement_by_id(source_leader_id),
            marker,
            offsets=((-15.0, 0.0),),
        )
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(
            state.battlefield_state.unit_placement_by_id(source_bodyguard_id),
            marker,
            offsets=((0.0, 0.0), (0.4, 0.0), (0.8, 0.0), (1.2, 0.0), (1.6, 0.0)),
        )
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(
            state.battlefield_state.unit_placement_by_id(target_unit_id),
            marker,
            offsets=((3.0, 0.0), (3.4, 0.0), (3.8, 0.0), (4.2, 0.0), (4.6, 0.0)),
        )
    )
    state.battlefield_state = battlefield_state
    dread_army = state.army_definition_for_player("player-a")
    assert dread_army is not None

    assert not army_rule._unit_within_dread_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        dread_army=dread_army,
        target_unit_instance_id=target_unit_id,
    )


def test_delirium_routes_mortal_wound_fnp_choices_and_resumes_command_step() -> None:
    state = battle_state()
    state.game_id = "phase17g-chaos-knights-delirium-fnp"
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    _record_real_harbingers_selection(
        state,
        decisions=decisions,
        player_id="player-a",
        selected=army_rule.DreadAbility.DELIRIUM,
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    _replace_unit_leadership(state, unit_instance_id=target_unit_id, leadership=13)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    target_unit = unit_by_id(state, target_unit_id)
    fnp_model = next(model for model in target_unit.own_models if model.is_alive)
    state.record_model_feel_no_pain_sources(
        model_instance_id=fnp_model.model_instance_id,
        sources=(FeelNoPainSource(source_id="phase17g-chaos-knights-fnp", threshold=5),),
        decline_allowed=True,
    )
    starting_wounds = sum(model.wounds_remaining for model in target_unit.own_models)
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_battle_shock_hooks(),
    )

    waiting = handler.begin_phase(state=state, decisions=decisions)

    assert waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = waiting.decision_request
    assert request is not None
    hooks = _battle_shock_hooks()
    pending_authority = hooks.pending_outcome_authority_for(
        BattleShockPendingOutcomeAuthorityContext(
            state=state,
            decisions=decisions,
            request=request,
        )
    )
    assert pending_authority is not None
    assert pending_authority.result.result_id == cast(
        str,
        _event_payload(decisions, "chaos_knights_delirium_mortal_wounds_pending")[
            "battle_shock_result_id"
        ],
    )
    contribution = army_rule.runtime_contribution()
    registry = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
        contribution.mortal_wound_feel_no_pain_hook_bindings
    )
    while request is not None:
        request_payload = cast(dict[str, JsonValue], request.payload)
        lost_wound_context = cast(
            dict[str, JsonValue],
            request_payload["lost_wound_context"],
        )
        result = DecisionResult.for_request(
            result_id=f"phase17g-chaos-knights-delirium-fnp-{request.request_id}",
            request=request,
            selected_option_id="decline",
        )
        decisions.submit_result(result)
        continuation = registry.apply_decision(
            MortalWoundFeelNoPainContinuationContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
                source_context=lost_wound_context["source_context"],
                dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
                runtime_modifier_registry=_runtime_modifier_registry(),
                battle_shock_hooks=hooks,
                ability_indexes_by_player_id={},
            )
        )
        request = None if continuation is None else continuation.decision_request
    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    applied_payload = _event_payload(decisions, "chaos_knights_delirium_mortal_wounds_applied")
    assert applied_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert applied_payload["feel_no_pain_result_id"] is not None
    final_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )
    assert final_wounds < starting_wounds


def test_delirium_applies_immediate_damage_in_non_command_phase() -> None:
    state, decisions, target_unit_id = _delirium_outcome_fixture(
        game_id="phase17g-chaos-knights-delirium-shooting-immediate",
        phase=BattlePhase.SHOOTING,
        with_feel_no_pain=False,
    )
    starting_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )

    _resolve_failed_delirium_battle_shock(
        state=state,
        decisions=decisions,
        target_unit_id=target_unit_id,
        phase=BattlePhase.SHOOTING,
    )

    applied = _event_payload(decisions, "chaos_knights_delirium_mortal_wounds_applied")
    assert applied["phase"] == BattlePhase.SHOOTING.value
    assert not decisions.queue.pending_requests
    assert (
        sum(model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models)
        < starting_wounds
    )


def test_delirium_non_command_fnp_round_trips_and_resumes_from_retained_phase() -> None:
    state, decisions, target_unit_id = _delirium_outcome_fixture(
        game_id="phase17g-chaos-knights-delirium-shooting-fnp",
        phase=BattlePhase.SHOOTING,
        with_feel_no_pain=True,
    )
    _resolve_failed_delirium_battle_shock(
        state=state,
        decisions=decisions,
        target_unit_id=target_unit_id,
        phase=BattlePhase.SHOOTING,
    )
    restored_state = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    restored_decisions = DecisionController.from_payload(
        json.loads(json.dumps(decisions.to_payload()))
    )
    request = restored_decisions.queue.peek_next()
    authority = _battle_shock_hooks().pending_outcome_authority_for(
        BattleShockPendingOutcomeAuthorityContext(
            state=restored_state,
            decisions=restored_decisions,
            request=request,
        )
    )
    assert authority is not None
    assert authority.result.request.unit_instance_id == target_unit_id
    registry = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
        army_rule.runtime_contribution().mortal_wound_feel_no_pain_hook_bindings
    )
    while restored_decisions.queue.pending_requests:
        request = restored_decisions.queue.peek_next()
        request_payload = cast(dict[str, JsonValue], request.payload)
        lost_wound_context = cast(dict[str, JsonValue], request_payload["lost_wound_context"])
        result = DecisionResult.for_request(
            result_id=f"phase17g-delirium-shooting-fnp:{request.request_id}",
            request=request,
            selected_option_id="decline",
        )
        restored_decisions.submit_result(result)
        continuation = registry.apply_decision(
            MortalWoundFeelNoPainContinuationContext(
                state=restored_state,
                decisions=restored_decisions,
                request=request,
                result=result,
                source_context=lost_wound_context["source_context"],
                dice_manager=DiceRollManager(
                    restored_state.game_id,
                    event_log=restored_decisions.event_log,
                ),
                runtime_modifier_registry=_runtime_modifier_registry(),
                battle_shock_hooks=_battle_shock_hooks(),
                ability_indexes_by_player_id={},
            )
        )
        if continuation is not None:
            assert isinstance(continuation.payload, dict)
            assert continuation.payload["phase"] == BattlePhase.SHOOTING.value
    applied = _event_payload(
        restored_decisions,
        "chaos_knights_delirium_mortal_wounds_applied",
    )
    assert applied["phase"] == BattlePhase.SHOOTING.value


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "wound_count",
        "d3_payload",
        "missing_d3",
        "duplicate_d3",
        "wrong_chaos_knights_player",
        "inactive_delirium",
        "target_not_below_half",
        "target_out_of_aura",
    ],
)
def test_delirium_pending_authority_rejects_source_and_predicate_tamper(
    tamper_kind: str,
) -> None:
    state, decisions, target_unit_id = _delirium_outcome_fixture(
        game_id=f"phase17g-chaos-knights-delirium-tamper:{tamper_kind}",
        phase=BattlePhase.SHOOTING,
        with_feel_no_pain=True,
    )
    _resolve_failed_delirium_battle_shock(
        state=state,
        decisions=decisions,
        target_unit_id=target_unit_id,
        phase=BattlePhase.SHOOTING,
    )
    forged_state = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    decisions_payload = cast(dict[str, Any], deepcopy(decisions.to_payload()))
    pending_payload = cast(
        dict[str, Any],
        cast(list[dict[str, Any]], decisions_payload["queue"]["pending_requests"])[0]["payload"],
    )
    lost_wound_context = cast(dict[str, Any], pending_payload["lost_wound_context"])
    source_context = cast(dict[str, Any], lost_wound_context["source_context"])
    resolution_payload = cast(dict[str, Any], source_context["resolution_payload"])
    if tamper_kind == "wound_count":
        lost_wound_context["mortal_wounds"] = int(lost_wound_context["mortal_wounds"]) + 1
        lost_wound_context["remaining_mortal_wounds"] = (
            int(lost_wound_context["remaining_mortal_wounds"]) + 1
        )
    elif tamper_kind == "d3_payload":
        d3_payload = cast(dict[str, Any], resolution_payload["d3_result"])
        source_roll = cast(dict[str, Any], d3_payload["source_d6_result"])
        replacement = 1 if source_roll["values"] != [1] else 6
        source_roll["values"] = [replacement]
        source_roll["total"] = replacement
        d3_payload["value"] = (replacement + 1) // 2
    elif tamper_kind in {"missing_d3", "duplicate_d3"}:
        events = cast(list[dict[str, Any]], decisions_payload["event_log"])
        d3_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "dice_rolled"
            and cast(dict[str, Any], event["payload"])["spec"]["roll_type"]
            == army_rule.HARBINGERS_DELIRIUM_D3_ROLL_TYPE
        )
        if tamper_kind == "missing_d3":
            events.pop(d3_index)
        else:
            events.insert(d3_index + 1, deepcopy(events[d3_index]))
        for index, event in enumerate(events, start=1):
            event["event_id"] = f"event-{index:06d}"
    elif tamper_kind == "wrong_chaos_knights_player":
        resolution_payload["player_id"] = "player-b"
    elif tamper_kind == "inactive_delirium":
        selection_event = next(
            event
            for event in cast(list[dict[str, Any]], decisions_payload["event_log"])
            if event["event_type"] == "chaos_knights_harbingers_of_dread_selected"
        )
        selection_event["event_type"] = "unrelated_harbingers_event"
    elif tamper_kind == "target_not_below_half":
        target_record = next(
            record
            for record in forged_state.starting_strength_records
            if record.unit_instance_id == target_unit_id
        )
        alive_count = sum(
            model.is_alive for model in unit_by_id(forged_state, target_unit_id).own_models
        )
        forged_state.starting_strength_records = [
            replace(target_record, starting_model_count=alive_count)
            if record == target_record
            else record
            for record in forged_state.starting_strength_records
        ]
    else:
        _place_source_outside_dread_aura(forged_state)
    forged_decisions = DecisionController.from_payload(
        cast(DecisionControllerPayload, decisions_payload)
    )
    forged_request = forged_decisions.queue.peek_next()

    with pytest.raises(GameLifecycleError):
        _battle_shock_hooks().pending_outcome_authority_for(
            BattleShockPendingOutcomeAuthorityContext(
                state=forged_state,
                decisions=forged_decisions,
                request=forged_request,
            )
        )


def test_deathly_terror_and_despair_worsen_enemy_leadership_in_aura() -> None:
    state = battle_state()
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
    state = battle_state()
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
    chaos_model_id = (
        unit_by_id(
            state,
            "army-alpha:intercessor-unit-1",
        )
        .own_models[0]
        .model_instance_id
    )
    enemy_model_id = unit_by_id(state, target_unit_id).own_models[0].model_instance_id

    wound_modifier = registry.wound_roll_modifier(
        WoundRollModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id="army-alpha:intercessor-unit-1",
            attacker_model_instance_id=chaos_model_id,
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
            attacker_model_instance_id=enemy_model_id,
            target_unit_instance_id="army-alpha:intercessor-unit-1",
            weapon_profile=profile,
            source_phase=BattlePhase.SHOOTING,
        )
    )

    assert wound_modifier == 1
    assert hit_modifier == -1


def test_harbingers_modifiers_return_neutral_outside_required_contexts() -> None:
    state = battle_state()
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
    enemy_model_id = unit_by_id(state, target_unit_id).own_models[0].model_instance_id

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
                attacker_model_instance_id=enemy_model_id,
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
                attacker_model_instance_id=enemy_model_id,
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
    assert contribution.mortal_wound_feel_no_pain_hook_bindings[0].source_id == record.execution_id
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
    state = battle_state()
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    request = _battle_round_start_hooks().next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("expected Harbingers selection request")
    return state, decisions, request


def _record_real_harbingers_selection(
    state: GameState,
    *,
    decisions: DecisionController,
    player_id: str,
    selected: army_rule.DreadAbility,
) -> None:
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None or request.actor_id != player_id:
        raise AssertionError("expected Harbingers selection request")
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id=f"phase17g-real-harbingers:{state.game_id}:{selected.value}",
        request=request,
        selected_option_id=f"chaos_knights:harbingers_of_dread:{selected.value}",
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


def _delirium_outcome_fixture(
    *,
    game_id: str,
    phase: BattlePhase,
    with_feel_no_pain: bool,
) -> tuple[GameState, DecisionController, str]:
    state = battle_state(game_id=game_id)
    _mark_player_as_chaos_knights(state, player_id="player-a")
    decisions = DecisionController()
    _record_real_harbingers_selection(
        state,
        decisions=decisions,
        player_id="player-a",
        selected=army_rule.DreadAbility.DELIRIUM,
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    target_unit_id = "army-beta:intercessor-unit-3"
    remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    if with_feel_no_pain:
        target = unit_by_id(state, target_unit_id)
        model = next(model for model in target.own_models if model.is_alive)
        state.record_model_feel_no_pain_sources(
            model_instance_id=model.model_instance_id,
            sources=(FeelNoPainSource(source_id=f"{game_id}:fnp", threshold=5),),
            decline_allowed=True,
        )
    return state, decisions, target_unit_id


def _resolve_failed_delirium_battle_shock(
    *,
    state: GameState,
    decisions: DecisionController,
    target_unit_id: str,
    phase: BattlePhase,
) -> None:
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    request = BattleShockTestRequest.for_unit(
        request_id=f"{state.game_id}:battle-shock",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=target.owner_player_id,
        unit_instance_id=target.unit_instance_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=13,
        below_half_strength_context=BelowHalfStrengthContext.from_rules_unit(
            rules_unit=target,
            starting_strength=state.starting_strength_record_for_unit(target.unit_instance_id),
            current_model_ids=tuple(model.model_instance_id for model in target.alive_models()),
        ),
    )
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise AssertionError("Delirium outcome fixture requires an active player")
    base_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": phase.value,
        "source_kind": "phase17g_delirium_non_command_test",
    }
    decisions.event_log.append(
        "battle_shock_test_requested",
        {
            **base_payload,
            "battle_shock_test_request": request.to_payload(),
        },
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    resolved = battle_shock_resolution.resolve_battle_shock_test_with_optional_reroll(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=_battle_shock_hooks(),
        request=request,
        roll_state=manager.roll_fixed(request.spec, (1, 1)),
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=(),
        passed_state_policy=battle_shock_resolution.BattleShockPassedStatePolicy.PRESERVE,
        source_kind="phase17g_delirium_non_command_test",
        base_payload=base_payload,
        resolved_event_types=("battle_shock_test_resolved",),
        pending_phase_body_status="phase17g_delirium_battle_shock_pending",
    )
    assert resolved.resolved_payload is not None


def _place_source_outside_dread_aura(state: GameState) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Delirium aura fixture requires battlefield state")
    source_unit_id = "army-alpha:intercessor-unit-1"
    source = state.battlefield_state.unit_placement_by_id(source_unit_id)
    marker = center_marker_definition(state)
    offsets = tuple((-20.0 - index, 0.0) for index in range(len(source.model_placements)))
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(source, marker, offsets=offsets)
    )


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
    marker = center_marker_definition(state)
    source = state.battlefield_state.unit_placement_by_id(source_unit_id)
    target = state.battlefield_state.unit_placement_by_id(target_unit_id)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(source, marker, offsets=((0.0, 0.0),))
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(target, marker, offsets=((1.0, 0.0),))
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
