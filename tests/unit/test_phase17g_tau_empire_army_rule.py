from __future__ import annotations

# pyright: reportPrivateUsage=false
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
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.tau_empire import (
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
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartHookBinding,
    ShootingPhaseStartHookRegistry,
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionHookRegistry
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

MARKER_OBSERVER_ID = "army-alpha:pathfinders"
OBSERVER_ID = "army-alpha:strike-team"
GUIDED_UNIT_ID = "army-alpha:breachers"
FORTIFICATION_UNIT_ID = "army-alpha:tidewall-gunrig"
BATTLE_SHOCKED_OBSERVER_ID = "army-alpha:stealth-team"
ENEMY_UNIT_ID = "army-beta:enemy-unit"
ENEMY_OTHER_ID = "army-beta:enemy-unit-2"
MARKER_OBSERVER_DATASHEET_ID = "phase17g-tau-pathfinders"
OBSERVER_DATASHEET_ID = "phase17g-tau-strike-team"
GUIDED_DATASHEET_ID = "phase17g-tau-breachers"
FORTIFICATION_DATASHEET_ID = "phase17g-tau-tidewall"
BATTLE_SHOCKED_DATASHEET_ID = "phase17g-tau-stealth-team"
NON_TAU_FACTION_ID = "phase17g-non-tau-force"
NON_TAU_DETACHMENT_ID = "phase17g-non-tau-detachment"


def test_lifecycle_requests_for_the_greater_good_and_guided_markerlight_modifier() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    state.battle_shocked_unit_ids.append(BATTLE_SHOCKED_OBSERVER_ID)
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()
    assert army_rule.HOOK_ID in summary["shooting_phase_start_hook_ids"]
    assert army_rule.WEAPON_PROFILE_MODIFIER_ID in summary["weapon_profile_modifier_ids"]

    request = _next_for_the_greater_good_request(lifecycle)

    assert request.decision_type == SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert json.loads(json.dumps(request.to_payload())) == request.to_payload()
    mark_option_ids = {
        option.option_id
        for option in request.options
        if option.option_id != army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID
    }
    assert all(FORTIFICATION_UNIT_ID not in option_id for option_id in mark_option_ids)
    assert all(BATTLE_SHOCKED_OBSERVER_ID not in option_id for option_id in mark_option_ids)
    selected = _mark_option(
        request,
        observer_rules_unit_id=MARKER_OBSERVER_ID,
        spotted_unit_id=ENEMY_UNIT_ID,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-markerlight-spots-enemy",
            request=request,
            selected_option_id=selected.option_id,
        )
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    assert army_rule.for_the_greater_good_spotted_unit_ids_for_player(
        state,
        player_id="player-a",
    ) == (ENEMY_UNIT_ID,)
    assert army_rule.for_the_greater_good_observer_unit_ids_for_player(
        state,
        player_id="player-a",
    ) == (MARKER_OBSERVER_ID,)

    retry_request = _request_from_status(status)
    if retry_request is None:
        retry_request = _next_for_the_greater_good_request(lifecycle)
    assert (
        _mark_option_or_none(
            retry_request,
            observer_rules_unit_id=OBSERVER_ID,
            spotted_unit_id=ENEMY_UNIT_ID,
        )
        is None
    )

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-done",
            request=retry_request,
            selected_option_id=army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
        )
    )
    state = _require_state(lifecycle)
    guided_profile = army_rule.for_the_greater_good_weapon_profile_modifier(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=GUIDED_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_ranged_weapon_profile(),
        )
    )
    assert guided_profile.skill.final == 3
    assert WeaponKeyword.IGNORES_COVER in guided_profile.keywords
    assert army_rule.SOURCE_RULE_ID in guided_profile.source_ids

    observer_profile = army_rule.for_the_greater_good_weapon_profile_modifier(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=MARKER_OBSERVER_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_ranged_weapon_profile(),
        )
    )
    assert observer_profile == _ranged_weapon_profile()

    unspotted_profile = army_rule.for_the_greater_good_weapon_profile_modifier(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=GUIDED_UNIT_ID,
            target_unit_instance_id=ENEMY_OTHER_ID,
            weapon_profile=_ranged_weapon_profile(),
        )
    )
    assert unspotted_profile == _ranged_weapon_profile()
    state.battle_shocked_unit_ids = []
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()


def test_done_option_opens_normal_shooting_without_spotted_effect() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = _next_for_the_greater_good_request(lifecycle)

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-done-immediately",
            request=request,
            selected_option_id=army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
        )
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    assert state.shooting_phase_state is not None
    assert (
        army_rule.for_the_greater_good_spotted_unit_ids_for_player(
            state,
            player_id="player-a",
        )
        == ()
    )


def test_non_tau_selected_detachment_with_tau_keyword_units_gets_no_request() -> None:
    lifecycle = _battle_ready_lifecycle(non_tau_selected=True)
    state = _require_state(lifecycle)
    army = state.army_definition_for_player("player-a")
    assert army is not None
    assert army.detachment_selection.faction_id == NON_TAU_FACTION_ID
    assert any("T'AU EMPIRE" in unit.faction_keywords for unit in army.units)

    request = army_rule.for_the_greater_good_request(
        ShootingPhaseStartRequestContext(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_config(lifecycle).ruleset_descriptor,
            army_catalog=_config(lifecycle).army_catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )

    assert request is None


def test_shooting_phase_start_submission_rejects_payload_drift_and_closed_window() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = _next_for_the_greater_good_request(lifecycle)
    option = _mark_option(
        request,
        observer_rules_unit_id=MARKER_OBSERVER_ID,
        spotted_unit_id=ENEMY_UNIT_ID,
    )
    drifted_payload = dict(cast(dict[str, JsonValue], option.payload))
    drifted_payload["spotted_unit_instance_id"] = ENEMY_OTHER_ID

    invalid = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-tau-payload-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=validate_json_value(drifted_payload),
        )
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = cast(dict[str, JsonValue], invalid.payload)
    assert invalid_payload["field"] == "payload"
    assert _require_state(lifecycle).persisting_effects == []

    closed_lifecycle = _battle_ready_lifecycle()
    closed_request = _next_for_the_greater_good_request(closed_lifecycle)
    closed_state = _require_state(closed_lifecycle)
    closed_state.shooting_phase_state = ShootingPhaseState(
        battle_round=closed_state.battle_round,
        active_player_id="player-a",
    )
    closed_option = _mark_option(
        closed_request,
        observer_rules_unit_id=MARKER_OBSERVER_ID,
        spotted_unit_id=ENEMY_UNIT_ID,
    )
    closed = closed_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-window-closed",
            request=closed_request,
            selected_option_id=closed_option.option_id,
        )
    )

    assert closed.status_kind is LifecycleStatusKind.INVALID
    closed_payload = cast(dict[str, JsonValue], closed.payload)
    assert closed_payload["invalid_reason"] == "shooting_phase_start_window_closed"
    assert closed_state.persisting_effects == []


def test_non_markerlight_guided_attack_improves_skill_without_ignores_cover() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = _next_for_the_greater_good_request(lifecycle)
    selected = _mark_option(
        request,
        observer_rules_unit_id=OBSERVER_ID,
        spotted_unit_id=ENEMY_UNIT_ID,
    )
    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-non-markerlight-spots-enemy",
            request=request,
            selected_option_id=selected.option_id,
        )
    )
    retry_request = _request_from_status(status)
    if retry_request is None:
        retry_request = _next_for_the_greater_good_request(lifecycle)
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-non-markerlight-done",
            request=retry_request,
            selected_option_id=army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
        )
    )
    state = _require_state(lifecycle)
    modified = army_rule.for_the_greater_good_weapon_profile_modifier(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=GUIDED_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_ranged_weapon_profile(),
        )
    )
    capped = army_rule.for_the_greater_good_weapon_profile_modifier(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=GUIDED_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=replace(
                _ranged_weapon_profile(),
                skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        )
    )
    off_phase_context = replace(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=GUIDED_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_ranged_weapon_profile(),
        ),
        source_phase=BattlePhase.FIGHT,
    )
    melee_profile = replace(_ranged_weapon_profile(), range_profile=RangeProfile.melee())

    assert modified.skill.final == 3
    assert WeaponKeyword.IGNORES_COVER not in modified.keywords
    assert capped.skill.final == 2
    assert capped.source_ids == (army_rule.SOURCE_RULE_ID,)
    assert (
        army_rule.for_the_greater_good_weapon_profile_modifier(off_phase_context)
        == _ranged_weapon_profile()
    )
    assert (
        army_rule.for_the_greater_good_weapon_profile_modifier(
            _weapon_context(
                state=state,
                attacking_unit_instance_id=GUIDED_UNIT_ID,
                target_unit_instance_id=ENEMY_UNIT_ID,
                weapon_profile=melee_profile,
            )
        )
        == melee_profile
    )


def test_for_the_greater_good_result_application_fails_fast_on_drift() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = _next_for_the_greater_good_request(lifecycle)
    done_payload = cast(dict[str, JsonValue], _done_option(request).payload)
    mark_option = _mark_option(
        request,
        observer_rules_unit_id=MARKER_OBSERVER_ID,
        spotted_unit_id=ENEMY_UNIT_ID,
    )
    mark_payload = dict(cast(dict[str, JsonValue], mark_option.payload))

    result_without_actor = DecisionResult(
        result_id="phase17g-tau-no-actor",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=None,
        selected_option_id=army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
        payload=validate_json_value(done_payload),
    )
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=result_without_actor)
        )

    wrong_actor = DecisionResult(
        result_id="phase17g-tau-wrong-actor",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id="player-b",
        selected_option_id=army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
        payload=validate_json_value(done_payload),
    )
    with pytest.raises(GameLifecycleError, match="does not own"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=wrong_actor)
        )

    done_drift = DecisionResult(
        result_id="phase17g-tau-done-drift",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=mark_option.option_id,
        payload=validate_json_value(done_payload),
    )
    with pytest.raises(GameLifecycleError, match="done option ID drift"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=done_drift)
        )

    unsupported_payload = dict(done_payload)
    unsupported_payload["selected_for_the_greater_good_option"] = "unsupported"
    unsupported = DecisionResult(
        result_id="phase17g-tau-unsupported-selection",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
        payload=validate_json_value(unsupported_payload),
    )
    with pytest.raises(GameLifecycleError, match="selection is unsupported"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=unsupported)
        )

    no_longer_eligible = DecisionResult(
        result_id="phase17g-tau-ineligible-mark",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="tau-empire:for-the-greater-good:observer:missing:spotted:missing",
        payload=validate_json_value(mark_payload),
    )
    with pytest.raises(GameLifecycleError, match="no longer eligible"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=no_longer_eligible)
        )

    observer_drift_payload = dict(mark_payload)
    observer_drift_payload["observer_rules_unit_instance_id"] = OBSERVER_ID
    observer_drift = DecisionResult(
        result_id="phase17g-tau-observer-drift",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=mark_option.option_id,
        payload=validate_json_value(observer_drift_payload),
    )
    with pytest.raises(GameLifecycleError, match="observer payload drift"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=observer_drift)
        )

    spotted_drift_payload = dict(mark_payload)
    spotted_drift_payload["spotted_unit_instance_id"] = ENEMY_OTHER_ID
    spotted_drift = replace(
        observer_drift,
        result_id="phase17g-tau-spotted-drift",
        payload=validate_json_value(spotted_drift_payload),
    )
    with pytest.raises(GameLifecycleError, match="spotted payload drift"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=spotted_drift)
        )

    markerlight_drift_payload = dict(mark_payload)
    markerlight_drift_payload["observer_has_markerlight"] = False
    markerlight_drift = replace(
        observer_drift,
        result_id="phase17g-tau-markerlight-drift",
        payload=validate_json_value(markerlight_drift_payload),
    )
    with pytest.raises(GameLifecycleError, match="Markerlight payload drift"):
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=markerlight_drift)
        )


def test_for_the_greater_good_result_handler_ignores_unrelated_shooting_start_request() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    request = DecisionRequest(
        request_id="phase17g-unrelated-shooting-start",
        decision_type=SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
        actor_id="player-b",
        payload=validate_json_value(
            {
                "hook_id": "warhammer_40000_11th:other_faction:army_rule:unrelated",
            }
        ),
        options=(
            DecisionOption(
                option_id="phase17g-unrelated-shooting-start-option",
                label="Unrelated option",
                payload=validate_json_value({"selected_unrelated_option": "done"}),
            ),
        ),
    )
    result = DecisionResult.for_request(
        result_id="phase17g-unrelated-shooting-start-result",
        request=request,
        selected_option_id="phase17g-unrelated-shooting-start-option",
    )

    assert (
        army_rule.apply_for_the_greater_good_result(
            _result_context(lifecycle, request=request, result=result)
        )
        is False
    )
    assert state.persisting_effects == []


def test_shooting_phase_start_hook_registry_fails_fast_and_orders_bindings() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = _synthetic_shooting_start_request("phase17g-hook-request")
    alternate_request = _synthetic_shooting_start_request("phase17g-hook-request-alt")
    context = _request_context(lifecycle)
    result_context = _result_context(
        lifecycle,
        request=request,
        result=DecisionResult.for_request(
            result_id="phase17g-hook-result",
            request=request,
            selected_option_id="phase17g-hook-option",
        ),
    )

    with pytest.raises(GameLifecycleError, match="requires a handler"):
        ShootingPhaseStartHookBinding(hook_id="phase17g-empty", source_id="phase17g-source")
    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        ShootingPhaseStartHookBinding(
            hook_id="phase17g-invalid-request",
            source_id="phase17g-source",
            request_handler=cast(
                Callable[[ShootingPhaseStartRequestContext], DecisionRequest | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        ShootingPhaseStartHookBinding(
            hook_id="phase17g-invalid-result",
            source_id="phase17g-source",
            result_handler=cast(
                Callable[[ShootingPhaseStartResultContext], bool | LifecycleStatus],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        ShootingPhaseStartHookRegistry(cast(tuple[ShootingPhaseStartHookBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="requires hook bindings"):
        ShootingPhaseStartHookRegistry(cast(tuple[ShootingPhaseStartHookBinding, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        ShootingPhaseStartHookRegistry(
            (
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-duplicate",
                    source_id="phase17g-source",
                    request_handler=_request_handler(request),
                ),
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-duplicate",
                    source_id="phase17g-source",
                    request_handler=_request_handler(request),
                ),
            )
        )

    ordered = ShootingPhaseStartHookRegistry.from_bindings(
        (
            ShootingPhaseStartHookBinding(
                hook_id="phase17g-b",
                source_id="phase17g-source",
                request_handler=_request_handler(None),
            ),
            ShootingPhaseStartHookBinding(
                hook_id="phase17g-a",
                source_id="phase17g-source",
                request_handler=_request_handler(request),
            ),
        )
    )
    assert [binding.hook_id for binding in ordered.all_bindings()] == ["phase17g-a", "phase17g-b"]
    assert ordered.next_request_for(context) == request
    assert ShootingPhaseStartHookRegistry.empty().next_request_for(context) is None

    with pytest.raises(GameLifecycleError, match="request hooks require context"):
        ordered.next_request_for(cast(ShootingPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="DecisionRequest or None"):
        ShootingPhaseStartHookRegistry.from_bindings(
            (
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-invalid-return",
                    source_id="phase17g-source",
                    request_handler=_invalid_request_handler,
                ),
            )
        ).next_request_for(context)
    with pytest.raises(GameLifecycleError, match="multiple simultaneous requests"):
        ShootingPhaseStartHookRegistry.from_bindings(
            (
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-request-a",
                    source_id="phase17g-source",
                    request_handler=_request_handler(request),
                ),
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-request-b",
                    source_id="phase17g-source",
                    request_handler=_request_handler(alternate_request),
                ),
            )
        ).next_request_for(context)

    with pytest.raises(GameLifecycleError, match="result hooks require context"):
        ordered.apply_result(cast(ShootingPhaseStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="bool or status"):
        ShootingPhaseStartHookRegistry.from_bindings(
            (
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-invalid-result-return",
                    source_id="phase17g-source",
                    result_handler=_invalid_result_handler,
                ),
            )
        ).apply_result(result_context)
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        ShootingPhaseStartHookRegistry.from_bindings(
            (
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-result-a",
                    source_id="phase17g-source",
                    result_handler=_true_result_handler,
                ),
                ShootingPhaseStartHookBinding(
                    hook_id="phase17g-result-b",
                    source_id="phase17g-source",
                    result_handler=_true_result_handler,
                ),
            )
        ).apply_result(result_context)
    assert ShootingPhaseStartHookRegistry.empty().apply_result(result_context) is False


def test_for_the_greater_good_public_entrypoints_reject_wrong_context_types() -> None:
    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.for_the_greater_good_request(cast(ShootingPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_for_the_greater_good_result(cast(ShootingPhaseStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="weapon modifier requires context"):
        army_rule.for_the_greater_good_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )


def test_for_the_greater_good_internal_guards_reject_invalid_state_and_payloads() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    observer = rules_unit_view_by_id(state=state, unit_instance_id=MARKER_OBSERVER_ID)
    target = rules_unit_view_by_id(state=state, unit_instance_id=ENEMY_UNIT_ID)

    with pytest.raises(GameLifecycleError, match="requires observer rules unit"):
        army_rule.ForTheGreaterGoodMarkOption(
            observer_rules_unit=cast(RulesUnitView, object()),
            spotted_rules_unit=target,
            observer_has_markerlight=True,
        )
    with pytest.raises(GameLifecycleError, match="requires spotted rules unit"):
        army_rule.ForTheGreaterGoodMarkOption(
            observer_rules_unit=observer,
            spotted_rules_unit=cast(RulesUnitView, object()),
            observer_has_markerlight=True,
        )
    with pytest.raises(GameLifecycleError, match="markerlight flag must be bool"):
        army_rule.ForTheGreaterGoodMarkOption(
            observer_rules_unit=observer,
            spotted_rules_unit=target,
            observer_has_markerlight=cast(bool, "yes"),
        )

    assert army_rule._rules_unit_is_eligible_observer(_request_context(lifecycle), target) is False
    with pytest.raises(GameLifecycleError, match="include_enemies must be bool"):
        army_rule._placed_rules_unit_ids(
            state,
            player_id="player-a",
            include_enemies=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="Battle-shock check requires rules unit"):
        army_rule._rules_unit_is_battle_shocked(state, cast(RulesUnitView, object()))
    with pytest.raises(GameLifecycleError, match="ability check requires rules unit"):
        army_rule._rules_unit_has_for_the_greater_good(cast(RulesUnitView, object()))
    with pytest.raises(GameLifecycleError, match="keyword check requires rules unit"):
        army_rule._rules_unit_has_keyword(cast(RulesUnitView, object()), "Markerlight")
    with pytest.raises(GameLifecycleError, match="keyword list must be a tuple"):
        army_rule._unit_has_keyword(cast(tuple[str, ...], ["Markerlight"]), "Markerlight")
    with pytest.raises(GameLifecycleError, match="ballistic skill requires value"):
        army_rule._improve_ballistic_skill(cast(CharacteristicValue, object()))
    with pytest.raises(GameLifecycleError, match="characteristic drift"):
        army_rule._improve_ballistic_skill(
            CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 4)
        )
    with pytest.raises(GameLifecycleError, match="cannot improve non-numeric"):
        army_rule._improve_ballistic_skill(
            CharacteristicValue.source_dash(Characteristic.BALLISTIC_SKILL)
        )
    with pytest.raises(GameLifecycleError, match="keywords must be a tuple"):
        army_rule._weapon_keywords_with_ignores_cover(cast(tuple[WeaponKeyword, ...], []))
    assert army_rule._weapon_keywords_with_ignores_cover((WeaponKeyword.IGNORES_COVER,)) == (
        WeaponKeyword.IGNORES_COVER,
    )
    with pytest.raises(GameLifecycleError, match="source_ids must be a tuple"):
        army_rule._source_ids_with_for_the_greater_good(cast(tuple[str, ...], ["source"]))
    with pytest.raises(GameLifecycleError, match="label requires rules unit"):
        army_rule._rules_unit_label(cast(RulesUnitView, object()))
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        army_rule._payload_object(cast(JsonValue, "payload"))
    with pytest.raises(GameLifecycleError, match="payload field field must be a string"):
        army_rule._payload_string({"field": 1}, key="field")
    with pytest.raises(GameLifecycleError, match="payload field field must be a bool"):
        army_rule._payload_bool({"field": "true"}, key="field")
    with pytest.raises(GameLifecycleError, match="field must be a string"):
        army_rule._validate_identifier("field", 1)
    with pytest.raises(GameLifecycleError, match="field must not be empty"):
        army_rule._validate_identifier("field", " ")
    with pytest.raises(GameLifecycleError, match="skill must be non-negative int"):
        army_rule._validate_non_negative_int("skill", -1)

    active_player_id = state.active_player_id
    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires active_player_id"):
        army_rule._active_player_id(state)
    state.active_player_id = active_player_id
    battlefield_state = state.battlefield_state
    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        army_rule._terrain_features_for_state(state)
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        army_rule._battlefield_scenario(state)
    state.battlefield_state = battlefield_state

    done_request = _next_for_the_greater_good_request(lifecycle)
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-guard-done",
            request=done_request,
            selected_option_id=army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID,
        )
    )
    done_state = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.FOR_THE_GREATER_GOOD_DONE_STATE_KIND,
    )[0]
    state.record_faction_rule_state(replace(done_state, state_id=f"{done_state.state_id}:copy"))
    with pytest.raises(GameLifecycleError, match="multiple done states"):
        army_rule._for_the_greater_good_done_this_shooting_phase(state, player_id="player-a")

    effect_lifecycle = _battle_ready_lifecycle()
    effect_request = _next_for_the_greater_good_request(effect_lifecycle)
    effect_option = _mark_option(
        effect_request,
        observer_rules_unit_id=MARKER_OBSERVER_ID,
        spotted_unit_id=ENEMY_UNIT_ID,
    )
    effect_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-tau-guard-markerlight",
            request=effect_request,
            selected_option_id=effect_option.option_id,
        )
    )
    effect_state = _require_state(effect_lifecycle)
    effect = effect_state.persisting_effects[0]
    effect_state.record_persisting_effect(replace(effect, effect_id=f"{effect.effect_id}:copy"))
    with pytest.raises(GameLifecycleError, match="multiple Spotted effects"):
        army_rule.for_the_greater_good_weapon_profile_modifier(
            _weapon_context(
                state=effect_state,
                attacking_unit_instance_id=GUIDED_UNIT_ID,
                target_unit_instance_id=ENEMY_UNIT_ID,
                weapon_profile=_ranged_weapon_profile(),
            )
        )


def _battle_ready_lifecycle(*, non_tau_selected: bool = False) -> GameLifecycle:
    config = _tau_config(non_tau_selected=non_tau_selected)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-tau-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _place_unit(state, unit_instance_id=MARKER_OBSERVER_ID, x=10.0, y=10.0)
    _place_unit(state, unit_instance_id=OBSERVER_ID, x=10.0, y=14.0)
    _place_unit(state, unit_instance_id=GUIDED_UNIT_ID, x=10.0, y=18.0)
    _place_unit(state, unit_instance_id=FORTIFICATION_UNIT_ID, x=10.0, y=24.0)
    _place_unit(state, unit_instance_id=BATTLE_SHOCKED_OBSERVER_ID, x=10.0, y=28.0)
    _place_unit(state, unit_instance_id=ENEMY_UNIT_ID, x=20.0, y=10.0)
    _place_unit(state, unit_instance_id=ENEMY_OTHER_ID, x=20.0, y=18.0)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(state=state, config=config)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _tau_config(*, non_tau_selected: bool) -> GameConfig:
    catalog = _tau_lifecycle_catalog()
    player_a_faction_id = (
        NON_TAU_FACTION_ID if non_tau_selected else army_rule.TAU_EMPIRE_FACTION_ID
    )
    player_a_detachment_id = NON_TAU_DETACHMENT_ID if non_tau_selected else "kauyon"
    return GameConfig(
        game_id="phase17g-tau-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-tau-test",
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
                    faction_id=player_a_faction_id,
                    detachment_ids=(player_a_detachment_id,),
                ),
                force_disposition_id="phase17g-force",
                unit_selections=(
                    _unit_selection("pathfinders", MARKER_OBSERVER_DATASHEET_ID),
                    _unit_selection("strike-team", OBSERVER_DATASHEET_ID),
                    _unit_selection("breachers", GUIDED_DATASHEET_ID),
                    _unit_selection("tidewall-gunrig", FORTIFICATION_DATASHEET_ID),
                    _unit_selection("stealth-team", BATTLE_SHOCKED_DATASHEET_ID),
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
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    _unit_selection("enemy-unit", "core-intercessor-like-infantry"),
                    _unit_selection("enemy-unit-2", "core-intercessor-like-infantry"),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _tau_lifecycle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            _datasheet(
                base_datasheet,
                datasheet_id=MARKER_OBSERVER_DATASHEET_ID,
                name="Pathfinder Team",
                keywords=("INFANTRY", "MARKERLIGHT"),
                faction_keywords=("T'AU EMPIRE",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=OBSERVER_DATASHEET_ID,
                name="Strike Team",
                keywords=("INFANTRY",),
                faction_keywords=("T'AU EMPIRE",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=GUIDED_DATASHEET_ID,
                name="Breacher Team",
                keywords=("INFANTRY",),
                faction_keywords=("T'AU EMPIRE",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=FORTIFICATION_DATASHEET_ID,
                name="Tidewall Gunrig",
                keywords=("FORTIFICATION",),
                faction_keywords=("T'AU EMPIRE",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=BATTLE_SHOCKED_DATASHEET_ID,
                name="Stealth Battlesuits",
                keywords=("INFANTRY",),
                faction_keywords=("T'AU EMPIRE",),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.TAU_EMPIRE_FACTION_ID,
                name="T'au Empire",
                faction_keywords=("T'AU EMPIRE",),
                source_ids=("phase17g:tau:faction",),
            ),
            FactionDefinition(
                faction_id=NON_TAU_FACTION_ID,
                name="Non-Tau Auxiliary Force",
                faction_keywords=("T'AU EMPIRE", "NON-TAU"),
                source_ids=("phase17g:tau:non-tau:faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="kauyon",
                name="Kauyon",
                faction_id=army_rule.TAU_EMPIRE_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    MARKER_OBSERVER_DATASHEET_ID,
                    OBSERVER_DATASHEET_ID,
                    GUIDED_DATASHEET_ID,
                    FORTIFICATION_DATASHEET_ID,
                    BATTLE_SHOCKED_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:tau:detachment:kauyon",),
            ),
            DetachmentDefinition(
                detachment_id=NON_TAU_DETACHMENT_ID,
                name="Non-Tau Detachment",
                faction_id=NON_TAU_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    MARKER_OBSERVER_DATASHEET_ID,
                    OBSERVER_DATASHEET_ID,
                    GUIDED_DATASHEET_ID,
                    FORTIFICATION_DATASHEET_ID,
                    BATTLE_SHOCKED_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:tau:non-tau:detachment",),
            ),
        ),
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
        abilities=(_for_the_greater_good_ability(),),
        source_ids=(f"phase17g:tau:datasheet:{datasheet_id}",),
    )


def _for_the_greater_good_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="phase17g-tau-for-the-greater-good",
        name="For the Greater Good",
        source_id=army_rule.SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="tau-army-rule",
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


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _next_for_the_greater_good_request(lifecycle: GameLifecycle) -> DecisionRequest:
    request = _request_from_status(lifecycle.advance_until_decision_or_terminal())
    if request is None:
        raise AssertionError("decision request is required")
    return request


def _request_from_status(status: LifecycleStatus) -> DecisionRequest | None:
    return status.decision_request


def _mark_option(
    request: DecisionRequest,
    *,
    observer_rules_unit_id: str,
    spotted_unit_id: str,
) -> DecisionOption:
    option = _mark_option_or_none(
        request,
        observer_rules_unit_id=observer_rules_unit_id,
        spotted_unit_id=spotted_unit_id,
    )
    if option is None:
        raise AssertionError(f"missing mark option {observer_rules_unit_id}->{spotted_unit_id}")
    return option


def _mark_option_or_none(
    request: DecisionRequest,
    *,
    observer_rules_unit_id: str,
    spotted_unit_id: str,
) -> DecisionOption | None:
    for option in request.options:
        if option.option_id == army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID:
            continue
        payload = cast(dict[str, JsonValue], option.payload)
        if (
            payload["observer_rules_unit_instance_id"] == observer_rules_unit_id
            and payload["spotted_unit_instance_id"] == spotted_unit_id
        ):
            return option
    return None


def _done_option(request: DecisionRequest) -> DecisionOption:
    for option in request.options:
        if option.option_id == army_rule.FOR_THE_GREATER_GOOD_DONE_OPTION_ID:
            return option
    raise AssertionError("missing done option")


def _request_context(lifecycle: GameLifecycle) -> ShootingPhaseStartRequestContext:
    return ShootingPhaseStartRequestContext(
        state=_require_state(lifecycle),
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_config(lifecycle).ruleset_descriptor,
        army_catalog=_config(lifecycle).army_catalog,
        shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
    )


def _result_context(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> ShootingPhaseStartResultContext:
    return ShootingPhaseStartResultContext(
        state=_require_state(lifecycle),
        decisions=lifecycle.decision_controller,
        request=request,
        result=result,
        ruleset_descriptor=_config(lifecycle).ruleset_descriptor,
        army_catalog=_config(lifecycle).army_catalog,
        shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
    )


def _synthetic_shooting_start_request(request_id: str) -> DecisionRequest:
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"request_id": request_id}),
        options=(
            DecisionOption(
                option_id="phase17g-hook-option",
                label="Hook option",
                payload=validate_json_value({"request_id": request_id}),
            ),
        ),
    )


def _request_handler(
    request: DecisionRequest | None,
) -> Callable[[ShootingPhaseStartRequestContext], DecisionRequest | None]:
    def handler(_context: ShootingPhaseStartRequestContext) -> DecisionRequest | None:
        return request

    return handler


def _invalid_request_handler(_context: ShootingPhaseStartRequestContext) -> DecisionRequest | None:
    return cast(DecisionRequest, "invalid")


def _true_result_handler(_context: ShootingPhaseStartResultContext) -> bool | LifecycleStatus:
    return True


def _invalid_result_handler(_context: ShootingPhaseStartResultContext) -> bool | LifecycleStatus:
    return cast(bool, "invalid")


def _weapon_context(
    *,
    state: GameState,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    weapon_profile: WeaponProfile,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacking_unit_instance_id,
        attacker_model_instance_id=f"{attacking_unit_instance_id}:model-001",
        target_unit_instance_id=target_unit_instance_id,
        weapon_profile=weapon_profile,
    )


def _ranged_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-tau-pulse-rifle",
        name="Pulse Rifle",
        range_profile=RangeProfile.distance(30),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 5),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:tau:test-ranged-weapon",),
    )


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


def _config(lifecycle: GameLifecycle) -> GameConfig:
    require_config = cast(
        Callable[[], GameConfig],
        object.__getattribute__(lifecycle, "_require_config"),
    )
    return require_config()
