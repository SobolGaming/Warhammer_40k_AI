from __future__ import annotations

# pyright: reportPrivateUsage=false
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    center_marker_definition,
    default_unit_selection,
    unit_by_id,
    with_model_offsets,
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_mechanicus import (
    army_rule,
)
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)


def test_doctrina_runtime_contribution_registers_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert army_rule.CONTRIBUTION_ID == army_rule.HOOK_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert tuple(binding.hook_id for binding in contribution.battle_round_start_hook_bindings) == (
        army_rule.HOOK_ID,
    )
    assert tuple(
        binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings
    ) == (army_rule.WEAPON_PROFILE_MODIFIER_ID,)
    assert tuple(binding.modifier_id for binding in contribution.hit_roll_modifier_bindings) == (
        army_rule.PROTECTOR_HIT_MODIFIER_ID,
    )


def test_doctrina_selection_records_protector_effect_and_round_trips() -> None:
    state = _admech_battle_state()
    unit = _unit_for_player(state, player_id="player-a")

    decisions, request = _select_doctrina(
        state,
        selected_option_id=army_rule.DoctrinaImperative.PROTECTOR.value,
    )

    assert request.decision_type == SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        _option_id(army_rule.DoctrinaImperative.PROTECTOR),
        _option_id(army_rule.DoctrinaImperative.CONQUEROR),
        army_rule.DOCTRINA_DECLINE_OPTION_ID,
    }
    assert (
        army_rule.active_doctrina_imperative_for_player(state, player_id="player-a")
        is army_rule.DoctrinaImperative.PROTECTOR
    )
    assert (
        army_rule.active_doctrina_imperative_for_unit(
            state,
            unit_instance_id=unit.unit_instance_id,
        )
        is army_rule.DoctrinaImperative.PROTECTOR
    )
    selected_payload = _event_payload(
        decisions,
        "adeptus_mechanicus_doctrina_imperative_selected",
    )
    assert selected_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert selected_payload["hook_id"] == army_rule.HOOK_ID
    assert selected_payload["selected_doctrina_imperative_id"] == "protector"
    assert _json_round_trip(state).to_payload() == state.to_payload()


def test_doctrina_decline_records_state_without_effect() -> None:
    state = _admech_battle_state()

    decisions, _request = _select_doctrina(
        state,
        selected_option_id=army_rule.DOCTRINA_DECLINE_OPTION_ID,
    )

    assert army_rule.active_doctrina_imperative_for_player(state, player_id="player-a") is None
    assert not [
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == army_rule.SOURCE_RULE_ID
    ]
    declined_payload = _event_payload(
        decisions,
        "adeptus_mechanicus_doctrina_imperatives_declined",
    )
    assert declined_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert (
        _battle_round_start_hooks().next_request_for(
            BattleRoundStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )


def test_protector_imperative_modifies_ranged_profiles_and_melee_target_hit_rolls() -> None:
    state = _admech_battle_state()
    target = _unit_for_player(state, player_id="player-a")
    attacker = _unit_for_player(state, player_id="player-b")
    _select_doctrina(state, selected_option_id=army_rule.DoctrinaImperative.PROTECTOR.value)

    modified = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=target, target=attacker, melee=False)
    )
    melee = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=target, target=attacker, melee=True)
    )

    assert WeaponKeyword.HEAVY in modified.keywords
    assert modified.skill.final == 2
    assert any(
        ability.ability_id == "heavy:stationary-or-policy-defined" for ability in modified.abilities
    )
    assert army_rule.SOURCE_RULE_ID in modified.source_ids
    assert melee == _weapon_profile(melee=True)
    assert (
        army_rule.protector_imperative_hit_roll_modifier(
            _hit_context(state=state, attacker=attacker, target=target, melee=True)
        )
        == -1
    )
    assert (
        army_rule.protector_imperative_hit_roll_modifier(
            _hit_context(state=state, attacker=attacker, target=target, melee=False)
        )
        == 0
    )


def test_conqueror_imperative_grants_assault_ws_and_battleline_ap() -> None:
    state = _admech_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _select_doctrina(state, selected_option_id=army_rule.DoctrinaImperative.CONQUEROR.value)

    ranged = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=unit, target=target, melee=False)
    )
    melee = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=unit, target=target, melee=True)
    )

    assert WeaponKeyword.ASSAULT in ranged.keywords
    assert ranged.skill.final == 3
    assert ranged.armor_penetration.final == -1
    assert melee.skill.final == 2
    assert melee.armor_penetration.final == -1

    unsupported_state = _admech_battle_state(battleline=False)
    unsupported_unit = _unit_for_player(unsupported_state, player_id="player-a")
    unsupported_target = _unit_for_player(unsupported_state, player_id="player-b")
    _select_doctrina(
        unsupported_state,
        selected_option_id=army_rule.DoctrinaImperative.CONQUEROR.value,
    )
    unsupported = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(
            state=unsupported_state,
            unit=unsupported_unit,
            target=unsupported_target,
            melee=False,
        )
    )
    assert WeaponKeyword.ASSAULT in unsupported.keywords
    assert unsupported.armor_penetration.final == 0


def test_doctrina_battleline_aura_supports_nearby_admech_battleline() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    supported_id = "army-alpha:intercessor-unit-1"
    battleline_id = "army-alpha:intercessor-unit-2"
    _mark_player_as_admech(
        state,
        player_id="player-a",
        battleline_by_unit_id={
            supported_id: False,
            battleline_id: True,
        },
    )
    _place_units_near_center(
        state,
        placements={
            supported_id: ((0.0, 0.0), (0.2, 0.0), (0.4, 0.0), (0.6, 0.0), (0.8, 0.0)),
            battleline_id: ((4.0, 0.0), (4.2, 0.0), (4.4, 0.0), (4.6, 0.0), (4.8, 0.0)),
        },
    )
    supported = unit_by_id(state, supported_id)
    enemy = _unit_for_player(state, player_id="player-b")
    _select_doctrina(state, selected_option_id=army_rule.DoctrinaImperative.CONQUEROR.value)

    nearby = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=supported, target=enemy, melee=False)
    )
    assert nearby.armor_penetration.final == -1

    _place_units_near_center(
        state,
        placements={
            battleline_id: ((30.0, 0.0), (30.2, 0.0), (30.4, 0.0), (30.6, 0.0), (30.8, 0.0)),
        },
    )
    far = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=supported, target=enemy, melee=False)
    )
    assert far.armor_penetration.final == 0


def test_doctrina_effect_applies_to_attached_rules_unit_components() -> None:
    state = _admech_battle_state()
    attached_id, bodyguard, leader = _attach_admech_rules_unit(state)
    enemy = _unit_for_player(state, player_id="player-b")

    decisions, request = _select_doctrina(
        state,
        selected_option_id=army_rule.DoctrinaImperative.CONQUEROR.value,
    )

    common_payload = cast(dict[str, JsonValue], request.payload)
    assert common_payload["target_unit_instance_ids"] == [attached_id]
    assert (
        army_rule.active_doctrina_imperative_for_unit(
            state,
            unit_instance_id=leader.unit_instance_id,
        )
        is army_rule.DoctrinaImperative.CONQUEROR
    )
    modified = army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=leader, target=enemy, melee=True)
    )
    assert modified.skill.final == 2
    assert modified.armor_penetration.final == -1
    assert (
        _event_payload(decisions, "adeptus_mechanicus_doctrina_imperative_selected")[
            "selected_doctrina_imperative_id"
        ]
        == "conqueror"
    )
    assert bodyguard.unit_instance_id != leader.unit_instance_id


def test_doctrina_selection_rejects_stale_payloads_and_invalid_contexts() -> None:
    state = _admech_battle_state()
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("Expected Doctrina Imperatives request.")
    selected_option_id = _option_id(army_rule.DoctrinaImperative.PROTECTOR)
    option = request.option_by_id(selected_option_id)

    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_doctrina_selection_result(cast(BattleRoundStartResultContext, object()))

    wrong_type_request = replace(request, decision_type="other-decision")
    wrong_type_result = DecisionResult.for_request(
        result_id="phase17g-admech-wrong-type",
        request=wrong_type_request,
        selected_option_id=selected_option_id,
    )
    assert not army_rule.apply_doctrina_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_type_request,
            result=wrong_type_result,
        )
    )

    wrong_hook_request = replace(
        request,
        payload=validate_json_value(
            {**cast(dict[str, JsonValue], request.payload), "hook_id": "wrong"}
        ),
    )
    wrong_hook_result = DecisionResult.for_request(
        result_id="phase17g-admech-wrong-hook",
        request=wrong_hook_request,
        selected_option_id=selected_option_id,
    )
    assert not army_rule.apply_doctrina_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_hook_request,
            result=wrong_hook_result,
        )
    )

    actorless_result = DecisionResult(
        result_id="phase17g-admech-actorless",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=None,
        selected_option_id=selected_option_id,
        payload=option.payload,
    )
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=actorless_result,
            )
        )

    missing_option_result = DecisionResult(
        result_id="phase17g-admech-missing-option",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="missing-option",
        payload=option.payload,
    )
    with pytest.raises(GameLifecycleError, match="selected option is not available"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=missing_option_result,
            )
        )

    drifted_result = DecisionResult(
        result_id="phase17g-admech-drifted-option",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=selected_option_id,
        payload=validate_json_value(
            {**cast(dict[str, JsonValue], option.payload), "battle_round": 99}
        ),
    )
    with pytest.raises(GameLifecycleError, match="selected option payload drift"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=drifted_result,
            )
        )

    stale_request = replace(
        request,
        payload=validate_json_value(
            {**cast(dict[str, JsonValue], request.payload), "battle_round": 99}
        ),
    )
    stale_result = DecisionResult.for_request(
        result_id="phase17g-admech-stale-request",
        request=stale_request,
        selected_option_id=selected_option_id,
    )
    with pytest.raises(GameLifecycleError, match="battle_round drift"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=stale_request,
                result=stale_result,
            )
        )

    drift_state = _admech_battle_state()
    drift_decisions = DecisionController()
    drift_request = registry.next_request_for(
        BattleRoundStartRequestContext(state=drift_state, decisions=drift_decisions)
    )
    if drift_request is None:
        raise AssertionError("Expected Doctrina Imperatives drift request.")
    _remove_doctrina_abilities(drift_state, player_id="player-a")
    drift_result = DecisionResult.for_request(
        result_id="phase17g-admech-target-drift",
        request=drift_request,
        selected_option_id=selected_option_id,
    )
    with pytest.raises(GameLifecycleError, match="eligible target drift"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=drift_state,
                decisions=drift_decisions,
                request=drift_request,
                result=drift_result,
            )
        )


def test_doctrina_skips_armies_without_eligible_doctrina_units() -> None:
    decisions = DecisionController()
    non_admech_state = battle_state()
    no_ability_state = _admech_battle_state()
    _remove_doctrina_abilities(no_ability_state, player_id="player-a")
    unit_without_ability = _unit_for_player(no_ability_state, player_id="player-a")

    assert (
        _battle_round_start_hooks().next_request_for(
            BattleRoundStartRequestContext(state=non_admech_state, decisions=decisions)
        )
        is None
    )
    assert (
        _battle_round_start_hooks().next_request_for(
            BattleRoundStartRequestContext(state=no_ability_state, decisions=decisions)
        )
        is None
    )
    assert (
        army_rule.active_doctrina_imperative_for_unit(
            no_ability_state,
            unit_instance_id=unit_without_ability.unit_instance_id,
        )
        is None
    )


def test_doctrina_duplicate_effects_and_selection_states_are_fail_fast() -> None:
    state = _admech_battle_state()
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = _require_doctrina_request(state=state, decisions=decisions, registry=registry)
    result = DecisionResult.for_request(
        result_id="phase17g-admech-duplicate-selection",
        request=request,
        selected_option_id=_option_id(army_rule.DoctrinaImperative.PROTECTOR),
    )

    assert registry.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    with pytest.raises(GameLifecycleError, match="already recorded"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )

    effect = state.persisting_effects[0]
    stale_effect_payload = cast(dict[str, JsonValue], effect.effect_payload)
    stale_effect = replace(
        effect,
        effect_id=f"{effect.effect_id}:stale-round",
        effect_payload=validate_json_value({**stale_effect_payload, "battle_round": 99}),
    )
    wrong_owner_effect = replace(
        effect,
        effect_id=f"{effect.effect_id}:wrong-owner",
        owner_player_id="player-b",
    )
    wrong_source_effect = replace(
        effect,
        effect_id=f"{effect.effect_id}:wrong-source",
        source_rule_id="doctrina-test:other-source",
    )
    state.persisting_effects = [stale_effect, wrong_owner_effect, wrong_source_effect]
    assert army_rule.active_doctrina_imperative_for_player(state, player_id="player-a") is None

    duplicate_effect = replace(effect, effect_id=f"{effect.effect_id}:duplicate")
    state.persisting_effects = [effect, duplicate_effect]
    with pytest.raises(GameLifecycleError, match="multiple active effects"):
        army_rule.active_doctrina_imperative_for_player(state, player_id="player-a")

    state_record = state.faction_rule_states[0]
    duplicate_state_record = replace(
        state_record,
        state_id=f"{state_record.state_id}:duplicate",
    )
    state.faction_rule_states.append(duplicate_state_record)
    with pytest.raises(GameLifecycleError, match="duplicate round states"):
        _battle_round_start_hooks().next_request_for(
            BattleRoundStartRequestContext(state=state, decisions=DecisionController())
        )


def test_doctrina_public_entry_points_fail_fast_for_malformed_inputs() -> None:
    state = _admech_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")

    with pytest.raises(GameLifecycleError, match="Unsupported Doctrina Imperative"):
        army_rule.DoctrinaImperativeDefinition(
            imperative=cast(army_rule.DoctrinaImperative, "unsupported"),
            label="Bad Imperative",
            effect_summary="Bad imperative.",
        )
    with pytest.raises(GameLifecycleError, match="imperative must be a string"):
        army_rule.DoctrinaImperativeDefinition(
            imperative=cast(army_rule.DoctrinaImperative, object()),
            label="Bad Imperative",
            effect_summary="Bad imperative.",
        )
    with pytest.raises(GameLifecycleError, match="label must be a string"):
        army_rule.DoctrinaImperativeDefinition(
            imperative=army_rule.DoctrinaImperative.PROTECTOR,
            label=cast(str, object()),
            effect_summary="Bad label.",
        )
    with pytest.raises(GameLifecycleError, match="label must not be empty"):
        army_rule.DoctrinaImperativeDefinition(
            imperative=army_rule.DoctrinaImperative.PROTECTOR,
            label=" ",
            effect_summary="Bad label.",
        )

    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.doctrina_selection_request(cast(BattleRoundStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="payload requires GameState"):
        army_rule.doctrina_common_payload(
            state=object(),
            player_id="player-a",
            target_unit_ids=("unit-a",),
        )
    with pytest.raises(GameLifecycleError, match="effect lookup requires GameState"):
        army_rule.active_doctrina_imperative_for_player(object(), player_id="player-a")
    with pytest.raises(GameLifecycleError, match="unit lookup requires GameState"):
        army_rule.active_doctrina_imperative_for_unit(object(), unit_instance_id="unit-a")
    with pytest.raises(GameLifecycleError, match="weapon profile modifier requires context"):
        army_rule.doctrina_weapon_profile_modifier(cast(WeaponProfileModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="Hit roll modifier requires context"):
        army_rule.protector_imperative_hit_roll_modifier(cast(HitRollModifierContext, object()))

    assert army_rule.doctrina_weapon_profile_modifier(
        _modifier_context(state=state, unit=unit, target=target, melee=False)
    ) == _weapon_profile(melee=False)
    assert (
        army_rule.protector_imperative_hit_roll_modifier(
            _hit_context(state=state, attacker=target, target=unit, melee=True)
        )
        == 0
    )


def test_doctrina_selection_rejects_wrong_actor_and_option_shape_drift() -> None:
    state = _admech_battle_state()
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = _require_doctrina_request(state=state, decisions=decisions, registry=registry)
    selected_option_id = _option_id(army_rule.DoctrinaImperative.PROTECTOR)
    option = request.option_by_id(selected_option_id)
    wrong_actor_result = DecisionResult(
        result_id="phase17g-admech-wrong-actor",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id="player-b",
        selected_option_id=selected_option_id,
        payload=option.payload,
    )

    with pytest.raises(GameLifecycleError, match="actor does not own Adeptus Mechanicus"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=wrong_actor_result,
            )
        )

    unsupported_payload = validate_json_value(
        {**cast(dict[str, JsonValue], option.payload), "selection_mode": "unsupported"}
    )
    unsupported_request = replace(
        request,
        options=(
            DecisionOption(
                option_id="adeptus_mechanicus:doctrina_imperatives:unsupported",
                label="Unsupported",
                payload=unsupported_payload,
            ),
        ),
    )
    unsupported_result = DecisionResult.for_request(
        result_id="phase17g-admech-unsupported-mode",
        request=unsupported_request,
        selected_option_id="adeptus_mechanicus:doctrina_imperatives:unsupported",
    )
    with pytest.raises(GameLifecycleError, match="selection mode is unsupported"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=unsupported_request,
                result=unsupported_result,
            )
        )

    drift_option_request = replace(
        request,
        options=(
            DecisionOption(
                option_id="adeptus_mechanicus:doctrina_imperatives:wrong-protector",
                label="Wrong Protector",
                payload=option.payload,
            ),
        ),
    )
    drift_option_result = DecisionResult.for_request(
        result_id="phase17g-admech-option-id-drift",
        request=drift_option_request,
        selected_option_id="adeptus_mechanicus:doctrina_imperatives:wrong-protector",
    )
    with pytest.raises(GameLifecycleError, match="selected option ID drift"):
        registry.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=drift_option_request,
                result=drift_option_result,
            )
        )


def test_doctrina_structured_validators_reject_malformed_values() -> None:
    with pytest.raises(GameLifecycleError, match="imperative must be a string"):
        army_rule._imperative_from_token(object())
    with pytest.raises(GameLifecycleError, match="Unsupported Doctrina Imperative"):
        army_rule._imperative_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="weapon keyword must be a string"):
        army_rule._weapon_keyword_from_token(object())
    with pytest.raises(GameLifecycleError, match="Unsupported Doctrina weapon keyword"):
        army_rule._weapon_keyword_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        army_rule._payload_object("bad-payload")
    with pytest.raises(GameLifecycleError, match="must be an object"):
        army_rule._json_object("Bad payload", object())
    with pytest.raises(GameLifecycleError, match="payload missing must be a string"):
        army_rule._payload_string({}, key="missing")
    with pytest.raises(GameLifecycleError, match="payload missing must be an int"):
        army_rule._payload_int({}, key="missing")
    with pytest.raises(GameLifecycleError, match="payload target_unit_instance_ids must be a list"):
        army_rule._payload_string_tuple(
            {"target_unit_instance_ids": "unit-a"},
            key="target_unit_instance_ids",
        )
    with pytest.raises(GameLifecycleError, match="source_rule_id drift"):
        army_rule._expect_payload_string(
            {"source_rule_id": "wrong"},
            key="source_rule_id",
            expected=army_rule.SOURCE_RULE_ID,
        )
    with pytest.raises(GameLifecycleError, match="field must be a string"):
        army_rule._validate_identifier("field", object())
    with pytest.raises(GameLifecycleError, match="field must not be empty"):
        army_rule._validate_identifier("field", " ")
    with pytest.raises(GameLifecycleError, match="ids must be a tuple"):
        army_rule._validate_identifier_tuple("ids", cast(tuple[str, ...], ["unit-a"]))
    with pytest.raises(GameLifecycleError, match="ids must be unique"):
        army_rule._validate_identifier_tuple("ids", ("unit-a", "unit-a"))
    with pytest.raises(GameLifecycleError, match="ids must not be empty"):
        army_rule._validate_identifier_tuple("ids", ())
    with pytest.raises(GameLifecycleError, match="count must be an integer"):
        army_rule._validate_positive_int("count", object())
    with pytest.raises(GameLifecycleError, match="count must be positive"):
        army_rule._validate_positive_int("count", 0)
    with pytest.raises(GameLifecycleError, match="distance must be numeric"):
        army_rule._validate_non_negative_float("distance", object())
    with pytest.raises(GameLifecycleError, match="distance must not be negative"):
        army_rule._validate_non_negative_float("distance", -1.0)
    with pytest.raises(GameLifecycleError, match="models must be a tuple"):
        army_rule._validate_geometry_models("models", cast(tuple[GeometryModel, ...], []))
    with pytest.raises(GameLifecycleError, match="models must contain GeometryModel"):
        army_rule._validate_geometry_models(
            "models",
            cast(tuple[GeometryModel, ...], (object(),)),
        )


def test_doctrina_source_coverage_and_execution_records_are_engine_consumed() -> None:
    coverage_row = next(
        row
        for row in faction_coverage_2026_27.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.faction_id == "adeptus-mechanicus"
    )
    execution_record = next(
        record
        for record in faction_execution_2026_27.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == "adeptus-mechanicus"
    )

    assert coverage_row.rule_name == "Doctrina Imperatives"
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == tuple(
        sorted(
            (
                army_rule.HOOK_ID,
                army_rule.PROTECTOR_HIT_MODIFIER_ID,
                army_rule.WEAPON_PROFILE_MODIFIER_ID,
            )
        )
    )
    assert execution_record.execution_id == army_rule.SOURCE_RULE_ID
    assert execution_record.runtime_consumer_ids == coverage_row.runtime_consumer_ids


def _admech_battle_state(*, battleline: bool = True) -> GameState:
    state = battle_state()
    _mark_player_as_admech(state, player_id="player-a", battleline=battleline)
    return state


def _mark_player_as_admech(
    state: GameState,
    *,
    player_id: str,
    battleline: bool = True,
    battleline_by_unit_id: Mapping[str, bool] | None = None,
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...] | None = None,
) -> None:
    resolved_abilities = (
        (_doctrina_ability(),) if datasheet_abilities is None else datasheet_abilities
    )
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            unit_is_battleline = (
                battleline
                if battleline_by_unit_id is None
                else battleline_by_unit_id[unit.unit_instance_id]
            )
            keywords = tuple(
                sorted(
                    {*unit.keywords, army_rule.BATTLELINE_KEYWORD}
                    if unit_is_battleline
                    else {
                        keyword
                        for keyword in unit.keywords
                        if keyword.upper() != army_rule.BATTLELINE_KEYWORD
                    }
                )
            )
            updated_units.append(
                replace(
                    unit,
                    keywords=keywords,
                    faction_keywords=(army_rule.ADEPTUS_MECHANICUS_FACTION_KEYWORD,),
                    datasheet_abilities=resolved_abilities,
                )
            )
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.ADEPTUS_MECHANICUS_FACTION_ID,
                ),
                units=tuple(updated_units),
            )
        )
    state.army_definitions = updated_armies


def _remove_doctrina_abilities(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                units=tuple(replace(unit, datasheet_abilities=()) for unit in army.units),
            )
        )
    state.army_definitions = updated_armies


def _doctrina_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="adeptus-mechanicus-test-doctrina-imperatives",
        name="Doctrina Imperatives",
        source_id=army_rule.SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Select a Doctrina Imperative at the start of the battle round.",
    )


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _select_doctrina(
    state: GameState,
    *,
    selected_option_id: str,
) -> tuple[DecisionController, DecisionRequest]:
    decisions = DecisionController()
    registry = _battle_round_start_hooks()
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("Expected Doctrina Imperatives request.")
    try:
        imperative = army_rule.DoctrinaImperative(selected_option_id)
    except ValueError:
        resolved_option_id = selected_option_id
    else:
        resolved_option_id = _option_id(imperative)
    result = DecisionResult.for_request(
        result_id=f"phase17g-admech-select:{resolved_option_id}",
        request=request,
        selected_option_id=resolved_option_id,
    )
    assert registry.apply_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    return decisions, request


def _require_doctrina_request(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: BattleRoundStartHookRegistry,
) -> DecisionRequest:
    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    if request is None:
        raise AssertionError("Expected Doctrina Imperatives request.")
    return request


def _battle_round_start_hooks() -> BattleRoundStartHookRegistry:
    return BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )


def _option_id(imperative: army_rule.DoctrinaImperative) -> str:
    return f"adeptus_mechanicus:doctrina_imperatives:{imperative.value}"


def _weapon_profile(*, melee: bool, ap: int = 0, skill: int = 3) -> WeaponProfile:
    return WeaponProfile(
        profile_id="test-melee-profile" if melee else "test-ranged-profile",
        name="Test melee weapon" if melee else "Test ranged weapon",
        range_profile=RangeProfile.melee() if melee else RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(
            Characteristic.WEAPON_SKILL if melee else Characteristic.BALLISTIC_SKILL,
            skill,
        ),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, ap),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("test-profile",),
    )


def _modifier_context(
    *,
    state: GameState,
    unit: UnitInstance,
    target: UnitInstance,
    melee: bool,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT if melee else BattlePhase.SHOOTING,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        weapon_profile=_weapon_profile(melee=melee),
    )


def _hit_context(
    *,
    state: GameState,
    attacker: UnitInstance,
    target: UnitInstance,
    melee: bool,
) -> HitRollModifierContext:
    return HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        weapon_profile=_weapon_profile(melee=melee),
        source_phase=BattlePhase.FIGHT if melee else BattlePhase.SHOOTING,
    )


def _place_units_near_center(
    state: GameState,
    *,
    placements: dict[str, tuple[tuple[float, float], ...]],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Expected battlefield state.")
    marker = center_marker_definition(state)
    battlefield_state = state.battlefield_state
    for unit_instance_id, offsets in placements.items():
        current = battlefield_state.unit_placement_by_id(unit_instance_id)
        battlefield_state = battlefield_state.with_unit_placement(
            with_model_offsets(current, marker, offsets=offsets)
        )
    state.battlefield_state = battlefield_state


def _attach_admech_rules_unit(state: GameState) -> tuple[str, UnitInstance, UnitInstance]:
    bodyguard = _unit_for_player(state, player_id="player-a")
    leader = _cloned_unit_instance(
        bodyguard,
        unit_instance_id="army-alpha:doctrina-leader",
        model_id_prefix="army-alpha:doctrina-leader",
    )
    attached_id = "attached-unit:army-alpha:doctrina"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="doctrina-test:attached-unit",
        attachment_source_ids=("doctrina-test:attachment-eligibility",),
    )
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                units=tuple(sorted((*army.units, leader), key=lambda unit: unit.unit_instance_id)),
                attached_units=(*army.attached_units, formation),
            )
        )
    state.army_definitions = updated_armies
    state.starting_strength_records.append(
        StartingStrengthRecord(
            player_id="player-a",
            unit_instance_id=attached_id,
            starting_model_count=len(bodyguard.own_models) + len(leader.own_models),
            single_model_starting_wounds=None,
            source_id="doctrina-test:attached-unit:starting-strength",
        )
    )
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    return attached_id, bodyguard, leader


def _cloned_unit_instance(
    unit: UnitInstance,
    *,
    unit_instance_id: str,
    model_id_prefix: str,
) -> UnitInstance:
    return replace(
        unit,
        unit_instance_id=unit_instance_id,
        own_models=tuple(
            replace(model, model_instance_id=f"{model_id_prefix}:{index:03}")
            for index, model in enumerate(unit.own_models, start=1)
        ),
    )


def _event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event {event_type}.")


def _json_round_trip(state: GameState) -> GameState:
    payload = cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    return GameState.from_payload(payload)
