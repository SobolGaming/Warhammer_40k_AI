from __future__ import annotations

from tests.support.wahapedia_bridge_fixtures import (
    advance_charge_bridge_artifacts,
    bloodcrushers_bridge_artifacts,
    flesh_hounds_bridge_artifacts,
    model_reroll_bridge_artifacts,
    named_weapon_choice_bridge_artifacts,
    post_shoot_cover_denial_bridge_artifacts,
    post_shoot_selected_target_effect_bridge_artifacts,
    split_fall_back_bridge_artifacts,
    split_model_reroll_bridge_artifacts,
    undivided_daemon_bridge_artifacts,
)
from tests.support.wahapedia_source_fixtures import catalog_package_id, catalog_version

from warhammer40k_core.core.datasheet import (
    DatasheetDefinition,
    DatasheetWargearOption,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    MusteringOptionSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.unit_factory import (
    UnitFactory,
    UnitInstance,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def bloodcrushers_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bloodcrushers_bridge_artifacts(),
    )


def flesh_hounds_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=flesh_hounds_bridge_artifacts(),
    )


def advance_charge_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=advance_charge_bridge_artifacts(),
    )


def model_reroll_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=model_reroll_bridge_artifacts(),
    )


def split_fall_back_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=split_fall_back_bridge_artifacts(),
    )


def split_model_reroll_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=split_model_reroll_bridge_artifacts(),
    )


def named_weapon_choice_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=named_weapon_choice_bridge_artifacts(),
    )


def undivided_daemon_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=undivided_daemon_bridge_artifacts(),
    )


def post_shoot_cover_denial_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=post_shoot_cover_denial_bridge_artifacts(),
    )


def post_shoot_selected_target_effect_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=post_shoot_selected_target_effect_bridge_artifacts(),
    )


def bloodcrushers_unit(
    *,
    package: CanonicalCatalogPackage,
    selected_wargear_id: str,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    option = _wargear_option_for_wargear(datasheet, selected_wargear_id)
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodcrushers-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001115:bloodcrushers",
                    model_count=2,
                ),
                ModelProfileSelection(
                    model_profile_id="000001115:bloodhunter",
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=option.option_id,
                    model_profile_id=option.model_profile_id,
                    wargear_ids=(selected_wargear_id,),
                ),
            ),
        ),
        datasheet=datasheet,
    )


def resolved_bloodthirster_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> tuple[str, ...]:
    datasheet = package.army_catalog.datasheet_by_id("000002582")
    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodthirster-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000002582:bloodthirster",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_selections,
        ),
        datasheet=datasheet,
    )
    return unit.own_models[0].wargear_ids


def resolved_great_unclean_one_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> tuple[str, ...]:
    return (
        great_unclean_one_unit(
            package=package,
            requested_selections=requested_selections,
        )
        .own_models[0]
        .wargear_ids
    )


def great_unclean_one_unit(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001130")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-nurgle",
        selection=UnitMusterSelection(
            unit_selection_id="great-unclean-one-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001130:great-unclean-one",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_selections,
        ),
        datasheet=datasheet,
    )


def resolved_keeper_of_secrets_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> tuple[str, ...]:
    return (
        keeper_of_secrets_unit(
            package=package,
            requested_selections=requested_selections,
        )
        .own_models[0]
        .wargear_ids
    )


def keeper_of_secrets_unit(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001137")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-slaanesh",
        selection=UnitMusterSelection(
            unit_selection_id="keeper-of-secrets-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001137:keeper-of-secrets",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_selections,
        ),
        datasheet=datasheet,
    )


def resolved_soul_grinder_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_wargear_selections: tuple[WargearSelection, ...],
    mustering_option_selections: tuple[MusteringOptionSelection, ...],
) -> tuple[str, ...]:
    return (
        soul_grinder_unit(
            package,
            requested_wargear_selections=requested_wargear_selections,
            mustering_option_selections=mustering_option_selections,
        )
        .own_models[0]
        .wargear_ids
    )


def soul_grinder_unit(
    package: CanonicalCatalogPackage,
    *,
    requested_wargear_selections: tuple[WargearSelection, ...],
    mustering_option_selections: tuple[MusteringOptionSelection, ...],
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001151")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-daemons",
        selection=UnitMusterSelection(
            unit_selection_id="soul-grinder-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001151:soul-grinder",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_wargear_selections,
            mustering_option_selections=mustering_option_selections,
        ),
        datasheet=datasheet,
    )


def daemon_prince_unit(
    *,
    package: CanonicalCatalogPackage,
    datasheet_id: str,
    allegiance: str,
    unit_selection_id: str,
    army_id: str = "army-daemons",
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
    profile_suffix = (
        "daemon-prince-of-chaos"
        if datasheet_id == "000001149"
        else "daemon-prince-of-chaos-with-wings"
    )
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=f"{datasheet_id}:{profile_suffix}",
                    model_count=1,
                ),
            ),
            mustering_option_selections=(
                MusteringOptionSelection(
                    option_id=f"{datasheet_id}:daemonic-allegiance:{allegiance.lower()}"
                ),
            ),
        ),
        datasheet=datasheet,
    )


def flesh_hounds_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str = "army-daemons",
    unit_selection_id: str = "flesh-hounds-1",
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("test-flesh-hounds")
    selected_wargear_id = "test-flesh-hounds:collar-of-khorne"
    option = _wargear_option_for_wargear(datasheet, selected_wargear_id)
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="test-flesh-hounds:flesh-hounds",
                    model_count=5,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=option.option_id,
                    model_profile_id=option.model_profile_id,
                    wargear_ids=(selected_wargear_id,),
                ),
            ),
        ),
        datasheet=datasheet,
    )


def advance_charge_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str = "army-daemons",
    unit_selection_id: str = "advance-charge-unit-1",
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("test-advance-charge-unit")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="test-advance-charge-unit:swift-hunter",
                    model_count=1,
                ),
            ),
        ),
        datasheet=datasheet,
    )


def named_weapon_choice_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str = "army-daemons",
    unit_selection_id: str = "lord-of-change-1",
    model_count: int = 1,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("test-lord-of-change")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="test-lord-of-change:lord-of-change",
                    model_count=model_count,
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _wargear_option_for_wargear(
    datasheet: DatasheetDefinition,
    wargear_id: str,
) -> DatasheetWargearOption:
    for option in datasheet.wargear_options:
        if option.allowed_wargear_ids == (wargear_id,):
            return option
    raise ValueError(f"Missing option for wargear: {wargear_id}.")


def bloodcrushers_army(
    *,
    package: CanonicalCatalogPackage,
    unit: UnitInstance,
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id="army-khorne",
        player_id="player-khorne",
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("phase17k-daemons",),
        ),
        force_disposition_id="phase17k-force",
        units=(unit,),
    )


def flesh_hounds_army(
    *,
    package: CanonicalCatalogPackage,
    unit: UnitInstance,
    army_id: str = "army-daemons",
    player_id: str = "player-daemons",
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("phase17k-daemons",),
        ),
        force_disposition_id="phase17k-force",
        units=(unit,),
    )
