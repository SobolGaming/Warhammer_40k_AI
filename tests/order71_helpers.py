"""Canonical real-model scenes for engaged shooting source and scope regressions."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _scenario_with_unit_pose,
    _shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.geometry.pose import Pose

SHOOTER = "army-alpha:shooter"
TARGET = "army-beta:enemy"
ATTACKER_SOURCE = "gw-11e-core-actions:close-quarters-shooting"
TARGET_SOURCE = "gw-11e-core-engaged-shooting:engaged-monster-vehicle-target"


def shooting_profile(session: LocalGameSession) -> WeaponProfile:
    config = session.lifecycle.config
    assert config is not None
    return next(
        item.weapon_profiles[0]
        for item in config.army_catalog.wargear
        if item.wargear_id == "core-bolt-rifle"
    )


def engaged_shooting_session(
    *,
    attacker_vehicle: bool = False,
    target_vehicle: bool = True,
    attacker_engaged: bool = False,
    target_engaged: bool = True,
    mutual: bool = False,
    keywords: tuple[WeaponKeyword, ...] = (),
    attached_attacker: bool = False,
    attached_target: bool = False,
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    infantry_sheet = next(
        row for row in catalog.datasheets if row.datasheet_id == "core-intercessor-like-infantry"
    )
    catalog = replace(
        catalog,
        datasheets=(
            *catalog.datasheets,
            replace(
                infantry_sheet,
                datasheet_id="order71-vehicle",
                keywords=replace(
                    infantry_sheet.keywords, keywords=(*infantry_sheet.keywords.keywords, "VEHICLE")
                ),
            ),
        ),
    )
    # All ranged profiles share controlled dice; the actual physical owner and
    # model keyword assignment still come from normal roster materialization.
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        keywords=keywords,
                        abilities=(),
                        attack_profile=AttackProfile.fixed(2),
                        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                    )
                    if profile.range_profile.distance_inches is not None
                    else profile
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
        datasheets=tuple(
            replace(
                row, keywords=replace(row.keywords, keywords=(*row.keywords.keywords, "VEHICLE"))
            )
            if row.datasheet_id == "core-character-leader"
            else row
            for row in catalog.datasheets
        ),
    )
    infantry: tuple[str, str, int] = ("core-intercessor-like-infantry", "core-intercessor-like", 1)
    leader: tuple[str, str, int] = ("core-character-leader", "core-character-leader", 1)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("shooter", "friendly"),
        alpha_unit_specs=(
            (
                "shooter",
                "order71-vehicle"
                if attacker_vehicle and not attached_attacker
                else "core-intercessor-like-infantry",
                "core-intercessor-like",
                1,
            ),
            ("friendly", *infantry),
            *(((("shooter-leader", *leader),)) if attached_attacker else ()),
        ),
        alpha_attachment_declarations=(AttachmentDeclaration("shooter-leader", "shooter"),)
        if attached_attacker
        else (),
        enemy_unit_specs=(
            (
                "enemy",
                "order71-vehicle"
                if target_vehicle and not attached_target
                else "core-intercessor-like-infantry",
                "core-intercessor-like",
                1,
            ),
            ("other", *infantry),
            *(((("enemy-leader", *leader),)) if attached_target else ()),
        ),
        enemy_attachment_declarations=(AttachmentDeclaration("enemy-leader", "enemy"),)
        if attached_target
        else (),
        catalog=catalog,
        game_id="order71-engaged-shooting",
    )
    state = lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    target_x = 11.8 if mutual else 20.0
    positions = {
        "shooter": (10.0, 20.0),
        "shooter-leader": (10.0, 21.4),
        "enemy": (target_x, 20.0),
        "enemy-leader": (target_x, 21.4),
        "friendly": (target_x, 18.2) if target_engaged else (40.0, 10.0),
        "other": (10.0, 18.2) if attacker_engaged else (40.0, 40.0),
    }
    for army in state.army_definitions:
        for unit in army.units:
            key = unit.unit_instance_id.split(":", 1)[1]
            x, y = positions[key]
            scenario = _scenario_with_unit_pose(
                scenario=scenario,
                unit=units[key],
                army_id=army.army_id,
                player_id=army.player_id,
                poses=tuple(Pose.at(x, y + index * 1.4) for index in range(len(unit.own_models))),
            )
    state.battlefield_state = scenario.battlefield_state
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
