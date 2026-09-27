"""Real catalog and facade fixtures for shooting selections with no attacks."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.geometry.pose import Pose

SHOOTER = "army-alpha:shooter"


def empty_shooting_session(
    *,
    no_weapons: bool = False,
    attached: bool = False,
    reachable: bool = False,
    spare: bool = False,
    advanced: bool = False,
    vehicle: bool = False,
    engaged: bool = False,
    keywords: tuple[WeaponKeyword, ...] = (),
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                row,
                wargear_options=tuple(
                    replace(option, default_wargear_ids=(), min_selections=0)
                    for option in row.wargear_options
                ),
            )
            if no_weapons
            and row.datasheet_id in {"core-intercessor-like-infantry", "core-character-leader"}
            else row
            for row in catalog.datasheets
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        range_profile=replace(
                            profile.range_profile, distance_inches=48 if reachable else 1
                        ),
                        keywords=keywords,
                        abilities=(),
                    )
                    if profile.range_profile.distance_inches is not None
                    else profile
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    if vehicle:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    row,
                    keywords=replace(row.keywords, keywords=(*row.keywords.keywords, "VEHICLE")),
                )
                if row.datasheet_id == "core-intercessor-like-infantry"
                else row
                for row in catalog.datasheets
            ),
        )
    specs: tuple[tuple[str, str, str, int], ...] = (
        ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 1),
    )
    if attached:
        specs += (("leader", "core-character-leader", "core-character-leader", 1),)
    if spare:
        specs += (("spare", "core-intercessor-like-infantry", "core-intercessor-like", 1),)
    lifecycle, _ = _shooting_lifecycle(
        alpha_unit_ids=("shooter",),
        alpha_unit_specs=specs,
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "shooter"),)
        if attached
        else (),
        enemy_datasheet=("core-intercessor-like-infantry", "core-intercessor-like", 1),
        enemy_pose=Pose.at(11.8 if engaged else 30, 35),
        catalog=catalog,
        game_id="order91-empty-shooting",
    )
    if advanced:
        from tests.phase13b_shooting_declaration_helpers import _advanced_unit_state

        assert lifecycle.state is not None
        lifecycle.state.record_advanced_unit_state(_advanced_unit_state(SHOOTER, can_shoot=False))
    return LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
