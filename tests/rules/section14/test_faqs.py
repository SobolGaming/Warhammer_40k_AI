"""Co-located objective FAQs, source boundary and production policy integration."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section13_fixtures import feature
from tests.support.section14_boundaries import boundary_case, move_checkpoint
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.attack_sequence_dice_rerolls import (
    _conditional_wound_full_reroll_applies,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import AttackRerollPermissionContext
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_data import RuleSourceText


@pytest.mark.parametrize("scope", list(ObjectiveRuleScope))
def test_faq58_marker_alias_is_applied_only_at_non_core_source_boundary(
    scope: ObjectiveRuleScope,
) -> None:
    raw = "This unit is within range of an objective marker you control."
    source = RuleSourceText.from_raw(
        source_id="constructed:s14:alias", raw_text=raw, objective_scope=scope
    )
    assert ("objective marker" not in source.normalized_text) is (
        scope is ObjectiveRuleScope.NON_CORE_RULES
    )
    assert source.raw_text == raw
    assert RuleSourceText.from_payload(source.to_payload()) == source


@pytest.mark.parametrize("terrain", [False, True])
@pytest.mark.parametrize("within", [False, True])
def test_faq43_and_58_native_infractor_producer_reaches_actual_objective_reroll_gate(
    section14_definitions: Section02Definitions,
    terrain: bool,
    within: bool,
) -> None:
    state, unit, enemy = boundary_case(
        section14_definitions, sheet="000004080", phase=BattlePhase.FIGHT
    )
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    marker = state.mission_setup.objective_markers[0]
    x = marker.x_inches + (0 if within else 12)
    move_checkpoint(state, enemy, x, marker.y_inches)
    if terrain:
        declared = feature(x=marker.x_inches, y=marker.y_inches, width=8, depth=8)
        state.mission_setup = replace(state.mission_setup, terrain_features=(declared,))
        state.replace_battlefield_state(
            replace(state.battlefield_state, terrain_features=(declared,))
        )
    records = tuple(
        r
        for r in catalog_ability_records_from_catalog(section14_definitions.package.army_catalog)
        if r.definition.source_id in {a.source_id for a in unit.datasheet_abilities}
    )
    runtime = CatalogDatasheetRuleRuntime(
        {
            "owner": AbilityCatalogIndex.from_records(records),
            "opponent": AbilityCatalogIndex.from_records(()),
        },
        tuple(state.army_definitions),
    )
    ctx = AttackRerollPermissionContext(
        state=state,
        player_id="owner",
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_model_ids()[0],
        target_unit_instance_id=enemy.unit_instance_id,
        source_phase=BattlePhase.FIGHT,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
    )
    permissions = tuple(
        p for b in runtime.attack_reroll_permission_bindings() if (p := b.handler(ctx)) is not None
    )
    assert len(permissions) == 1
    conditional = permissions[0].source_payload["conditional_wound_reroll"]
    assert isinstance(conditional, dict)
    assert conditional["full_reroll_if_target_within_objective_range"] is True
    assert (
        _conditional_wound_full_reroll_applies(
            state=state,
            conditional=conditional,
            target_unit_instance_id=enemy.unit_instance_id,
            attacker_keywords=unit.keywords,
        )
        is within
    )
