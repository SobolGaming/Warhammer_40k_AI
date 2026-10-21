"""Required positive unit-wide grants and negative source availability controls."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section09_fixtures import add_unit
from tests.support.section19_fixtures import PSYKER, WRAITHBLADES, attached_scene
from warhammer40k_core.core.datasheet import CatalogJsonObject
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.model_ability_grants import ModelAbilityGrantContext
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload, RuleParameter, RuleTargetKind


@pytest.mark.parametrize("whole_unit", [False, True])
@pytest.mark.parametrize("source_available", [False, True])
def test_conditional_unit_and_model_recipients_keep_positive_scope_and_source_lifetime(
    section19_definitions: Section02Definitions,
    whole_unit: bool,
    source_available: bool,
) -> None:
    d = section19_definitions
    native = next(
        a
        for a in d.package.army_catalog.datasheet_by_id(PSYKER).abilities
        if a.ability_id == f"{PSYKER}:spiritseer"
    )
    assert native.rule_ir_payload is not None
    if whole_unit:
        # Explicit typed Core unit-target control, derived from supported native
        # conditional shape. No altered rule is attributed to the datasheet.
        ir = RuleIR.from_payload(cast(RuleIRPayload, native.rule_ir_payload))
        text = native.effect_description.replace(", this model has", ", this unit has")
        clause = ir.clauses[0]
        assert clause.target is not None
        target_start = text.index("this unit")
        ability_start = text.index("Lone Operative ability")
        effect = replace(
            clause.effects[0],
            source_span=TextSpan(
                text="Lone Operative ability", start=ability_start, end=ability_start + 22
            ),
            parameters=(
                RuleParameter("ability", "lone_operative"),
                RuleParameter("target_scope", "this_unit"),
            ),
        )
        clause = replace(
            clause,
            clause_id="constructed:s19:unit-lone-operative:clause",
            source_span=TextSpan(text=text, start=0, end=len(text)),
            target=replace(
                clause.target,
                kind=RuleTargetKind.THIS_UNIT,
                source_span=TextSpan(text="this unit", start=target_start, end=target_start + 9),
            ),
            effects=(effect,),
        )
        ir = replace(
            ir,
            rule_id="constructed:s19:unit-lone-operative",
            source_id="constructed:s19:unit-lone-operative",
            normalized_text=text,
            clauses=(clause,),
        )
        declared = replace(
            native,
            ability_id="constructed:s19:unit-lone-operative",
            source_id=ir.source_id,
            effect_description=text,
            rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()),
        )
        catalog = replace(
            d.package.army_catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    abilities=tuple(
                        declared if a.ability_id == native.ability_id else a
                        for a in sheet.abilities
                    ),
                )
                if sheet.datasheet_id == PSYKER
                else sheet
                for sheet in d.package.army_catalog.datasheets
            ),
        )
        d = Section02Definitions(replace(d.package, army_catalog=catalog), d.preparation_seconds)
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
    if not source_available:
        s.set_living("support", 0)
    records = catalog_ability_records_from_catalog(d.package.army_catalog)
    runtime = CatalogDatasheetRuleRuntime(
        {p: AbilityCatalogIndex.from_records(records) for p in s.state.player_ids},
        tuple(s.state.army_definitions),
    )
    grants = tuple(
        b for b in runtime.model_ability_grant_bindings() if b.ability_id == "core-lone-operative"
    )
    assert len(grants) == 1
    expected = (
        tuple(sorted(m.model_instance_id for m in s.view.alive_models()))
        if whole_unit
        else s.support.own_model_ids()
    )
    assert grants[0].model_ids(ModelAbilityGrantContext(s.state, s.view)) == (
        expected if source_available else ()
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
    assert bool(restrictions) is (whole_unit and source_available)
