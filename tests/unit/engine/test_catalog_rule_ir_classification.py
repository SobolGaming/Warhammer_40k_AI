# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import cast

import pytest
from tests.support.catalog_package_fixtures import bloodcrushers_package
from tests.support.catalog_rule_ir_fixtures import (
    ability_coverage_category_row,
    ability_coverage_row,
    ability_datasheet_pair,
    catalog_rule_ir,
    effect,
)
from tests.support.catalog_runtime_fixtures import SOURCE_KEYWORD_SEQUENCE_PARTS
from tests.support.wahapedia_bridge_fixtures import (
    undivided_daemon_bridge_artifacts,
)
from tests.support.wahapedia_source_fixtures import (
    bridge_package_id,
    catalog_package_id,
    catalog_version,
    unsupported_wargear_rule_source_artifacts,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometrySourceUnits,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageAbilityDatasheetPair,
    AbilityCoverageCategoryRow,
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_from_catalog,
    ability_coverage_rows_payload,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID,
    CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID,
    CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID,
    CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
    _effect_is_roll_reroll_permission,
    _roll_reroll_consumer_id_for_effect,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    catalog_rule_ir_registered_hook_ids,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
)
from warhammer40k_core.engine.phases.movement import (
    _ability_index_for_player,
    _validate_ability_index_mapping,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)


def test_phase17k_undivided_daemon_datasheet_rule_ir_is_fully_consumed() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=undivided_daemon_bridge_artifacts(),
    )
    expected_consumers_by_ability_name = {
        "DAEMONIC ALLEGIANCE": ("army-mustering:required-datasheet-option",),
        "Daemon Prince of Khorne": ("catalog-ir:strength-characteristic-modifier",),
        "Daemon Prince of Tzeentch": ("catalog-ir:attacks-characteristic-modifier",),
        "Daemon Prince of Nurgle": ("catalog-ir:toughness-characteristic-modifier",),
        "Daemon Prince of Slaanesh": ("catalog-ir:movement-characteristic-modifier",),
        "Daemonic Lord": ("catalog-ir:conditional-ability:lone-operative",),
        "Prince of Darkness (Aura)": ("catalog-ir:aura-ability:stealth",),
        "Unholy Vigour": (CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,),
        "Malefic Destruction": (CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,),
        "Harbinger of Death": (
            "catalog-ir:fight-selected-weapon-ability-choice",
            CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
            "catalog-ir:weapon-keyword-grant:lethal-hits",
            "catalog-ir:weapon-keyword-grant:precision",
            "catalog-ir:weapon-keyword-grant:sustained-hits",
        ),
        "Scuttling Walker": ("catalog-ir:movement-transit-permission",),
    }

    for datasheet_id in ("000001149", "000002758", "000001151"):
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        datasheet_abilities = tuple(
            ability
            for ability in datasheet.abilities
            if ability.source_kind is CatalogAbilitySourceKind.DATASHEET
        )
        assert datasheet_abilities
        for ability in datasheet_abilities:
            assert ability.support is CatalogAbilitySupport.GENERIC_RULE_IR
            assert ability.rule_ir_payload is not None
            rule_ir = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
            assert rule_ir.is_supported
            assert rule_ir.diagnostics == ()
            assert (
                catalog_rule_ir_consumers_for_rule(rule_ir)
                == (expected_consumers_by_ability_name[ability.name])
            )
            if ability.name == "DAEMONIC ALLEGIANCE":
                parameters = parameter_payload(rule_ir.clauses[0].effects[0].parameters)
                assert set(cast(tuple[str, ...], parameters["selection_option_ids"])) == {
                    option.option_id for option in datasheet.mustering_options
                }


def test_phase17k_catalog_ir_roll_reroll_classification_requires_supported_target() -> None:
    this_unit_rule = catalog_rule_ir(
        (
            effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance"),
            effect(RuleEffectKind.REROLL_PERMISSION, roll_type="charge"),
        ),
        target_kind=RuleTargetKind.THIS_UNIT,
    )
    selected_unit_without_leader_rule = catalog_rule_ir(
        (effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance"),),
        target_kind=RuleTargetKind.SELECTED_UNIT,
    )
    aura_attack_reroll_rule = catalog_rule_ir(
        (
            effect(
                RuleEffectKind.REROLL_PERMISSION,
                roll_type="hit",
                attack_role="attacker",
            ),
            effect(
                RuleEffectKind.REROLL_PERMISSION,
                roll_type="advance",
                attack_role="attacker",
            ),
        ),
        target_kind=RuleTargetKind.AURA_UNITS,
    )
    damage_roll_rule = catalog_rule_ir(
        (effect(RuleEffectKind.REROLL_PERMISSION, roll_type="damage"),),
        target_kind=RuleTargetKind.THIS_UNIT,
    )

    assert catalog_rule_ir_consumers_for_rule(this_unit_rule) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(this_unit_rule)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert catalog_rule_ir_consumers_for_rule(selected_unit_without_leader_rule) == ()
    assert catalog_rule_ir_consumers_for_rule(aura_attack_reroll_rule) == (
        CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(damage_roll_rule) == (
        CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(damage_roll_rule) == (
        CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID,
    )


def test_phase17k_catalog_ir_roll_reroll_effect_helpers_are_strict() -> None:
    advance_effect = effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance")
    charge_effect = effect(RuleEffectKind.REROLL_PERMISSION, roll_type="charge")
    non_reroll_effect = effect(RuleEffectKind.GRANT_ABILITY, ability="can_advance_and_charge")
    malformed_effect = effect(RuleEffectKind.REROLL_PERMISSION, roll_type=1)

    assert _effect_is_roll_reroll_permission(advance_effect, roll_type="advance_roll")
    assert not _effect_is_roll_reroll_permission(advance_effect, roll_type="charge_roll")
    assert not _effect_is_roll_reroll_permission(non_reroll_effect, roll_type="advance_roll")
    assert not _effect_is_roll_reroll_permission(malformed_effect, roll_type="advance_roll")
    assert (
        _roll_reroll_consumer_id_for_effect(advance_effect)
        == CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID
    )
    assert (
        _roll_reroll_consumer_id_for_effect(charge_effect)
        == CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID
    )
    assert _roll_reroll_consumer_id_for_effect(non_reroll_effect) is None
    assert _roll_reroll_consumer_id_for_effect(malformed_effect) is None
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _effect_is_roll_reroll_permission(
            cast(RuleEffectSpec, object()),
            roll_type="advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _roll_reroll_consumer_id_for_effect(cast(RuleEffectSpec, object()))


def test_phase17k_catalog_ir_shadow_of_chaos_aura_classifies_contextual_status() -> None:
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17k:test:shadow-of-chaos-aura",
            raw_text=(
                "Daemonic Shadow (Aura): While a friendly Khorne Legiones Daemonica unit "
                'is within 6" of this model, that unit is within your army\u2019s Shadow of Chaos.'
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir

    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    }
    assert CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID in set(catalog_rule_ir_registered_hook_ids())


def test_phase17k_movement_phase_ability_index_mapping_is_fail_fast() -> None:
    index = AbilityCatalogIndex.from_records(())
    validated = _validate_ability_index_mapping({"player-a": index})
    present_index = _ability_index_for_player(validated, player_id="player-a")
    missing_index = _ability_index_for_player(validated, player_id="player-b")

    assert validated["player-a"] is index
    assert present_index is index
    assert tuple(missing_index.all_records()) == ()
    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        _validate_ability_index_mapping(("player-a", index))
    with pytest.raises(GameLifecycleError, match="values must be AbilityCatalogIndex"):
        _validate_ability_index_mapping({"player-a": cast(AbilityCatalogIndex, object())})
    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        _ability_index_for_player(("player-a", index), player_id="player-a")
    with pytest.raises(GameLifecycleError, match="contained an invalid value"):
        _ability_index_for_player(
            {"player-a": cast(AbilityCatalogIndex, object())},
            player_id="player-a",
        )


def test_phase17k_ability_coverage_api_fails_fast_and_classifies_unsupported_ir() -> None:
    package = bloodcrushers_package()
    unsupported_package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=unsupported_wargear_rule_source_artifacts(),
            bridge_package_id=bridge_package_id(),
            datasheet_ids=("test-unsupported-unit",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="test-unsupported-unit",
                    model_name="Alpha",
                    height=1.0,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="test-source:unsupported-height",
                    height_document_reference="test-doc:unsupported-height",
                ),
            ),
        ),
    )
    unsupported_rows = ability_coverage_rows_from_catalog(
        unsupported_package.army_catalog,
        datasheet_ids=("test-unsupported-unit",),
    )
    rows_by_name = {row.ability_name: row for row in unsupported_rows}
    scatter = rows_by_name["Scatter Icon"]
    broken_instrument = rows_by_name["Broken Instrument"]
    hit_charm = rows_by_name["Hit Charm"]
    tithe_charm = rows_by_name["Tithe Charm"]

    assert (
        ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=("not-a-datasheet",),
        )
        == ()
    )
    assert scatter.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    assert scatter.diagnostic_reasons == ("unsupported_language",)
    assert scatter.semantic_categories == ("wargear.unsupported.unsupported_language",)
    assert broken_instrument.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    assert broken_instrument.runtime_consumer_ids == ("catalog-ir:charge-roll-modifier",)
    assert broken_instrument.semantic_categories == (
        "wargear.roll_modifier.charge.this_unit",
        "wargear.unsupported.unsupported_language",
    )
    assert hit_charm.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    assert hit_charm.semantic_categories == ("wargear.roll_modifier.hit.this_unit",)
    assert tithe_charm.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    assert tithe_charm.semantic_categories == ("wargear.rule_ir.modify_command_points.unscoped",)
    with pytest.raises(GameLifecycleError, match="requires an ArmyCatalog"):
        ability_coverage_rows_from_catalog(cast(ArmyCatalog, object()))
    with pytest.raises(GameLifecycleError, match="datasheet_ids must be a tuple"):
        ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=cast(tuple[str, ...], ["000001115"]),
        )
    with pytest.raises(GameLifecycleError, match="rows must be a tuple"):
        ability_coverage_rows_payload(cast(tuple[AbilityCoverageRow, ...], []))
    with pytest.raises(GameLifecycleError, match="rows must be a tuple"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], []))
    with pytest.raises(GameLifecycleError, match="require coverage rows"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="category rows must be a tuple"):
        ability_coverage_category_rows_payload(cast(tuple[AbilityCoverageCategoryRow, ...], []))
    with pytest.raises(GameLifecycleError, match="require category rows"):
        ability_coverage_category_rows_payload(
            cast(tuple[AbilityCoverageCategoryRow, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="catalog_id"):
        ability_coverage_row(catalog_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_id"):
        ability_coverage_row(datasheet_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_name"):
        ability_coverage_row(datasheet_name="")
    with pytest.raises(GameLifecycleError, match="ability_id"):
        ability_coverage_row(ability_id="")
    with pytest.raises(GameLifecycleError, match="ability_name"):
        ability_coverage_row(ability_name="")
    with pytest.raises(GameLifecycleError, match="source_kind"):
        ability_coverage_row(source_kind=cast(CatalogAbilitySourceKind, "bad"))
    with pytest.raises(GameLifecycleError, match="source_wargear_id"):
        ability_coverage_row(source_wargear_id="")
    with pytest.raises(GameLifecycleError, match="catalog_support"):
        ability_coverage_row(catalog_support=cast(CatalogAbilitySupport, "bad"))
    with pytest.raises(GameLifecycleError, match="support_stage"):
        ability_coverage_row(support_stage=cast(AbilityCoverageSupportStage, "bad"))
    with pytest.raises(GameLifecycleError, match="semantic_categories"):
        ability_coverage_row(semantic_categories=("",))
    with pytest.raises(GameLifecycleError, match="runtime_consumer_ids"):
        ability_coverage_row(runtime_consumer_ids=cast(tuple[str, ...], []))
    with pytest.raises(GameLifecycleError, match="diagnostic_reasons"):
        ability_coverage_row(diagnostic_reasons=("",))
    with pytest.raises(GameLifecycleError, match="coverage_row_id"):
        ability_datasheet_pair(coverage_row_id="")
    with pytest.raises(GameLifecycleError, match="ability_id"):
        ability_datasheet_pair(ability_id="")
    with pytest.raises(GameLifecycleError, match="ability_name"):
        ability_datasheet_pair(ability_name="")
    with pytest.raises(GameLifecycleError, match="datasheet_id"):
        ability_datasheet_pair(datasheet_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_name"):
        ability_datasheet_pair(datasheet_name="")
    with pytest.raises(GameLifecycleError, match="source_kind"):
        ability_datasheet_pair(source_kind=cast(CatalogAbilitySourceKind, "bad"))
    with pytest.raises(GameLifecycleError, match="category_id"):
        ability_coverage_category_row(category_id="")
    with pytest.raises(GameLifecycleError, match="category_name"):
        ability_coverage_category_row(category_name="")
    with pytest.raises(GameLifecycleError, match="coverage_row_count"):
        ability_coverage_category_row(coverage_row_count=0)
    with pytest.raises(GameLifecycleError, match="coverage_row_ids"):
        ability_coverage_category_row(coverage_row_ids=())
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must be a tuple"):
        ability_coverage_category_row(
            ability_datasheet_pairs=cast(tuple[AbilityCoverageAbilityDatasheetPair, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must match"):
        ability_coverage_category_row(ability_datasheet_pairs=())
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must contain"):
        ability_coverage_category_row(
            ability_datasheet_pairs=cast(
                tuple[AbilityCoverageAbilityDatasheetPair, ...],
                (object(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts must be a tuple"):
        ability_coverage_category_row(source_kind_counts=cast(tuple[tuple[str, int], ...], []))
    with pytest.raises(GameLifecycleError, match="source_kind_counts entries must be pairs"):
        ability_coverage_category_row(source_kind_counts=cast(tuple[tuple[str, int], ...], ((),)))
    with pytest.raises(GameLifecycleError, match="source_kind_counts keys must be strings"):
        ability_coverage_category_row(
            source_kind_counts=cast(tuple[tuple[str, int], ...], ((1, 1),))
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts keys must be unique"):
        ability_coverage_category_row(
            coverage_row_count=2,
            coverage_row_ids=("test-row-1", "test-row-2"),
            ability_datasheet_pairs=(
                ability_datasheet_pair(coverage_row_id="test-row-1"),
                ability_datasheet_pair(coverage_row_id="test-row-2"),
            ),
            source_kind_counts=(("wargear", 1), ("wargear", 1)),
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts values"):
        ability_coverage_category_row(source_kind_counts=(("wargear", 0),))
    with pytest.raises(GameLifecycleError, match="source_kind_counts must match"):
        ability_coverage_category_row(source_kind_counts=(("wargear", 2),))
    with pytest.raises(GameLifecycleError, match="support_stages"):
        ability_coverage_category_row(
            support_stages=cast(tuple[AbilityCoverageSupportStage, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="support_stages"):
        ability_coverage_category_row(
            support_stages=cast(tuple[AbilityCoverageSupportStage, ...], ("bad",))
        )


def test_phase17k_catalog_ir_future_hooks_classify_supported_rule_ir_without_consuming() -> None:
    registered_hook_ids = set(catalog_rule_ir_registered_hook_ids())
    rule_ir = catalog_rule_ir(
        (
            effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="hit", delta=1),
            effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="wound", delta=1),
            effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="invulnerable_save", delta=1),
            effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="critical_hit", delta=-1),
            effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance_roll"),
            effect(RuleEffectKind.REROLL_PERMISSION, roll_type="charge_roll"),
            effect(
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                characteristic=Characteristic.TOUGHNESS.value,
                delta=-1,
            ),
            effect(
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                characteristic=Characteristic.OBJECTIVE_CONTROL.value,
                delta=-1,
            ),
            effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_ability="Lethal Hits"),
            effect(RuleEffectKind.GRANT_ABILITY, ability="can_advance_and_charge"),
            effect(RuleEffectKind.GRANT_ABILITY, ability="Feel No Pain", threshold=3),
            effect(RuleEffectKind.PLACEMENT_PERMISSION, placement_kind="turn_end_reserves"),
        ),
        target_kind=RuleTargetKind.ENEMY_UNIT,
    )

    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) >= {
        CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID,
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
        "catalog-ir:toughness-characteristic-modifier",
        "catalog-ir:objective-control-characteristic-modifier",
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    }
    assert registered_hook_ids >= {
        CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
        CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID,
        CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
        CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID,
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
        "catalog-ir:movement-characteristic-query",
        "catalog-ir:toughness-characteristic-query",
        "catalog-ir:objective-control-characteristic-query",
        "catalog-ir:wounds-characteristic-query",
        "catalog-ir:attacks-characteristic-query",
        "catalog-ir:armor-penetration-characteristic-query",
        "catalog-ir:ballistic-skill-characteristic-query",
        "catalog-ir:weapon-skill-characteristic-query",
        "catalog-ir:strength-characteristic-query",
        "catalog-ir:damage-characteristic-query",
        "catalog-ir:range-characteristic-query",
        "catalog-ir:weapon-keyword-grant:devastating-wounds",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == ()
