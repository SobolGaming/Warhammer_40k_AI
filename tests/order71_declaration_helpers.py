"""One physical shooting unit with distinct model keyword assignments."""

from __future__ import annotations

from dataclasses import replace

from tests.model_keyword_helpers import mixed_keyword_catalog
from tests.phase13b_shooting_declaration_helpers import (
    _build_shooting_lifecycle,  # pyright: ignore[reportPrivateUsage]
    _config,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import DatasheetWargearOption
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose


def mixed_model_shooting_session(
    *, monster_vehicle_keyword: str, close_quarters_keyword: WeaponKeyword
) -> LocalGameSession:
    catalog = mixed_keyword_catalog()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    rifle = next(row for row in catalog.wargear if row.wargear_id == "core-bolt-rifle")
    close_weapon = replace(
        rifle,
        wargear_id="order71-close-weapon",
        name="Order 71 close weapon",
        weapon_profiles=(
            replace(
                rifle.weapon_profiles[0],
                profile_id="order71-close-weapon:standard",
                keywords=(close_quarters_keyword,),
                abilities=(),
                attack_profile=AttackProfile.fixed(1),
            ),
        ),
    )
    weapon_ids = (rifle.wargear_id, close_weapon.wargear_id)
    sheet = replace(
        sheet,
        keywords=replace(
            sheet.keywords,
            keywords=tuple(
                monster_vehicle_keyword if keyword == "PSYKER" else keyword
                for keyword in sheet.keywords.keywords
            ),
        ),
        composition=tuple(replace(row, min_models=1, max_models=1) for row in sheet.composition),
        wargear_options=tuple(
            DatasheetWargearOption(
                option_id=f"order71-weapons:{profile.model_profile_id}",
                model_profile_id=profile.model_profile_id,
                default_wargear_ids=weapon_ids,
                allowed_wargear_ids=weapon_ids,
                min_selections=2,
                max_selections=2,
            )
            for profile in sheet.model_profiles
        ),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
        wargear=(*catalog.wargear, close_weapon),
        model_keyword_assignments=tuple(
            replace(
                row,
                keywords=tuple(
                    monster_vehicle_keyword if keyword == "PSYKER" else keyword
                    for keyword in row.keywords
                ),
            )
            for row in catalog.model_keyword_assignments
        ),
    )
    config = _config(
        game_id="order71-model-exclusivity",
        alpha_unit_ids=("shooter",),
        alpha_datasheets=None,
        alpha_unit_specs=(("shooter", sheet.datasheet_id, "core-intercessor-like", 1),),
        enemy_datasheet=("core-vehicle-monster", "core-vehicle-monster", 1),
        catalog=catalog,
    )
    config = replace(
        config,
        army_muster_requests=tuple(
            replace(
                army,
                unit_selections=tuple(
                    replace(
                        selection,
                        model_profile_selections=(
                            *selection.model_profile_selections,
                            ModelProfileSelection(
                                model_profile_id="core-keyword-specialist", model_count=1
                            ),
                        ),
                    )
                    for selection in army.unit_selections
                ),
            )
            if army.player_id == "player-a"
            else army
            for army in config.army_muster_requests
        ),
    )
    lifecycle, _ = _build_shooting_lifecycle(
        alpha_unit_ids=("shooter",), config_override=config, enemy_pose=Pose.at(25, 35)
    )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
