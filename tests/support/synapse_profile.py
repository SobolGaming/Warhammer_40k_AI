"""Canonical native-loaded Synapse checkpoints; geometry edits are query seams, not moves."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase15c_fight_order_helpers import fight_config, fight_lifecycle, unit_placement_at

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.battlefield_state import geometry_model_at_pose
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.tyranids import army_rule
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose


@pytest.fixture(scope="session")
def shared_synapse_config() -> Iterator[GameConfig]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base = catalog.datasheet_by_id("core-character-leader")
    fighter = replace(
        base,
        datasheet_id="batch20-fighter",
        name="Canonical Synapse recipient",
        keywords=DatasheetKeywordSet(
            keywords=base.keywords.keywords, faction_keywords=("Tyranids",)
        ),
        abilities=(),
    )
    source = replace(
        fighter,
        datasheet_id="batch20-source",
        name="Canonical Synapse source",
        keywords=replace(fighter.keywords, keywords=(*base.keywords.keywords, "Synapse")),
    )
    catalog = replace(
        catalog,
        datasheets=(*catalog.datasheets, fighter, source),
        factions=(
            *catalog.factions,
            FactionDefinition(
                faction_id="tyranids",
                name="Tyranids",
                faction_keywords=("Tyranids",),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
        detachments=(
            *catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id="batch20-synapse",
                detachment_id="batch20-synapse",
                name="Synapse query fixture",
                faction_id="tyranids",
                detachment_point_cost=1,
                unit_datasheet_ids=(fighter.datasheet_id, source.datasheet_id, base.datasheet_id),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("batch20:fixture",),
            ),
        ),
    )
    config = fight_config(
        game_id="batch20-loaded-synapse",
        alpha_unit_ids=("source", "fighter", "neutral"),
        enemy_unit_ids=("enemy",),
        datasheet_id=base.datasheet_id,
        model_profile_id="core-character-leader",
        model_count=1,
        alpha_unit_specs={
            "source": (source.datasheet_id, "core-character-leader", 1),
            "fighter": (fighter.datasheet_id, "core-character-leader", 1),
            "neutral": (fighter.datasheet_id, "core-character-leader", 1),
        },
        catalog=catalog,
        alpha_faction_id="tyranids",
        alpha_detachment_ids=("batch20-synapse",),
    )
    before = json.dumps(config.to_payload(), sort_keys=True)
    yield config
    assert json.dumps(config.to_payload(), sort_keys=True) == before


def loaded_synapse(config: GameConfig) -> tuple[GameLifecycle, GameState, RuntimeModifierRegistry]:
    lifecycle, _ = fight_lifecycle(
        config=deepcopy(config),
        game_id=config.game_id,
        alpha_unit_ids=("source", "fighter", "neutral"),
        enemy_unit_ids=("enemy",),
        origins={
            "source": Pose.at(8, 10),
            "fighter": Pose.at(13, 10),
            "neutral": Pose.at(10, 15),
            "enemy": Pose.at(15, 11),
        },
        model_count=1,
    )
    state = lifecycle.state
    assert state is not None
    bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )()
    assert (
        army_rule.WEAPON_PROFILE_MODIFIER_ID
        in bundle.to_summary_payload()["weapon_profile_modifier_ids"]
    )
    assert "SYNAPSE" not in unit(state, "fighter").keywords
    return lifecycle, state, bundle.runtime_modifier_registry


def unit(state: GameState, key: str) -> UnitInstance:
    return state.army_definitions[0].unit_by_id(f"army-alpha:{key}")


def profile_context(state: GameState, key: str = "fighter") -> WeaponProfileModifierContext:
    attacker = unit(state, key)
    return WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id="army-beta:enemy",
        weapon_profile=WeaponProfile(
            profile_id="batch20:claws",
            name="Canonical claws",
            range_profile=RangeProfile.melee(),
            attack_profile=AttackProfile.fixed(1),
            skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
            damage_profile=DamageProfile.fixed(1),
            source_ids=("batch20:profile",),
        ),
    )


def place_at_gap(state: GameState, gap: float) -> float:
    source = unit(state, "source")
    fighter = unit(state, "fighter")
    source_geometry = geometry_model_at_pose(model=source.own_models[0], pose=Pose.at(8, 10))
    fighter_geometry = geometry_model_at_pose(model=fighter.own_models[0], pose=Pose.at(8, 10))
    assert isinstance(source_geometry.base, CircularBase)
    assert isinstance(fighter_geometry.base, CircularBase)
    pose = Pose.at(8 + source_geometry.base.radius + fighter_geometry.base.radius + gap, 10)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            unit_placement_at(fighter, army_id="army-alpha", player_id="player-a", poses=(pose,))
        )
    )
    return shapely_backend.base_footprint_distance(
        source_geometry.base, source_geometry.pose, fighter_geometry.base, pose
    )


def replace_source(state: GameState, source: UnitInstance) -> None:
    army = state.army_definitions[0]
    state.army_definitions[0] = replace(
        army,
        units=tuple(
            source if u.unit_instance_id == source.unit_instance_id else u for u in army.units
        ),
    )
