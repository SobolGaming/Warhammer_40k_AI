"""19.04/FAQ64: native model rule at a declared Core attachment boundary.

Spiritseer Support membership is constructed, not native provider/roster admission.
The native rule and the nearby native Wraithblades are unchanged.
"""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section09_fixtures import add_unit
from tests.support.section19_fixtures import PSYKER, WRAITHBLADES, attached_scene
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.model_ability_grants import ModelAbilityGrantContext
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("other_alive", [False, True])
def test_native_model_lone_operative_keeps_exact_recipients_and_targeting_scope(
    section19_definitions: Section02Definitions,
    other_alive: bool,
) -> None:
    d = section19_definitions
    s = attached_scene(d, support=True)
    assert s.support is not None
    escort = d.unit(WRAITHBLADES, identity="escort")
    add_unit(
        s.state, escort, tuple(Pose.at(10 + i * 1.7, 14) for i in range(len(escort.own_models)))
    )
    assert s.state.battlefield_state is not None
    s.state.replace_battlefield_state(
        s.state.battlefield_state.with_unit_placement(
            placement(s.enemy, (Pose.at(40, 10),), enemy=True)
        )
    )
    if not other_alive:
        s.set_living("bodyguard", 0)
        s.set_living("leader", 0)
    records = catalog_ability_records_from_catalog(d.package.army_catalog)
    runtime = CatalogDatasheetRuleRuntime(
        {p: AbilityCatalogIndex.from_records(records) for p in s.state.player_ids},
        tuple(s.state.army_definitions),
    )
    descriptor = next(
        a
        for a in d.package.army_catalog.datasheet_by_id(PSYKER).abilities
        if a.ability_id == f"{PSYKER}:spiritseer"
    )
    assert descriptor.rule_ir_payload is not None
    source = descriptor.rule_ir_payload["source_id"]
    grants = tuple(b for b in runtime.model_ability_grant_bindings() if b.source_id == source)
    assert len(grants) == 1
    granted = grants[0].model_ids(ModelAbilityGrantContext(s.state, s.view))
    context = ShootingTargetRestrictionContext(
        state=s.state,
        player_id="opponent",
        battle_round=1,
        attacking_unit_instance_id=s.enemy.unit_instance_id,
        attacker_model_instance_id=s.enemy.own_model_ids()[0],
        target_unit_instance_id=s.view.unit_instance_id,
    )
    restrictions = tuple(
        r
        for b in runtime.shooting_target_restriction_bindings()
        if (r := b.handler(context)) is not None
    )
    assert (granted, bool(restrictions)) == (s.support.own_model_ids(), not other_alive)
    assert granted == s.support.own_model_ids()
    assert bool(restrictions) is (not other_alive)


@pytest.mark.parametrize("enemy_x", [27, 40])
def test_mixed_native_and_conditional_owners_cover_all_models_and_keep_highest_range(
    section19_definitions: Section02Definitions,
    enemy_x: int,
) -> None:
    from tests.support.section05_fixtures import replace_unit
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        DatasheetAbilityDescriptor,
    )

    s = attached_scene(section19_definitions, support=True)
    assert s.support is not None
    s.set_living("leader", 0)
    # Explicit Core native descriptor on bodyguard; no faction grant claim.
    native = DatasheetAbilityDescriptor(
        ability_id="core-lone-operative",
        name="Lone Operative",
        source_id="constructed:s19:bodyguard-lone-operative-15",
        source_kind=CatalogAbilitySourceKind.CORE,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        effect_description="Lone Operative 15 inches",
        parameter_tokens=("15",),
    )
    body = s.component("bodyguard")
    replace_unit(s.state, replace(body, datasheet_abilities=(*body.datasheet_abilities, native)))
    escort = section19_definitions.unit(WRAITHBLADES, identity="escort")
    add_unit(
        s.state, escort, tuple(Pose.at(10 + i * 1.7, 14) for i in range(len(escort.own_models)))
    )
    assert s.state.battlefield_state is not None
    s.state.replace_battlefield_state(
        s.state.battlefield_state.with_unit_placement(
            placement(s.enemy, (Pose.at(enemy_x, 10),), enemy=True)
        )
    )
    records = catalog_ability_records_from_catalog(section19_definitions.package.army_catalog)
    runtime = CatalogDatasheetRuleRuntime(
        {p: AbilityCatalogIndex.from_records(records) for p in s.state.player_ids},
        tuple(s.state.army_definitions),
    )
    ctx = ShootingTargetRestrictionContext(
        state=s.state,
        player_id="opponent",
        battle_round=1,
        attacking_unit_instance_id=s.enemy.unit_instance_id,
        attacker_model_instance_id=s.enemy.own_model_ids()[0],
        target_unit_instance_id=s.view.unit_instance_id,
    )
    restrictions = tuple(
        r
        for b in runtime.shooting_target_restriction_bindings()
        if (r := b.handler(ctx)) is not None
    )
    assert bool(restrictions) is (enemy_x == 40)
