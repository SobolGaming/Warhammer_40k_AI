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
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    remove_first_models,
    secondary_choice,
    unit_by_id,
    unit_selection,
    with_model_offsets,
)
from tests.setup_completion_helpers import record_current_battlefield_placements_for_fixture

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import (
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.faction import FactionDefinition
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
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequenceStep
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
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
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestApplication,
    BattleShockForcedTestContext,
    BattleShockHookBinding,
    BattleShockHookRegistry,
    BattleShockOutcomeContext,
    BattleShockPendingOutcomeAuthorityContext,
    BattleShockRerollPermissionContext,
    HistoricalBattleShockContribution,
)
from warhammer40k_core.engine.catalog_selected_target_battle_shock_continuation import (
    CatalogSelectedTargetBattleShockContinuationPhase,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    CATALOG_SHOOTING_START_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
    CatalogSelectedTargetEffectRuntime,
)
from warhammer40k_core.engine.command_battle_shock_candidates import (
    CommandBattleShockCandidate,
    CommandBattleShockCandidatePayload,
    CommandBattleShockEligibilityReason,
)
from warhammer40k_core.engine.command_battle_shock_forced_provider_authority import (
    validate_command_forced_test_applications,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    FeelNoPainSource,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
)
from warhammer40k_core.engine.decision import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.runtime import (
    runtime_content_activation_for_armies,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
    army_rule,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.game_state import (
    GameState,
    GameStatePayload,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import AttachmentDeclaration, DetachmentSelection
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
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
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParameter,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
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


def test_delirium_pending_restore_and_submission_use_loaded_provider_authority() -> None:
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id="phase17g-chaos-knights-delirium-lifecycle-pending",
        with_feel_no_pain=True,
    )
    restored = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            json.loads(json.dumps(lifecycle.to_payload())),
        ),
        runtime_content_bundle=bundle,
    )
    request = restored.decision_controller.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-delirium-lifecycle-pending:decline",
        request=request,
        selected_option_id="decline",
    )
    events = restored.decision_controller.event_log.records
    marker_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "chaos_knights_delirium_mortal_wounds_pending"
    )
    marker = events[marker_index]
    marker_payload = cast(dict[str, JsonValue], marker.payload)
    drifted_events = list(events)
    drifted_events[marker_index] = replace(
        marker,
        payload={
            **marker_payload,
            "remaining_mortal_wounds": cast(int, marker_payload["remaining_mortal_wounds"]) + 1,
        },
    )
    restored.decision_controller.event_log.replace_records(tuple(drifted_events))
    before_state = restored.state.to_payload() if restored.state is not None else None
    before_queue = restored.decision_controller.queue.pending_requests
    before_records = restored.decision_controller.records

    with pytest.raises(GameLifecycleError, match="pending marker authority drifted"):
        restored.submit_decision(result)

    assert restored.decision_controller.queue.pending_requests == before_queue
    assert restored.decision_controller.records == before_records
    assert restored.state is not None
    assert restored.state.to_payload() == before_state


def test_selected_target_direct_battle_shock_waits_for_delirium_outcome_via_facade() -> None:
    _assert_selected_target_delirium_continuation(reroll=False)


def test_selected_target_rerolled_battle_shock_waits_for_delirium_outcome_via_facade() -> None:
    _assert_selected_target_delirium_continuation(reroll=True)


def test_selected_target_later_battle_shock_reroll_retains_parent_via_facade() -> None:
    game_id = "phase17g-selected-target-later-battle-shock-reroll"
    selected_target_record = _selected_target_two_battle_shocks_then_modifier_record()

    def reroll_permission(
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        if not context.request.request_id.endswith(":001"):
            return None
        return RerollPermission(
            source_id="phase17g:test:selected-target-later-reroll",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    def historical_contribution(
        context: HistoricalBattleShockAuthorityContext,
    ) -> HistoricalBattleShockContribution:
        if not context.request.request_id.endswith(":001"):
            return HistoricalBattleShockContribution()
        return HistoricalBattleShockContribution(
            reroll_permission=RerollPermission(
                source_id="phase17g:test:selected-target-later-reroll",
                timing_window="battle_shock_test",
                owning_player_id=context.request.player_id,
                eligible_roll_type=context.request.spec.roll_type,
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            )
        )

    contribution = RuntimeContentContribution(
        contribution_id="phase17g:test:selected-target-later-reroll",
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id="phase17g:test:selected-target-later-reroll",
                source_id="phase17g:test:selected-target-later-reroll",
                reroll_permission_handler=reroll_permission,
                historical_contribution_handler=historical_contribution,
            ),
        ),
    )
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id=game_id,
        with_feel_no_pain=True,
        selected_target_record=selected_target_record,
        target_starting_wounds=50,
        begin_command_phase=False,
        extra_contributions=(contribution,),
    )
    lifecycle = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    _queue_selected_target_delirium_request(
        lifecycle=lifecycle,
        selected_target_record=selected_target_record,
    )
    initial_payload = deepcopy(lifecycle.to_payload())
    initial_record_count = len(lifecycle.decision_controller.records)
    session = LocalGameSession(lifecycle=lifecycle)
    selected_request = lifecycle.decision_controller.queue.peek_next()
    first_provider_status = session.submit_option(
        request_id=selected_request.request_id,
        option_id=selected_request.options[0].option_id,
        result_id=f"{game_id}:selected-target-result",
    )
    first_provider_request = lifecycle.decision_controller.queue.peek_next()
    assert first_provider_status.decision_request == first_provider_request
    assert first_provider_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert lifecycle.decision_controller.queue.pending_requests == (first_provider_request,)

    state = lifecycle.state
    if state is None:
        raise AssertionError("selected-target later-reroll fixture requires state")
    for provider_decision_index in range(50):
        current_request = lifecycle.decision_controller.queue.peek_next()
        if current_request.decision_type == DICE_REROLL_DECISION_TYPE:
            break
        assert current_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
        status = session.submit_option(
            request_id=current_request.request_id,
            option_id="decline",
            result_id=f"{game_id}:first-provider:{provider_decision_index}",
        )
        assert status.decision_request == lifecycle.decision_controller.queue.peek_next()
    else:
        raise AssertionError("first provider outcome did not reach the later Battle-shock reroll")

    reroll_request = lifecycle.decision_controller.queue.peek_next()
    assert lifecycle.decision_controller.queue.pending_requests == (reroll_request,)
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    assert continuation is not None
    assert continuation.continuation_phase is (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_BATTLE_SHOCK_REROLL
    )
    assert len(state.persisting_effects) == 0
    assert not _events_of_type(
        lifecycle.decision_controller,
        CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    )

    restored = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    if restored.state is None:
        raise AssertionError("restored selected-target later-reroll fixture requires state")
    restored_continuation = restored.state.pending_catalog_selected_target_battle_shock_continuation
    assert restored_continuation is not None
    assert restored_continuation.to_payload() == continuation.to_payload()
    restored_session = LocalGameSession(lifecycle=restored)
    reroll_request = restored.decision_controller.queue.peek_next()
    reroll_option_id = next(
        option.option_id for option in reroll_request.options if option.option_id != "decline"
    )
    second_provider_status = restored_session.submit_option(
        request_id=reroll_request.request_id,
        option_id=reroll_option_id,
        result_id=f"{game_id}:later-reroll-result",
    )
    second_provider_request = restored.decision_controller.queue.peek_next()
    assert second_provider_status.decision_request == second_provider_request
    assert second_provider_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert restored.decision_controller.queue.pending_requests == (second_provider_request,)
    assert len(restored.state.persisting_effects) == 0

    for provider_decision_index in range(50):
        remaining_continuation = (
            restored.state.pending_catalog_selected_target_battle_shock_continuation
        )
        if remaining_continuation is None:
            break
        current_request = restored.decision_controller.queue.peek_next()
        assert current_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
        restored_session.submit_option(
            request_id=current_request.request_id,
            option_id="decline",
            result_id=f"{game_id}:second-provider:{provider_decision_index}",
        )
        if restored.state.pending_catalog_selected_target_battle_shock_continuation is None:
            break
        assert len(restored.state.persisting_effects) == 0
    else:
        raise AssertionError("second provider outcome did not close")

    assert len(restored.state.persisting_effects) == 1
    requested = _events_of_type(restored.decision_controller, "battle_shock_test_requested")
    resolved = _events_of_type(
        restored.decision_controller,
        "battle_shock_test_resolved",
        source_kind="catalog_selected_target_effect",
    )
    assert len(requested) == 2
    assert len(resolved) == 2
    effect_indices = tuple(
        cast(int, cast(dict[str, JsonValue], event.payload)["effect_index"]) for event in resolved
    )
    assert tuple(sorted(effect_indices)) == (0, 1)
    assert (
        len(
            _events_of_type(
                restored.decision_controller,
                CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
            )
        )
        == 1
    )
    selected_records = tuple(
        record
        for record in restored.decision_controller.records
        if record.request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE
    )
    assert len(selected_records) == 1

    replay = GameLifecycle.from_payload(initial_payload, runtime_content_bundle=bundle)
    replay_session = LocalGameSession(lifecycle=replay)
    for record in restored.decision_controller.records[initial_record_count:]:
        submit_replay_record(session=replay_session, record=record)
    assert replay.state is not None
    assert replay.state.to_payload() == restored.state.to_payload()
    assert replay.decision_controller.to_payload() == restored.decision_controller.to_payload()


@pytest.mark.parametrize(
    "phase",
    [BattlePhase.SHOOTING, BattlePhase.FIGHT],
    ids=("shooting-start", "fight-start"),
)
def test_phase_start_selected_target_battle_shock_waits_for_delirium_outcome_via_facade(
    phase: BattlePhase,
) -> None:
    _assert_phase_start_selected_target_delirium_continuation(phase=phase)


def test_selected_target_continuation_phase_tamper_rejects_before_provider_mutation() -> None:
    lifecycle, bundle, provider_request = _selected_target_delirium_provider_checkpoint(
        game_id="phase17g-selected-target-delirium-phase-tamper"
    )
    payload = deepcopy(lifecycle.to_payload())
    state_payload = cast(dict[str, Any], payload["state"])
    continuation_payload = cast(
        dict[str, Any],
        state_payload["pending_catalog_selected_target_battle_shock_continuation"],
    )
    assert continuation_payload["continuation_phase"] == "awaiting_provider_outcome"
    continuation_payload["continuation_phase"] = "awaiting_remaining_effects"

    with pytest.raises(
        GameLifecycleError,
        match="completed provider request remains queued",
    ):
        GameLifecycle.from_payload(payload, runtime_content_bundle=bundle)

    state = lifecycle.state
    if state is None:
        raise AssertionError("selected-target phase tamper requires state")
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if continuation is None:
        raise AssertionError("selected-target phase tamper requires continuation")
    state.replace_catalog_selected_target_battle_shock_continuation(
        replace(
            continuation,
            continuation_phase=(
                CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_EFFECTS
            ),
        )
    )
    result = DecisionResult.for_request(
        result_id="phase17g-selected-target-delirium-phase-tamper:decline",
        request=provider_request,
        selected_option_id="decline",
    )
    decisions = lifecycle.decision_controller
    before_state = deepcopy(state.to_payload())
    before_queue = decisions.queue.pending_requests
    before_records = decisions.records
    before_events = decisions.event_log.records

    with pytest.raises(
        GameLifecycleError,
        match="completed provider request remains queued",
    ):
        lifecycle.submit_decision(result)

    assert state.to_payload() == before_state
    assert decisions.queue.pending_requests == before_queue
    assert decisions.records == before_records
    assert decisions.event_log.records == before_events
    assert not _events_of_type(
        decisions,
        CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    )


def test_selected_target_continuation_rejects_completed_provider_in_pending_phase() -> None:
    lifecycle, bundle, provider_request = _selected_target_delirium_provider_checkpoint(
        game_id="phase17g-selected-target-delirium-completed-provider-phase"
    )
    state = lifecycle.state
    if state is None:
        raise AssertionError("selected-target completed provider requires state")
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if continuation is None:
        raise AssertionError("selected-target completed provider requires continuation")
    assert continuation.continuation_phase is (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_PROVIDER_OUTCOME
    )
    assert continuation.provider_pending_request == provider_request
    retained_pending_continuation = continuation
    session = LocalGameSession(lifecycle=lifecycle)
    for provider_decision_index in range(30):
        provider_request = lifecycle.decision_controller.queue.peek_next()
        session.submit_option(
            request_id=provider_request.request_id,
            option_id="decline",
            result_id=(
                "phase17g-selected-target-delirium-completed-provider-phase:"
                f"decline:{provider_decision_index}"
            ),
        )
        if state.pending_catalog_selected_target_battle_shock_continuation is None:
            break
    else:
        raise AssertionError("selected-target provider outcome did not complete")
    assert any(
        record.request == retained_pending_continuation.provider_pending_request
        for record in lifecycle.decision_controller.records
    )
    state.replace_catalog_selected_target_battle_shock_continuation(retained_pending_continuation)

    with pytest.raises(
        GameLifecycleError,
        match="pending provider request is already completed",
    ):
        GameLifecycle.from_payload(
            deepcopy(lifecycle.to_payload()),
            runtime_content_bundle=bundle,
        )


def test_selected_target_remaining_effect_request_requires_retained_ancestry() -> None:
    selected_target_record = _selected_target_battle_shock_then_mortal_record()
    lifecycle, bundle, _provider_request = _selected_target_delirium_provider_checkpoint(
        game_id="phase17g-selected-target-delirium-remaining-mortal-wounds",
        selected_target_record=selected_target_record,
    )
    state = lifecycle.state
    if state is None:
        raise AssertionError("selected-target remaining effects require state")
    session = LocalGameSession(lifecycle=lifecycle)
    for provider_decision_index in range(30):
        continuation = state.pending_catalog_selected_target_battle_shock_continuation
        if continuation is None:
            raise AssertionError("selected-target remaining mortal-wound roll resolved to zero")
        if continuation.continuation_phase is (
            CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_EFFECTS
        ):
            break
        provider_request = lifecycle.decision_controller.queue.peek_next()
        session.submit_option(
            request_id=provider_request.request_id,
            option_id="decline",
            result_id=(
                "phase17g-selected-target-delirium-remaining-mortal-wounds:"
                f"provider:{provider_decision_index}"
            ),
        )
    else:
        raise AssertionError("selected-target provider outcome did not reach remaining effects")

    nested_request = lifecycle.decision_controller.queue.peek_next()
    assert nested_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    restored = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    assert restored.state is not None
    assert restored.state.pending_catalog_selected_target_battle_shock_continuation is not None

    forged_request = replace(
        nested_request,
        request_id=f"{nested_request.request_id}:unrelated",
    )
    lifecycle.decision_controller.queue._pending_requests[0] = (  # pyright: ignore[reportPrivateUsage]
        forged_request
    )
    result = DecisionResult.for_request(
        result_id=("phase17g-selected-target-delirium-remaining-mortal-wounds:forged-result"),
        request=forged_request,
        selected_option_id="decline",
    )
    before_state = deepcopy(state.to_payload())
    before_queue = lifecycle.decision_controller.queue.pending_requests
    before_records = lifecycle.decision_controller.records
    before_events = lifecycle.decision_controller.event_log.records

    with pytest.raises(
        GameLifecycleError,
        match="remaining-effects request event authority drifted",
    ):
        lifecycle.submit_decision(result)

    assert state.to_payload() == before_state
    assert lifecycle.decision_controller.queue.pending_requests == before_queue
    assert lifecycle.decision_controller.records == before_records
    assert lifecycle.decision_controller.event_log.records == before_events

    restored_session = LocalGameSession(lifecycle=restored)
    for nested_decision_index in range(30):
        if _events_of_type(
            restored.decision_controller,
            CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        ):
            break
        current_request = restored.decision_controller.queue.peek_next()
        restored_session.submit_option(
            request_id=current_request.request_id,
            option_id="decline",
            result_id=(
                "phase17g-selected-target-delirium-remaining-mortal-wounds:"
                f"nested:{nested_decision_index}"
            ),
        )
    else:
        raise AssertionError("selected-target remaining effects did not complete")
    assert (
        len(
            _events_of_type(
                restored.decision_controller,
                CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
            )
        )
        == 1
    )


def test_delirium_source_identity_drift_rejects_before_lifecycle_mutation() -> None:
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id="phase17g-chaos-knights-delirium-source-identity-drift",
        with_feel_no_pain=True,
    )
    decisions = lifecycle.decision_controller
    request = decisions.queue.peek_next()
    request_payload = cast(dict[str, Any], deepcopy(request.payload))
    lost_wound_context = cast(dict[str, Any], request_payload["lost_wound_context"])
    application_id = cast(str, lost_wound_context["application_id"])
    lost_wound_context["source_rule_id"] = "phase17g:forged-delirium-source"
    forged_request = replace(request, payload=validate_json_value(request_payload))
    decisions.queue._pending_requests[0] = forged_request  # pyright: ignore[reportPrivateUsage]

    original_request_payload = request.to_payload()
    forged_request_payload = forged_request.to_payload()
    changed_request_event = False
    changed_application_root = False
    drifted_events: list[EventRecord] = []
    for event in decisions.event_log.records:
        if event.event_type == "decision_requested" and event.payload == original_request_payload:
            drifted_events.append(
                replace(event, payload=validate_json_value(forged_request_payload))
            )
            changed_request_event = True
            continue
        if (
            event.event_type == "mortal_wound_application_started"
            and isinstance(event.payload, dict)
            and event.payload.get("application_id") == application_id
        ):
            drifted_events.append(
                replace(
                    event,
                    payload={
                        **event.payload,
                        "source_rule_id": "phase17g:forged-delirium-source",
                    },
                )
            )
            changed_application_root = True
            continue
        drifted_events.append(event)
    assert changed_request_event
    assert changed_application_root
    decisions.event_log.replace_records(tuple(drifted_events))

    forged_payload = deepcopy(lifecycle.to_payload())
    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        GameLifecycle.from_payload(forged_payload, runtime_content_bundle=bundle)

    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-delirium-source-identity-drift:decline",
        request=forged_request,
        selected_option_id="decline",
    )
    assert lifecycle.state is not None
    before_state = lifecycle.state.to_payload()
    before_queue = decisions.queue.pending_requests
    before_records = decisions.records
    before_events = decisions.event_log.records
    before_dice_events = sum(event.event_type == "dice_rolled" for event in before_events)

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        lifecycle.submit_decision(result)

    assert lifecycle.state.to_payload() == before_state
    assert decisions.queue.pending_requests == before_queue
    assert decisions.records == before_records
    assert decisions.event_log.records == before_events
    assert (
        sum(event.event_type == "dice_rolled" for event in decisions.event_log.records)
        == before_dice_events
    )


def test_delirium_source_kind_drift_rejects_before_lifecycle_mutation() -> None:
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id="phase17g-chaos-knights-delirium-source-kind-drift",
        with_feel_no_pain=True,
    )
    decisions = lifecycle.decision_controller
    request = decisions.queue.peek_next()
    request_payload = cast(dict[str, Any], deepcopy(request.payload))
    lost_wound_context = cast(dict[str, Any], request_payload["lost_wound_context"])
    application_id = cast(str, lost_wound_context["application_id"])
    source_context = cast(dict[str, Any], lost_wound_context["source_context"])
    source_context["source_kind"] = "phase17g:forged-delirium-source-kind"
    forged_request = replace(request, payload=validate_json_value(request_payload))
    decisions.queue._pending_requests[0] = forged_request  # pyright: ignore[reportPrivateUsage]

    original_request_payload = request.to_payload()
    forged_request_payload = forged_request.to_payload()
    changed_request_event = False
    changed_application_root = False
    drifted_events: list[EventRecord] = []
    for event in decisions.event_log.records:
        if event.event_type == "decision_requested" and event.payload == original_request_payload:
            drifted_events.append(
                replace(event, payload=validate_json_value(forged_request_payload))
            )
            changed_request_event = True
            continue
        if (
            event.event_type == "mortal_wound_application_started"
            and isinstance(event.payload, dict)
            and event.payload.get("application_id") == application_id
        ):
            root_source_context = cast(dict[str, Any], deepcopy(event.payload["source_context"]))
            root_source_context["source_kind"] = "phase17g:forged-delirium-source-kind"
            drifted_events.append(
                replace(
                    event,
                    payload={
                        **event.payload,
                        "source_context": validate_json_value(root_source_context),
                    },
                )
            )
            changed_application_root = True
            continue
        drifted_events.append(event)
    assert changed_request_event
    assert changed_application_root
    decisions.event_log.replace_records(tuple(drifted_events))

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        GameLifecycle.from_payload(
            deepcopy(lifecycle.to_payload()),
            runtime_content_bundle=bundle,
        )

    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-delirium-source-kind-drift:decline",
        request=forged_request,
        selected_option_id="decline",
    )
    assert lifecycle.state is not None
    before_state = lifecycle.state.to_payload()
    before_queue = decisions.queue.pending_requests
    before_records = decisions.records
    before_events = decisions.event_log.records
    before_dice_events = sum(event.event_type == "dice_rolled" for event in before_events)

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        lifecycle.submit_decision(result)

    assert lifecycle.state.to_payload() == before_state
    assert decisions.queue.pending_requests == before_queue
    assert decisions.records == before_records
    assert decisions.event_log.records == before_events
    assert (
        sum(event.event_type == "dice_rolled" for event in decisions.event_log.records)
        == before_dice_events
    )


def test_delirium_dual_identity_drift_keeps_provider_ownership() -> None:
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id="phase17g-chaos-knights-delirium-dual-identity-drift",
        with_feel_no_pain=True,
    )
    decisions = lifecycle.decision_controller
    request = decisions.queue.peek_next()
    request_payload = cast(dict[str, Any], deepcopy(request.payload))
    lost_wound_context = cast(dict[str, Any], request_payload["lost_wound_context"])
    application_id = cast(str, lost_wound_context["application_id"])
    lost_wound_context["source_rule_id"] = "phase17g:forged-delirium-source"
    source_context = cast(dict[str, Any], lost_wound_context["source_context"])
    source_context["source_kind"] = "phase17g:forged-delirium-source-kind"
    forged_request = replace(request, payload=validate_json_value(request_payload))
    decisions.queue._pending_requests[0] = forged_request  # pyright: ignore[reportPrivateUsage]

    original_request_payload = request.to_payload()
    forged_request_payload = forged_request.to_payload()
    changed_request_event = False
    changed_application_root = False
    drifted_events: list[EventRecord] = []
    for event in decisions.event_log.records:
        if event.event_type == "decision_requested" and event.payload == original_request_payload:
            drifted_events.append(
                replace(event, payload=validate_json_value(forged_request_payload))
            )
            changed_request_event = True
            continue
        if (
            event.event_type == "mortal_wound_application_started"
            and isinstance(event.payload, dict)
            and event.payload.get("application_id") == application_id
        ):
            root_source_context = cast(dict[str, Any], deepcopy(event.payload["source_context"]))
            root_source_context["source_kind"] = "phase17g:forged-delirium-source-kind"
            drifted_events.append(
                replace(
                    event,
                    payload={
                        **event.payload,
                        "source_rule_id": "phase17g:forged-delirium-source",
                        "source_context": validate_json_value(root_source_context),
                    },
                )
            )
            changed_application_root = True
            continue
        drifted_events.append(event)
    assert changed_request_event
    assert changed_application_root
    decisions.event_log.replace_records(tuple(drifted_events))

    pending_marker = _event_payload(decisions, "chaos_knights_delirium_mortal_wounds_pending")
    assert pending_marker["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert pending_marker["feel_no_pain_request_id"] == request.request_id

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        GameLifecycle.from_payload(
            deepcopy(lifecycle.to_payload()),
            runtime_content_bundle=bundle,
        )

    result = DecisionResult.for_request(
        result_id="phase17g-chaos-knights-delirium-dual-identity-drift:decline",
        request=forged_request,
        selected_option_id="decline",
    )
    assert lifecycle.state is not None
    before_state = lifecycle.state.to_payload()
    before_queue = decisions.queue.pending_requests
    before_records = decisions.records
    before_events = decisions.event_log.records
    before_dice_events = sum(event.event_type == "dice_rolled" for event in before_events)

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        lifecycle.submit_decision(result)

    assert lifecycle.state.to_payload() == before_state
    assert decisions.queue.pending_requests == before_queue
    assert decisions.records == before_records
    assert decisions.event_log.records == before_events
    assert (
        sum(event.event_type == "dice_rolled" for event in decisions.event_log.records)
        == before_dice_events
    )


def test_delirium_loaded_continuation_requires_pending_provider_claim() -> None:
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id="phase17g-chaos-knights-delirium-missing-provider-claim",
        with_feel_no_pain=True,
    )
    contribution = army_rule.runtime_contribution()
    battle_shock_binding = next(
        binding
        for binding in contribution.battle_shock_hook_bindings
        if binding.source_id == army_rule.SOURCE_RULE_ID
    )

    def no_pending_claim(_context: BattleShockPendingOutcomeAuthorityContext) -> None:
        return None

    no_claim_battle_shock_binding = replace(
        battle_shock_binding,
        pending_outcome_authority_validator=no_pending_claim,
    )
    no_claim_contribution = replace(
        contribution,
        hook_bindings=tuple(
            replace(runtime_binding, binding=no_claim_battle_shock_binding)
            if runtime_binding.binding == battle_shock_binding
            else runtime_binding
            for runtime_binding in contribution.hook_bindings
        ),
    )
    assert lifecycle.state is not None
    no_claim_bundle = RuntimeContentBundle.from_contributions(
        activation=bundle.activation,
        armies=tuple(lifecycle.state.army_definitions),
        catalog=lifecycle.config.army_catalog,
        contributions=(no_claim_contribution,),
    )

    with pytest.raises(GameLifecycleError, match="lacks pending provider authority"):
        GameLifecycle.from_payload(
            deepcopy(lifecycle.to_payload()),
            runtime_content_bundle=no_claim_bundle,
        )


def test_delirium_completed_immediate_and_fnp_history_restore_through_lifecycle() -> None:
    immediate, immediate_bundle = _command_delirium_lifecycle_fixture(
        game_id="phase17g-chaos-knights-delirium-lifecycle-immediate",
        with_feel_no_pain=False,
    )
    immediate_restored = GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(immediate.to_payload()))),
        runtime_content_bundle=immediate_bundle,
    )
    immediate_applied = _event_payload(
        immediate_restored.decision_controller,
        "chaos_knights_delirium_mortal_wounds_applied",
    )
    assert "feel_no_pain_result_id" not in immediate_applied

    resumed_source, resumed_bundle = _command_delirium_lifecycle_fixture(
        game_id="phase17g-chaos-knights-delirium-lifecycle-resumed",
        with_feel_no_pain=True,
    )
    resumed = GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(resumed_source.to_payload()))),
        runtime_content_bundle=resumed_bundle,
    )
    while resumed.decision_controller.queue.pending_requests:
        request = resumed.decision_controller.queue.peek_next()
        if request.decision_type != SELECT_FEEL_NO_PAIN_DECISION_TYPE:
            break
        resumed.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase17g-chaos-knights-delirium-resumed:{request.request_id}",
                request=request,
                selected_option_id="decline",
            )
        )
    applied = _event_payload(
        resumed.decision_controller,
        "chaos_knights_delirium_mortal_wounds_applied",
    )
    assert type(applied.get("feel_no_pain_result_id")) is str
    GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(resumed.to_payload()))),
        runtime_content_bundle=resumed_bundle,
    )


@pytest.mark.parametrize("history_kind", ["pending", "completed"])
def test_delirium_lifecycle_restore_rejects_outcome_history_tamper(
    history_kind: str,
) -> None:
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id=f"phase17g-chaos-knights-delirium-lifecycle-tamper:{history_kind}",
        with_feel_no_pain=history_kind == "pending",
    )
    payload = cast(dict[str, Any], deepcopy(lifecycle.to_payload()))
    event_type = (
        "chaos_knights_delirium_mortal_wounds_pending"
        if history_kind == "pending"
        else "chaos_knights_delirium_mortal_wounds_applied"
    )
    marker = next(
        event
        for event in cast(list[dict[str, Any]], payload["decisions"]["event_log"])
        if event["event_type"] == event_type
    )
    marker_payload = cast(dict[str, Any], marker["payload"])
    marker_payload["battle_shock_result_id"] = "forged:result"

    with pytest.raises(GameLifecycleError, match=r"Delirium .* authority drifted"):
        GameLifecycle.from_payload(
            cast(GameLifecyclePayload, payload),
            runtime_content_bundle=bundle,
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


def _assert_selected_target_delirium_continuation(*, reroll: bool) -> None:
    game_id = (
        "phase17g-selected-target-delirium-reroll"
        if reroll
        else "phase17g-selected-target-delirium-direct"
    )
    selected_target_record = _selected_target_battle_shock_then_modifier_record()
    extra_contributions: tuple[RuntimeContentContribution, ...] = ()
    if reroll:

        def reroll_permission(
            context: BattleShockRerollPermissionContext,
        ) -> RerollPermission | None:
            return RerollPermission(
                source_id="phase17g:test:selected-target-reroll",
                timing_window="battle_shock_test",
                owning_player_id=context.request.player_id,
                eligible_roll_type=context.request.spec.roll_type,
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            )

        def historical_contribution(
            context: HistoricalBattleShockAuthorityContext,
        ) -> HistoricalBattleShockContribution:
            return HistoricalBattleShockContribution(
                reroll_permission=RerollPermission(
                    source_id="phase17g:test:selected-target-reroll",
                    timing_window="battle_shock_test",
                    owning_player_id=context.request.player_id,
                    eligible_roll_type=context.request.spec.roll_type,
                    component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
                )
            )

        extra_contributions = (
            RuntimeContentContribution(
                contribution_id="phase17g:test:selected-target-reroll",
                battle_shock_hook_bindings=(
                    BattleShockHookBinding(
                        hook_id="phase17g:test:selected-target-reroll",
                        source_id="phase17g:test:selected-target-reroll",
                        reroll_permission_handler=reroll_permission,
                        historical_contribution_handler=historical_contribution,
                    ),
                ),
            ),
        )
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id=game_id,
        with_feel_no_pain=True,
        selected_target_record=selected_target_record,
        target_starting_wounds=30,
        begin_command_phase=False,
        extra_contributions=extra_contributions,
    )
    lifecycle = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    _queue_selected_target_delirium_request(
        lifecycle=lifecycle,
        selected_target_record=selected_target_record,
    )
    initial_payload = deepcopy(lifecycle.to_payload())
    initial_record_count = len(lifecycle.decision_controller.records)
    session = LocalGameSession(lifecycle=lifecycle)
    selected_request = lifecycle.decision_controller.queue.peek_next()
    assert selected_request.decision_type == (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE
    )
    status = session.submit_option(
        request_id=selected_request.request_id,
        option_id=selected_request.options[0].option_id,
        result_id=f"{game_id}:selected-target-result",
    )
    if reroll:
        reroll_request = lifecycle.decision_controller.queue.peek_next()
        assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
        reroll_option_id = next(
            option.option_id for option in reroll_request.options if option.option_id != "decline"
        )
        status = session.submit_option(
            request_id=reroll_request.request_id,
            option_id=reroll_option_id,
            result_id=f"{game_id}:reroll-result",
        )
    provider_request = lifecycle.decision_controller.queue.peek_next()
    assert status.decision_request == provider_request
    assert provider_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert lifecycle.decision_controller.queue.pending_requests == (provider_request,)
    state = lifecycle.state
    if state is None:
        raise AssertionError("selected-target continuation requires state")
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    assert continuation is not None
    assert continuation.provider_pending_request == provider_request
    assert (continuation.battle_shock_reroll_result_id is not None) is reroll
    assert state.persisting_effects == []
    assert not _events_of_type(
        lifecycle.decision_controller,
        CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    )
    provider_payload = deepcopy(lifecycle.to_payload())
    restored = GameLifecycle.from_payload(
        provider_payload,
        runtime_content_bundle=bundle,
    )
    if restored.state is None:
        raise AssertionError("restored selected-target continuation requires state")
    restored_continuation = restored.state.pending_catalog_selected_target_battle_shock_continuation
    assert restored_continuation is not None
    assert restored_continuation.to_payload() == continuation.to_payload()
    restored_session = LocalGameSession(lifecycle=restored)
    final_status = status
    for provider_decision_index in range(30):
        restored_continuation = (
            restored.state.pending_catalog_selected_target_battle_shock_continuation
        )
        if restored_continuation is None:
            break
        provider_request = restored.decision_controller.queue.peek_next()
        assert provider_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
        assert restored.decision_controller.queue.pending_requests == (provider_request,)
        assert restored_continuation.provider_pending_request == provider_request
        final_status = restored_session.submit_option(
            request_id=provider_request.request_id,
            option_id="decline",
            result_id=f"{game_id}:fnp-result:{provider_decision_index}",
        )
        if restored.state.pending_catalog_selected_target_battle_shock_continuation is not None:
            assert restored.state.persisting_effects == []
            assert not _events_of_type(
                restored.decision_controller,
                CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
            )
    else:
        raise AssertionError("selected-target provider outcome did not close")
    assert final_status.decision_request is not None
    assert restored.state.pending_catalog_selected_target_battle_shock_continuation is None
    assert len(restored.state.persisting_effects) == 1
    assert (
        len(
            _events_of_type(
                restored.decision_controller,
                "battle_shock_test_resolved",
                source_kind="catalog_selected_target_effect",
            )
        )
        == 1
    )
    assert (
        len(
            _events_of_type(
                restored.decision_controller,
                CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
            )
        )
        == 1
    )
    selected_records = tuple(
        record
        for record in restored.decision_controller.records
        if record.request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE
    )
    assert len(selected_records) == 1
    assert not any(
        request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE
        for request in restored.decision_controller.queue.pending_requests
    )
    replay = GameLifecycle.from_payload(
        initial_payload,
        runtime_content_bundle=bundle,
    )
    replay_session = LocalGameSession(lifecycle=replay)
    for record in restored.decision_controller.records[initial_record_count:]:
        submit_replay_record(session=replay_session, record=record)
    assert replay.state is not None
    assert replay.state.to_payload() == restored.state.to_payload()
    assert replay.decision_controller.to_payload() == restored.decision_controller.to_payload()


def _selected_target_delirium_provider_checkpoint(
    *,
    game_id: str,
    selected_target_record: AbilityCatalogRecord | None = None,
) -> tuple[GameLifecycle, RuntimeContentBundle, DecisionRequest]:
    selected_target_record = (
        _selected_target_battle_shock_then_modifier_record()
        if selected_target_record is None
        else selected_target_record
    )
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id=game_id,
        with_feel_no_pain=True,
        selected_target_record=selected_target_record,
        target_starting_wounds=30,
        begin_command_phase=False,
    )
    lifecycle = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    _queue_selected_target_delirium_request(
        lifecycle=lifecycle,
        selected_target_record=selected_target_record,
    )
    selected_request = lifecycle.decision_controller.queue.peek_next()
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.submit_option(
        request_id=selected_request.request_id,
        option_id=selected_request.options[0].option_id,
        result_id=f"{game_id}:selected-target-result",
    )
    provider_request = lifecycle.decision_controller.queue.peek_next()
    assert status.decision_request == provider_request
    assert provider_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    return lifecycle, bundle, provider_request


def _assert_phase_start_selected_target_delirium_continuation(*, phase: BattlePhase) -> None:
    game_id = f"phase17g-selected-target-{phase.value}-start-delirium"
    selected_target_record = _phase_start_selected_target_battle_shock_record(phase=phase)
    lifecycle, bundle = _command_delirium_lifecycle_fixture(
        game_id=game_id,
        with_feel_no_pain=True,
        selected_target_record=selected_target_record,
        target_starting_wounds=30,
        begin_command_phase=False,
        battle_phase=phase,
    )
    lifecycle = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    status = lifecycle.advance_until_decision_or_terminal()
    selected_request = lifecycle.decision_controller.queue.peek_next()
    expected_decision_type = (
        SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE
        if phase is BattlePhase.SHOOTING
        else SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    )
    expected_final_event_type = (
        CATALOG_SHOOTING_START_SELECTED_TARGET_EFFECT_SELECTED_EVENT
        if phase is BattlePhase.SHOOTING
        else CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT
    )
    assert status.decision_request == selected_request
    assert selected_request.decision_type == expected_decision_type
    selected_option = next(
        option
        for option in selected_request.options
        if isinstance(option.payload, dict) and "selected_catalog_target_effect" in option.payload
    )
    initial_payload = deepcopy(lifecycle.to_payload())
    initial_record_count = len(lifecycle.decision_controller.records)
    session = LocalGameSession(lifecycle=lifecycle)
    provider_status = session.submit_option(
        request_id=selected_request.request_id,
        option_id=selected_option.option_id,
        result_id=f"{game_id}:selected-target-result",
    )
    provider_request = lifecycle.decision_controller.queue.peek_next()
    assert provider_status.decision_request == provider_request
    assert provider_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert lifecycle.decision_controller.queue.pending_requests == (provider_request,)
    state = lifecycle.state
    if state is None:
        raise AssertionError("phase-start selected-target continuation requires state")
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    assert continuation is not None
    assert continuation.phase is phase
    assert continuation.final_event_type == expected_final_event_type
    assert state.persisting_effects == []
    assert not _events_of_type(lifecycle.decision_controller, expected_final_event_type)

    restored = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    if restored.state is None:
        raise AssertionError("restored phase-start continuation requires state")
    restored_session = LocalGameSession(lifecycle=restored)
    for provider_decision_index in range(30):
        restored_continuation = (
            restored.state.pending_catalog_selected_target_battle_shock_continuation
        )
        if restored_continuation is None:
            break
        provider_request = restored.decision_controller.queue.peek_next()
        assert provider_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
        assert restored.decision_controller.queue.pending_requests == (provider_request,)
        assert restored_continuation.provider_pending_request == provider_request
        restored_session.submit_option(
            request_id=provider_request.request_id,
            option_id="decline",
            result_id=f"{game_id}:fnp-result:{provider_decision_index}",
        )
        if restored.state.pending_catalog_selected_target_battle_shock_continuation is not None:
            assert restored.state.persisting_effects == []
            assert not _events_of_type(restored.decision_controller, expected_final_event_type)
    else:
        raise AssertionError("phase-start provider outcome did not close")
    assert restored.state.pending_catalog_selected_target_battle_shock_continuation is None
    assert len(restored.state.persisting_effects) == 1
    assert len(_events_of_type(restored.decision_controller, expected_final_event_type)) == 1
    assert (
        len(
            tuple(
                record
                for record in restored.decision_controller.records
                if record.request.decision_type == expected_decision_type
            )
        )
        == 1
    )

    replay = GameLifecycle.from_payload(initial_payload, runtime_content_bundle=bundle)
    replay_session = LocalGameSession(lifecycle=replay)
    for record in restored.decision_controller.records[initial_record_count:]:
        submit_replay_record(session=replay_session, record=record)
    assert replay.state is not None
    assert replay.state.to_payload() == restored.state.to_payload()
    assert replay.decision_controller.to_payload() == restored.decision_controller.to_payload()


def _selected_target_battle_shock_then_modifier_record() -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        source_id="phase17g:test:selected-target-battle-shock-then-modifier",
        raw_text=(
            "In your Shooting phase, after this model has shot, select one enemy unit that "
            "was hit by one or more of those attacks. That unit must take a Battle-shock "
            "test. Until the end of the turn, subtract 1 from the Hit roll for that unit."
        ),
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    return AbilityCatalogRecord(
        record_id="phase17g:test:selected-target-battle-shock-then-modifier",
        definition=AbilityDefinition(
            ability_id="phase17g:test:selected-target-battle-shock-then-modifier:ability",
            name="Selected-target Delirium continuation regression",
            source_id=source.source_id,
            when_descriptor="After this model has shot.",
            effect_descriptor="Battle-shock, then a persisting modifier.",
            restrictions_descriptor="Select one enemy unit hit by those attacks.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _selected_target_two_battle_shocks_then_modifier_record() -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        source_id="phase17g:test:selected-target-two-battle-shocks-then-modifier",
        raw_text=(
            "In your Shooting phase, after this model has shot, select one enemy unit that "
            "was hit by one or more of those attacks. That unit must take a Battle-shock "
            "test. That unit must take a Battle-shock test. Until the end of the turn, "
            "subtract 1 from the Hit roll for that unit."
        ),
    )
    compiled_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    if not compiled_ir.is_supported or len(compiled_ir.clauses) != 4:
        raise AssertionError("selected-target two-Battle-shock fixture must compile")
    selection_clause, first_battle_shock, second_battle_shock, modifier_clause = compiled_ir.clauses
    rule_ir = replace(
        compiled_ir,
        clauses=(
            selection_clause,
            replace(
                first_battle_shock,
                effects=(*first_battle_shock.effects, *second_battle_shock.effects),
            ),
            modifier_clause,
        ),
    )
    return AbilityCatalogRecord(
        record_id="phase17g:test:selected-target-two-battle-shocks-then-modifier",
        definition=AbilityDefinition(
            ability_id=("phase17g:test:selected-target-two-battle-shocks-then-modifier:ability"),
            name="Selected-target later Battle-shock reroll continuation regression",
            source_id=source.source_id,
            when_descriptor="After this model has shot.",
            effect_descriptor="Two Battle-shock tests, then a persisting modifier.",
            restrictions_descriptor="Select one enemy unit hit by those attacks.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _selected_target_battle_shock_then_mortal_record() -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        source_id="phase17g:test:selected-target-battle-shock-then-mortal-wounds",
        raw_text=(
            "In your Shooting phase, after this model has shot, select one enemy unit that "
            "was hit by one or more of those attacks. That unit must take a Battle-shock "
            "test. Roll three D6: for each 4+, that enemy unit suffers 1 mortal wound."
        ),
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    if not rule_ir.is_supported:
        raise AssertionError("selected-target Battle-shock/mortal-wound fixture must compile")
    return AbilityCatalogRecord(
        record_id="phase17g:test:selected-target-battle-shock-then-mortal-wounds",
        definition=AbilityDefinition(
            ability_id="phase17g:test:selected-target-battle-shock-then-mortal-wounds:ability",
            name="Selected-target remaining-effects continuation regression",
            source_id=source.source_id,
            when_descriptor="After this model has shot.",
            effect_descriptor="Battle-shock, then mortal wounds.",
            restrictions_descriptor="Select one enemy unit hit by those attacks.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _phase_start_selected_target_battle_shock_record(
    *,
    phase: BattlePhase,
) -> AbilityCatalogRecord:
    if phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        raise ValueError("phase-start selected-target fixture requires Shooting or Fight")
    source_id = f"phase17g:test:{phase.value}-start-selected-target-battle-shock"
    selection_text = f"{phase.value} phase start selected target"
    battle_shock_text = "selected unit takes a Battle-shock test"
    modifier_text = "selected unit suffers a Hit roll modifier until turn end"
    normalized_text = f"{selection_text}. {battle_shock_text}. {modifier_text}."
    selection_span = TextSpan(text=selection_text, start=0, end=len(selection_text))
    battle_shock_start = len(selection_text) + 2
    battle_shock_span = TextSpan(
        text=battle_shock_text,
        start=battle_shock_start,
        end=battle_shock_start + len(battle_shock_text),
    )
    modifier_start = battle_shock_span.end + 2
    modifier_span = TextSpan(
        text=modifier_text,
        start=modifier_start,
        end=modifier_start + len(modifier_text),
    )
    selection_clause_id = f"{source_id}:selection"
    selection = RuleClause(
        clause_id=selection_clause_id,
        template_id="phase17c:selected-target-constraint",
        source_span=selection_span,
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=selection_span,
            parameters=(
                RuleParameter(key="edge", value="start"),
                *(
                    (
                        RuleParameter(key="optional", value=True),
                        RuleParameter(key="owner", value="opponent"),
                        RuleParameter(key="phase", value=BattlePhase.SHOOTING.value),
                        RuleParameter(key="subject", value="this_unit"),
                    )
                    if phase is BattlePhase.SHOOTING
                    else (
                        RuleParameter(key="owner", value=None),
                        RuleParameter(key="phase", value=BattlePhase.FIGHT.value),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=(
                RuleTargetKind.FRIENDLY_UNIT
                if phase is BattlePhase.SHOOTING
                else RuleTargetKind.ENEMY_UNIT
            ),
            source_span=selection_span,
            parameters=(
                RuleParameter(
                    key="allegiance",
                    value="friendly" if phase is BattlePhase.SHOOTING else "enemy",
                ),
                *(
                    (RuleParameter(key="required_keyword_sequence", value=("CHARACTER",)),)
                    if phase is BattlePhase.SHOOTING
                    else ()
                ),
            ),
        ),
    )
    battle_shock_clause = RuleClause(
        clause_id=f"{source_id}:battle-shock",
        template_id="phase17c:contextual-status",
        source_span=battle_shock_span,
        target=RuleTargetSpec(
            kind=RuleTargetKind.SELECTED_UNIT,
            source_span=battle_shock_span,
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=battle_shock_span,
                parameters=(
                    RuleParameter(key="reason", value="forced_by_ability"),
                    RuleParameter(key="required", value=True),
                    RuleParameter(key="rules_context", value="battle_shock"),
                    RuleParameter(key="status", value="force_battle_shock_test"),
                    RuleParameter(key="target_scope", value="selected_unit"),
                ),
            ),
        ),
    )
    modifier_clause = RuleClause(
        clause_id=f"{source_id}:modifier",
        template_id="phase17c:dice-roll-modifier",
        source_span=modifier_span,
        target=RuleTargetSpec(
            kind=RuleTargetKind.SELECTED_UNIT,
            source_span=modifier_span,
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_DICE_ROLL,
                source_span=modifier_span,
                parameters=(
                    RuleParameter(key="delta", value=-1),
                    RuleParameter(key="roll_type", value="hit"),
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=modifier_span,
            parameters=(RuleParameter(key="endpoint", value="turn"),),
        ),
    )
    rule_ir = RuleIR(
        rule_id=source_id,
        source_id=source_id,
        normalized_text=normalized_text,
        parser_version="phase17g-selected-target-continuation-test-v1",
        clauses=(selection, battle_shock_clause, modifier_clause),
    )
    return AbilityCatalogRecord(
        record_id=f"record:{source_id}",
        definition=AbilityDefinition(
            ability_id=f"ability:{source_id}",
            name=f"{phase.value.title()}-start selected-target continuation regression",
            source_id=source_id,
            when_descriptor=f"At the start of the {phase.value} phase.",
            effect_descriptor="Battle-shock, then a persisting modifier.",
            restrictions_descriptor="Select one eligible unit.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=(
            "core-character-leader"
            if phase is BattlePhase.SHOOTING
            else "core-intercessor-like-infantry"
        ),
    )


def _queue_selected_target_delirium_request(
    *,
    lifecycle: GameLifecycle,
    selected_target_record: AbilityCatalogRecord,
) -> None:
    state = lifecycle.state
    if state is None:
        raise AssertionError("selected-target fixture requires state")
    source_army = next(army for army in state.army_definitions if army.player_id == "player-b")
    target_army = next(army for army in state.army_definitions if army.player_id == "player-a")
    source_unit = unit_by_id(state, "army-beta:intercessor-unit-3")
    target_unit = unit_by_id(state, "army-alpha:intercessor-unit-1")
    profile = _weapon_profile()
    declaration_request_id = f"{state.game_id}:selected-target-declaration-request"
    declaration_result_id = f"{state.game_id}:selected-target-declaration-result"
    sequence = AttackSequence(
        sequence_id=f"attack-sequence:{declaration_result_id}",
        attacker_player_id=source_army.player_id,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            RangedAttackPool(
                attacker_model_instance_id=source_unit.own_models[0].model_instance_id,
                weapon_instance_id=f"{state.game_id}:selected-target-weapon",
                wargear_id="phase17g:selected-target-wargear",
                weapon_profile_id=profile.profile_id,
                weapon_profile=profile,
                target_unit_instance_id=target_unit.unit_instance_id,
                shooting_type=ShootingType.NORMAL,
                attacks=1,
                target_visible_model_ids=target_unit.own_model_ids(),
                target_in_range_model_ids=target_unit.own_model_ids(),
            ),
        ),
    ).advanced_after_attack()
    decisions = lifecycle.decision_controller
    declaration_request = DecisionRequest(
        request_id=declaration_request_id,
        decision_type="phase17g_selected_target_declaration",
        actor_id=source_army.player_id,
        payload=validate_json_value(
            {"attack_pools": [pool.to_payload() for pool in sequence.attack_pools]}
        ),
        options=(
            DecisionOption(
                option_id="accept",
                label="Accept declaration",
                payload=validate_json_value(
                    {"attack_pools": [pool.to_payload() for pool in sequence.attack_pools]}
                ),
            ),
        ),
    )
    decisions.request_decision(declaration_request)
    declaration_result = DecisionResult.for_request(
        result_id=declaration_result_id,
        request=declaration_request,
        selected_option_id="accept",
    )
    decisions.submit_result(declaration_result)
    decisions.event_log.append(
        "shooting_declaration_accepted",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": source_army.player_id,
            "phase": BattlePhase.SHOOTING.value,
            "unit_instance_id": source_unit.unit_instance_id,
            "request_id": declaration_request_id,
            "result_id": declaration_result_id,
            "attack_pools": [pool.to_payload() for pool in sequence.attack_pools],
        },
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    completed = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": sequence.sequence_id,
            "attacker_player_id": source_army.player_id,
            "attacking_unit_instance_id": source_unit.unit_instance_id,
        },
    )
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((selected_target_record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    status = runtime.post_shoot_hit_target_request(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=sequence,
            attack_sequence_completed_event_id=completed.event_id,
        )
    )
    if status is None or status.decision_request is None:
        raise AssertionError("selected-target fixture did not queue target selection")


def _events_of_type(
    decisions: DecisionController,
    event_type: str,
    *,
    source_kind: str | None = None,
) -> tuple[EventRecord, ...]:
    return tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == event_type
        and (
            source_kind is None
            or (isinstance(event.payload, dict) and event.payload.get("source_kind") == source_kind)
        )
    )


def _command_delirium_lifecycle_fixture(
    *,
    game_id: str,
    with_feel_no_pain: bool,
    selected_target_record: AbilityCatalogRecord | None = None,
    target_starting_wounds: int | None = None,
    begin_command_phase: bool = True,
    battle_phase: BattlePhase = BattlePhase.SHOOTING,
    extra_contributions: tuple[RuntimeContentContribution, ...] = (),
) -> tuple[GameLifecycle, RuntimeContentBundle]:
    target_unit_id = "army-alpha:intercessor-unit-1"
    source_unit_id = "army-beta:intercessor-unit-3"
    target_selection = unit_selection(
        unit_selection_id="intercessor-unit-1",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    base_config = phase11c_config(game_id=game_id, player_a_units=(target_selection,))
    catalog = _command_delirium_catalog(
        base_config.army_catalog,
        target_starting_wounds=target_starting_wounds,
    )
    config = replace(
        base_config,
        army_catalog=catalog,
        army_muster_requests=tuple(
            replace(
                request,
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=(
                    DetachmentSelection(
                        faction_id=army_rule.CHAOS_KNIGHTS_FACTION_ID,
                        detachment_ids=("phase17g-chaos-knights-delirium",),
                    )
                    if request.player_id == "player-b"
                    else request.detachment_selection
                ),
            )
            for request in base_config.army_muster_requests
        ),
    )
    state = GameState.from_config(config)
    armies = mustered_armies(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-chaos-knights-lifecycle-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )
    if state.battlefield_state is None:
        raise AssertionError("Delirium lifecycle fixture requires battlefield state")
    marker = center_marker_definition(state)
    source_placement = state.battlefield_state.unit_placement_by_id(source_unit_id)
    target_placement = state.battlefield_state.unit_placement_by_id(target_unit_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            source_placement,
            marker,
            offsets=tuple(
                (index * 1.5, 0.0) for index in range(len(source_placement.model_placements))
            ),
        )
    ).with_unit_placement(with_model_offsets(target_placement, marker, offsets=((8.0, 0.0),)))
    decisions = DecisionController()
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    _record_real_harbingers_selection(
        state,
        decisions=decisions,
        player_id="player-b",
        selected=army_rule.DreadAbility.DELIRIUM,
    )
    target_model = unit_by_id(state, target_unit_id).own_models[0]
    prewound = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=f"{game_id}:prewound-request",
        progress=MortalWoundApplicationProgress.start(
            application_id=f"{game_id}:prewound",
            source_rule_id="phase17g:test:delirium-prewound",
            source_context={"source_kind": "phase17g_delirium_fixture_prewound"},
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=state,
                destroying_player_id="player-b",
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=BattlePhase.COMMAND,
                source_step="delirium_fixture_prewound",
            ),
            target_unit_instance_id=target_unit_id,
            defender_player_id="player-a",
            mortal_wounds=target_model.wounds_remaining // 2 + 1,
            spill_over=True,
        ),
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )
    if prewound.request is not None or prewound.application is None:
        raise AssertionError("Delirium lifecycle pre-wound must resolve immediately")
    if with_feel_no_pain:
        state.record_model_feel_no_pain_sources(
            model_instance_id=target_model.model_instance_id,
            sources=(FeelNoPainSource(source_id=f"{game_id}:fnp", threshold=5),),
            decline_allowed=True,
        )
    contribution = army_rule.runtime_contribution()
    runtime_bundle = RuntimeContentBundle.from_contributions(
        activation=runtime_content_activation_for_armies(
            config=config,
            armies=tuple(state.army_definitions),
        ),
        armies=tuple(state.army_definitions),
        catalog=config.army_catalog,
        contributions=(contribution, *extra_contributions),
        base_ability_records=(() if selected_target_record is None else (selected_target_record,)),
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=runtime_bundle.battle_shock_hook_registry,
        runtime_modifier_registry=runtime_bundle.runtime_modifier_registry,
        ability_indexes_by_player_id=runtime_bundle.ability_indexes_by_player_id,
    )
    if not begin_command_phase:
        state.command_step_state = None
        state.active_player_id = "player-b"
        state.battle_phase_index = state.battle_phase_sequence.index(battle_phase)
        lifecycle = GameLifecycle(
            state=state,
            decision_controller=decisions,
            reaction_queue=ReactionQueue(),
            _config=config,
            _command_phase_handler=handler,
            _runtime_content_bundle=runtime_bundle,
        )
        return lifecycle, runtime_bundle
    status = handler.begin_phase(state=state, decisions=decisions)
    expected_kind = (
        LifecycleStatusKind.WAITING_FOR_DECISION
        if with_feel_no_pain
        else LifecycleStatusKind.ADVANCED
    )
    if status.status_kind is not expected_kind:
        raise AssertionError("Delirium lifecycle fixture did not reach its expected boundary")
    lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        reaction_queue=ReactionQueue(),
        _config=config,
        _command_phase_handler=handler,
        _runtime_content_bundle=runtime_bundle,
    )
    return lifecycle, runtime_bundle


def _command_delirium_catalog(
    base_catalog: ArmyCatalog,
    *,
    target_starting_wounds: int | None = None,
) -> ArmyCatalog:
    source_datasheet_id = "core-intercessor-like-infantry"
    target_datasheet_id = "core-character-leader"
    datasheets: list[DatasheetDefinition] = []
    for datasheet in base_catalog.datasheets:
        if datasheet.datasheet_id == source_datasheet_id:
            datasheets.append(
                replace(
                    datasheet,
                    keywords=DatasheetKeywordSet(
                        keywords=datasheet.keywords.keywords,
                        faction_keywords=(army_rule.CHAOS_KNIGHTS_FACTION_KEYWORD,),
                    ),
                )
            )
            continue
        if datasheet.datasheet_id == target_datasheet_id:
            datasheets.append(
                replace(
                    datasheet,
                    model_profiles=tuple(
                        replace(
                            profile,
                            characteristics=tuple(
                                (
                                    CharacteristicValue.from_raw(Characteristic.LEADERSHIP, 13)
                                    if value.characteristic is Characteristic.LEADERSHIP
                                    else CharacteristicValue.from_raw(
                                        Characteristic.WOUNDS,
                                        target_starting_wounds,
                                    )
                                    if value.characteristic is Characteristic.WOUNDS
                                    and target_starting_wounds is not None
                                    else value
                                )
                                for value in profile.characteristics
                            ),
                        )
                        for profile in datasheet.model_profiles
                    ),
                )
            )
            continue
        datasheets.append(datasheet)
    return replace(
        base_catalog,
        catalog_id="phase17g-chaos-knights-delirium-lifecycle",
        source_package_id="data-package:core-v2:phase17g-chaos-knights-delirium:0.1.0",
        datasheets=tuple(datasheets),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.CHAOS_KNIGHTS_FACTION_ID,
                name="Chaos Knights",
                faction_keywords=(army_rule.CHAOS_KNIGHTS_FACTION_KEYWORD,),
                source_ids=("phase17g:test:chaos-knights-faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="phase17g-chaos-knights-delirium",
                name="Phase 17G Delirium Test Detachment",
                faction_id=army_rule.CHAOS_KNIGHTS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(source_datasheet_id,),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("phase17g:test:chaos-knights-delirium-detachment",),
            ),
        ),
    )


def _delirium_outcome_fixture(
    *,
    game_id: str,
    phase: BattlePhase,
    with_feel_no_pain: bool,
) -> tuple[GameState, DecisionController, str]:
    target_unit_id = "army-beta:intercessor-unit-3"
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
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    if state.battlefield_state is None:
        raise AssertionError("Delirium fixture requires battlefield state")
    target_placement = state.battlefield_state.unit_placement_by_id(target_unit_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            target_placement,
            center_marker_definition(state),
            offsets=tuple(
                (1.0 + index * 1.25, 0.0) for index in range(len(target_placement.model_placements))
            ),
        )
    )
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    target = unit_by_id(state, target_unit_id)
    prewound = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=f"{game_id}:prewound-request",
        progress=MortalWoundApplicationProgress.start(
            application_id=f"{game_id}:prewound",
            source_rule_id="phase17g:test:delirium-prewound",
            source_context={"source_kind": "phase17g_delirium_fixture_prewound"},
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=state,
                destroying_player_id="player-a",
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=phase,
                source_step="delirium_fixture_prewound",
            ),
            target_unit_instance_id=target_unit_id,
            defender_player_id="player-b",
            mortal_wounds=sum(model.wounds_remaining for model in target.own_models[:3]),
            spill_over=True,
        ),
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )
    if prewound.request is not None or prewound.application is None:
        raise AssertionError("Delirium pre-wound fixture must resolve immediately")
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
