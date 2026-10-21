"""Native selected definitions; fresh attached Core kernels, no full-roster claim.

Lord Exultant/Infractors uses its retained structured eligibility. Spiritseer as
Support, optional extra components and rule transplants are explicit Core input
premises, never admission of a native Support provider or mixed-faction roster.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section05_fixtures import replace_unit
from tests.support.section09_fixtures import add_unit
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.catalog_rule_consumption import CatalogWeaponKeywordGrantRuntime
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.starting_attached_units import starting_attached_unit_records_for_army
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army
from warhammer40k_core.geometry.pose import Pose

BODY = "000004080"
LORD = "000004078"
PSYKER = "000000588"
AVENGERS = "000000593"
YRIEL = "000004193"
WRAITHBLADES = "000000598"
IDS = (BODY, LORD, PSYKER, AVENGERS, YRIEL, WRAITHBLADES)


@pytest.fixture(scope="session")
def section19_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    elapsed = perf_counter() - start
    print(f"Section19 preparation: {elapsed:.6f}s; six native selected definitions")
    yield Section02Definitions(package, elapsed)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )


@dataclass
class AttachedScene:
    definitions: Section02Definitions
    state: GameState
    body: UnitInstance
    leader: UnitInstance
    support: UnitInstance | None
    enemy: UnitInstance
    formation: AttachedUnitFormation

    @property
    def view(self) -> RulesUnitView:
        return rules_unit_view_by_id(
            state=self.state, unit_instance_id=self.formation.attached_unit_instance_id
        )

    def component(self, role: str) -> UnitInstance:
        return next(c.unit for c in self.view.components if c.role == role)

    def set_living(self, role: str, count: int) -> None:
        """Declared casualty checkpoint; actual destruction tests use mutation owners."""
        unit = self.component(role)
        replace_unit(
            self.state,
            replace(
                unit,
                own_models=tuple(
                    replace(m, wounds_remaining=m.initial_wounds if i < count else 0)
                    for i, m in enumerate(unit.own_models)
                ),
            ),
        )
        assert self.state.battlefield_state is not None
        dead = tuple(m.model_instance_id for i, m in enumerate(unit.own_models) if i >= count)
        placed = set(self.state.battlefield_state.placed_model_ids())
        board = (
            self.state.battlefield_state.with_removed_models(
                tuple(mid for mid in dead if mid in placed)
            )
            if any(mid in placed for mid in dead)
            else self.state.battlefield_state
        )
        self.state.replace_battlefield_state(
            replace(
                board, removed_model_ids=tuple(sorted(set(board.removed_model_ids) | set(dead)))
            )
        )


def attached_scene(
    d: Section02Definitions, *, support: bool = False, leader_sheet: str = LORD
) -> AttachedScene:
    body = d.unit(BODY, identity="body")
    leader = d.unit(leader_sheet, identity="leader")
    enemy = d.unit(LORD, identity="enemy", army_id="enemy")
    state = native_state(
        d,
        body,
        tuple(Pose.at(10 + i * 1.3, 10) for i in range(len(body.own_models))),
        enemy=enemy,
        enemy_poses=(Pose.at(25, 10),),
    )
    add_unit(state, leader, (Pose.at(12, 11.5),))
    extra = d.unit(PSYKER, identity="support") if support else None
    if extra is not None:
        add_unit(state, extra, (Pose.at(13.5, 11.5),))
    components = tuple(
        sorted(
            (
                body.unit_instance_id,
                leader.unit_instance_id,
                *((extra.unit_instance_id,) if extra else ()),
            )
        )
    )
    formation = AttachedUnitFormation(
        "attached-unit:section02:s19",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        (extra.unit_instance_id,) if extra else (),
        components,
        "constructed:s19:selected-attachment",
        ("constructed:s19:attachment-boundary",),
    )
    army = replace(state.army_definitions[0], attached_units=(formation,))
    state.army_definitions[0] = army
    state.starting_strength_records[:] = sorted(
        (r for a in state.army_definitions for r in starting_strength_records_for_army(a)),
        key=lambda r: r.unit_instance_id,
    )
    state.starting_attached_unit_records[:] = starting_attached_unit_records_for_army(army)
    state.army_definitions.sort(key=lambda a: a.army_id)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    return AttachedScene(d, state, body, leader, extra, enemy, formation)


def profile_for_model(s: AttachedScene, model_id: str) -> WeaponProfile:
    """Real native weapon through the shared catalog grant consumer."""
    from warhammer40k_core.core.weapon_profiles import RangeProfileKind
    from warhammer40k_core.engine.weapon_instances import (
        equipped_weapon_profile_instances_for_model,
    )

    records = catalog_ability_records_from_catalog(s.definitions.package.army_catalog)
    runtime = CatalogWeaponKeywordGrantRuntime(
        {p: AbilityCatalogIndex.from_records(records) for p in s.state.player_ids},
        tuple(s.state.army_definitions),
    )
    physical = next(
        weapon
        for weapon in equipped_weapon_profile_instances_for_model(
            model=s.view.model_by_id(model_id), army_catalog=s.definitions.package.army_catalog
        )
        if weapon.weapon_profile.range_profile.kind is RangeProfileKind.DISTANCE
    )
    return runtime.weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=s.state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=s.view.unit_instance_id,
            attacker_model_instance_id=model_id,
            target_unit_instance_id=s.enemy.unit_instance_id,
            weapon_profile=physical.weapon_profile,
        )
    )


def has_lethal(s: AttachedScene, model_id: str) -> bool:
    return WeaponKeyword.LETHAL_HITS in profile_for_model(s, model_id).keywords


def grant_definitions(
    d: Section02Definitions, role: str, *, wargear: bool = False
) -> Section02Definitions:
    """Declared Core rule input on native bodies; no invented datasheet admission.

    Keep original package immutable. A shallow new catalog carries one compiled
    unit-wide grant so each table source is isolated from the native leading grant.
    """
    from typing import cast

    from tests.support.ability_presence_fixtures import compiled_ability_rule

    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
        DatasheetAbilityDescriptor,
    )

    text = "Ranged weapons equipped by models in this unit have the [LETHAL HITS] ability."
    ir = compiled_ability_rule(text, source_id="constructed:s19:table-grant")
    sheet = {"bodyguard": BODY, "leader": LORD, "support": PSYKER}[role]
    descriptor = DatasheetAbilityDescriptor(
        ability_id="constructed:s19:table-grant",
        name="Declared Section19 grant",
        source_id=ir.source_id,
        source_kind=CatalogAbilitySourceKind.WARGEAR
        if wargear
        else CatalogAbilitySourceKind.DATASHEET,
        source_wargear_id=f"{LORD}:bolt-pistol" if wargear else None,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()),
    )
    catalog = replace(
        d.package.army_catalog,
        datasheets=tuple(
            replace(
                row,
                abilities=(descriptor,)
                if row.datasheet_id == sheet
                else tuple(a for a in row.abilities if a.ability_id != f"{LORD}:perfectionists"),
            )
            for row in d.package.army_catalog.datasheets
        ),
    )
    return Section02Definitions(replace(d.package, army_catalog=catalog), d.preparation_seconds)


def destroy(s: AttachedScene, decisions: object, model_id: str) -> None:
    """Actual rule-caused casualty producer with explicit liability authority."""
    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.rule_model_destruction import destroy_model_with_rule_reactions

    assert isinstance(decisions, DecisionController)
    effect_id = f"constructed:s19:destruction:{model_id}"
    s.state.record_persisting_effect(
        generic_effect(
            effect_id=effect_id,
            owner_player_id="opponent",
            target_unit_instance_ids=(s.view.unit_instance_id,),
            target_kind="selected_unit",
            effect_kind="set_contextual_status",
            parameters={"status": "s19_destruction_liability"},
        )
    )
    result = destroy_model_with_rule_reactions(
        state=s.state,
        decisions=decisions,
        model_instance_id=model_id,
        rules_unit_instance_id=s.view.unit_instance_id,
        destroying_player_id="opponent",
        source_rule_id="constructed:s19:destruction",
        source_effect_ids=(effect_id,),
        source_phase=BattlePhase.SHOOTING,
        source_step="s19:rule-casualty",
        source_result_id=effect_id,
        completion_event_type="s19_casualty_completed",
        completion_event_payload={},
    )
    assert result.status is None
