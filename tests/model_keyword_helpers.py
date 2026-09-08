# pyright: reportPrivateUsage=false
"""Real mixed-model catalog fixtures for Order 31 keyword ownership."""

from dataclasses import replace

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import UnitCompositionDefinition
from warhammer40k_core.core.model_keywords import ModelKeywordAssignment
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection


def mixed_keyword_catalog() -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    profile = sheet.model_profiles[0]
    specialist = replace(profile, model_profile_id="core-keyword-specialist", name="Specialist")
    sheet = replace(
        sheet,
        keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "PSYKER")),
        model_profiles=(profile, specialist),
        composition=(
            UnitCompositionDefinition(
                model_profile_id=profile.model_profile_id, min_models=2, max_models=2
            ),
            UnitCompositionDefinition(
                model_profile_id=specialist.model_profile_id, min_models=1, max_models=1
            ),
        ),
        wargear_options=(),
    )
    return replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
        model_keyword_assignments=tuple(
            ModelKeywordAssignment(
                datasheet_id=sheet.datasheet_id,
                model_profile_id=row.model_profile_id,
                keywords=sheet.keywords.keywords
                if row == specialist
                else tuple(k for k in sheet.keywords.keywords if k != "PSYKER"),
                faction_keywords=sheet.keywords.faction_keywords if row == specialist else (),
                source_ids=(f"{row.model_profile_id}:keyword-source",),
            )
            for row in sheet.model_profiles
        ),
    )


def mixed_keyword_unit() -> UnitInstance:
    catalog = mixed_keyword_catalog()
    return UnitFactory(catalog=catalog).instantiate_unit(
        army_id="keyword-army",
        selection=UnitMusterSelection(
            unit_selection_id="mixed",
            model_profile_selections=tuple(
                ModelProfileSelection(model_profile_id=p.model_profile_id, model_count=p.min_models)
                for p in catalog.datasheet_by_id("core-intercessor-like-infantry").composition
            ),
            datasheet_id="core-intercessor-like-infantry",
        ),
        datasheet=catalog.datasheet_by_id("core-intercessor-like-infantry"),
    )


def mixed_keyword_shooting_session(*, retained: bool = False) -> tuple[LocalGameSession, str]:
    from tests.phase13b_shooting_declaration_helpers import _build_shooting_lifecycle, _config
    from tests.retained_attack_helpers import lethal_retained_attack_catalog
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionKind,
        DestructionReactionSource,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.geometry.pose import Pose

    mixed = mixed_keyword_catalog()
    catalog = replace(mixed, wargear=lethal_retained_attack_catalog().wargear)
    shooter_ids = ("shooter", "second-shooter", "third-shooter")
    config = _config(
        game_id="order31-keyword-shooting",
        alpha_unit_ids=shooter_ids,
        alpha_datasheets=None,
        alpha_unit_specs=tuple(
            (name, "core-vehicle-monster", "core-vehicle-monster", 1) for name in shooter_ids
        ),
        enemy_datasheet=None,
        enemy_unit_specs=(
            ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 2),
            ("support", "core-vehicle-monster", "core-vehicle-monster", 1),
        ),
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
                            ModelProfileSelection(
                                model_profile_id="core-keyword-specialist", model_count=1
                            ),
                        ),
                    )
                    if selection.unit_selection_id == "enemy"
                    else selection
                    for selection in request.unit_selections
                ),
            )
            for request in config.army_muster_requests
        ),
    )
    lifecycle, units = _build_shooting_lifecycle(
        alpha_unit_ids=shooter_ids,
        config_override=config,
        enemy_pose=Pose.at(30, 35),
    )
    state = lifecycle.state
    assert state is not None
    specialist = next(model for model in units["enemy"].own_models if "PSYKER" in model.keywords)
    if retained:
        state.record_model_destruction_reaction_sources(
            model_instance_id=specialist.model_instance_id,
            sources=(
                DestructionReactionSource(
                    source_id="order31-retention",
                    source_rule_id="order31-retention",
                    reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                ),
            ),
        )
    return LocalGameSession(
        lifecycle=GameLifecycle.from_payload(lifecycle.to_payload())
    ), specialist.model_instance_id
