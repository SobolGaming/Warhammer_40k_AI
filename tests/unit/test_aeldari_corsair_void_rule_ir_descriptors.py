from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_rule_consumption import (
    CatalogWeaponKeywordGrantRuntime,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
)
from warhammer40k_core.engine.catalog_tracked_target_runtime import CatalogTrackedTargetRuntime
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
)
from warhammer40k_core.engine.unit_factory import UnitFactory
from warhammer40k_core.rules.rule_ir import RuleIR, RuleParameter
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_corsair_void_units_2026_06 as void_units_package,
)

VOIDREAVERS_ID = "000002531"
VOIDSCARRED_ID = "000002532"
VOIDREAVER_PROFILE_ID = f"{VOIDREAVERS_ID}:corsair-voidreavers"
VOIDREAVER_FELARCH_PROFILE_ID = f"{VOIDREAVERS_ID}:voidreaver-felarch"
VOIDSCARRED_PROFILE_ID = f"{VOIDSCARRED_ID}:corsair-voidscarred"
VOIDSCARRED_FELARCH_PROFILE_ID = f"{VOIDSCARRED_ID}:voidscarred-felarch"


@pytest.mark.parametrize(
    ("source_row_id", "mutation"),
    [
        ("000002531:3", "unexpected_effect_parameter"),
        ("000002531:3", "incompatible_attack_role"),
        ("000002531:3", "weapon_scope"),
        ("000002531:4", "target_parameter"),
        ("000002532:4", "trigger_parameter"),
        ("000002532:4", "frequency_parameter"),
    ],
)
def test_void_unit_exact_runtime_shapes_reject_unconsumed_parameters(
    source_row_id: str,
    mutation: str,
) -> None:
    rule_ir = _rule_ir(source_row_id)
    clause = rule_ir.clauses[0]
    if mutation in {
        "unexpected_effect_parameter",
        "incompatible_attack_role",
        "weapon_scope",
    }:
        parameter = {
            "unexpected_effect_parameter": RuleParameter("phase_restriction", "shooting"),
            "incompatible_attack_role": RuleParameter("attack_role", "target"),
            "weapon_scope": RuleParameter("weapon_scope", "ranged"),
        }[mutation]
        clause = replace(
            clause,
            effects=(
                replace(
                    clause.effects[0],
                    parameters=(*clause.effects[0].parameters, parameter),
                ),
            ),
        )
    elif mutation == "target_parameter":
        assert clause.target is not None
        clause = replace(
            clause,
            target=replace(
                clause.target,
                parameters=(RuleParameter("model_role", "bearer"),),
            ),
        )
    elif mutation == "trigger_parameter":
        assert clause.trigger is not None
        clause = replace(
            clause,
            trigger=replace(
                clause.trigger,
                parameters=(*clause.trigger.parameters, RuleParameter("phase", "shooting")),
            ),
        )
    else:
        condition = clause.conditions[0]
        clause = replace(
            clause,
            conditions=(
                replace(
                    condition,
                    parameters=(*condition.parameters, RuleParameter("reset", "phase")),
                ),
            ),
        )
    mutated_rule_ir = replace(rule_ir, clauses=(clause,))

    assert catalog_rule_ir_consumers_for_rule(mutated_rule_ir) == ()
    assert catalog_rule_ir_hook_ids_for_rule(mutated_rule_ir) == ()

    catalog, army = _catalog_and_army()
    source_record = next(
        record
        for record in catalog_ability_records_from_catalog(catalog)
        if cast(dict[str, Any], record.definition.replay_payload).get("rule_ir")
        == rule_ir.to_payload()
    )
    replay_payload = cast(dict[str, Any], source_record.definition.replay_payload)
    mutated_record = replace(
        source_record,
        definition=replace(
            source_record.definition,
            replay_payload=cast(
                Any,
                {**replay_payload, "rule_ir": mutated_rule_ir.to_payload()},
            ),
        ),
    )
    runtime = CatalogDatasheetRuleRuntime(
        {"player-a": AbilityCatalogIndex.from_records((mutated_record,))},
        (army,),
    )

    assert runtime.save_option_modifier_bindings() == ()
    assert runtime.attack_reroll_permission_bindings() == ()
    assert runtime.failed_save_damage_replacement_bindings() == ()


@pytest.mark.parametrize(
    ("clause_index", "mutation", "runtime_kind"),
    [
        (0, RuleParameter("phase_restriction", "setup"), "selection"),
        (1, RuleParameter("attack_role", "target"), "weapon_grant"),
    ],
)
def test_piratical_exact_shapes_reject_ignored_selection_and_grant_parameters(
    clause_index: int,
    mutation: RuleParameter,
    runtime_kind: str,
) -> None:
    rule_ir = _rule_ir("000002532:3")
    clause = rule_ir.clauses[clause_index]
    if runtime_kind == "selection":
        assert clause.trigger is not None
        clause = replace(
            clause,
            trigger=replace(
                clause.trigger,
                parameters=(*clause.trigger.parameters, mutation),
            ),
        )
    else:
        clause = replace(
            clause,
            effects=(
                replace(
                    clause.effects[0],
                    parameters=(*clause.effects[0].parameters, mutation),
                ),
            ),
        )
    mutated_rule_ir = replace(rule_ir, clauses=(clause,))

    assert catalog_rule_ir_consumers_for_rule(mutated_rule_ir) == ()
    assert catalog_rule_ir_hook_ids_for_rule(mutated_rule_ir) == ()

    catalog, army = _catalog_and_army()
    source_record = next(
        record
        for record in catalog_ability_records_from_catalog(catalog)
        if cast(dict[str, Any], record.definition.replay_payload).get("runtime_clause_id")
        == rule_ir.clauses[clause_index].clause_id
    )
    replay_payload = cast(dict[str, Any], source_record.definition.replay_payload)
    mutated_record = replace(
        source_record,
        definition=replace(
            source_record.definition,
            replay_payload=cast(
                Any,
                {**replay_payload, "rule_ir": mutated_rule_ir.to_payload()},
            ),
        ),
    )
    index = AbilityCatalogIndex.from_records((mutated_record,))

    if runtime_kind == "selection":
        assert (
            CatalogTrackedTargetRuntime({"player-a": index}, (army,)).battle_formation_bindings()
            == ()
        )
    else:
        assert CatalogWeaponKeywordGrantRuntime({"player-a": index}, (army,)).bindings() == ()


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = void_units_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _catalog_and_army() -> tuple[Any, ArmyDefinition]:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    voidreavers = factory.instantiate_unit(
        army_id="army-a",
        datasheet=catalog.datasheet_by_id(VOIDREAVERS_ID),
        selection=UnitMusterSelection(
            unit_selection_id="voidreavers",
            datasheet_id=VOIDREAVERS_ID,
            model_profile_selections=(
                ModelProfileSelection(VOIDREAVER_PROFILE_ID, 4),
                ModelProfileSelection(VOIDREAVER_FELARCH_PROFILE_ID, 1),
            ),
        ),
    )
    voidscarred = factory.instantiate_unit(
        army_id="army-a",
        datasheet=catalog.datasheet_by_id(VOIDSCARRED_ID),
        selection=UnitMusterSelection(
            unit_selection_id="voidscarred",
            datasheet_id=VOIDSCARRED_ID,
            model_profile_selections=(
                ModelProfileSelection(VOIDSCARRED_PROFILE_ID, 4),
                ModelProfileSelection(VOIDSCARRED_FELARCH_PROFILE_ID, 1),
                ModelProfileSelection(f"{VOIDSCARRED_ID}:shade-runner", 1),
                ModelProfileSelection(f"{VOIDSCARRED_ID}:soul-weaver", 1),
                ModelProfileSelection(f"{VOIDSCARRED_ID}:way-seeker", 1),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=f"{VOIDSCARRED_ID}:mistshield:option-3",
                    model_profile_id=VOIDSCARRED_FELARCH_PROFILE_ID,
                    wargear_ids=(f"{VOIDSCARRED_ID}:mistshield",),
                ),
            ),
        ),
    )
    return catalog, ArmyDefinition(
        army_id="army-a",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=catalog.factions[0].faction_id,
            detachment_ids=("void-rule-ir-descriptor-test",),
        ),
        units=(voidreavers, voidscarred),
    )
