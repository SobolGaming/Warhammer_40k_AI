from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.battle_shock_historical_helpers import historical_battle_shock_context_for_unit
from tests.phase11c_command_phase_helpers import (
    battle_shock_request_for_unit,
    battle_state,
    center_marker_definition,
    default_unit_selection,
    remove_first_models,
    unit_by_id,
    unit_selection,
    with_model_offsets,
)
from tests.setup_completion_helpers import ensure_army_mustered_events_for_fixture

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
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockForcedTestContext,
    BattleShockHookBinding,
    BattleShockHookRegistry,
    BattleShockModifierApplication,
    BattleShockModifierApplicationAuthorityContext,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    parse_pending_battle_shock_reroll_authority,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    army_rule as chaos_daemons_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.tyranids import (
    army_rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.healing import SELECT_HEALING_MODEL_DECISION_TYPE
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.command import (
    CommandPhaseHandler,
    invalid_command_phase_decision_status,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
)

TYRANIDS_WARRIORS_DATASHEET_ID = "phase17g-tyranids-warriors"
TYRANIDS_GAUNTS_DATASHEET_ID = "phase17g-tyranids-gaunts"
TYRANIDS_WARRIORS_UNIT_ID = "army-alpha:warriors"
TYRANIDS_GAUNTS_UNIT_ID = "army-alpha:gaunts"
ENEMY_UNIT_ID = "army-beta:enemy-unit"
TYRANIDS_DETACHMENT_ID = "phase17g-tyranids-synaptic-test"


def test_lifecycle_requests_shadow_in_either_command_phase_and_resolves_battle_shock() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-shadow",
        active_player_id="player-b",
    )
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    summary_payload = _runtime_content_bundle(lifecycle).to_summary_payload()
    assert army_rule.HOOK_ID in summary_payload["command_phase_start_hook_ids"]
    assert army_rule.BATTLE_SHOCK_HOOK_ID in summary_payload["battle_shock_hook_ids"]
    assert army_rule.WEAPON_PROFILE_MODIFIER_ID in summary_payload["weapon_profile_modifier_ids"]

    status = lifecycle.advance_until_decision_or_terminal()

    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        army_rule.SHADOW_UNLEASH_OPTION_ID,
        army_rule.SHADOW_DECLINE_OPTION_ID,
    }
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["active_player_id"] == "player-b"
    assert request_payload["actor_may_be_non_active"] is True
    assert request_payload["effect_kind"] == army_rule.SHADOW_EFFECT_KIND
    assert json.loads(json.dumps(request.to_payload())) == request.to_payload()

    result_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-unleash-shadow",
            request=request,
            selected_option_id=army_rule.SHADOW_UNLEASH_OPTION_ID,
        )
    )

    assert result_status.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    assert army_rule.shadow_in_the_warp_unleashed_for_player(state, player_id="player-a")
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()
    requested_payload = _event_payload(
        lifecycle.decision_controller,
        "battle_shock_test_requested",
    )
    battle_shock_request = cast(
        dict[str, JsonValue],
        requested_payload["battle_shock_test_request"],
    )
    request_spec = cast(dict[str, JsonValue], battle_shock_request["spec"])
    request_expression = cast(dict[str, JsonValue], request_spec["expression"])
    assert battle_shock_request["unit_instance_id"] == ENEMY_UNIT_ID
    assert battle_shock_request["reason"] == BattleShockTestReason.FORCED_BY_ARMY_RULE.value
    assert request_expression["quantity"] == 2
    assert request_expression["sides"] == 6

    resolved_payload = _event_payload(
        lifecycle.decision_controller,
        "battle_shock_test_resolved",
    )
    result_payload = cast(dict[str, JsonValue], resolved_payload["battle_shock_result"])
    modified_roll = cast(dict[str, JsonValue], result_payload["modified_roll"])
    modifiers = cast(list[JsonValue], modified_roll["modifiers"])
    assert len(modifiers) == 1
    modifier = cast(dict[str, JsonValue], modifiers[0])
    assert modifier["source_id"] == army_rule.SOURCE_RULE_ID
    assert modifier["operand"] == -1
    lifecycle_payload = lifecycle.to_payload()
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload
    forged_lifecycle_payload = cast(
        dict[str, object],
        json.loads(json.dumps(lifecycle_payload)),
    )
    forged_decisions = cast(dict[str, object], forged_lifecycle_payload["decisions"])
    forged_events = cast(list[dict[str, object]], forged_decisions["event_log"])
    application_event = next(
        event
        for event in forged_events
        if event["event_type"] == "battle_shock_modifier_applications_recorded"
    )
    application_payload = cast(dict[str, object], application_event["payload"])
    applications = cast(
        list[dict[str, object]],
        application_payload["battle_shock_modifier_applications"],
    )
    applications[0]["hook_id"] = "forged:shadow-modifier-hook"
    with pytest.raises(GameLifecycleError, match="provider output evidence drifted"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged_lifecycle_payload))


def test_restore_rejects_coordinated_shadow_source_state_kind_tamper() -> None:
    lifecycle = _resolved_shadow_lifecycle(
        game_id="phase17g-tyranids-shadow-source-state-kind-tamper",
    )
    forged = _mutable_lifecycle_payload(lifecycle)

    def rewrite_shadow_state_kind(value: object) -> None:
        if isinstance(value, dict):
            object_value = cast(dict[str, object], value)
            if (
                object_value.get("state_kind") == army_rule.SHADOW_STATE_KIND
                and object_value.get("source_rule_id") == army_rule.SOURCE_RULE_ID
            ):
                object_value["state_kind"] = "forged:shadow-source-state-kind"
            for nested in object_value.values():
                rewrite_shadow_state_kind(nested)
            return
        if isinstance(value, list):
            for nested in cast(list[object], value):
                rewrite_shadow_state_kind(nested)

    rewrite_shadow_state_kind(forged)
    forged_decisions = cast(dict[str, object], forged["decisions"])
    forged_events = cast(list[dict[str, object]], forged_decisions["event_log"])
    events_by_id = {cast(str, event["event_id"]): event for event in forged_events}
    for event in forged_events:
        event_payload = event.get("payload")
        if not isinstance(event_payload, dict):
            continue
        typed_event_payload = cast(dict[str, object], event_payload)
        rows = typed_event_payload.get("provider_dispositions")
        if not isinstance(rows, list):
            continue
        for row in cast(list[object], rows):
            if not isinstance(row, dict):
                continue
            typed_row = cast(dict[str, object], row)
            event_ids = typed_row.get("emitted_event_ids")
            if not isinstance(event_ids, list):
                continue
            emitted = [
                events_by_id[cast(str, event_id)] for event_id in cast(list[object], event_ids)
            ]
            typed_row["emitted_events_hash"] = hashlib.sha256(
                canonical_json(emitted).encode("utf-8")
            ).hexdigest()

    with pytest.raises(GameLifecycleError, match="Completed Shadow in the Warp authority drifted"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_shadow_reroll_restore_continues_each_target_before_success_completion() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-shadow-multi-target-reroll",
        active_player_id="player-b",
        enemy_unit_count=2,
        enemy_battle_shock_reroll=True,
    )
    outer_request = _initial_shadow_request(lifecycle)
    first_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-multi-target-reroll:unleash",
            request=outer_request,
            selected_option_id=army_rule.SHADOW_UNLEASH_OPTION_ID,
        )
    )
    first_reroll = first_status.decision_request
    assert first_reroll is not None
    assert first_reroll.actor_id == "player-b"
    first_authority = parse_pending_battle_shock_reroll_authority(first_reroll)
    assert first_authority.source_kind == "command_phase_start_battle_shock"
    assert first_authority.test_request.unit_instance_id == ENEMY_UNIT_ID

    first_pending_payload = _mutable_lifecycle_payload(lifecycle)
    tampered = cast(dict[str, object], json.loads(json.dumps(first_pending_payload)))
    tampered_state = cast(dict[str, object], tampered["state"])
    source_states = cast(list[dict[str, object]], tampered_state["faction_rule_states"])
    shadow_state = next(
        row for row in source_states if row["state_kind"] == army_rule.SHADOW_STATE_KIND
    )
    shadow_payload = cast(dict[str, object], shadow_state["payload"])
    shadow_targets = cast(list[str], shadow_payload["target_enemy_unit_instance_ids"])
    shadow_payload["target_enemy_unit_instance_ids"] = list(reversed(shadow_targets))
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, tampered))

    restored = GameLifecycle.from_payload(cast(GameLifecyclePayload, first_pending_payload))
    first_reroll = restored.decision_controller.queue.peek_next()
    second_status = restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-multi-target-reroll:first-decline",
            request=first_reroll,
            selected_option_id="decline",
        )
    )
    second_reroll = second_status.decision_request
    assert second_reroll is not None
    second_authority = parse_pending_battle_shock_reroll_authority(second_reroll)
    assert second_authority.test_request.unit_instance_id == "army-beta:enemy-unit-2"
    assert not any(
        event.event_type == "tyranids_shadow_in_the_warp_unleashed"
        for event in restored.decision_controller.event_log.records
    )

    restored = GameLifecycle.from_payload(restored.to_payload())
    second_reroll = restored.decision_controller.queue.peek_next()
    restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-multi-target-reroll:second-decline",
            request=second_reroll,
            selected_option_id="decline",
        )
    )
    completion_events = tuple(
        event
        for event in restored.decision_controller.event_log.records
        if event.event_type == "tyranids_shadow_in_the_warp_unleashed"
    )
    assert len(completion_events) == 1
    completion_payload = cast(dict[str, JsonValue], completion_events[0].payload)
    assert completion_payload["battle_shock_result_ids"] == [
        f"{first_authority.test_request.request_id}:result",
        f"{second_authority.test_request.request_id}:result",
    ]


def test_shadow_outcome_revival_restore_preempts_completion_and_resumes_exactly_once() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-shadow-outcome-2",
        active_player_id="player-b",
        enemy_chaos_daemons=True,
    )
    state = _require_state(lifecycle)
    _place_unit_in_owner_deployment_zone(state, unit_instance_id=ENEMY_UNIT_ID)
    remove_first_models(state, unit_instance_id=ENEMY_UNIT_ID, count=1)
    outer_request = _initial_shadow_request(lifecycle)

    pending = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-daemonic-outcome:unleash",
            request=outer_request,
            selected_option_id=army_rule.SHADOW_UNLEASH_OPTION_ID,
        )
    )

    outcome_request = pending.decision_request
    assert outcome_request is not None
    assert outcome_request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    assert not any(
        event.event_type == "tyranids_shadow_in_the_warp_unleashed"
        for event in lifecycle.decision_controller.event_log.records
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    restored_request = restored.decision_controller.queue.peek_next()
    finish_option = next(
        option for option in restored_request.options if option.option_id.endswith(":finish")
    )

    restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-daemonic-outcome:finish",
            request=restored_request,
            selected_option_id=finish_option.option_id,
        )
    )

    completions = tuple(
        event
        for event in restored.decision_controller.event_log.records
        if event.event_type == "tyranids_shadow_in_the_warp_unleashed"
    )
    assert len(completions) == 1


def test_shadow_outcome_restore_rejects_coordinated_revival_amount_forgery() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-shadow-outcome-amount-forgery",
        active_player_id="player-b",
        enemy_chaos_daemons=True,
    )
    state = _require_state(lifecycle)
    _place_unit_in_owner_deployment_zone(state, unit_instance_id=ENEMY_UNIT_ID)
    remove_first_models(state, unit_instance_id=ENEMY_UNIT_ID, count=1)
    outer_request = _initial_shadow_request(lifecycle)
    pending = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-shadow-outcome-amount-forgery:unleash",
            request=outer_request,
            selected_option_id=army_rule.SHADOW_UNLEASH_OPTION_ID,
        )
    )
    assert pending.decision_request is not None
    forged = _mutable_lifecycle_payload(lifecycle)
    rewritten = 0

    def rewrite_effect_amount(value: object) -> None:
        nonlocal rewritten
        if isinstance(value, dict):
            payload = cast(dict[str, object], value)
            effect_id = payload.get("effect_id")
            amount = payload.get("amount")
            if (
                type(effect_id) is str
                and effect_id.startswith(
                    f"{chaos_daemons_army_rule.JULY_HOOK_ID}:daemonic-manifestation-battleline:"
                )
                and type(amount) is int
            ):
                payload["amount"] = amount + 3
                rewritten += 1
            for nested in payload.values():
                rewrite_effect_amount(nested)
            return
        if isinstance(value, list):
            for nested in cast(list[object], value):
                rewrite_effect_amount(nested)

    rewrite_effect_amount(forged)
    assert rewritten >= 3
    forged_decisions = cast(dict[str, object], forged["decisions"])
    forged_events = cast(list[dict[str, object]], forged_decisions["event_log"])
    events_by_id = {cast(str, event["event_id"]): event for event in forged_events}
    for event in forged_events:
        event_payload = event.get("payload")
        if not isinstance(event_payload, dict):
            continue
        rows = cast(dict[str, object], event_payload).get("provider_dispositions")
        if not isinstance(rows, list):
            continue
        for row in cast(list[object], rows):
            if not isinstance(row, dict):
                continue
            typed_row = cast(dict[str, object], row)
            event_ids = typed_row.get("emitted_event_ids")
            if not isinstance(event_ids, list):
                continue
            emitted = [
                events_by_id[cast(str, event_id)] for event_id in cast(list[object], event_ids)
            ]
            typed_row["emitted_events_hash"] = hashlib.sha256(
                canonical_json(emitted).encode("utf-8")
            ).hexdigest()

    with pytest.raises(GameLifecycleError, match="Daemonic Manifestation"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_restore_rejects_coordinated_shadow_leadership_and_dice_semantic_tamper() -> None:
    lifecycle = _resolved_shadow_lifecycle(
        game_id="phase17g-tyranids-coordinated-semantics-tamper",
    )
    forged = _mutable_lifecycle_payload(lifecycle)
    events = _mutable_lifecycle_events(forged)

    for event in events:
        event_type = event["event_type"]
        event_payload = cast(dict[str, object], event["payload"])
        if event_type in {
            "battle_shock_test_requested",
            "battle_shock_modifier_applications_recorded",
        }:
            _forge_shadow_request_leadership_and_expression(
                cast(dict[str, object], event_payload["battle_shock_test_request"])
            )
        elif event_type == "dice_rolled":
            dice_values = cast(list[int], event_payload["values"])
            dice_values.append(1)
            event_payload["total"] = cast(int, event_payload["total"]) + 1
            dice_spec = cast(dict[str, object], event_payload["spec"])
            dice_expression = cast(dict[str, object], dice_spec["expression"])
            dice_expression["quantity"] = 3
        elif event_type == "battle_shock_test_resolved":
            result = cast(dict[str, object], event_payload["battle_shock_result"])
            _forge_shadow_request_leadership_and_expression(
                cast(dict[str, object], result["request"])
            )
            result["leadership_target"] = cast(int, result["leadership_target"]) + 1
            result["total"] = cast(int, result["total"]) + 1
            roll_state = cast(dict[str, object], result["roll_state"])
            current_values = cast(list[int], roll_state["current_values"])
            current_values.append(1)
            roll_state["current_total"] = cast(int, roll_state["current_total"]) + 1
            original_result = cast(dict[str, object], roll_state["original_result"])
            original_values = cast(list[int], original_result["values"])
            original_values.append(1)
            original_result["total"] = cast(int, original_result["total"]) + 1
            original_spec = cast(dict[str, object], original_result["spec"])
            original_expression = cast(dict[str, object], original_spec["expression"])
            original_expression["quantity"] = 3
            modified_roll = cast(dict[str, object], result["modified_roll"])
            unmodified = cast(dict[str, object], modified_roll["unmodified"])
            component_values = cast(list[int], unmodified["component_values"])
            component_values.append(1)
            unmodified["value"] = cast(int, unmodified["value"]) + 1
            modified_roll["final_value"] = cast(int, modified_roll["final_value"]) + 1

    with pytest.raises(GameLifecycleError, match="provider output evidence drifted"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_restore_rejects_omitted_mandatory_shadow_modifier_application() -> None:
    lifecycle = _resolved_shadow_lifecycle(
        game_id="phase17g-tyranids-omitted-modifier-authority",
    )
    forged = _mutable_lifecycle_payload(lifecycle)
    events = _mutable_lifecycle_events(forged)
    application_event = _mutable_event(events, "battle_shock_modifier_applications_recorded")
    application_payload = cast(dict[str, object], application_event["payload"])
    application_payload["battle_shock_modifier_applications"] = []
    resolved_event = _mutable_event(events, "battle_shock_test_resolved")
    resolved_payload = cast(dict[str, object], resolved_event["payload"])
    result = cast(dict[str, object], resolved_payload["battle_shock_result"])
    modified_roll = cast(dict[str, object], result["modified_roll"])
    unmodified = cast(dict[str, object], modified_roll["unmodified"])
    unmodified_value = cast(int, unmodified["value"])
    assert result["passed"] is True
    assert unmodified_value >= cast(int, result["leadership_target"])
    modified_roll["modifiers"] = []
    modified_roll["applied_modifier_ids"] = []
    modified_roll["final_value"] = unmodified_value
    result["total"] = unmodified_value

    with pytest.raises(GameLifecycleError, match="provider output evidence drifted"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_restore_rejects_out_of_context_inserted_shadow_modifier_application() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-inserted-modifier-authority",
        active_player_id="player-b",
    )
    state = _require_state(lifecycle)
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    enemy = state.battlefield_state.unit_placement_by_id(ENEMY_UNIT_ID)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            enemy,
            marker,
            offsets=(
                (20.0, -0.5),
                (20.4, -0.5),
                (20.8, -0.5),
                (21.2, -0.5),
                (21.6, -0.5),
            ),
        )
    )
    tyranids_army = state.army_definition_for_player("player-a")
    assert tyranids_army is not None
    assert not army_rule.tyranids_unit_within_synapse_range(
        state,
        tyranids_army=tyranids_army,
        unit_instance_id=ENEMY_UNIT_ID,
    )
    request = lifecycle.advance_until_decision_or_terminal().decision_request
    assert request is not None
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-inserted-modifier-authority:unleash",
            request=request,
            selected_option_id=army_rule.SHADOW_UNLEASH_OPTION_ID,
        )
    )
    forged = _mutable_lifecycle_payload(lifecycle)
    events = _mutable_lifecycle_events(forged)
    application_event = _mutable_event(events, "battle_shock_modifier_applications_recorded")
    application_payload = cast(dict[str, object], application_event["payload"])
    request_payload = cast(dict[str, object], application_payload["battle_shock_test_request"])
    request_id = cast(str, request_payload["request_id"])
    modifier_id = f"{army_rule.BATTLE_SHOCK_HOOK_ID}:shadow-penalty:{request_id}:player-a"
    modifier_payload: dict[str, object] = {
        "modifier_id": modifier_id,
        "operand": 0,
        "operation": "add",
        "priority": 0,
        "source_id": army_rule.SOURCE_RULE_ID,
    }
    application_payload["battle_shock_modifier_applications"] = [
        {
            "hook_id": army_rule.BATTLE_SHOCK_HOOK_ID,
            "source_id": army_rule.SOURCE_RULE_ID,
            "modifiers": [modifier_payload],
        }
    ]
    resolved_event = _mutable_event(events, "battle_shock_test_resolved")
    resolved_payload = cast(dict[str, object], resolved_event["payload"])
    result = cast(dict[str, object], resolved_payload["battle_shock_result"])
    modified_roll = cast(dict[str, object], result["modified_roll"])
    unmodified = cast(dict[str, object], modified_roll["unmodified"])
    unmodified_value = cast(int, unmodified["value"])
    modified_roll["modifiers"] = [modifier_payload]
    modified_roll["applied_modifier_ids"] = [modifier_id]
    modified_roll["final_value"] = unmodified_value
    result["total"] = unmodified_value

    with pytest.raises(GameLifecycleError, match="provider output evidence drifted"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))


def test_shadow_request_sequences_with_active_player_command_start_request() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-shadow-sequencing",
        active_player_id="player-b",
    )
    state = _require_state(lifecycle)
    contribution = army_rule.runtime_contribution()
    registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase17g:active-command-start:test",
                source_id="phase17g:active-command-start:source",
                request_handler=_active_command_start_request,
                result_handler=lambda _context: False,
            ),
            contribution.command_phase_start_hook_bindings[0],
        )
    )

    request = registry.next_request_for(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=lifecycle.decision_controller,
            active_player_id="player-b",
        )
    )

    assert request is not None
    assert request.request_id == "phase17g:active-command-start:player-b"
    assert request.actor_id == "player-b"


def test_shadow_in_the_warp_targets_an_attached_enemy_once_by_canonical_identity() -> None:
    state = battle_state(
        game_id="phase17g-tyranids-shadow-attached-enemy",
        player_b_units=(
            default_unit_selection("shadow-bodyguard"),
            unit_selection(
                unit_selection_id="shadow-leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_b_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="shadow-leader",
                bodyguard_unit_selection_id="shadow-bodyguard",
            ),
        ),
    )
    state.army_definitions = [
        replace(
            army,
            detachment_selection=replace(
                army.detachment_selection,
                faction_id=army_rule.TYRANIDS_FACTION_ID,
            ),
            units=tuple(
                replace(unit, faction_keywords=(army_rule.TYRANIDS_FACTION_KEYWORD,))
                for unit in army.units
            ),
        )
        if army.player_id == "player-a"
        else army
        for army in state.army_definitions
    ]
    state.active_player_id = "player-b"
    state.command_step_state = None
    enemy_army = state.army_definition_for_player("player-b")
    assert enemy_army is not None
    attached_id = enemy_army.attached_units[0].attached_unit_instance_id
    decisions = DecisionController()
    request = army_rule.shadow_in_the_warp_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-b",
        )
    )
    assert request is not None
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["target_enemy_unit_instance_ids"] == [attached_id]

    decisions.request_decision(request)
    result_record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-attached-enemy-result",
            request=request,
            selected_option_id=army_rule.SHADOW_UNLEASH_OPTION_ID,
        )
    )

    assert army_rule.apply_shadow_in_the_warp_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result_record.result,
            active_player_id="player-b",
            ability_indexes_by_player_id={
                "player-a": AbilityCatalogIndex.from_records(()),
                "player-b": AbilityCatalogIndex.from_records(()),
            },
        )
    )
    requested_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "battle_shock_test_requested"
    )
    resolved_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "battle_shock_test_resolved"
    )
    assert len(requested_events) == 1
    assert len(resolved_events) == 1
    requested_payload = cast(dict[str, JsonValue], requested_events[0].payload)
    battle_shock_request = cast(
        dict[str, JsonValue],
        requested_payload["battle_shock_test_request"],
    )
    assert battle_shock_request["unit_instance_id"] == attached_id


def test_lifecycle_rejects_shadow_drift_before_mutation() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-shadow-drift",
        active_player_id="player-b",
    )
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    option = request.option_by_id(army_rule.SHADOW_UNLEASH_OPTION_ID)
    state = _require_state(lifecycle)

    request_payload = cast(dict[str, JsonValue], request.payload)
    request_without_flag = replace(
        request,
        payload=validate_json_value(
            {
                key: value
                for key, value in request_payload.items()
                if key != "actor_may_be_non_active"
            }
        ),
    )
    non_active_status = invalid_command_phase_decision_status(
        state=state,
        decisions=lifecycle.decision_controller,
        battle_shock_hooks=lifecycle._command_phase_handler.battle_shock_hooks,  # pyright: ignore[reportPrivateUsage]
        request=request_without_flag,
        result=DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-non-active-check",
            request=request,
            selected_option_id=option.option_id,
        ),
    )
    assert non_active_status is not None
    assert isinstance(non_active_status.payload, dict)
    assert non_active_status.payload["invalid_reason"] == "player_not_active"

    malformed_payload = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-tyranids-shadow-malformed-payload",
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
    assert not army_rule.shadow_in_the_warp_unleashed_for_player(state, player_id="player-a")

    drifted_payload = dict(cast(dict[str, JsonValue], option.payload))
    drifted_payload["battle_round"] = 99
    payload_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-tyranids-shadow-payload-drift",
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
    assert not army_rule.shadow_in_the_warp_unleashed_for_player(state, player_id="player-a")

    state.battle_round = 2
    stale_request = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tyranids-shadow-stale-request",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert stale_request.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(stale_request.payload, dict)
    assert stale_request.payload["invalid_reason"] == "battle_round_drift"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert not army_rule.shadow_in_the_warp_unleashed_for_player(state, player_id="player-a")


def test_shadow_decline_suppresses_only_current_command_phase_request() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-shadow-decline",
        active_player_id="player-b",
    )
    request = _initial_shadow_request(lifecycle)
    state = _require_state(lifecycle)

    assert army_rule.apply_shadow_in_the_warp_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=lifecycle.decision_controller,
            request=request,
            result=DecisionResult.for_request(
                result_id="phase17g-tyranids-shadow-decline-result",
                request=request,
                selected_option_id=army_rule.SHADOW_DECLINE_OPTION_ID,
            ),
            active_player_id="player-b",
        )
    )

    assert not army_rule.shadow_in_the_warp_unleashed_for_player(state, player_id="player-a")
    assert state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.SHADOW_DECLINE_STATE_KIND,
    )
    assert (
        army_rule.shadow_in_the_warp_request(
            CommandPhaseStartRequestContext(
                state=state,
                decisions=lifecycle.decision_controller,
                active_player_id="player-b",
            )
        )
        is None
    )


def test_synapse_battle_shock_uses_three_d6_in_command_phase() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-synapse-battle-shock",
        active_player_id="player-a",
    )
    state = _require_state(lifecycle)
    remove_first_models(state, unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID, count=3)
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    requested_payload = _event_payload(decisions, "battle_shock_test_requested")
    battle_shock_request = cast(
        dict[str, JsonValue],
        requested_payload["battle_shock_test_request"],
    )
    spec = cast(dict[str, JsonValue], battle_shock_request["spec"])
    expression = cast(dict[str, JsonValue], spec["expression"])
    assert battle_shock_request["unit_instance_id"] == TYRANIDS_GAUNTS_UNIT_ID
    assert battle_shock_request["reason"] == BattleShockTestReason.COMMAND_PHASE_REQUIRED.value
    assert expression["quantity"] == 3
    assert expression["sides"] == 6


def test_synapse_historical_contribution_recomputes_from_authenticated_geometry() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-historical-synapse",
        active_player_id="player-a",
        authenticate_reposition=True,
    )
    state = _require_state(lifecycle)
    context = historical_battle_shock_context_for_unit(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
        active_player_id="player-a",
    )

    contribution = army_rule.historical_synapse_battle_shock_contribution(context)

    assert contribution.dice_expression == DiceExpression(quantity=3, sides=6)
    assert contribution.modifiers == ()
    with pytest.raises(GameLifecycleError, match="historical authority requires"):
        army_rule.historical_synapse_battle_shock_contribution(cast(Any, object()))


def test_synapse_melee_strength_modifier_uses_live_range() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-synapse-strength",
        active_player_id="player-a",
    )
    state = _require_state(lifecycle)
    registry = _runtime_modifier_registry()
    melee_profile = _melee_weapon_profile()
    ranged_profile = _ranged_weapon_profile()

    modified = registry.modified_weapon_profile(
        _weapon_context(state=state, weapon_profile=melee_profile)
    )

    assert modified.strength.final == melee_profile.strength.final + 1
    assert army_rule.SOURCE_RULE_ID in modified.source_ids
    assert (
        registry.modified_weapon_profile(
            _weapon_context(state=state, weapon_profile=ranged_profile)
        )
        == ranged_profile
    )
    assert (
        registry.modified_weapon_profile(
            _weapon_context(
                state=state,
                weapon_profile=melee_profile,
                source_phase=BattlePhase.COMMAND,
            )
        )
        == melee_profile
    )


def test_synapse_source_geometry_does_not_expand_to_attached_bodyguards() -> None:
    source_bodyguard_id = "army-alpha:synapse-bodyguard"
    source_leader_id = "army-alpha:synapse-leader"
    target_unit_id = "army-alpha:synapse-target"
    state = battle_state(
        game_id="phase17g-tyranids-attached-synapse-source-geometry",
        player_a_units=(
            default_unit_selection("synapse-bodyguard"),
            unit_selection(
                unit_selection_id="synapse-leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            default_unit_selection("synapse-target"),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="synapse-leader",
                bodyguard_unit_selection_id="synapse-bodyguard",
            ),
        ),
    )
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.TYRANIDS_FACTION_ID,
                ),
                units=tuple(
                    replace(
                        unit,
                        keywords=(
                            (*unit.keywords, army_rule.SYNAPSE_KEYWORD)
                            if unit.unit_instance_id == source_leader_id
                            else unit.keywords
                        ),
                        faction_keywords=(army_rule.TYRANIDS_FACTION_KEYWORD,),
                    )
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies
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
    tyranids_army = state.army_definition_for_player("player-a")
    assert tyranids_army is not None

    assert not army_rule.tyranids_unit_within_synapse_range(
        state,
        tyranids_army=tyranids_army,
        unit_instance_id=target_unit_id,
    )


@pytest.mark.stubbed
def test_battle_shock_hook_registry_dice_expression_contracts() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-battle-shock-dice-hooks",
        active_player_id="player-a",
    )
    state = _require_state(lifecycle)
    context = _battle_shock_dice_context(state)
    default_expression = DiceExpression(quantity=2, sides=6)
    synapse_expression = DiceExpression(quantity=3, sides=6)

    assert BattleShockHookRegistry.empty().dice_expression_for(context) == default_expression
    assert (
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:dice-none",
                    source_id="phase17g:dice-none:source",
                    dice_expression_handler=lambda _context: None,
                ),
                BattleShockHookBinding(
                    hook_id="phase17g:dice-synapse",
                    source_id="phase17g:dice-synapse:source",
                    dice_expression_handler=lambda _context: synapse_expression,
                ),
            )
        ).dice_expression_for(context)
        == synapse_expression
    )

    with pytest.raises(GameLifecycleError, match="requires at least one handler"):
        BattleShockHookBinding(
            hook_id="phase17g:dice-empty",
            source_id="phase17g:dice-empty:source",
        )
    with pytest.raises(GameLifecycleError, match="dice_expression_handler must be callable"):
        BattleShockHookBinding(
            hook_id="phase17g:dice-not-callable",
            source_id="phase17g:dice-not-callable:source",
            dice_expression_handler=cast(
                Callable[[BattleShockDiceExpressionContext], DiceExpression | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="dice-expression hooks require a context"):
        BattleShockHookRegistry.empty().dice_expression_for(
            cast(BattleShockDiceExpressionContext, object())
        )
    with pytest.raises(GameLifecycleError, match="must return DiceExpression or None"):
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:dice-bad-return",
                    source_id="phase17g:dice-bad-return:source",
                    dice_expression_handler=lambda _context: cast(DiceExpression, object()),
                ),
            )
        ).dice_expression_for(context)
    with pytest.raises(GameLifecycleError, match="must be 2D6 or 3D6"):
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:dice-invalid-expression",
                    source_id="phase17g:dice-invalid-expression:source",
                    dice_expression_handler=lambda _context: DiceExpression(
                        quantity=1,
                        sides=6,
                    ),
                ),
            )
        ).dice_expression_for(context)
    with pytest.raises(GameLifecycleError, match="conflicting overrides"):
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:dice-override-a",
                    source_id="phase17g:dice-override-a:source",
                    dice_expression_handler=lambda _context: synapse_expression,
                ),
                BattleShockHookBinding(
                    hook_id="phase17g:dice-override-b",
                    source_id="phase17g:dice-override-b:source",
                    dice_expression_handler=lambda _context: default_expression,
                ),
            )
        ).dice_expression_for(context)


@pytest.mark.stubbed
def test_battle_shock_hook_registry_modifier_and_outcome_contracts() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-battle-shock-hook-contracts",
        active_player_id="player-a",
    )
    state = _require_state(lifecycle)
    modifier_context = _battle_shock_modifier_context(state)
    modifier = RollModifier(
        modifier_id="phase17g:modifier",
        operand=-1,
        source_id="phase17g:modifier:source",
    )

    grouped_applications = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase17g:grouped-modifier-hook",
                source_id="phase17g:grouped-modifier-producer",
                modifier_handler=lambda _context: (
                    RollModifier(
                        modifier_id="phase17g:grouped-modifier:a",
                        operand=-1,
                        source_id="phase17g:grouped-source:a",
                    ),
                    RollModifier(
                        modifier_id="phase17g:grouped-modifier:b",
                        operand=1,
                        source_id="phase17g:grouped-source:b",
                    ),
                ),
            ),
        )
    ).modifier_applications_for(modifier_context)
    assert tuple(
        (application.hook_id, application.source_id) for application in grouped_applications
    ) == (
        ("phase17g:grouped-modifier-hook", "phase17g:grouped-source:a"),
        ("phase17g:grouped-modifier-hook", "phase17g:grouped-source:b"),
    )

    authority_modifier_id = (
        f"{army_rule.BATTLE_SHOCK_HOOK_ID}:shadow-penalty:"
        f"{modifier_context.request.request_id}:player-a"
    )
    with pytest.raises(GameLifecycleError, match="modifier predicate drifted"):
        army_rule.validate_shadow_in_the_warp_battle_shock_modifier_application(
            BattleShockModifierApplicationAuthorityContext(
                state=modifier_context.state,
                request=modifier_context.request,
                application=BattleShockModifierApplication(
                    hook_id=army_rule.BATTLE_SHOCK_HOOK_ID,
                    source_id=army_rule.SOURCE_RULE_ID,
                    modifiers=(
                        RollModifier(
                            modifier_id=authority_modifier_id,
                            operand=-1,
                            source_id=army_rule.SOURCE_RULE_ID,
                        ),
                    ),
                ),
                active_player_id=modifier_context.active_player_id,
                phase=modifier_context.phase,
                phase_start_battle_shocked_unit_ids=(
                    modifier_context.phase_start_battle_shocked_unit_ids
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="modifier operand drifted"):
        army_rule.validate_shadow_in_the_warp_battle_shock_modifier_application(
            BattleShockModifierApplicationAuthorityContext(
                state=modifier_context.state,
                request=modifier_context.request,
                application=BattleShockModifierApplication(
                    hook_id=army_rule.BATTLE_SHOCK_HOOK_ID,
                    source_id=army_rule.SOURCE_RULE_ID,
                    modifiers=(
                        RollModifier(
                            modifier_id=authority_modifier_id,
                            operand=1,
                            source_id=army_rule.SOURCE_RULE_ID,
                        ),
                    ),
                ),
                active_player_id=modifier_context.active_player_id,
                phase=modifier_context.phase,
                phase_start_battle_shocked_unit_ids=(
                    modifier_context.phase_start_battle_shocked_unit_ids
                ),
            )
        )

    assert BattleShockHookRegistry.empty().modifiers_for(modifier_context) == ()
    assert (
        BattleShockHookRegistry.empty().forced_below_starting_strength_unit_ids(
            _battle_shock_forced_test_context(state)
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="modifier hooks require a context"):
        BattleShockHookRegistry.empty().modifiers_for(cast(BattleShockModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="forced-test hooks require a context"):
        BattleShockHookRegistry.empty().forced_below_starting_strength_unit_ids(
            cast(BattleShockForcedTestContext, object())
        )
    with pytest.raises(GameLifecycleError, match="must return a tuple"):
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:modifier-list",
                    source_id="phase17g:modifier-list:source",
                    modifier_handler=lambda _context: cast(
                        tuple[RollModifier, ...],
                        [modifier],
                    ),
                ),
            )
        ).modifiers_for(modifier_context)
    with pytest.raises(GameLifecycleError, match="must return RollModifier values"):
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:modifier-object",
                    source_id="phase17g:modifier-object:source",
                    modifier_handler=lambda _context: (cast(RollModifier, object()),),
                ),
            )
        ).modifiers_for(modifier_context)
    with pytest.raises(GameLifecycleError, match="must be unique"):
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:modifier-duplicate-a",
                    source_id="phase17g:modifier-duplicate-a:source",
                    modifier_handler=lambda _context: (modifier,),
                ),
                BattleShockHookBinding(
                    hook_id="phase17g:modifier-duplicate-b",
                    source_id="phase17g:modifier-duplicate-b:source",
                    modifier_handler=lambda _context: (modifier,),
                ),
            )
        ).modifiers_for(modifier_context)

    outcome_calls: list[str] = []
    outcome_context = _battle_shock_outcome_context(state)
    BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase17g:outcome",
                source_id="phase17g:outcome:source",
                outcome_handler=lambda context: outcome_calls.append(context.result.result_id),
            ),
        )
    ).resolve_outcomes(outcome_context)
    assert outcome_calls == [outcome_context.result.result_id]
    with pytest.raises(GameLifecycleError, match="outcome hooks require a context"):
        BattleShockHookRegistry.empty().resolve_outcomes(cast(BattleShockOutcomeContext, object()))
    with pytest.raises(GameLifecycleError, match="auto_passed must be a bool"):
        BattleShockOutcomeContext(
            state=outcome_context.state,
            decisions=outcome_context.decisions,
            dice_manager=outcome_context.dice_manager,
            result=outcome_context.result,
            active_player_id=outcome_context.active_player_id,
            phase=outcome_context.phase,
            auto_passed=cast(bool, "yes"),
            phase_start_battle_shocked_unit_ids=outcome_context.phase_start_battle_shocked_unit_ids,
        )


def test_battle_shock_hook_contexts_and_bindings_are_fail_fast() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-battle-shock-context-contracts",
        active_player_id="player-a",
    )
    state = _require_state(lifecycle)
    modifier_context = _battle_shock_modifier_context(state)
    outcome_context = _battle_shock_outcome_context(state)

    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        BattleShockForcedTestContext(
            state=cast(GameState, object()),
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        BattleShockModifierContext(
            state=cast(GameState, object()),
            request=modifier_context.request,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        BattleShockDiceExpressionContext(
            state=cast(GameState, object()),
            player_id="player-a",
            unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            default_expression=DiceExpression(quantity=2, sides=6),
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        BattleShockOutcomeContext(
            state=cast(GameState, object()),
            decisions=DecisionController(),
            dice_manager=outcome_context.dice_manager,
            result=outcome_context.result,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="active_player_id must be a string"):
        BattleShockForcedTestContext(
            state=state,
            active_player_id=cast(str, object()),
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="active_player_id must not be empty"):
        BattleShockForcedTestContext(
            state=state,
            active_player_id=" ",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="request must be a BattleShockTestRequest"):
        BattleShockModifierContext(
            state=state,
            request=cast(BattleShockTestRequest, object()),
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="default_expression must be a DiceExpression"):
        BattleShockDiceExpressionContext(
            state=state,
            player_id="player-a",
            unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
            reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            default_expression=cast(DiceExpression, object()),
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="decisions must be a DecisionController"):
        BattleShockOutcomeContext(
            state=state,
            decisions=cast(DecisionController, object()),
            dice_manager=outcome_context.dice_manager,
            result=outcome_context.result,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="dice_manager must be a DiceRollManager"):
        BattleShockOutcomeContext(
            state=state,
            decisions=DecisionController(),
            dice_manager=cast(DiceRollManager, object()),
            result=outcome_context.result,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="result must be a BattleShockResult"):
        BattleShockOutcomeContext(
            state=state,
            decisions=DecisionController(),
            dice_manager=outcome_context.dice_manager,
            result=cast(BattleShockResult, object()),
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported Battle-shock hook phase"):
        BattleShockModifierContext(
            state=state,
            request=modifier_context.request,
            active_player_id="player-a",
            phase=cast(BattlePhase, "not-a-phase"),
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="phase must be a BattlePhase"):
        BattleShockModifierContext(
            state=state,
            request=modifier_context.request,
            active_player_id="player-a",
            phase=cast(BattlePhase, object()),
            phase_start_battle_shocked_unit_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        BattleShockForcedTestContext(
            state=state,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=cast(tuple[str, ...], ["unit-a"]),
        )
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        BattleShockForcedTestContext(
            state=state,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=("unit-a", "unit-a"),
        )
    with pytest.raises(GameLifecycleError, match="forced_test_handler must be callable"):
        BattleShockHookBinding(
            hook_id="phase17g:forced-not-callable",
            source_id="phase17g:forced-not-callable:source",
            forced_test_handler=cast(
                Callable[[BattleShockForcedTestContext], tuple[str, ...]],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="modifier_handler must be callable"):
        BattleShockHookBinding(
            hook_id="phase17g:modifier-not-callable",
            source_id="phase17g:modifier-not-callable:source",
            modifier_handler=cast(
                Callable[[BattleShockModifierContext], tuple[RollModifier, ...]],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="outcome_handler must be callable"):
        BattleShockHookBinding(
            hook_id="phase17g:outcome-not-callable",
            source_id="phase17g:outcome-not-callable:source",
            outcome_handler=cast(Callable[[BattleShockOutcomeContext], None], object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        BattleShockHookRegistry(cast(tuple[BattleShockHookBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="must contain BattleShockHookBinding"):
        BattleShockHookRegistry(cast(tuple[BattleShockHookBinding, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    hook_id="phase17g:duplicate-hook",
                    source_id="phase17g:duplicate-hook-a:source",
                    forced_test_handler=lambda _context: (),
                ),
                BattleShockHookBinding(
                    hook_id="phase17g:duplicate-hook",
                    source_id="phase17g:duplicate-hook-b:source",
                    forced_test_handler=lambda _context: (),
                ),
            )
        )


def test_shadow_and_synapse_handlers_are_fail_fast_on_edge_paths() -> None:
    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.shadow_in_the_warp_request(cast(CommandPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_shadow_in_the_warp_result(cast(CommandPhaseStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="dice expression requires context"):
        army_rule.synapse_battle_shock_dice_expression(
            cast(BattleShockDiceExpressionContext, object())
        )
    with pytest.raises(GameLifecycleError, match="modifiers require context"):
        army_rule.shadow_in_the_warp_battle_shock_modifiers(
            cast(BattleShockModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="modifier requires context"):
        army_rule.synapse_weapon_profile_modifier(cast(WeaponProfileModifierContext, object()))

    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-edge-paths",
        active_player_id="player-b",
    )
    state = _require_state(lifecycle)
    with pytest.raises(GameLifecycleError, match="player drift"):
        army_rule.synapse_battle_shock_dice_expression(
            _battle_shock_dice_context(
                state,
                player_id="player-b",
                unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
            )
        )
    assert (
        army_rule.synapse_battle_shock_dice_expression(
            _battle_shock_dice_context(
                state,
                player_id="player-b",
                unit_instance_id=ENEMY_UNIT_ID,
            )
        )
        is None
    )

    enemy_army = state.army_definition_for_player("player-b")
    tyranids_army = state.army_definition_for_player("player-a")
    assert enemy_army is not None
    assert tyranids_army is not None
    assert not army_rule.tyranids_unit_within_synapse_range(
        state,
        tyranids_army=enemy_army,
        unit_instance_id=ENEMY_UNIT_ID,
    )
    with pytest.raises(GameLifecycleError, match="unit_instance_id is unknown"):
        army_rule.tyranids_unit_within_synapse_range(
            state,
            tyranids_army=tyranids_army,
            unit_instance_id="phase17g:missing-placement",
        )
    with pytest.raises(GameLifecycleError, match="requires an ArmyDefinition"):
        army_rule.tyranids_unit_within_synapse_range(
            state,
            tyranids_army=cast(ArmyDefinition, object()),
            unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
        )

    no_sources = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-no-shadow-sources",
        active_player_id="player-b",
    )
    no_source_state = _require_state(no_sources)
    remove_first_models(no_source_state, unit_instance_id=TYRANIDS_WARRIORS_UNIT_ID, count=5)
    remove_first_models(no_source_state, unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID, count=5)
    no_source_army = no_source_state.army_definition_for_player("player-a")
    assert no_source_army is not None
    assert not army_rule.tyranids_unit_within_synapse_range(
        no_source_state,
        tyranids_army=no_source_army,
        unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
    )
    assert (
        army_rule.shadow_in_the_warp_request(
            CommandPhaseStartRequestContext(
                state=no_source_state,
                decisions=no_sources.decision_controller,
                active_player_id="player-b",
            )
        )
        is None
    )

    missing_battlefield = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-missing-battlefield",
        active_player_id="player-b",
    )
    missing_battlefield_state = _require_state(missing_battlefield)
    missing_battlefield_army = missing_battlefield_state.army_definition_for_player("player-a")
    assert missing_battlefield_army is not None
    missing_battlefield_state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield state"):
        army_rule.tyranids_unit_within_synapse_range(
            missing_battlefield_state,
            tyranids_army=missing_battlefield_army,
            unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
        )

    no_targets = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-no-shadow-targets",
        active_player_id="player-b",
    )
    no_target_state = _require_state(no_targets)
    remove_first_models(no_target_state, unit_instance_id=ENEMY_UNIT_ID, count=5)
    assert (
        army_rule.shadow_in_the_warp_request(
            CommandPhaseStartRequestContext(
                state=no_target_state,
                decisions=no_targets.decision_controller,
                active_player_id="player-b",
            )
        )
        is None
    )


def test_shadow_result_handler_rejects_non_matching_and_drifted_results() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-result-edge-paths",
        active_player_id="player-b",
    )
    request = _initial_shadow_request(lifecycle)
    state = _require_state(lifecycle)
    result = DecisionResult.for_request(
        result_id="phase17g-tyranids-result-edge",
        request=request,
        selected_option_id=army_rule.SHADOW_DECLINE_OPTION_ID,
    )
    context = CommandPhaseStartResultContext(
        state=state,
        decisions=lifecycle.decision_controller,
        request=request,
        result=result,
        active_player_id="player-b",
    )

    assert not army_rule.apply_shadow_in_the_warp_result(
        replace(
            context,
            request=replace(request, decision_type="phase17g:other-command-start"),
        )
    )

    request_payload = dict(cast(dict[str, JsonValue], request.payload))
    assert not army_rule.apply_shadow_in_the_warp_result(
        replace(
            context,
            request=replace(
                request,
                payload=validate_json_value(
                    {
                        **request_payload,
                        "hook_id": "phase17g:other-hook",
                    }
                ),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        army_rule.apply_shadow_in_the_warp_result(
            replace(context, result=replace(result, actor_id=None))
        )
    with pytest.raises(GameLifecycleError, match="actor does not own Tyranids"):
        army_rule.apply_shadow_in_the_warp_result(
            replace(context, result=replace(result, actor_id="player-b"))
        )
    with pytest.raises(GameLifecycleError, match="selected option is not available"):
        army_rule.apply_shadow_in_the_warp_result(
            replace(
                context,
                result=replace(result, selected_option_id="phase17g:missing-option"),
            )
        )
    with pytest.raises(GameLifecycleError, match="selected option payload drift"):
        army_rule.apply_shadow_in_the_warp_result(
            replace(
                context,
                result=replace(
                    result,
                    payload=validate_json_value(
                        {
                            "selected_shadow_option": "decline",
                        }
                    ),
                ),
            )
        )


def test_shadow_result_handler_rejects_request_payload_drift() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-request-drift-paths",
        active_player_id="player-b",
    )
    request = _initial_shadow_request(lifecycle)
    state = _require_state(lifecycle)
    result = DecisionResult.for_request(
        result_id="phase17g-tyranids-request-drift",
        request=request,
        selected_option_id=army_rule.SHADOW_DECLINE_OPTION_ID,
    )
    context = CommandPhaseStartResultContext(
        state=state,
        decisions=lifecycle.decision_controller,
        request=request,
        result=result,
        active_player_id="player-b",
    )
    request_payload = dict(cast(dict[str, JsonValue], request.payload))

    drift_cases: tuple[tuple[str, dict[str, JsonValue], str], ...] = (
        ("game_id", {"game_id": "phase17g-other-game"}, "game_id drift"),
        ("battle_round", {"battle_round": 99}, "battle_round drift"),
        ("phase", {"phase": BattlePhase.MOVEMENT.value}, "phase drift"),
        ("active_player_id", {"active_player_id": "player-a"}, "active player drift"),
        ("player_id", {"player_id": "player-b"}, "player drift"),
        (
            "source_unit_instance_ids",
            {"source_unit_instance_ids": [TYRANIDS_WARRIORS_UNIT_ID]},
            "source unit drift",
        ),
        (
            "target_enemy_unit_instance_ids",
            {"target_enemy_unit_instance_ids": []},
            "target unit drift",
        ),
    )
    for _field_name, updates, message in drift_cases:
        with pytest.raises(GameLifecycleError, match=message):
            army_rule.apply_shadow_in_the_warp_result(
                replace(
                    context,
                    request=replace(
                        request,
                        payload=validate_json_value({**request_payload, **updates}),
                    ),
                )
            )


def test_tyranids_army_rule_validation_helpers_are_fail_fast() -> None:
    lifecycle = _battle_ready_lifecycle(
        game_id="phase17g-tyranids-helper-validation",
        active_player_id="player-b",
    )
    state = _require_state(lifecycle)
    payload_object = army_rule._payload_object  # pyright: ignore[reportPrivateUsage]
    payload_string_list = army_rule._payload_string_list  # pyright: ignore[reportPrivateUsage]
    shadow_request_prefix = army_rule._shadow_request_prefix  # pyright: ignore[reportPrivateUsage]
    eligible_shadow_source_unit_ids = (
        army_rule._eligible_shadow_source_unit_ids  # pyright: ignore[reportPrivateUsage]
    )
    unit_and_army_by_id = army_rule._unit_and_army_by_id  # pyright: ignore[reportPrivateUsage]
    tyranids_army_for_player = (
        army_rule._tyranids_army_for_player  # pyright: ignore[reportPrivateUsage]
    )
    unit_has_shadow_in_the_warp = (
        army_rule._unit_has_shadow_in_the_warp  # pyright: ignore[reportPrivateUsage]
    )
    unit_has_synapse = army_rule._unit_has_synapse  # pyright: ignore[reportPrivateUsage]
    strength_with_plus_one = army_rule._strength_with_plus_one  # pyright: ignore[reportPrivateUsage]
    source_ids_with_synapse = (
        army_rule._source_ids_with_synapse  # pyright: ignore[reportPrivateUsage]
    )
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        army_rule.shadow_in_the_warp_unleashed_for_player(
            cast(GameState, object()),
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="player_id must be a string"):
        army_rule.shadow_in_the_warp_unleashed_for_player(state, player_id=cast(str, object()))
    with pytest.raises(GameLifecycleError, match="player_id must not be empty"):
        army_rule.shadow_in_the_warp_unleashed_for_player(state, player_id=" ")
    with pytest.raises(GameLifecycleError, match="battle_round must be an integer"):
        shadow_request_prefix(battle_round=cast(int, "1"), tyranids_player_id="player-a")
    with pytest.raises(GameLifecycleError, match="battle_round must be positive"):
        shadow_request_prefix(battle_round=0, tyranids_player_id="player-a")
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        payload_object("not-an-object")
    with pytest.raises(GameLifecycleError, match="payload ids must be a list"):
        payload_string_list({}, key="ids")
    with pytest.raises(GameLifecycleError, match="requires an ArmyDefinition"):
        eligible_shadow_source_unit_ids(state=state, army=cast(ArmyDefinition, object()))
    with pytest.raises(GameLifecycleError, match="unit_instance_id was not found"):
        unit_and_army_by_id(state, unit_instance_id="phase17g:missing-unit")
    assert tyranids_army_for_player(state, player_id="player-b") is None
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        unit_has_shadow_in_the_warp(cast(UnitInstance, object()))
    with pytest.raises(GameLifecycleError, match="Synapse requires a UnitInstance"):
        unit_has_synapse(cast(UnitInstance, object()))
    assert unit_has_shadow_in_the_warp(unit_by_id(state, TYRANIDS_GAUNTS_UNIT_ID))
    assert unit_has_synapse(unit_by_id(state, TYRANIDS_WARRIORS_UNIT_ID))
    with pytest.raises(GameLifecycleError, match="requires CharacteristicValue"):
        strength_with_plus_one(cast(CharacteristicValue, object()))
    with pytest.raises(GameLifecycleError, match="characteristic drift"):
        strength_with_plus_one(CharacteristicValue.from_raw(Characteristic.TOUGHNESS, 4))
    with pytest.raises(GameLifecycleError, match="non-numeric Strength"):
        strength_with_plus_one(CharacteristicValue.source_dash(Characteristic.STRENGTH))
    with pytest.raises(GameLifecycleError, match="source IDs must be a tuple"):
        source_ids_with_synapse(cast(tuple[str, ...], ["phase17g:source"]))
    assert source_ids_with_synapse((army_rule.SOURCE_RULE_ID,)) == (army_rule.SOURCE_RULE_ID,)


def test_tyranids_army_rule_uses_phase17f_execution_source_id() -> None:
    record = _tyranids_army_rule_execution_record()
    contribution = army_rule.runtime_contribution()

    assert record.coverage_descriptor_id == "phase17e:tyranids:army-rule"
    assert record.execution_id == army_rule.SOURCE_RULE_ID
    assert record.rule_name == "Shadow in the Warp / Synapse"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(
        sorted(
            (
                army_rule.CONTRIBUTION_ID,
                army_rule.BATTLE_SHOCK_HOOK_ID,
                army_rule.WEAPON_PROFILE_MODIFIER_ID,
            )
        )
    )
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == army_rule.CONTRIBUTION_ID
    assert record.block_reason is None
    assert contribution.command_phase_start_hook_bindings[0].source_id == record.execution_id
    assert contribution.battle_shock_hook_bindings[0].source_id == record.execution_id
    assert contribution.weapon_profile_modifier_bindings[0].source_id == record.execution_id


def _initial_shadow_request(lifecycle: GameLifecycle) -> DecisionRequest:
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    return request


def _active_command_start_request(context: CommandPhaseStartRequestContext) -> DecisionRequest:
    return DecisionRequest(
        request_id=f"phase17g:active-command-start:{context.active_player_id}",
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=context.active_player_id,
        payload=validate_json_value(
            {
                "active_player_id": context.active_player_id,
                "effect_kind": "phase17g_active_command_start_test",
            }
        ),
        options=(
            DecisionOption(
                option_id="phase17g:active-command-start:resolve",
                label="Resolve",
                payload=validate_json_value(
                    {
                        "active_player_id": context.active_player_id,
                        "effect_kind": "phase17g_active_command_start_test",
                    }
                ),
            ),
        ),
    )


def _battle_ready_lifecycle(
    *,
    game_id: str,
    active_player_id: str,
    enemy_unit_count: int = 1,
    enemy_battle_shock_reroll: bool = False,
    enemy_chaos_daemons: bool = False,
    authenticate_reposition: bool = False,
) -> GameLifecycle:
    other_player_id = "player-b" if active_player_id == "player-a" else "player-a"
    config = replace(
        _tyranids_config(
            game_id=game_id,
            enemy_unit_count=enemy_unit_count,
            enemy_battle_shock_reroll=enemy_battle_shock_reroll,
            enemy_chaos_daemons=enemy_chaos_daemons,
        ),
        turn_order=(active_player_id, other_player_id),
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    if authenticate_reposition:
        _place_units_near_center(state)
    _complete_setup_through_gate(
        state=state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    if not authenticate_reposition:
        _place_units_near_center(state)
    assert state.active_player_id == active_player_id
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _tyranids_config(
    *,
    game_id: str,
    enemy_unit_count: int = 1,
    enemy_battle_shock_reroll: bool = False,
    enemy_chaos_daemons: bool = False,
) -> GameConfig:
    if type(enemy_unit_count) is not int or enemy_unit_count < 1:
        raise AssertionError("enemy_unit_count must be positive")
    catalog = _tyranids_lifecycle_catalog(
        enemy_battle_shock_reroll=enemy_battle_shock_reroll,
        enemy_chaos_daemons=enemy_chaos_daemons,
    )
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-tyranids-test",
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
                    faction_id=army_rule.TYRANIDS_FACTION_ID,
                    detachment_ids=(TYRANIDS_DETACHMENT_ID,),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=(
                    _unit_selection("warriors", TYRANIDS_WARRIORS_DATASHEET_ID),
                    _unit_selection("gaunts", TYRANIDS_GAUNTS_DATASHEET_ID),
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=(
                        chaos_daemons_army_rule.CHAOS_DAEMONS_FACTION_ID
                        if enemy_chaos_daemons
                        else "core-marine-force"
                    ),
                    detachment_ids=(
                        "phase17g-tyranids-test-daemonic-incursion"
                        if enemy_chaos_daemons
                        else "core-combined-arms",
                    ),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=tuple(
                    _unit_selection(
                        "enemy-unit" if index == 0 else f"enemy-unit-{index + 1}",
                        "core-intercessor-like-infantry",
                    )
                    for index in range(enemy_unit_count)
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _tyranids_lifecycle_catalog(
    *,
    enemy_battle_shock_reroll: bool = False,
    enemy_chaos_daemons: bool = False,
) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    enemy_datasheet = (
        replace(
            base_datasheet,
            abilities=(*base_datasheet.abilities, _battle_shock_reroll_ability()),
            keywords=DatasheetKeywordSet(
                keywords=(
                    *base_datasheet.keywords.keywords,
                    "DAEMON",
                    "FORTIFICATION",
                    "KHORNE",
                ),
                faction_keywords=base_datasheet.keywords.faction_keywords,
            ),
        )
        if enemy_battle_shock_reroll
        else base_datasheet
    )
    if enemy_chaos_daemons:
        enemy_datasheet = replace(
            enemy_datasheet,
            keywords=DatasheetKeywordSet(
                keywords=("BATTLELINE", "DAEMON", "INFANTRY", "KHORNE"),
                faction_keywords=("LEGIONES DAEMONICA",),
            ),
        )
    return replace(
        base_catalog,
        datasheets=(
            *(
                enemy_datasheet if datasheet is base_datasheet else datasheet
                for datasheet in base_catalog.datasheets
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=TYRANIDS_WARRIORS_DATASHEET_ID,
                name="Tyranid Warriors",
                keywords=("INFANTRY", "SYNAPSE"),
                faction_keywords=("TYRANIDS",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=TYRANIDS_GAUNTS_DATASHEET_ID,
                name="Termagants",
                keywords=("INFANTRY",),
                faction_keywords=("TYRANIDS",),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.TYRANIDS_FACTION_ID,
                name="Tyranids",
                faction_keywords=("TYRANIDS",),
                source_ids=("phase17g:tyranids:faction",),
            ),
            *(
                (
                    FactionDefinition(
                        faction_id=chaos_daemons_army_rule.CHAOS_DAEMONS_FACTION_ID,
                        name="Chaos Daemons",
                        faction_keywords=("LEGIONES DAEMONICA",),
                        source_ids=(chaos_daemons_army_rule.JULY_SOURCE_RULE_ID,),
                    ),
                )
                if enemy_chaos_daemons
                else ()
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=TYRANIDS_DETACHMENT_ID,
                name="Synaptic Test Swarm",
                faction_id=army_rule.TYRANIDS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    TYRANIDS_WARRIORS_DATASHEET_ID,
                    TYRANIDS_GAUNTS_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=("phase17g:tyranids:detachment:synaptic-test",),
            ),
            *(
                (
                    DetachmentDefinition(
                        detachment_id="phase17g-tyranids-test-daemonic-incursion",
                        name="Daemonic Incursion",
                        faction_id=chaos_daemons_army_rule.CHAOS_DAEMONS_FACTION_ID,
                        detachment_point_cost=1,
                        unit_datasheet_ids=(enemy_datasheet.datasheet_id,),
                        force_disposition_ids=("phase17g-force", "purge-the-foe"),
                        source_ids=(chaos_daemons_army_rule.JULY_SOURCE_RULE_ID,),
                    ),
                )
                if enemy_chaos_daemons
                else ()
            ),
        ),
    )


def _battle_shock_reroll_ability() -> DatasheetAbilityDescriptor:
    text = (
        'While a friendly KHORNE DAEMON unit is within 9" of this FORTIFICATION, each time '
        "you take a Battle-shock test for that unit, you can re-roll that test."
    )
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17g:tyranids:test:enemy-battle-shock-reroll",
            raw_text=text,
        ),
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    return DatasheetAbilityDescriptor(
        ability_id="phase17g-enemy-battle-shock-reroll",
        name="Battle-shock Reroll Authority",
        source_id=rule_ir.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(dict[str, JsonValue], rule_ir.to_payload()),
    )


def _datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=faction_keywords,
        ),
        source_ids=(f"phase17g:tyranids:datasheet:{datasheet_id}",),
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


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _complete_setup_through_gate(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=decisions,
        config=config,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _place_units_near_center(state: GameState) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    warriors = state.battlefield_state.unit_placement_by_id(TYRANIDS_WARRIORS_UNIT_ID)
    gaunts = state.battlefield_state.unit_placement_by_id(TYRANIDS_GAUNTS_UNIT_ID)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            warriors,
            marker,
            offsets=((0.0, 0.0), (0.4, 0.0), (0.8, 0.0), (1.2, 0.0), (1.6, 0.0)),
        )
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(
            gaunts,
            marker,
            offsets=((1.0, 0.6), (1.4, 0.6), (1.8, 0.6), (2.2, 0.6), (2.6, 0.6)),
        )
    )
    enemy_army = state.army_definition_for_player("player-b")
    if enemy_army is None:
        raise AssertionError("test state requires enemy army")
    for enemy_index, enemy_unit in enumerate(enemy_army.units):
        enemy = state.battlefield_state.unit_placement_by_id(enemy_unit.unit_instance_id)
        x_offset = float(enemy_index) * 0.2
        battlefield_state = battlefield_state.with_unit_placement(
            with_model_offsets(
                enemy,
                marker,
                offsets=tuple(
                    (2.0 + x_offset + model_index * 0.4, -0.5 - enemy_index * 12.0)
                    for model_index in range(len(enemy.model_placements))
                ),
            )
        )
    state.battlefield_state = battlefield_state


def _place_unit_in_owner_deployment_zone(
    state: GameState,
    *,
    unit_instance_id: str,
) -> None:
    if state.mission_setup is None or state.battlefield_state is None:
        raise AssertionError("test state requires battle setup")
    owner = next(
        army.player_id
        for army in state.army_definitions
        if any(unit.unit_instance_id == unit_instance_id for unit in army.units)
    )
    zone = next(zone for zone in state.mission_setup.deployment_zones if zone.player_id == owner)
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    center_x = (zone.min_x + zone.max_x) / 2.0
    center_y = (zone.min_y + zone.max_y) / 2.0
    model_placements = tuple(
        model_placement.with_pose(
            Pose.at(
                x=center_x + (index - len(placement.model_placements) / 2.0) * 0.5,
                y=center_y,
                facing_degrees=model_placement.pose.facing.degrees,
            )
        )
        for index, model_placement in enumerate(placement.model_placements)
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        placement.with_model_placements(model_placements)
    )


def _battle_shock_dice_context(
    state: GameState,
    *,
    player_id: str = "player-a",
    unit_instance_id: str = TYRANIDS_GAUNTS_UNIT_ID,
) -> BattleShockDiceExpressionContext:
    active_player_id = _active_player_id(state)
    return BattleShockDiceExpressionContext(
        state=state,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        active_player_id=active_player_id,
        phase=BattlePhase.COMMAND,
        default_expression=DiceExpression(quantity=2, sides=6),
        phase_start_battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )


def _battle_shock_modifier_context(state: GameState) -> BattleShockModifierContext:
    active_player_id = _active_player_id(state)
    request = battle_shock_request_for_unit(
        state,
        unit_by_id(state, TYRANIDS_GAUNTS_UNIT_ID),
    )
    return BattleShockModifierContext(
        state=state,
        request=request,
        active_player_id=active_player_id,
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )


def _battle_shock_forced_test_context(state: GameState) -> BattleShockForcedTestContext:
    active_player_id = _active_player_id(state)
    return BattleShockForcedTestContext(
        state=state,
        active_player_id=active_player_id,
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )


def _battle_shock_outcome_context(state: GameState) -> BattleShockOutcomeContext:
    active_player_id = _active_player_id(state)
    request = _battle_shock_modifier_context(state).request
    dice_manager = DiceRollManager("phase17g-tyranids-outcome-context")
    roll_state = dice_manager.roll_fixed(
        request.spec,
        [6] * request.spec.expression.quantity,
    )
    return BattleShockOutcomeContext(
        state=state,
        decisions=DecisionController(),
        dice_manager=dice_manager,
        result=BattleShockResult.from_roll_state(
            result_id="phase17g-tyranids-outcome-context:result",
            request=request,
            roll_state=roll_state,
        ),
        active_player_id=active_player_id,
        phase=BattlePhase.COMMAND,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )


def _battle_shock_hooks() -> BattleShockHookRegistry:
    return BattleShockHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_shock_hook_bindings
    )


def _runtime_modifier_registry() -> RuntimeModifierRegistry:
    return RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=(
            army_rule.runtime_contribution().weapon_profile_modifier_bindings
        )
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
        attacking_unit_instance_id=TYRANIDS_GAUNTS_UNIT_ID,
        attacker_model_instance_id=f"{TYRANIDS_GAUNTS_UNIT_ID}:core-intercessor-like:001",
        target_unit_instance_id=ENEMY_UNIT_ID,
        weapon_profile=weapon_profile,
    )


def _melee_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-tyranids-claws",
        name="Claws",
        range_profile=RangeProfile.melee(),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:tyranids:test-melee-weapon",),
    )


def _ranged_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-tyranids-fleshborer",
        name="Fleshborer",
        range_profile=RangeProfile.distance(18),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 5),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:tyranids:test-ranged-weapon",),
    )


def _tyranids_army_rule_execution_record() -> Phase17FExecutionRecord:
    return next(
        record
        for record in faction_execution_2026_27.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == army_rule.TYRANIDS_FACTION_ID
    )


def _event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _resolved_shadow_lifecycle(*, game_id: str) -> GameLifecycle:
    lifecycle = _battle_ready_lifecycle(
        game_id=game_id,
        active_player_id="player-b",
    )
    request = lifecycle.advance_until_decision_or_terminal().decision_request
    assert request is not None
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"{game_id}:unleash",
            request=request,
            selected_option_id=army_rule.SHADOW_UNLEASH_OPTION_ID,
        )
    )
    return lifecycle


def _mutable_lifecycle_payload(lifecycle: GameLifecycle) -> dict[str, object]:
    return cast(dict[str, object], json.loads(json.dumps(lifecycle.to_payload())))


def _mutable_lifecycle_events(payload: dict[str, object]) -> list[dict[str, object]]:
    decisions = cast(dict[str, object], payload["decisions"])
    return cast(list[dict[str, object]], decisions["event_log"])


def _mutable_event(
    events: list[dict[str, object]],
    event_type: str,
) -> dict[str, object]:
    matches = tuple(event for event in events if event["event_type"] == event_type)
    assert len(matches) == 1
    return matches[0]


def _forge_shadow_request_leadership_and_expression(request: dict[str, object]) -> None:
    request["leadership_target"] = cast(int, request["leadership_target"]) + 1
    spec = cast(dict[str, object], request["spec"])
    expression = cast(dict[str, object], spec["expression"])
    expression["quantity"] = 3


def _require_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("lifecycle state is required")
    return lifecycle.state


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise AssertionError("test state requires active_player_id")
    return state.active_player_id


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()
