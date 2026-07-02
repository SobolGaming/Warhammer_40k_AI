from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockOutcomeContext
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.astra_militarum import (
    army_rule,
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
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    MovementBudgetModifierContext,
    ObjectiveControlModifierContext,
    SaveOptionModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

OFFICER_DATASHEET_ID = "phase17g-astra-castellan"
INFANTRY_DATASHEET_ID = "phase17g-astra-infantry"
SQUADRON_DATASHEET_ID = "phase17g-astra-squadron"
UNORDERABLE_DATASHEET_ID = "phase17g-astra-unorderable"
OFFICER_UNIT_ID = "army-alpha:castellan"
INFANTRY_UNIT_ID = "army-alpha:infantry"
SQUADRON_UNIT_ID = "army-alpha:sentinel"
UNORDERABLE_UNIT_ID = "army-alpha:servitors"
ENEMY_UNIT_ID = "army-beta:enemy-unit"
NON_ASTRA_FACTION_ID = "phase17g-non-astra-force"
NON_ASTRA_DETACHMENT_ID = "phase17g-non-astra-auxiliary-detachment"
_DEFAULT_OFFICER_ORDERS_PAYLOAD = object()


def test_lifecycle_requests_voice_of_command_and_records_move_order() -> None:
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=6)
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()
    assert army_rule.HOOK_ID in summary["command_phase_start_hook_ids"]
    assert army_rule.BATTLE_SHOCK_HOOK_ID in summary["battle_shock_hook_ids"]
    assert army_rule.UNIT_CHARACTERISTIC_MODIFIER_ID in summary["unit_characteristic_modifier_ids"]
    assert army_rule.MOVEMENT_MODIFIER_ID in summary["movement_budget_modifier_ids"]
    assert army_rule.OBJECTIVE_CONTROL_MODIFIER_ID in summary["objective_control_modifier_ids"]
    assert army_rule.SAVE_OPTION_MODIFIER_ID in summary["save_option_modifier_ids"]
    assert army_rule.WEAPON_PROFILE_MODIFIER_ID in summary["weapon_profile_modifier_ids"]

    request = _next_voice_request(lifecycle)

    assert request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert army_rule.VOICE_OF_COMMAND_DONE_OPTION_ID in {
        option.option_id for option in request.options
    }
    issue_options = tuple(
        option
        for option in request.options
        if option.option_id != army_rule.VOICE_OF_COMMAND_DONE_OPTION_ID
    )
    assert len(issue_options) == 12
    assert json.loads(json.dumps(request.to_payload())) == request.to_payload()

    option = _order_option(
        request,
        order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
        target_rules_unit_id=INFANTRY_UNIT_ID,
    )
    result_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-astra-issue-move-order",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert result_status.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    assert (
        army_rule.active_voice_of_command_order_id_for_unit(
            state,
            unit_instance_id=INFANTRY_UNIT_ID,
        )
        == army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE.value
    )
    assert (
        army_rule.active_voice_of_command_order_id_for_unit(
            state,
            unit_instance_id=ENEMY_UNIT_ID,
        )
        is None
    )
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()


def test_non_astra_selected_detachment_with_astra_keyword_units_gets_no_request() -> None:
    lifecycle = _non_astra_selected_lifecycle_with_astra_keyword_units(
        orders_per_battle_round=6,
    )
    state = _require_state(lifecycle)
    army = state.army_definition_for_player("player-a")
    assert army is not None
    assert army.detachment_selection.faction_id == NON_ASTRA_FACTION_ID
    assert any("ASTRA MILITARUM" in unit.faction_keywords for unit in army.units)

    request = army_rule.voice_of_command_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=lifecycle.decision_controller,
            active_player_id="player-a",
        )
    )

    assert request is None


def test_lifecycle_rejects_voice_of_command_drift_before_mutation() -> None:
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=6)
    request = _next_voice_request(lifecycle)
    option = _order_option(
        request,
        order=army_rule.VoiceOfCommandOrder.TAKE_AIM,
        target_rules_unit_id=SQUADRON_UNIT_ID,
    )

    actor_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-astra-wrong-actor",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id="player-b",
            selected_option_id=option.option_id,
            payload=option.payload,
        )
    )

    assert actor_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(actor_drift.payload, dict)
    assert actor_drift.payload["invalid_reason"] == "invalid_command_phase_decision_result"
    assert actor_drift.payload["field"] == "actor_id"
    assert lifecycle.decision_controller.queue.peek_next() == request
    state = _require_state(lifecycle)
    assert (
        army_rule.active_voice_of_command_order_id_for_unit(
            state,
            unit_instance_id=SQUADRON_UNIT_ID,
        )
        is None
    )

    malformed_payload = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-astra-malformed-payload",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload="not-an-object",
        )
    )

    assert malformed_payload.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(malformed_payload.payload, dict)
    assert malformed_payload.payload["invalid_reason"] == "invalid_command_phase_decision_result"
    assert malformed_payload.payload["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request

    drifted_payload = dict(cast(dict[str, object], option.payload))
    drifted_payload["battle_round"] = 99
    payload_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-astra-payload-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=validate_json_value(drifted_payload),
        )
    )

    assert payload_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(payload_drift.payload, dict)
    assert payload_drift.payload["invalid_reason"] == "invalid_command_phase_decision_result"
    assert payload_drift.payload["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert (
        army_rule.active_voice_of_command_order_id_for_unit(
            state,
            unit_instance_id=SQUADRON_UNIT_ID,
        )
        is None
    )


def test_voice_of_command_done_suppresses_current_command_phase_request() -> None:
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=2)
    request = _direct_voice_request(lifecycle)
    state = _require_state(lifecycle)

    assert army_rule.apply_voice_of_command_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=lifecycle.decision_controller,
            request=request,
            result=DecisionResult.for_request(
                result_id="phase17g-astra-no-more-orders",
                request=request,
                selected_option_id=army_rule.VOICE_OF_COMMAND_DONE_OPTION_ID,
            ),
            active_player_id="player-a",
        )
    )

    assert state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.VOICE_OF_COMMAND_DONE_STATE_KIND,
    )
    assert (
        army_rule.voice_of_command_request(
            CommandPhaseStartRequestContext(
                state=state,
                decisions=lifecycle.decision_controller,
                active_player_id="player-a",
            )
        )
        is None
    )

    state.battle_round = 2
    later_request = army_rule.voice_of_command_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=lifecycle.decision_controller,
            active_player_id="player-a",
        )
    )
    assert later_request is not None


def test_voice_of_command_replaces_prior_order_and_battle_shock_clears_order() -> None:
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=2)
    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-replace-first",
    )
    state = _require_state(lifecycle)
    assert len(_voice_order_effects(state, target_rules_unit_id=INFANTRY_UNIT_ID)) == 1

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.TAKE_COVER,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-replace-second",
    )

    assert (
        army_rule.active_voice_of_command_order_id_for_unit(
            state,
            unit_instance_id=INFANTRY_UNIT_ID,
        )
        == army_rule.VoiceOfCommandOrder.TAKE_COVER.value
    )
    effects = _voice_order_effects(state, target_rules_unit_id=INFANTRY_UNIT_ID)
    assert len(effects) == 1
    assert _effect_payload(effects[0])["order_id"] == army_rule.VoiceOfCommandOrder.TAKE_COVER.value
    assert (
        army_rule.voice_of_command_movement_modifier(
            _movement_context(state=state, unit_instance_id=INFANTRY_UNIT_ID)
        )
        == 6.0
    )

    context = _failed_battle_shock_context(lifecycle, unit_instance_id=INFANTRY_UNIT_ID)
    army_rule.voice_of_command_battle_shock_outcome(context)

    assert (
        army_rule.active_voice_of_command_order_id_for_unit(
            state,
            unit_instance_id=INFANTRY_UNIT_ID,
        )
        is None
    )
    assert not _voice_order_effects(state, target_rules_unit_id=INFANTRY_UNIT_ID)


def test_voice_of_command_modifiers_cover_all_orders() -> None:
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=6)
    state = _require_state(lifecycle)

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-move-order",
    )
    assert (
        army_rule.voice_of_command_movement_modifier(
            _movement_context(state=state, unit_instance_id=INFANTRY_UNIT_ID)
        )
        == 9.0
    )

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.FIX_BAYONETS,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-fix-bayonets",
    )
    fixed_melee = army_rule.voice_of_command_weapon_profile_modifier(
        _weapon_context(state=state, weapon_profile=_melee_weapon_profile())
    )
    assert fixed_melee.skill.final == 3
    assert army_rule.SOURCE_RULE_ID in fixed_melee.source_ids
    capped_melee = army_rule.voice_of_command_weapon_profile_modifier(
        _weapon_context(
            state=state,
            weapon_profile=replace(
                _melee_weapon_profile(),
                skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 2),
            ),
        )
    )
    assert capped_melee.skill.final == 2

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.TAKE_AIM,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-take-aim",
    )
    aimed_ranged = army_rule.voice_of_command_weapon_profile_modifier(
        _weapon_context(
            state=state,
            weapon_profile=_ranged_weapon_profile(),
            source_phase=BattlePhase.SHOOTING,
        )
    )
    assert aimed_ranged.skill.final == 3
    assert army_rule.SOURCE_RULE_ID in aimed_ranged.source_ids

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.FIRST_RANK_FIRE_SECOND_RANK_FIRE,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-first-rank",
    )
    rapid_fire = army_rule.voice_of_command_weapon_profile_modifier(
        _weapon_context(
            state=state,
            weapon_profile=_rapid_fire_weapon_profile(),
            source_phase=BattlePhase.SHOOTING,
        )
    )
    non_rapid = army_rule.voice_of_command_weapon_profile_modifier(
        _weapon_context(
            state=state,
            weapon_profile=_ranged_weapon_profile(),
            source_phase=BattlePhase.SHOOTING,
        )
    )
    assert rapid_fire.attack_profile.fixed_attacks == 3
    assert non_rapid.attack_profile.fixed_attacks == 2

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.TAKE_COVER,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-take-cover",
    )
    armour = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=5,
        characteristic_target_number=4,
        armor_penetration=-1,
    )
    invulnerable = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=5,
        characteristic_target_number=5,
        armor_penetration=-1,
    )
    improved_options = army_rule.voice_of_command_save_option_modifier(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=INFANTRY_UNIT_ID,
            save_options=(armour, invulnerable),
        )
    )
    improved_armour = improved_options[0]
    assert improved_armour.save_kind is SaveKind.ARMOUR
    assert improved_armour.characteristic_target_number == 3
    assert improved_armour.target_number == 4
    assert improved_options[1] == invulnerable
    already_capped_armour = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=0,
    )
    assert (
        army_rule.voice_of_command_save_option_modifier(
            SaveOptionModifierContext(
                state=state,
                target_unit_instance_id=INFANTRY_UNIT_ID,
                save_options=(already_capped_armour,),
            )
        )[0]
        == already_capped_armour
    )
    assert (
        army_rule.voice_of_command_unit_characteristic_modifier(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=INFANTRY_UNIT_ID,
                characteristic=Characteristic.SAVE,
                base_value=4,
                current_value=4,
            )
        )
        == 3
    )
    assert (
        army_rule.voice_of_command_unit_characteristic_modifier(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=INFANTRY_UNIT_ID,
                characteristic=Characteristic.SAVE,
                base_value=3,
                current_value=3,
            )
        )
        == 3
    )

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.DUTY_AND_HONOUR,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-duty-and-honour",
    )
    assert (
        army_rule.voice_of_command_unit_characteristic_modifier(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=INFANTRY_UNIT_ID,
                characteristic=Characteristic.LEADERSHIP,
                base_value=7,
                current_value=7,
            )
        )
        == 6
    )
    assert (
        army_rule.voice_of_command_unit_characteristic_modifier(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=INFANTRY_UNIT_ID,
                characteristic=Characteristic.LEADERSHIP,
                base_value=4,
                current_value=4,
            )
        )
        == 4
    )
    assert (
        army_rule.voice_of_command_unit_characteristic_modifier(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=INFANTRY_UNIT_ID,
                characteristic=Characteristic.OBJECTIVE_CONTROL,
                base_value=2,
                current_value=2,
            )
        )
        == 3
    )
    assert (
        army_rule.voice_of_command_objective_control_modifier(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=INFANTRY_UNIT_ID,
                model_instance_id=f"{INFANTRY_UNIT_ID}:model-001",
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 3
    )


def test_voice_of_command_filters_battle_shocked_targets_and_wrong_keywords() -> None:
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=6)
    state = _require_state(lifecycle)
    state.battle_shocked_unit_ids.append(INFANTRY_UNIT_ID)

    request = _direct_voice_request(lifecycle)

    option_payloads = tuple(_option_payload(option) for option in request.options)
    assert all(
        payload.get("ordered_rules_unit_instance_id") != INFANTRY_UNIT_ID
        for payload in option_payloads
    )
    assert all(
        payload.get("ordered_rules_unit_instance_id") != UNORDERABLE_UNIT_ID
        for payload in option_payloads
    )
    assert any(
        payload.get("ordered_rules_unit_instance_id") == SQUADRON_UNIT_ID
        for payload in option_payloads
    )


def test_voice_of_command_requires_structured_orders_profile() -> None:
    lifecycle = _battle_ready_lifecycle(
        orders_per_battle_round=1,
        officer_orders_payload=None,
    )

    with pytest.raises(GameLifecycleError, match="requires rule_ir_payload"):
        lifecycle.advance_until_decision_or_terminal()


def test_voice_of_command_noops_and_result_drift_are_fail_fast() -> None:
    no_astra_lifecycle = _battle_ready_lifecycle(orders_per_battle_round=6)
    no_astra_state = _require_state(no_astra_lifecycle)
    no_astra_state.active_player_id = "player-b"
    assert (
        army_rule.voice_of_command_request(
            CommandPhaseStartRequestContext(
                state=no_astra_state,
                decisions=no_astra_lifecycle.decision_controller,
                active_player_id="player-b",
            )
        )
        is None
    )

    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=6)
    state = _require_state(lifecycle)
    request = _direct_voice_request(lifecycle)
    option = _order_option(
        request,
        order=army_rule.VoiceOfCommandOrder.TAKE_AIM,
        target_rules_unit_id=INFANTRY_UNIT_ID,
    )
    assert not army_rule.apply_voice_of_command_result(
        _command_result_context(
            lifecycle,
            request=replace(request, decision_type="other-decision"),
            result=DecisionResult(
                result_id="phase17g-astra-ignored-decision-type",
                request_id=request.request_id,
                decision_type="other-decision",
                actor_id=request.actor_id,
                selected_option_id=option.option_id,
                payload=option.payload,
            ),
        )
    )
    assert not army_rule.apply_voice_of_command_result(
        _command_result_context(
            lifecycle,
            request=replace(
                request,
                payload=validate_json_value(
                    {
                        **cast(dict[str, JsonValue], request.payload),
                        "hook_id": "phase17g:other-hook",
                    }
                ),
            ),
            result=DecisionResult.for_request(
                result_id="phase17g-astra-ignored-hook",
                request=request,
                selected_option_id=option.option_id,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="result requires an actor"):
        army_rule.apply_voice_of_command_result(
            _command_result_context(
                lifecycle,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-astra-missing-actor",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id=None,
                    selected_option_id=option.option_id,
                    payload=option.payload,
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="does not own Astra Militarum"):
        army_rule.apply_voice_of_command_result(
            _command_result_context(
                lifecycle,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-astra-non-astra-actor",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id="player-b",
                    selected_option_id=option.option_id,
                    payload=option.payload,
                ),
            )
        )

    done_payload = _option_payload(_done_option(request))
    with pytest.raises(GameLifecycleError, match="done option ID drift"):
        army_rule.apply_voice_of_command_result(
            _command_result_context(
                lifecycle,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-astra-done-id-drift",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id=request.actor_id,
                    selected_option_id="phase17g:wrong-done-option",
                    payload=validate_json_value(done_payload),
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="selection is unsupported"):
        army_rule.apply_voice_of_command_result(
            _command_result_context(
                lifecycle,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-astra-unsupported-selection",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id=request.actor_id,
                    selected_option_id=option.option_id,
                    payload=validate_json_value(
                        {
                            **cast(dict[str, JsonValue], option.payload),
                            "selected_voice_of_command_option": "unsupported",
                        }
                    ),
                ),
            )
        )

    done_lifecycle = _battle_ready_lifecycle(orders_per_battle_round=1)
    done_request = _direct_voice_request(done_lifecycle)
    done_result = DecisionResult.for_request(
        result_id="phase17g-astra-done-once",
        request=done_request,
        selected_option_id=army_rule.VOICE_OF_COMMAND_DONE_OPTION_ID,
    )
    assert army_rule.apply_voice_of_command_result(
        _command_result_context(done_lifecycle, request=done_request, result=done_result)
    )
    with pytest.raises(GameLifecycleError, match="already completed"):
        army_rule.apply_voice_of_command_result(
            _command_result_context(
                done_lifecycle,
                request=done_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-astra-done-twice",
                    request=done_request,
                    selected_option_id=army_rule.VOICE_OF_COMMAND_DONE_OPTION_ID,
                ),
            )
        )

    drift_cases = (
        (
            "phase17g-astra-order-drift",
            {"order_id": army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE.value},
            "order payload drift",
        ),
        (
            "phase17g-astra-officer-drift",
            {"issuing_officer_unit_instance_id": SQUADRON_UNIT_ID},
            "officer payload drift",
        ),
        (
            "phase17g-astra-target-drift",
            {"ordered_rules_unit_instance_id": SQUADRON_UNIT_ID},
            "target payload drift",
        ),
    )
    for result_id, payload_delta, expected_error in drift_cases:
        with pytest.raises(GameLifecycleError, match=expected_error):
            army_rule.apply_voice_of_command_result(
                _command_result_context(
                    lifecycle,
                    request=request,
                    result=DecisionResult(
                        result_id=result_id,
                        request_id=request.request_id,
                        decision_type=request.decision_type,
                        actor_id=request.actor_id,
                        selected_option_id=option.option_id,
                        payload=validate_json_value(
                            {
                                **cast(dict[str, JsonValue], option.payload),
                                **payload_delta,
                            }
                        ),
                    ),
                )
            )

    _place_unit(state, unit_instance_id=INFANTRY_UNIT_ID, x=60.0, y=10.0)
    with pytest.raises(GameLifecycleError, match="issue is no longer eligible"):
        army_rule.apply_voice_of_command_result(
            _command_result_context(
                lifecycle,
                request=request,
                result=DecisionResult.for_request(
                    result_id="phase17g-astra-target-out-of-range",
                    request=request,
                    selected_option_id=option.option_id,
                ),
            )
        )

    exhausted = _battle_ready_lifecycle(orders_per_battle_round=1)
    exhausted_request = _direct_voice_request(exhausted)
    exhausted_option = _order_option(
        exhausted_request,
        order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
        target_rules_unit_id=INFANTRY_UNIT_ID,
    )
    assert army_rule.apply_voice_of_command_result(
        _command_result_context(
            exhausted,
            request=exhausted_request,
            result=DecisionResult.for_request(
                result_id="phase17g-astra-exhaust-only-order",
                request=exhausted_request,
                selected_option_id=exhausted_option.option_id,
            ),
        )
    )
    assert (
        army_rule.voice_of_command_request(
            CommandPhaseStartRequestContext(
                state=_require_state(exhausted),
                decisions=exhausted.decision_controller,
                active_player_id="player-a",
            )
        )
        is None
    )


def test_voice_of_command_non_applicable_modifiers_and_battle_shock_noops() -> None:
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=6)
    state = _require_state(lifecycle)

    assert (
        army_rule.voice_of_command_movement_modifier(
            _movement_context(state=state, unit_instance_id=ENEMY_UNIT_ID)
        )
        == 6.0
    )
    assert (
        army_rule.voice_of_command_objective_control_modifier(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=ENEMY_UNIT_ID,
                model_instance_id=f"{ENEMY_UNIT_ID}:model-001",
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 2
    )
    assert (
        army_rule.voice_of_command_unit_characteristic_modifier(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=INFANTRY_UNIT_ID,
                characteristic=Characteristic.STRENGTH,
                base_value=3,
                current_value=3,
            )
        )
        == 3
    )
    ranged_profile = _ranged_weapon_profile()
    assert (
        army_rule.voice_of_command_weapon_profile_modifier(
            _weapon_context(
                state=state,
                weapon_profile=ranged_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == ranged_profile
    )
    save_options = (
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            characteristic_target_number=3,
            armor_penetration=0,
        ),
    )
    assert (
        army_rule.voice_of_command_save_option_modifier(
            SaveOptionModifierContext(
                state=state,
                target_unit_instance_id=INFANTRY_UNIT_ID,
                save_options=save_options,
            )
        )
        == save_options
    )

    passed_context = _battle_shock_context(
        lifecycle,
        unit_instance_id=INFANTRY_UNIT_ID,
        roll_values=(6, 6),
        result_id="phase17g-astra-passed-battle-shock",
    )
    army_rule.voice_of_command_battle_shock_outcome(passed_context)
    no_order_context = _battle_shock_context(
        lifecycle,
        unit_instance_id=INFANTRY_UNIT_ID,
        roll_values=(1, 1),
        result_id="phase17g-astra-no-order-battle-shock",
    )
    army_rule.voice_of_command_battle_shock_outcome(no_order_context)

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.FIX_BAYONETS,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-fix-non-applicable",
    )
    melee_profile = _melee_weapon_profile()
    assert (
        army_rule.voice_of_command_weapon_profile_modifier(
            _weapon_context(
                state=state,
                weapon_profile=melee_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == melee_profile
    )
    assert (
        army_rule.voice_of_command_weapon_profile_modifier(
            _weapon_context(state=state, weapon_profile=ranged_profile)
        )
        == ranged_profile
    )

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.TAKE_AIM,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-aim-non-applicable",
    )
    assert (
        army_rule.voice_of_command_weapon_profile_modifier(
            _weapon_context(state=state, weapon_profile=ranged_profile)
        )
        == ranged_profile
    )
    assert (
        army_rule.voice_of_command_weapon_profile_modifier(
            _weapon_context(
                state=state,
                weapon_profile=melee_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == melee_profile
    )

    _issue_order(
        lifecycle,
        order=army_rule.VoiceOfCommandOrder.FIRST_RANK_FIRE_SECOND_RANK_FIRE,
        target_rules_unit_id=INFANTRY_UNIT_ID,
        result_id="phase17g-astra-first-rank-non-applicable",
    )
    assert (
        army_rule.voice_of_command_weapon_profile_modifier(
            _weapon_context(state=state, weapon_profile=ranged_profile)
        )
        == ranged_profile
    )
    assert (
        army_rule.voice_of_command_weapon_profile_modifier(
            _weapon_context(
                state=state,
                weapon_profile=melee_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == melee_profile
    )
    dice_rapid_fire = replace(
        _rapid_fire_weapon_profile(),
        attack_profile=AttackProfile.dice(DiceExpression(quantity=1, sides=6, modifier=2)),
        source_ids=(army_rule.SOURCE_RULE_ID,),
    )
    improved_dice = army_rule.voice_of_command_weapon_profile_modifier(
        _weapon_context(
            state=state,
            weapon_profile=dice_rapid_fire,
            source_phase=BattlePhase.SHOOTING,
        )
    )
    assert improved_dice.attack_profile.dice_expression is not None
    assert improved_dice.attack_profile.dice_expression.modifier == 3
    assert improved_dice.source_ids == (army_rule.SOURCE_RULE_ID,)


def test_voice_of_command_fail_fast_context_and_profile_guards() -> None:
    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.voice_of_command_request(cast(CommandPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_voice_of_command_result(cast(CommandPhaseStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="Battle-shock outcome requires context"):
        army_rule.voice_of_command_battle_shock_outcome(cast(BattleShockOutcomeContext, object()))
    with pytest.raises(GameLifecycleError, match="characteristic modifier requires context"):
        army_rule.voice_of_command_unit_characteristic_modifier(
            cast(UnitCharacteristicModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="movement modifier requires context"):
        army_rule.voice_of_command_movement_modifier(cast(MovementBudgetModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Objective Control modifier requires context"):
        army_rule.voice_of_command_objective_control_modifier(
            cast(ObjectiveControlModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="save option modifier requires context"):
        army_rule.voice_of_command_save_option_modifier(cast(SaveOptionModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="weapon profile modifier requires context"):
        army_rule.voice_of_command_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )

    with pytest.raises(GameLifecycleError, match="positive integer"):
        army_rule.VoiceOfCommandOrdersProfile(
            orders_per_battle_round=0,
            eligible_target_keywords=("REGIMENT",),
            allowed_order_ids=(army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,),
        )
    lifecycle = _battle_ready_lifecycle(orders_per_battle_round=1)
    state = _require_state(lifecycle)
    officer = _unit_by_id(state, unit_instance_id=OFFICER_UNIT_ID)
    target = _direct_voice_request(lifecycle).options[0]
    target_payload = _option_payload(target)
    rules_unit_id = cast(str, target_payload["ordered_rules_unit_instance_id"])
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_id)
    with pytest.raises(GameLifecycleError, match="requires officer unit"):
        army_rule.VoiceOfCommandIssueOption(
            officer_unit=cast(UnitInstance, object()),
            officer_profile=army_rule.VoiceOfCommandOrdersProfile(
                orders_per_battle_round=1,
                eligible_target_keywords=("REGIMENT",),
                allowed_order_ids=(army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,),
            ),
            target_rules_unit=rules_unit,
            order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
            issued_count_before=0,
        )
    with pytest.raises(GameLifecycleError, match="requires officer profile"):
        army_rule.VoiceOfCommandIssueOption(
            officer_unit=officer,
            officer_profile=cast(army_rule.VoiceOfCommandOrdersProfile, object()),
            target_rules_unit=rules_unit,
            order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
            issued_count_before=0,
        )
    with pytest.raises(GameLifecycleError, match="requires target rules unit"):
        army_rule.VoiceOfCommandIssueOption(
            officer_unit=officer,
            officer_profile=army_rule.VoiceOfCommandOrdersProfile(
                orders_per_battle_round=1,
                eligible_target_keywords=("REGIMENT",),
                allowed_order_ids=(army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,),
            ),
            target_rules_unit=cast(RulesUnitView, object()),
            order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
            issued_count_before=0,
        )
    with pytest.raises(GameLifecycleError, match="issued_count_before must be non-negative"):
        army_rule.VoiceOfCommandIssueOption(
            officer_unit=officer,
            officer_profile=army_rule.VoiceOfCommandOrdersProfile(
                orders_per_battle_round=1,
                eligible_target_keywords=("REGIMENT",),
                allowed_order_ids=(army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,),
            ),
            target_rules_unit=rules_unit,
            order=army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE,
            issued_count_before=-1,
        )

    unsupported_profile = _battle_ready_lifecycle(
        orders_per_battle_round=1,
        officer_orders_payload={
            "profile_kind": "phase17g:unsupported-orders-profile",
            "orders_per_battle_round": 1,
            "eligible_target_keywords": ["REGIMENT"],
            "allowed_order_ids": [army_rule.VoiceOfCommandOrder.MOVE_MOVE_MOVE.value],
        },
    )
    with pytest.raises(GameLifecycleError, match="profile kind is unsupported"):
        unsupported_profile.advance_until_decision_or_terminal()


def _issue_order(
    lifecycle: GameLifecycle,
    *,
    order: army_rule.VoiceOfCommandOrder,
    target_rules_unit_id: str,
    result_id: str,
) -> DecisionRequest:
    request = _next_voice_request(lifecycle)
    option = _order_option(request, order=order, target_rules_unit_id=target_rules_unit_id)
    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option.option_id,
        )
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    return request


def _next_voice_request(lifecycle: GameLifecycle) -> DecisionRequest:
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    return request


def _direct_voice_request(lifecycle: GameLifecycle) -> DecisionRequest:
    state = _require_state(lifecycle)
    request = army_rule.voice_of_command_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=lifecycle.decision_controller,
            active_player_id="player-a",
        )
    )
    assert request is not None
    return request


def _order_option(
    request: DecisionRequest,
    *,
    order: army_rule.VoiceOfCommandOrder,
    target_rules_unit_id: str,
) -> DecisionOption:
    for option in request.options:
        payload = _option_payload(option)
        if payload.get("order_id") != order.value:
            continue
        if payload.get("ordered_rules_unit_instance_id") != target_rules_unit_id:
            continue
        return option
    raise AssertionError(f"missing option for {order.value} to {target_rules_unit_id}")


def _done_option(request: DecisionRequest) -> DecisionOption:
    for option in request.options:
        if option.option_id == army_rule.VOICE_OF_COMMAND_DONE_OPTION_ID:
            return option
    raise AssertionError("missing Voice of Command done option")


def _command_result_context(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> CommandPhaseStartResultContext:
    return CommandPhaseStartResultContext(
        state=_require_state(lifecycle),
        decisions=lifecycle.decision_controller,
        request=request,
        result=result,
        active_player_id="player-a",
    )


def _option_payload(option: DecisionOption) -> dict[str, JsonValue]:
    payload = option.payload
    if not isinstance(payload, dict):
        raise TypeError("option payload must be an object")
    return payload


def _effect_payload(effect: PersistingEffect) -> dict[str, JsonValue]:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise TypeError("effect payload must be an object")
    return payload


def _voice_order_effects(
    state: GameState,
    *,
    target_rules_unit_id: str,
) -> tuple[PersistingEffect, ...]:
    return tuple(
        effect
        for effect in state.persisting_effects_for_unit(target_rules_unit_id)
        if effect.source_rule_id == army_rule.SOURCE_RULE_ID
        and _effect_payload(effect).get("effect_kind") == army_rule.VOICE_OF_COMMAND_EFFECT_KIND
    )


def _failed_battle_shock_context(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
) -> BattleShockOutcomeContext:
    return _battle_shock_context(
        lifecycle,
        unit_instance_id=unit_instance_id,
        roll_values=(1, 1),
        result_id="phase17g-astra-failed-battle-shock",
    )


def _battle_shock_context(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
    roll_values: tuple[int, int],
    result_id: str,
) -> BattleShockOutcomeContext:
    state = _require_state(lifecycle)
    unit = _unit_by_id(state, unit_instance_id=unit_instance_id)
    below_half = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=unit,
        starting_strength=state.starting_strength_record_for_unit(unit_instance_id),
        current_model_ids=unit.own_model_ids(),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase17g-astra-battle-shock-request",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
        reason=BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
        leadership_target=7,
        below_half_strength_context=below_half,
    )
    dice_manager = DiceRollManager(state.game_id, event_log=lifecycle.decision_controller.event_log)
    roll_state = dice_manager.roll_fixed(request.spec, roll_values)
    result = BattleShockResult.from_roll_state(
        result_id=result_id,
        request=request,
        roll_state=roll_state,
    )
    return BattleShockOutcomeContext(
        state=state,
        decisions=lifecycle.decision_controller,
        dice_manager=dice_manager,
        result=result,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=(),
    )


def _battle_ready_lifecycle(
    *,
    orders_per_battle_round: int,
    officer_orders_payload: dict[str, JsonValue] | None | object = (
        _DEFAULT_OFFICER_ORDERS_PAYLOAD
    ),
) -> GameLifecycle:
    config = _astra_config(
        orders_per_battle_round=orders_per_battle_round,
        officer_orders_payload=officer_orders_payload,
    )
    return _battle_ready_lifecycle_from_config(config)


def _non_astra_selected_lifecycle_with_astra_keyword_units(
    *,
    orders_per_battle_round: int,
) -> GameLifecycle:
    config = _astra_config(
        orders_per_battle_round=orders_per_battle_round,
        officer_orders_payload=_DEFAULT_OFFICER_ORDERS_PAYLOAD,
    )
    catalog = _catalog_with_non_astra_auxiliary_detachment(config.army_catalog)
    player_a_request, player_b_request = config.army_muster_requests
    non_astra_request = replace(
        player_a_request,
        catalog_id=catalog.catalog_id,
        detachment_selection=DetachmentSelection(
            faction_id=NON_ASTRA_FACTION_ID,
            detachment_ids=(NON_ASTRA_DETACHMENT_ID,),
        ),
    )
    return _battle_ready_lifecycle_from_config(
        replace(
            config,
            army_catalog=catalog,
            army_muster_requests=(non_astra_request, player_b_request),
        )
    )


def _battle_ready_lifecycle_from_config(config: GameConfig) -> GameLifecycle:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-astra-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _place_unit(state, unit_instance_id=OFFICER_UNIT_ID, x=10.0, y=10.0)
    _place_unit(state, unit_instance_id=INFANTRY_UNIT_ID, x=13.0, y=10.0)
    _place_unit(state, unit_instance_id=SQUADRON_UNIT_ID, x=15.0, y=10.0)
    _place_unit(state, unit_instance_id=UNORDERABLE_UNIT_ID, x=12.0, y=13.0)
    _place_unit(state, unit_instance_id=ENEMY_UNIT_ID, x=35.0, y=10.0)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(state=state, config=config)
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _catalog_with_non_astra_auxiliary_detachment(catalog: ArmyCatalog) -> ArmyCatalog:
    return replace(
        catalog,
        factions=(
            *catalog.factions,
            FactionDefinition(
                faction_id=NON_ASTRA_FACTION_ID,
                name="Non-Astra Auxiliary Force",
                faction_keywords=("ASTRA MILITARUM", "NON-ASTRA"),
                source_ids=("phase17g:astra:non-astra:faction",),
            ),
        ),
        detachments=(
            *catalog.detachments,
            DetachmentDefinition(
                detachment_id=NON_ASTRA_DETACHMENT_ID,
                name="Non-Astra Auxiliary Detachment",
                faction_id=NON_ASTRA_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    OFFICER_DATASHEET_ID,
                    INFANTRY_DATASHEET_ID,
                    SQUADRON_DATASHEET_ID,
                    UNORDERABLE_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:astra:non-astra:detachment",),
            ),
        ),
    )


def _astra_config(
    *,
    orders_per_battle_round: int,
    officer_orders_payload: dict[str, JsonValue] | None | object,
) -> GameConfig:
    catalog = _astra_lifecycle_catalog(
        orders_per_battle_round=orders_per_battle_round,
        officer_orders_payload=officer_orders_payload,
    )
    return GameConfig(
        game_id="phase17g-astra-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-astra-test",
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
                    faction_id=army_rule.ASTRA_MILITARUM_FACTION_ID,
                    detachment_ids=("combined-regiment",),
                ),
                unit_selections=(
                    _unit_selection("castellan", OFFICER_DATASHEET_ID),
                    _unit_selection("infantry", INFANTRY_DATASHEET_ID),
                    _unit_selection("sentinel", SQUADRON_DATASHEET_ID),
                    _unit_selection("servitors", UNORDERABLE_DATASHEET_ID),
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
                unit_selections=(_unit_selection("enemy-unit", "core-intercessor-like-infantry"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _astra_lifecycle_catalog(
    *,
    orders_per_battle_round: int,
    officer_orders_payload: dict[str, JsonValue] | None | object,
) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    order_payload = (
        _orders_profile_payload(orders_per_battle_round=orders_per_battle_round)
        if officer_orders_payload is _DEFAULT_OFFICER_ORDERS_PAYLOAD
        else cast(dict[str, JsonValue] | None, officer_orders_payload)
    )
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            _datasheet(
                base_datasheet,
                datasheet_id=OFFICER_DATASHEET_ID,
                name="Cadian Castellan",
                keywords=("CHARACTER", "INFANTRY", "OFFICER"),
                faction_keywords=("ASTRA MILITARUM",),
                abilities=(_orders_ability(order_payload),),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=INFANTRY_DATASHEET_ID,
                name="Cadian Shock Troops",
                keywords=("INFANTRY", "REGIMENT"),
                faction_keywords=("ASTRA MILITARUM",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=SQUADRON_DATASHEET_ID,
                name="Armoured Sentinel",
                keywords=("VEHICLE", "SQUADRON"),
                faction_keywords=("ASTRA MILITARUM",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=UNORDERABLE_DATASHEET_ID,
                name="Munitorum Servitors",
                keywords=("INFANTRY",),
                faction_keywords=("ASTRA MILITARUM",),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.ASTRA_MILITARUM_FACTION_ID,
                name="Astra Militarum",
                faction_keywords=("ASTRA MILITARUM",),
                source_ids=("phase17g:astra:faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="combined-regiment",
                name="Combined Regiment",
                faction_id=army_rule.ASTRA_MILITARUM_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    OFFICER_DATASHEET_ID,
                    INFANTRY_DATASHEET_ID,
                    SQUADRON_DATASHEET_ID,
                    UNORDERABLE_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:astra:detachment:combined-regiment",),
            ),
        ),
    )


def _orders_profile_payload(*, orders_per_battle_round: int) -> dict[str, JsonValue]:
    return {
        "profile_kind": army_rule.ORDERS_PROFILE_KIND,
        "orders_per_battle_round": orders_per_battle_round,
        "eligible_target_keywords": ["REGIMENT", "SQUADRON"],
        "allowed_order_ids": [order.value for order in army_rule.VoiceOfCommandOrder],
    }


def _orders_ability(rule_ir_payload: dict[str, JsonValue] | None) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="phase17g-astra-orders",
        name="Orders",
        source_id=army_rule.SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="voice-of-command-orders-profile",
        rule_ir_payload=rule_ir_payload,
    )


def _datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    abilities: tuple[DatasheetAbilityDescriptor, ...] = (),
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=faction_keywords,
        ),
        abilities=abilities,
        source_ids=(f"phase17g:astra:datasheet:{datasheet_id}",),
    )


def _unit_selection(unit_selection_id: str, datasheet_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _place_unit(
    state: GameState,
    *,
    unit_instance_id: str,
    x: float,
    y: float,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("battlefield is required")
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    updated = placement.with_model_placements(
        tuple(
            model_placement.with_pose(Pose.at(x + float(index), y, 0.0))
            for index, model_placement in enumerate(placement.model_placements)
        )
    )
    state.battlefield_state = battlefield.with_unit_placement(updated)


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _complete_setup_through_gate(*, state: GameState, config: GameConfig) -> None:
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=DecisionController(),
        config=config,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _movement_context(*, state: GameState, unit_instance_id: str) -> MovementBudgetModifierContext:
    return MovementBudgetModifierContext(
        state=state,
        unit_instance_id=unit_instance_id,
        model_instance_id=f"{unit_instance_id}:model-001",
        base_movement_inches=6.0,
        current_movement_inches=6.0,
    )


def _weapon_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    source_phase: BattlePhase = BattlePhase.FIGHT,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=INFANTRY_UNIT_ID,
        attacker_model_instance_id=f"{INFANTRY_UNIT_ID}:model-001",
        target_unit_instance_id=ENEMY_UNIT_ID,
        weapon_profile=weapon_profile,
    )


def _melee_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-astra-bayonet",
        name="Bayonet",
        range_profile=RangeProfile.melee(),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 3),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:astra:test-melee-weapon",),
    )


def _ranged_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-astra-lasgun",
        name="Lasgun",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 3),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:astra:test-ranged-weapon",),
    )


def _rapid_fire_weapon_profile() -> WeaponProfile:
    return replace(
        _ranged_weapon_profile(),
        profile_id="phase17g-astra-rapid-lasgun",
        keywords=(WeaponKeyword.RAPID_FIRE,),
        attack_profile=AttackProfile.fixed(2),
    )


def _unit_by_id(state: GameState, *, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _require_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("lifecycle state is required")
    return lifecycle.state


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()
