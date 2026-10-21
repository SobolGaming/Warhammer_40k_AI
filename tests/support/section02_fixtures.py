"""Real definitions prepared once; no shared mutable unit or ability payloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage

INFRACTORS = "000004080"
AVENGERS = "000000593"
MAULERFIEND = "000000968"
RANGERS = "000000592"
LORD_EXULTANT = "000004078"
CHAOS_SPAWN = "000004090"
DATASHEETS = (INFRACTORS, AVENGERS, MAULERFIEND, RANGERS, LORD_EXULTANT, CHAOS_SPAWN)


def health_state(definitions: Section02Definitions, unit: UnitInstance) -> GameState:
    """Health-owner kernel. Real unit, no mission, no mustering or phase traversal.

    Detachment is identity metadata only; this kernel grants no detachment rules.
    """
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_detachments_2026_27,
    )

    assert unit.datasheet_id == INFRACTORS
    detachment = next(
        row
        for row in faction_detachments_2026_27.detachment_rows()
        if row.faction_id == "emperors-children" and row.detachment_id == "mercurial-host"
    )
    catalog = definitions.package.army_catalog
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    army = ArmyDefinition(
        army_id="section02",
        player_id="owner",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection("EC", (detachment.detachment_id,)),
        force_disposition_id="take-and-hold",
        units=(unit,),
    )
    return GameState(
        game_id="section02-health",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        player_ids=("owner", "opponent"),
        turn_order=("owner", "opponent"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(descriptor.battle_phase_sequence.phases).index(
            BattlePhase.COMMAND
        ),
        battle_round=1,
        active_player_id="owner",
        army_definitions=[army],
        starting_strength_records=[StartingStrengthRecord.from_unit(player_id="owner", unit=unit)],
    )


@dataclass(frozen=True)
class Section02Definitions:
    package: CanonicalCatalogPackage
    preparation_seconds: float

    def unit(
        self,
        datasheet_id: str = INFRACTORS,
        *,
        identity: str = "subject",
        army_id: str = "section02",
        wargear: tuple[WargearSelection, ...] = (),
        composition: tuple[ModelProfileSelection, ...] | None = None,
    ) -> UnitInstance:
        datasheet = self.package.army_catalog.datasheet_by_id(datasheet_id)
        selection = UnitMusterSelection(
            unit_selection_id=identity,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                tuple(
                    ModelProfileSelection(p.model_profile_id, p.min_models)
                    for p in datasheet.composition
                )
                if composition is None
                else composition
            ),
            wargear_selections=wargear,
        )
        unit = UnitFactory(
            catalog=self.package.army_catalog, model_geometries=self.package.model_geometries
        ).instantiate_unit(army_id=army_id, datasheet=datasheet, selection=selection)
        # UnitFactory intentionally shares definition payloads. Deep-copy only the
        # small fresh unit graph, not the catalog or the source tables.
        return deepcopy(unit)

    def weapon(self, wargear_id: str, profile: int = 0) -> WeaponProfile:
        return next(
            w for w in self.package.army_catalog.wargear if w.wargear_id == wargear_id
        ).weapon_profiles[profile]

    def characteristic(self, characteristic: Characteristic) -> CharacteristicValue:
        if characteristic in {
            Characteristic.RANGE,
            Characteristic.ATTACKS,
            Characteristic.STRENGTH,
            Characteristic.ARMOR_PENETRATION,
            Characteristic.DAMAGE,
            Characteristic.WEAPON_SKILL,
            Characteristic.BALLISTIC_SKILL,
        }:
            weapon = self.weapon(
                f"{INFRACTORS}:duelling-sabre"
                if characteristic is Characteristic.WEAPON_SKILL
                else f"{AVENGERS}:avenger-shuriken-catapult"
            )
            if characteristic in {Characteristic.WEAPON_SKILL, Characteristic.BALLISTIC_SKILL}:
                value = weapon.skill
            elif characteristic is Characteristic.STRENGTH:
                value = weapon.strength
            elif characteristic is Characteristic.ARMOR_PENETRATION:
                value = weapon.armor_penetration
            else:
                raw = {
                    Characteristic.RANGE: weapon.range_profile.distance_inches,
                    Characteristic.ATTACKS: weapon.attack_profile.fixed_attacks,
                    Characteristic.DAMAGE: weapon.damage_profile.fixed_damage,
                }[characteristic]
                assert isinstance(raw, int)
                value = CharacteristicValue.from_raw(characteristic, raw)
        else:
            value = self.unit(AVENGERS).own_models[0].characteristic(characteristic)
        assert isinstance(value, CharacteristicValue)
        return value


@pytest.fixture(scope="session")
def section02_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=DATASHEETS, source_index_dir=selected_army_source_index
    )
    elapsed = perf_counter() - start
    print(f"Section02 preparation: {elapsed:.6f}s; one build, {len(DATASHEETS)} definitions")
    definition_digest = hashlib.sha256(
        json.dumps(package.to_payload(), sort_keys=True).encode()
    ).hexdigest()
    yield Section02Definitions(package, elapsed)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == definition_digest
    )
