"""Catalog-backed mixed-model Hazard fixtures, with ordinary facade decisions."""

from dataclasses import replace

from tests.model_keyword_helpers import mixed_keyword_catalog
from tests.phase13b_shooting_declaration_helpers import (
    _build_shooting_lifecycle,
    _config,
    _unit_placement_at,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose


def hazard_scene(
    ordinary_keyword: str, *, attached: bool = False, game_id: str = "order105-hazard-1"
) -> tuple[LocalGameSession, dict[str, UnitInstance]]:
    catalog = mixed_keyword_catalog()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    sheet = replace(
        sheet,
        keywords=replace(sheet.keywords, keywords=(ordinary_keyword, "VEHICLE", "BATTLELINE")),
        wargear_options=tuple(
            replace(
                option,
                option_id=f"order105:{profile.model_profile_id}",
                model_profile_id=profile.model_profile_id,
            )
            for profile in sheet.model_profiles
            for option in ArmyCatalog.phase9a_canonical_content_pack()
            .datasheet_by_id(sheet.datasheet_id)
            .wargear_options
        ),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet
            if row.datasheet_id == sheet.datasheet_id
            else replace(row, keywords=replace(row.keywords, keywords=("VEHICLE", "CHARACTER")))
            if row.datasheet_id == "core-character-leader"
            else row
            for row in catalog.datasheets
        ),
        model_keyword_assignments=tuple(
            replace(
                row,
                keywords=("VEHICLE", "BATTLELINE")
                if row.model_profile_id == "core-keyword-specialist"
                else (ordinary_keyword, "BATTLELINE"),
            )
            for row in catalog.model_keyword_assignments
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        keywords=(WeaponKeyword.HAZARDOUS,),
                        abilities=(),
                        attack_profile=AttackProfile.fixed(1),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    specs = (
        ("shooter", sheet.datasheet_id, "core-intercessor-like", 2),
        *(((("leader", "core-character-leader", "core-character-leader", 1),)) if attached else ()),
        ("transport", "core-transport", "core-transport", 1),
    )
    config = _config(
        game_id=game_id,
        alpha_unit_ids=tuple(row[0] for row in specs),
        alpha_datasheets=None,
        alpha_unit_specs=specs,
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "shooter"),)
        if attached
        else (),
        enemy_datasheet=("core-vehicle-monster", "core-vehicle-monster", 1),
        catalog=catalog,
    )
    config = replace(
        config,
        army_muster_requests=tuple(
            replace(
                request,
                unit_selections=tuple(
                    replace(
                        selection,
                        model_profile_selections=(
                            *selection.model_profile_selections,
                            ModelProfileSelection("core-keyword-specialist", 1),
                        ),
                    )
                    if selection.unit_selection_id == "shooter"
                    else selection
                    for selection in request.unit_selections
                ),
            )
            for request in config.army_muster_requests
        ),
    )
    lifecycle, units = _build_shooting_lifecycle(
        alpha_unit_ids=tuple(row[0] for row in specs), config_override=config
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    if attached:
        state.replace_battlefield_state(
            state.battlefield_state.with_unit_placement(
                _unit_placement_at(
                    units["leader"],
                    army_id="army-alpha",
                    player_id="player-a",
                    poses=(Pose.at(14.2, 35),),
                )
            )
        )
    return LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload())), units
