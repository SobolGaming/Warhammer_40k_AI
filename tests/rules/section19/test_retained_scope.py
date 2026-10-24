"""19.04/FAQ49/64: physical retention is distinct from ordinary death.

Native Spiritseer rule; declared Core Support and FoD fixture premises only.
Native Support/FoD provider admission and a full facade combination are unproven.
"""

from dataclasses import replace

import pytest

from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section05_fixtures import replace_unit
from tests.support.section09_fixtures import add_unit
from tests.support.section19_fixtures import (
    PSYKER,
    WRAITHBLADES,
    AttachedScene,
    attached_scene,
    destroy,
)
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.ability_presence import ability_presence
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.model_ability_grants import ModelAbilityGrantContext
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    TargetRestriction,
)
from warhammer40k_core.geometry.pose import Pose


def _scene(d: Section02Definitions, *, other_alive: bool, enemy_x: int) -> AttachedScene:
    s = attached_scene(d, support=True)
    if not other_alive:
        s.set_living("bodyguard", 0)
        s.set_living("leader", 0)
    escort = d.unit(WRAITHBLADES, identity="escort")
    add_unit(
        s.state, escort, tuple(Pose.at(10 + i * 1.7, 14) for i in range(len(escort.own_models)))
    )
    assert s.state.battlefield_state is not None
    s.state.replace_battlefield_state(
        s.state.battlefield_state.with_unit_placement(
            placement(s.enemy, (Pose.at(enemy_x, 10),), enemy=True)
        )
    )
    return s


def _scope(s: AttachedScene) -> tuple[tuple[str, ...], tuple[TargetRestriction, ...]]:
    catalog = s.definitions.package.army_catalog
    records = catalog_ability_records_from_catalog(catalog)
    runtime = CatalogDatasheetRuleRuntime(
        {p: AbilityCatalogIndex.from_records(records) for p in s.state.player_ids},
        tuple(s.state.army_definitions),
    )
    descriptor = next(
        a
        for a in catalog.datasheet_by_id(PSYKER).abilities
        if a.ability_id == f"{PSYKER}:spiritseer"
    )
    assert descriptor.rule_ir_payload is not None
    grant = next(
        b
        for b in runtime.model_ability_grant_bindings()
        if b.source_id == descriptor.rule_ir_payload["source_id"]
    )
    recipients = grant.model_ids(ModelAbilityGrantContext(s.state, s.view))
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
    return recipients, restrictions


def _casualty(s: AttachedScene, *, retained: bool) -> str:
    assert s.support is not None
    assert s.state.battlefield_state is not None
    model = s.component("support").own_models[0]
    saved = s.state.battlefield_state.model_placement_by_id(model.model_instance_id)
    decisions = DecisionController()
    if retained:
        apply_damage_to_model(
            state=s.state,
            target_unit_instance_id=s.support.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.current_wounds,
            damage_kind=DamageKind.NORMAL,
            remove_destroyed_model=False,
        )
        retain_destroyed_model_for_fixture(
            state=s.state,
            placement=saved,
            effect_id="constructed:s19:retained-recipient",
            source_rule_id="constructed:s19:fod",
            source_phase=BattlePhase.SHOOTING,
            decisions=decisions,
        )
        assert any(
            e.event_type == "fight_on_death_retention_selected" for e in decisions.event_log.records
        )
    else:
        destroy(s, decisions, model.model_instance_id)
    assert not s.component("support").own_models[0].is_alive
    return model.model_instance_id


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("other_alive", [False, True])
@pytest.mark.parametrize("enemy_x", [20, 40])
def test_conditional_recipient_selection_uses_physical_presence_not_ordinary_death(
    section19_definitions: Section02Definitions,
    retained: bool,
    other_alive: bool,
    enemy_x: int,
) -> None:
    s = _scene(section19_definitions, other_alive=other_alive, enemy_x=enemy_x)
    assert s.support is not None
    before_ids, before_restrictions = _scope(s)
    assert before_ids == s.support.own_model_ids()
    assert bool(before_restrictions) is (not other_alive and enemy_x == 40)
    model_id = _casualty(s, retained=retained)
    ids, restrictions = _scope(s)
    presence = ability_presence(state=s.state, rules_unit=s.view)
    assert ids == ((model_id,) if retained else ())
    assert (model_id in presence.active_model_ids) is retained
    assert (model_id in presence.battlefield_model_ids) is retained
    assert (model_id in s.view.retained_model_ids) is retained
    assert bool(restrictions) is (retained and not other_alive and enemy_x == 40)
    if not other_alive:
        assert s.view.living_components == ()
        assert len(s.view.rules_present_components) == (1 if retained else 0)


def test_retained_recipient_still_requires_duplicate_instance_selection(
    section19_definitions: Section02Definitions,
) -> None:
    s = _scene(section19_definitions, other_alive=False, enemy_x=40)
    support = s.component("support")
    # Declared Core duplicate, never attributed to the native datasheet.
    native = DatasheetAbilityDescriptor(
        ability_id="core-lone-operative",
        name="Lone Operative",
        source_id="constructed:s19:retained:native-lone-operative",
        source_kind=CatalogAbilitySourceKind.CORE,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        effect_description="Lone Operative 9 inches",
        parameter_tokens=("9",),
    )
    replace_unit(
        s.state, replace(support, datasheet_abilities=(*support.datasheet_abilities, native))
    )
    with pytest.raises(GameLifecycleError, match="controlling-player selection"):
        _scope(s)
    model_id = _casualty(s, retained=True)
    assert model_id in s.view.retained_model_ids
    with pytest.raises(GameLifecycleError, match="controlling-player selection"):
        _scope(s)
