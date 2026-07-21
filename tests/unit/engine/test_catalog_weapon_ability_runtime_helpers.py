# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.support.catalog_package_fixtures import (
    advance_charge_package,
    advance_charge_unit,
    flesh_hounds_army,
    named_weapon_choice_package,
    named_weapon_choice_unit,
)
from tests.support.catalog_rule_ir_fixtures import (
    effect as rule_effect,
)
from tests.support.catalog_rule_ir_fixtures import (
    phase17k_named_choice_effect,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_army,
    bloodcrushers_battlefield_state,
    player_ability_index,
    set_state_battle_phase,
    shooting_phase_start_request_context,
    weapon_profile_by_name,
)

from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
    CatalogNamedWeaponAbilityChoiceOption,
    CatalogNamedWeaponAbilityChoiceRuntime,
    CatalogWeaponKeywordGrant,
    CatalogWeaponKeywordGrantRuntime,
    _available_catalog_named_weapon_ability_choice_groups,
    _catalog_weapon_keyword_grant_from_effect,
    _clause_is_named_weapon_ability_choice,
    _effect_is_named_weapon_ability_choice_option,
    _named_weapon_ability_choice_option_from_effect,
    _optional_named_weapon_names,
    _payload_object,
    _payload_string,
    _payload_string_tuple,
    _selected_catalog_named_weapon_ability_grants,
    _validate_named_weapon_choice_option,
    _validate_named_weapon_choice_target_scope,
    _validate_named_weapon_names,
    _weapon_ability_choice_has_supported_runtime_shape,
    _weapon_ability_descriptor_for_grant,
    _weapon_ability_descriptor_for_selected_choice_payload,
    _weapon_keyword_grant_consumer_ids_for_effect,
    _weapon_names_from_parameters,
    _weapon_scope_matches_profile,
)
from warhammer40k_core.engine.catalog_tracked_target_weapon_grants import (
    profile_with_catalog_weapon_keyword_grant as _profile_with_catalog_weapon_keyword_grant,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
)
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
)


def test_phase17k_named_weapon_ability_choice_helpers_cover_invalid_paths() -> None:
    package = named_weapon_choice_package()
    unit = named_weapon_choice_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    record = next(
        record for record in player_index.all_records() if record.definition.name == "Daemonspark"
    )
    replay_payload = record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    clause = rule_ir.clauses[0]
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
    runtime = CatalogNamedWeaponAbilityChoiceRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )

    assert runtime.bindings()
    assert _available_catalog_named_weapon_ability_choice_groups(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
        context=request_context,
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogNamedWeaponAbilityChoiceRuntime(ability_indexes_by_player_id={}, armies=(army,))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.request_handler(cast(ShootingPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.result_handler(cast(ShootingPhaseStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="require context"):
        _available_catalog_named_weapon_ability_choice_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army,),
            context=cast(ShootingPhaseStartRequestContext, object()),
        )
    with pytest.raises(GameLifecycleError, match="index is missing player"):
        _available_catalog_named_weapon_ability_choice_groups(
            ability_indexes_by_player_id={},
            armies=(army,),
            context=request_context,
        )

    option = _named_weapon_ability_choice_option_from_effect(
        record=record,
        unit=unit,
        clause=clause,
        effect_index=0,
        effect=clause.effects[0],
    )
    assert option is not None
    assert option.label == "Ignores Cover"
    assert _validate_named_weapon_choice_option(option) is option
    assert _clause_is_named_weapon_ability_choice(clause)
    assert _effect_is_named_weapon_ability_choice_option(clause.effects[0])
    assert (
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=rule_effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="hit", delta=1),
        )
        is None
    )
    assert (
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=rule_effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_scope="all"),
        )
        is None
    )
    assert (
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=rule_effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Sustained Hits",
                weapon_name="Bolt of Change",
                target_scope="this_model",
                selection_kind="select_one",
                selection_group_id="group",
                selection_option_id="option",
                selection_option_index=1,
            ),
        )
        is None
    )

    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _named_weapon_ability_choice_option_from_effect(
            record=cast(AbilityCatalogRecord, object()),
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=cast(RuleClause, object()),
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=-1,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule effect"):
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=cast(RuleEffectSpec, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires RuleClause values"):
        _clause_is_named_weapon_ability_choice(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _effect_is_named_weapon_ability_choice_option(cast(RuleEffectSpec, object()))

    assert _optional_named_weapon_names(
        {"weapon_names": ("Bolt of Change", "Infernal Gateway")}
    ) == (
        "Bolt of Change",
        "Infernal Gateway",
    )
    assert _optional_named_weapon_names({"weapon_name": "Bolt of Change"}) == ("Bolt of Change",)
    with pytest.raises(GameLifecycleError, match="weapon_names must be a tuple"):
        _optional_named_weapon_names({"weapon_names": "Bolt of Change|Infernal Gateway"})
    with pytest.raises(GameLifecycleError, match="requires weapon names"):
        _weapon_names_from_parameters({})
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        _validate_named_weapon_names(["Bolt of Change"])
    with pytest.raises(GameLifecycleError, match="must contain strings"):
        _validate_named_weapon_names((1,))
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        _validate_named_weapon_names(("  ",))
    with pytest.raises(GameLifecycleError, match="must not duplicate names"):
        _validate_named_weapon_names(("Bolt-of-Change", "bolt of change"))
    with pytest.raises(GameLifecycleError, match="target_scope must be a string"):
        _validate_named_weapon_choice_target_scope(1)
    with pytest.raises(GameLifecycleError, match="Unsupported"):
        _validate_named_weapon_choice_target_scope("selected_unit")
    with pytest.raises(GameLifecycleError, match="requires option values"):
        _validate_named_weapon_choice_option(object())

    base_choice_parameters = {
        "selection_kind": "select_one",
        "selection_group_id": "group",
        "selection_option_id": "option",
        "selection_option_index": 1,
        "target_scope": "this_model",
        "weapon_name": "Bolt of Change",
        "weapon_ability_value": "D3",
    }
    assert _weapon_ability_choice_has_supported_runtime_shape(
        base_choice_parameters,
        keyword=WeaponKeyword.SUSTAINED_HITS,
    )
    for malformed_parameters in (
        {**base_choice_parameters, "selection_kind": "choose_any"},
        {**base_choice_parameters, "selection_group_id": 1},
        {**base_choice_parameters, "selection_option_index": 0},
        {key: value for key, value in base_choice_parameters.items() if key != "weapon_name"},
    ):
        assert not _weapon_ability_choice_has_supported_runtime_shape(
            malformed_parameters,
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported"):
        _weapon_ability_choice_has_supported_runtime_shape(
            {**base_choice_parameters, "target_scope": "selected_unit"},
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    assert (
        _weapon_ability_descriptor_for_selected_choice_payload(
            payload={"keyword": "Lethal Hits"},
            keyword=WeaponKeyword.LETHAL_HITS,
        )
        == AbilityDescriptor.lethal_hits()
    )

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        _payload_object([])
    with pytest.raises(GameLifecycleError, match="payload weapon_names must be a string"):
        _payload_string({"weapon_names": ["Bolt of Change"]}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="payload weapon_names must be a list"):
        _payload_string_tuple({"weapon_names": "Bolt of Change"}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="payload weapon_names must contain strings"):
        _payload_string_tuple({"weapon_names": [1]}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="must not duplicate values"):
        _payload_string_tuple({"weapon_names": ["Bolt", "Bolt"]}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        _payload_string_tuple({"weapon_names": []}, key="weapon_names")

    bolt_profile = weapon_profile_by_name(package.army_catalog, "Bolt of Change")
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id="phase17k-target-unit",
        weapon_profile=bolt_profile,
    )
    for effect in (
        phase17k_named_choice_effect(
            effect_id="phase17k-non-object-payload",
            unit=unit,
            owner_player_id=army.player_id,
            payload=None,
        ),
        phase17k_named_choice_effect(
            effect_id="phase17k-other-effect-kind",
            unit=unit,
            owner_player_id=army.player_id,
            payload={"effect_kind": "other"},
        ),
        phase17k_named_choice_effect(
            effect_id="phase17k-other-target-model",
            unit=unit,
            owner_player_id=army.player_id,
            payload={
                "effect_kind": CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
                "target_model_instance_ids": ["other-model"],
                "weapon_names": ["Bolt of Change"],
                "keyword": "Lethal Hits",
            },
        ),
        phase17k_named_choice_effect(
            effect_id="phase17k-other-weapon",
            unit=unit,
            owner_player_id=army.player_id,
            payload={
                "effect_kind": CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
                "target_model_instance_ids": [unit.own_models[0].model_instance_id],
                "weapon_names": ["Other Weapon"],
                "keyword": "Lethal Hits",
            },
        ),
    ):
        state.record_persisting_effect(effect)
    assert _selected_catalog_named_weapon_ability_grants(context) == ()

    with pytest.raises(GameLifecycleError, match="weapon ability value must be positive or D3"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-value",
            selection_option_id="option",
            selection_option_index=1,
            keyword=WeaponKeyword.SUSTAINED_HITS,
            weapon_ability_value="D6",
            ability=None,
            effect_index=0,
        )
    with pytest.raises(GameLifecycleError, match="must be a positive integer"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-index",
            selection_option_id="option",
            selection_option_index=0,
            keyword=WeaponKeyword.LETHAL_HITS,
            weapon_ability_value=None,
            ability=None,
            effect_index=0,
        )
    with pytest.raises(GameLifecycleError, match="ability must be a descriptor"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-ability",
            selection_option_id="option",
            selection_option_index=1,
            keyword=WeaponKeyword.LETHAL_HITS,
            weapon_ability_value=None,
            ability=cast(AbilityDescriptor, object()),
            effect_index=0,
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-effect-index",
            selection_option_id="option",
            selection_option_index=1,
            keyword=WeaponKeyword.LETHAL_HITS,
            weapon_ability_value=None,
            ability=None,
            effect_index=-1,
        )


def test_phase17k_catalog_weapon_keyword_grant_helpers_cover_scopes_and_values() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    record = {record.definition.name: record for record in player_index.all_records()}[
        "Pack Killers"
    ]
    replay_payload = record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    clause = rule_ir.clauses[0]
    melee_profile = next(
        wargear.weapon_profiles[0]
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id == "test-advance-charge-unit:swift-claws"
    )
    ranged_profile = replace(
        melee_profile,
        profile_id=f"{melee_profile.profile_id}:helper-ranged-copy",
        range_profile=RangeProfile.distance(12),
    )
    grant = CatalogWeaponKeywordGrant(
        source_id="phase17k-helper-grant",
        keyword=cast(WeaponKeyword, "Lance"),
        weapon_scope="all",
    )
    updated_profile = _profile_with_catalog_weapon_keyword_grant(
        profile=melee_profile,
        grant=grant,
    )

    assert _catalog_weapon_keyword_grant_from_effect(
        record=record,
        unit=unit,
        clause=clause,
        effect_index=0,
        effect=clause.effects[0],
    ) == CatalogWeaponKeywordGrant(
        source_id=f"{record.record_id}:{clause.clause_id}:effect-000:weapon-keyword",
        keyword=WeaponKeyword.LETHAL_HITS,
        weapon_scope="melee",
        ability=AbilityDescriptor.lethal_hits(),
        source_unit_instance_id=unit.unit_instance_id,
        requires_source_leading=True,
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=1,
            effect=rule_effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="hit", delta=1),
        )
        is None
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=1,
            effect=rule_effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_scope="melee"),
        )
        is None
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=1,
            effect=rule_effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_ability="Lethal Hits"),
        )
        is None
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=1,
            effect=rule_effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Sustained Hits",
                weapon_scope="all",
            ),
        )
        is None
    )
    assert _weapon_keyword_grant_consumer_ids_for_effect(
        rule_effect(
            RuleEffectKind.GRANT_WEAPON_ABILITY,
            weapon_ability="Sustained Hits",
            weapon_ability_value=1,
            weapon_scope="all",
        )
    ) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    )
    assert (
        _weapon_keyword_grant_consumer_ids_for_effect(
            rule_effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Hunter",
                weapon_scope="all",
            )
        )
        == ()
    )
    assert grant.keyword is WeaponKeyword.LANCE
    assert grant.weapon_scope == "all"
    assert WeaponKeyword.LANCE in updated_profile.keywords
    assert grant.source_id in updated_profile.source_ids
    assert (
        _profile_with_catalog_weapon_keyword_grant(profile=updated_profile, grant=grant)
        is updated_profile
    )
    assert _weapon_scope_matches_profile(weapon_scope="all", profile=melee_profile)
    assert _weapon_scope_matches_profile(weapon_scope="melee", profile=melee_profile)
    assert not _weapon_scope_matches_profile(weapon_scope="ranged", profile=melee_profile)
    assert _weapon_scope_matches_profile(weapon_scope="ranged", profile=ranged_profile)
    assert not _weapon_scope_matches_profile(weapon_scope="melee", profile=ranged_profile)
    for keyword, parameters, expected_kind in (
        (WeaponKeyword.DEVASTATING_WOUNDS, {}, AbilityKind.DEVASTATING_WOUNDS),
        (WeaponKeyword.HEAVY, {}, AbilityKind.HEAVY),
        (WeaponKeyword.SUSTAINED_HITS, {"weapon_ability_value": 1}, AbilityKind.SUSTAINED_HITS),
        (WeaponKeyword.RAPID_FIRE, {"weapon_ability_value": 2}, AbilityKind.RAPID_FIRE),
        (WeaponKeyword.MELTA, {"weapon_ability_value": 3}, AbilityKind.MELTA),
        (WeaponKeyword.CLEAVE, {"weapon_ability_value": 4}, AbilityKind.CLEAVE),
    ):
        descriptor = _weapon_ability_descriptor_for_grant(
            parameters=parameters,
            keyword=keyword,
        )
        assert descriptor is not None
        assert descriptor.ability_kind is expected_kind
    assert _weapon_ability_descriptor_for_grant(parameters={}, keyword=WeaponKeyword.LANCE) is None
    runtime = CatalogWeaponKeywordGrantRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogWeaponKeywordGrantRuntime(ability_indexes_by_player_id={}, armies=(army,))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.weapon_profile_modifier(cast(WeaponProfileModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="unit is unknown"):
        runtime.weapon_profile_modifier(
            WeaponProfileModifierContext(
                state=battle_state_with_army(
                    army=army,
                    battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
                ),
                source_phase=BattlePhase.FIGHT,
                attacking_unit_instance_id="phase17k-unknown-unit",
                attacker_model_instance_id=unit.own_models[0].model_instance_id,
                target_unit_instance_id="phase17k-target-unit",
                weapon_profile=melee_profile,
            )
        )
    with pytest.raises(GameLifecycleError, match="ability must be a descriptor"):
        CatalogWeaponKeywordGrant(
            source_id="phase17k-bad-ability-grant",
            keyword=WeaponKeyword.LANCE,
            weapon_scope="all",
            ability=cast(AbilityDescriptor, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _catalog_weapon_keyword_grant_from_effect(
            record=cast(AbilityCatalogRecord, object()),
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            unit=unit,
            clause=cast(RuleClause, object()),
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=-1,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule effect"):
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=cast(RuleEffectSpec, object()),
        )
    with pytest.raises(GameLifecycleError, match="unsupported keyword"):
        _weapon_keyword_grant_consumer_ids_for_effect(
            rule_effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Bad Keyword",
                weapon_scope="all",
            )
        )
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _weapon_keyword_grant_consumer_ids_for_effect(cast(RuleEffectSpec, object()))
    with pytest.raises(GameLifecycleError, match="cannot infer Hunter targets"):
        _weapon_ability_descriptor_for_grant(parameters={}, keyword=WeaponKeyword.HUNTER)
    with pytest.raises(GameLifecycleError, match="positive or D3"):
        _weapon_ability_descriptor_for_grant(
            parameters={},
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    with pytest.raises(GameLifecycleError, match="positive or D3"):
        _weapon_ability_descriptor_for_grant(
            parameters={"weapon_ability_value": 0},
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    with pytest.raises(GameLifecycleError, match="requires a WeaponProfile"):
        _profile_with_catalog_weapon_keyword_grant(
            profile=cast(WeaponProfile, object()),
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="requires grant data"):
        _profile_with_catalog_weapon_keyword_grant(
            profile=melee_profile,
            grant=cast(CatalogWeaponKeywordGrant, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires a WeaponProfile"):
        _weapon_scope_matches_profile(
            weapon_scope="all",
            profile=cast(WeaponProfile, object()),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported catalog weapon keyword grant scope"):
        _weapon_scope_matches_profile(weapon_scope="bad scope", profile=melee_profile)
    with pytest.raises(GameLifecycleError, match="Unsupported catalog weapon keyword grant scope"):
        _weapon_scope_matches_profile(weapon_scope="ranged weapons", profile=ranged_profile)
