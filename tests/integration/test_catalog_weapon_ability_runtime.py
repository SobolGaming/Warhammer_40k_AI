# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.support.catalog_package_fixtures import (
    flesh_hounds_army,
    named_weapon_choice_package,
    named_weapon_choice_unit,
)
from tests.support.catalog_rule_ir_fixtures import (
    multi_clause_named_weapon_choice_record,
    multi_clause_named_weapon_choice_rule_ir,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_army,
    bloodcrushers_battlefield_state,
    player_ability_index,
    set_state_battle_phase,
    shooting_phase_start_request_context,
    weapon_profile_by_name,
)

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    WeaponKeyword,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
    CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SELECTED_EVENT,
    SELECT_CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SUBMISSION_KIND,
    CatalogNamedWeaponAbilityChoiceRuntime,
    _available_catalog_named_weapon_ability_choice_groups,
    _record_can_select_catalog_named_weapon_ability,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    catalog_weapon_profile_modifier_bindings,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import (
    BattlePhase,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartHookRegistry,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.rule_ir import (
    RuleIR,
    RuleIRPayload,
)


def test_phase17k_named_weapon_ability_choice_records_and_modifies_profile() -> None:
    package = named_weapon_choice_package()
    unit = named_weapon_choice_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    choice_record = records_by_name["Daemonspark"]
    replay_payload = choice_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=battlefield)
    set_state_battle_phase(state, BattlePhase.SHOOTING)
    decisions = DecisionController()
    runtime = CatalogNamedWeaponAbilityChoiceRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = ShootingPhaseStartHookRegistry.from_bindings(runtime.bindings())
    request_context = shooting_phase_start_request_context(
        state=state,
        decisions=decisions,
        army_catalog=package.army_catalog,
    )
    request = registry.next_request_for(request_context)

    assert request is not None
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:ignores-cover",
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:ignores-cover",
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    }
    assert request.decision_type == SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SUBMISSION_KIND
    )
    assert request_payload["weapon_names"] == ["Bolt of Change"]
    assert request_payload["target_model_instance_ids"] == [unit.own_models[0].model_instance_id]
    assert tuple(option.label for option in request.options) == (
        "Ignores Cover for Bolt of Change",
        "Lethal Hits for Bolt of Change",
        "Sustained Hits D3 for Bolt of Change",
    )
    sustained_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["selected_named_weapon_ability_choice"]
        == {
            "option_id": option.option_id,
            "selection_option_id": "option_003_sustained_hits_d3",
            "selection_option_index": 3,
            "selected_weapon_ability": "Sustained Hits",
            "keyword": "Sustained Hits",
            "ability_descriptor": AbilityDescriptor.sustained_hits("D3").to_payload(),
            "weapon_ability_value": "D3",
        }
    )
    result = DecisionResult.for_request(
        result_id="phase17k-named-weapon-choice-sustained-d3",
        request=request,
        selected_option_id=sustained_option.option_id,
    )
    decisions.request_decision(request)
    record = decisions.submit_result(result)
    handled = registry.apply_result(
        ShootingPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=record.request,
            result=record.result,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=package.army_catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )
    bolt_profile = weapon_profile_by_name(package.army_catalog, "Bolt of Change")
    other_profile = replace(
        bolt_profile,
        profile_id=f"{bolt_profile.profile_id}:other",
        name="Infernal Gateway",
    )
    modifier_registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=catalog_weapon_profile_modifier_bindings(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army,),
        )
    )
    shooting_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id=unit.unit_instance_id,
        weapon_profile=bolt_profile,
    )
    modified_bolt = modifier_registry.modified_weapon_profile(shooting_context)

    assert handled is True
    effects = state.persisting_effects_for_unit(unit.unit_instance_id)
    assert len(effects) == 1
    effect_payload = cast(dict[str, JsonValue], effects[0].effect_payload)
    assert effect_payload["effect_kind"] == CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND
    assert effect_payload["weapon_ability_value"] == "D3"
    assert WeaponKeyword.SUSTAINED_HITS in modified_bolt.keywords
    assert any(
        ability.to_payload() == AbilityDescriptor.sustained_hits("D3").to_payload()
        for ability in modified_bolt.abilities
    )
    assert (
        modifier_registry.modified_weapon_profile(
            replace(shooting_context, source_phase=BattlePhase.FIGHT)
        )
        == bolt_profile
    )
    assert (
        modifier_registry.modified_weapon_profile(
            replace(shooting_context, weapon_profile=other_profile)
        )
        == other_profile
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SELECTED_EVENT
    )
    assert len(selected_events) == 1
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_named_weapon_choice_uses_runtime_clause_scoped_records() -> None:
    package = named_weapon_choice_package()
    unit = named_weapon_choice_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    rule_ir = multi_clause_named_weapon_choice_rule_ir()
    clause_001_record = multi_clause_named_weapon_choice_record(
        rule_ir=rule_ir,
        clause_index=0,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    )
    clause_002_record = multi_clause_named_weapon_choice_record(
        rule_ir=rule_ir,
        clause_index=1,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    ability_index = AbilityCatalogIndex.from_records((clause_001_record, clause_002_record))
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    set_state_battle_phase(state, BattlePhase.SHOOTING)
    request_context = shooting_phase_start_request_context(
        state=state,
        decisions=DecisionController(),
        army_catalog=package.army_catalog,
    )

    groups = _available_catalog_named_weapon_ability_choice_groups(
        ability_indexes_by_player_id={army.player_id: ability_index},
        armies=(army,),
        context=request_context,
    )
    request = ShootingPhaseStartHookRegistry.from_bindings(
        CatalogNamedWeaponAbilityChoiceRuntime(
            ability_indexes_by_player_id={army.player_id: ability_index},
            armies=(army,),
        ).bindings()
    ).next_request_for(request_context)

    assert not _record_can_select_catalog_named_weapon_ability(clause_001_record)
    assert _record_can_select_catalog_named_weapon_ability(clause_002_record)
    assert len(groups) == 1
    assert groups[0].record.record_id == clause_002_record.record_id
    assert groups[0].clause.clause_id == rule_ir.clauses[1].clause_id
    assert request is not None
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["catalog_record_id"] == clause_002_record.record_id
    assert len(request.options) == 2


def test_phase17k_named_weapon_ability_choice_rejects_availability_drift() -> None:
    package = named_weapon_choice_package()
    unit = named_weapon_choice_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=battlefield)
    set_state_battle_phase(state, BattlePhase.SHOOTING)
    decisions = DecisionController()
    registry = ShootingPhaseStartHookRegistry.from_bindings(
        CatalogNamedWeaponAbilityChoiceRuntime(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army,),
        ).bindings()
    )
    request = registry.next_request_for(
        shooting_phase_start_request_context(
            state=state,
            decisions=decisions,
            army_catalog=package.army_catalog,
        )
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17k-named-weapon-choice-drift",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.request_decision(request)
    record = decisions.submit_result(result)
    state.battlefield_state = battlefield.with_removed_models(
        (unit.own_models[0].model_instance_id,)
    )

    handled = registry.apply_result(
        ShootingPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=record.request,
            result=record.result,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=package.army_catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )

    assert not isinstance(handled, bool)
    assert handled.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = cast(dict[str, JsonValue], handled.payload)
    assert invalid_payload["invalid_reason"] == ("catalog_named_weapon_ability_choice_unavailable")
    assert state.persisting_effects_for_unit(unit.unit_instance_id) == ()


def test_phase17k_named_weapon_ability_choice_rejects_submission_drifts() -> None:
    package = named_weapon_choice_package()
    unit = named_weapon_choice_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    set_state_battle_phase(state, BattlePhase.SHOOTING)
    decisions = DecisionController()
    runtime = CatalogNamedWeaponAbilityChoiceRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = ShootingPhaseStartHookRegistry.from_bindings(runtime.bindings())
    request = registry.next_request_for(
        shooting_phase_start_request_context(
            state=state,
            decisions=decisions,
            army_catalog=package.army_catalog,
        )
    )
    assert request is not None
    selected_option = request.options[0]

    def apply(payload: JsonValue, selected_option_id: str = selected_option.option_id) -> object:
        return registry.apply_result(
            ShootingPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=DecisionResult(
                    result_id=f"phase17k-drift-{len(decisions.event_log.records)}",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id=request.actor_id,
                    selected_option_id=selected_option_id,
                    payload=payload,
                ),
                ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
                army_catalog=package.army_catalog,
                shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
            )
        )

    wrong_kind_payload = dict(cast(dict[str, JsonValue], selected_option.payload))
    wrong_kind_payload["submission_kind"] = "wrong_named_weapon_choice_submission"

    def invalid_reason(value: object) -> JsonValue:
        assert not isinstance(value, bool)
        status = cast(LifecycleStatus, value)
        assert status.status_kind is LifecycleStatusKind.INVALID
        return cast(dict[str, JsonValue], status.payload)["invalid_reason"]

    wrong_kind = apply(wrong_kind_payload)
    assert invalid_reason(wrong_kind) == (
        "catalog_named_weapon_ability_choice_submission_kind_drift"
    )

    option_drift = apply(
        selected_option.payload,
        selected_option_id=f"{selected_option.option_id}:missing",
    )
    assert invalid_reason(option_drift) == ("catalog_named_weapon_ability_choice_option_drift")

    payload_drift = dict(cast(dict[str, JsonValue], selected_option.payload))
    payload_drift["weapon_names"] = ["Changed Weapon"]
    drifted = apply(payload_drift)
    assert invalid_reason(drifted) == ("catalog_named_weapon_ability_choice_payload_drift")

    wrong_hook_request = replace(
        request,
        payload={
            **cast(dict[str, JsonValue], request.payload),
            "hook_id": "phase17k-other-hook",
        },
    )
    ignored = registry.apply_result(
        ShootingPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_hook_request,
            result=DecisionResult.for_request(
                result_id="phase17k-wrong-hook",
                request=request,
                selected_option_id=selected_option.option_id,
            ),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=package.army_catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )
    assert ignored is False
    assert state.persisting_effects_for_unit(unit.unit_instance_id) == ()
