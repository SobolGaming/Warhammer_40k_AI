from __future__ import annotations

from pathlib import Path

from tests.support.wahapedia_source_fixtures import (
    artifact_from_csv,
    bridge_package_id,
    csv_field,
    flesh_hounds_source_artifacts,
    source_artifacts_with_datasheet_option_description,
    wahapedia_source_artifacts,
)

from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometrySourceUnits,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
)

_WAHAPEDIA_10E_JSON = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
_REQUIRED_TABLES = (
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Datasheets_keywords",
    "Datasheets_leader",
    "Datasheets_models",
    "Datasheets_models_cost",
    "Datasheets_options",
    "Datasheets_unit_composition",
    "Datasheets_wargear",
    "Factions",
)


def bloodcrushers_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001115",),
    )


def weirdboy_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000000004",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000000004",
                model_name="Weirdboy",
                height=1.8,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:orks:weirdboy:height",
                height_document_reference="Phase 17K Orks bridge regression fixture",
            ),
        ),
    )


def bloodthirster_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000002582",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000002582",
                model_name="Bloodthirster",
                height=5.75,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:bloodthirster:height",
                height_document_reference="Chaos Daemons Faction Pack p.16-17",
            ),
        ),
    )


def kairos_fateweaver_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001117",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001117",
                model_name="Kairos Fateweaver - EPIC HERO",
                height=7.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:kairos-fateweaver:height",
                height_document_reference=(
                    "https://www.adeptusars.com/miniatures/kairos-fateweaver"
                ),
                evidence_kind=GeometryEvidenceKind.CROWD_SOURCED_MEASUREMENT,
            ),
        ),
    )


def great_unclean_one_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001130",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001130",
                model_name="Great Unclean One",
                height=5.25,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:great-unclean-one:height",
                height_document_reference="Chaos Daemons Faction Pack p.66-67",
            ),
        ),
    )


def keeper_of_secrets_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001137",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001137",
                model_name="Keeper of Secrets",
                height=5.6,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:keeper-of-secrets:height",
                height_document_reference="Chaos Daemons Faction Pack p.90-91",
            ),
        ),
    )


def lord_of_change_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001120",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001120",
                model_name="Lord of Change",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:lord-of-change:height",
                height_document_reference="Chaos Daemons Faction Pack p.40-41",
            ),
        ),
    )


def keeper_of_secrets_non_single_item_choice_source_artifacts() -> tuple[
    WahapediaJsonArtifact, ...
]:
    return source_artifacts_with_datasheet_option_description(
        datasheet_id="000001137",
        option_row_id="000001137:1",
        description=(
            "This model can be equipped with one of the following:\n"
            "- 2 Living whips\n"
            "- Ritual knife\n"
            "- Shining aegis"
        ),
    )


def soul_grinder_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001151",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001151",
                model_name="Soul Grinder",
                height=6.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:soul-grinder:height",
                height_document_reference="Chaos Daemons Faction Pack p.114-115",
            ),
        ),
    )


def daemon_prince_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001149", "000002758"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001149",
                model_name="Daemon Prince of Chaos",
                height=4.75,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:daemon-prince:height",
                height_document_reference="Chaos Daemons Faction Pack p.116-117",
            ),
            ModelHeightOverride(
                datasheet_id="000002758",
                model_name="Daemon Prince of Chaos with Wings",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id=("geometry-review:chaos-daemons:daemon-prince-with-wings:height"),
                height_document_reference="Chaos Daemons Faction Pack p.118-119",
            ),
        ),
    )


def undivided_daemon_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001149", "000002758", "000001151"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001149",
                model_name="Daemon Prince of Chaos",
                height=4.75,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:daemon-prince:height",
                height_document_reference="Chaos Daemons Faction Pack p.116-117",
            ),
            ModelHeightOverride(
                datasheet_id="000002758",
                model_name="Daemon Prince of Chaos with Wings",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id=("geometry-review:chaos-daemons:daemon-prince-with-wings:height"),
                height_document_reference="Chaos Daemons Faction Pack p.118-119",
            ),
            ModelHeightOverride(
                datasheet_id="000001151",
                model_name="Soul Grinder",
                height=6.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:soul-grinder:height",
                height_document_reference="Chaos Daemons Faction Pack p.114-115",
            ),
        ),
    )


def no_equipment_daemon_fortification_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001470", "000001588"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001470",
                model_name="Feculent Gnarlmaw",
                height=5.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:feculent-gnarlmaw:height",
                height_document_reference="Chaos Daemons Faction Pack p.86-87",
            ),
            ModelHeightOverride(
                datasheet_id="000001588",
                model_name="Skull Altar",
                height=6.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:skull-altar:height",
                height_document_reference=(
                    "Reddit r/ChaosDaemons40k community measurement; "
                    "Battle Foam BFS-4.5 tray storage evidence"
                ),
            ),
        ),
    )


def jakhals_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_jakhals_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-jakhals",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-jakhals",
                model_name="Jakhal Pack Leader",
                height=1.25,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:world-eaters:jakhals:pack-leader:height",
                height_document_reference="World Eaters Faction Pack p.34",
            ),
            ModelHeightOverride(
                datasheet_id="test-jakhals",
                model_name="Dishonoured",
                height=1.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:world-eaters:jakhals:dishonoured:height",
                height_document_reference="World Eaters Faction Pack p.34",
            ),
            ModelHeightOverride(
                datasheet_id="test-jakhals",
                model_name="Jakhals",
                height=1.25,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:world-eaters:jakhals:jakhals:height",
                height_document_reference="World Eaters Faction Pack p.34",
            ),
        ),
    )


def _jakhals_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-world-eaters-rule,WE,Blessings of Khorne,Army rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-jakhals,Jakhals,WE",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-jakhals,1,Faction,test-world-eaters-rule,,,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-jakhals,Chaos,,false",
                    "test-jakhals,Grenades,,false",
                    "test-jakhals,Infantry,,false",
                    "test-jakhals,Jakhals,,false",
                    "test-jakhals,Khorne,,false",
                    "test-jakhals,World Eaters,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-jakhals,1,7,4,6,-,1,7,1,28.5mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-jakhals,1,1,Autopistol,Ranged,12,1,4,3,0,1,pistol",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    'test-jakhals,1,"1 Jakhal Pack Leader, 1 Dishonoured and 8 Jakhals"',
                    "test-jakhals,2,or:",
                    'test-jakhals,3,"1 Jakhal Pack Leader, 2 Dishonoured and 17 Jakhals"',
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "WE,World Eaters")),
        ),
    )


def damaged_source_artifacts(damaged_description: str) -> tuple[WahapediaJsonArtifact, ...]:
    escaped_description = csv_field(damaged_description)
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-faction-rule,TST,Test Rule,Army rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id,damaged_description",
                    f'test-damaged,Damaged Beast,TST,"{escaped_description}"',
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-damaged,1,Faction,test-faction-rule,,,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-damaged,Character,,false",
                    "test-damaged,Monster,,false",
                    "test-damaged,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-damaged,1,8,10,4,5,14,6,5,100mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-damaged,1,1,Claws,Melee,melee,4,2,10,-2,3,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    'test-damaged,1,"1 Damaged Beast"',
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "TST,Test Faction")),
        ),
    )


def flesh_hounds_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=flesh_hounds_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-flesh-hounds",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-flesh-hounds",
                model_name="Flesh Hounds",
                height=1.6,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:flesh-hounds:height",
                height_document_reference="Chaos Daemons Faction Pack p.26",
            ),
        ),
    )


def advance_charge_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_advance_charge_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-advance-charge-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-advance-charge-unit",
                model_name="Swift Hunter",
                height=1.4,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:advance-charge:swift-hunter:height",
                height_document_reference="Test Advance Charge Datasheet",
            ),
        ),
    )


def model_reroll_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_model_reroll_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-advance-charge-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-advance-charge-unit",
                model_name="Swift Hunter",
                height=1.4,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:model-reroll:swift-hunter:height",
                height_document_reference="Test Model Reroll Datasheet",
            ),
        ),
    )


def split_fall_back_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return _single_advance_charge_ability_bridge_artifacts(
        ability_name="Split Slip Away",
        description=(
            "Models in this unit have a Leadership characteristic of 6+. "
            "This unit is eligible to shoot in a turn in which it Fell Back."
        ),
        height_source_id="geometry-review:test:split-fall-back:swift-hunter:height",
        height_document_reference="Test Split Fall Back Datasheet",
    )


def split_model_reroll_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return _single_advance_charge_ability_bridge_artifacts(
        ability_name="Split Swift Instincts",
        description=(
            "After a Hit roll, re-roll Hit rolls. "
            "You can re\u2011roll Advance and Charge rolls made for this model."
        ),
        height_source_id="geometry-review:test:split-model-reroll:swift-hunter:height",
        height_document_reference="Test Split Model Reroll Datasheet",
    )


def _single_advance_charge_ability_bridge_artifacts(
    *,
    ability_name: str,
    description: str,
    height_source_id: str,
    height_document_reference: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_single_advance_charge_ability_source_artifacts(
            ability_name=ability_name,
            description=description,
        ),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-advance-charge-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-advance-charge-unit",
                model_name="Swift Hunter",
                height=1.4,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id=height_source_id,
                height_document_reference=height_document_reference,
            ),
        ),
    )


def named_weapon_choice_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_named_weapon_choice_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-lord-of-change",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-lord-of-change",
                model_name="Lord of Change",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:lord-of-change:height",
                height_document_reference="Test Lord of Change Datasheet",
            ),
        ),
    )


def post_shoot_cover_denial_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_post_shoot_cover_denial_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-lord-of-change",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-lord-of-change",
                model_name="Lord of Change",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:lord-of-change:height",
                height_document_reference="Test Lord of Change Datasheet",
            ),
        ),
    )


def post_shoot_selected_target_effect_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_post_shoot_selected_target_effect_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-lord-of-change",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-lord-of-change",
                model_name="Lord of Change",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:lord-of-change:height",
                height_document_reference="Test Lord of Change Datasheet",
            ),
        ),
    )


def _advance_charge_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-advance-charge-unit,Advance Charge Unit,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-advance-charge-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-advance-charge-unit,2,Datasheet,,Bounding Advance,"
                        "This unit is eligible to declare a charge in a turn in  which "
                        "it Advanced.,"
                    ),
                    (
                        "test-advance-charge-unit,3,Datasheet,,Lead the Hunt,"
                        '"While this model is leading a unit, you can re-roll  Advance '
                        'and Charge rolls made for that unit.",'
                    ),
                    (
                        "test-advance-charge-unit,4,Datasheet,,Pack Killers,"
                        '"While this model is leading a unit, melee weapons equipped by '
                        'models in that unit have the  [LETHAL HITS] ability.",'
                    ),
                    (
                        "test-advance-charge-unit,5,Datasheet,,Slip Away,"
                        "This unit is eligible to shoot in a turn in  which it Fell Back.,"
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-advance-charge-unit,Beasts,,false",
                    "test-advance-charge-unit,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-advance-charge-unit,1,10,4,6,5,2,7,1,40mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-advance-charge-unit,1,1,Swift claws,Melee,Melee,4,4,4,0,1,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-advance-charge-unit,1,1 Swift Hunter",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _model_reroll_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return _single_advance_charge_ability_source_artifacts(
        ability_name="Swift Instincts",
        description="You can re\u2011roll Advance and Charge rolls made for this model.",
    )


def _single_advance_charge_ability_source_artifacts(
    *,
    ability_name: str,
    description: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-advance-charge-unit,Advance Charge Unit,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-advance-charge-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-advance-charge-unit,2,Datasheet,,"
                        f'{csv_field(ability_name)},"{csv_field(description)}",'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-advance-charge-unit,Beasts,,false",
                    "test-advance-charge-unit,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-advance-charge-unit,1,10,4,6,5,2,7,1,40mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-advance-charge-unit,1,1,Swift claws,Melee,Melee,4,4,4,0,1,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-advance-charge-unit,1,1 Swift Hunter",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _named_weapon_choice_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-daemons-rule,test-faction,Test Daemons Rule,Test rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-lord-of-change,Lord of Change,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-lord-of-change,1,Faction,test-daemons-rule,"
                        "Test Daemons Rule,Test rule text.,"
                    ),
                    (
                        "test-lord-of-change,2,Datasheet,,Daemonspark,"
                        '"In your Shooting phase, select one of the following abilities: '
                        "[IGNORES COVER]; [LETHAL HITS]; [SUSTAINED HITS D3]. "
                        "Until the end of the phase, this model's Bolt of Change has "
                        'that ability.",'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-lord-of-change,Character,,false",
                    "test-lord-of-change,Monster,,false",
                    "test-lord-of-change,Psyker,,false",
                    "test-lord-of-change,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-lord-of-change,1,12,10,6,5,20,6,5,100mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-lord-of-change,1,1,Bolt of Change,Ranged,18,9,2,9,-2,3,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-lord-of-change,1,1 Lord of Change",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _post_shoot_cover_denial_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-daemons-rule,test-faction,Test Daemons Rule,Test rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-lord-of-change,Lord of Change,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-lord-of-change,1,Faction,test-daemons-rule,"
                        "Test Daemons Rule,Test rule text.,"
                    ),
                    (
                        "test-lord-of-change,2,Datasheet,,Purge and Cleanse,"
                        '"In your Shooting phase, after this model has shot, select one '
                        "enemy unit hit by one or more of those attacks. Until the end "
                        'of the phase, that unit cannot have the Benefit of Cover.",'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-lord-of-change,Character,,false",
                    "test-lord-of-change,Monster,,false",
                    "test-lord-of-change,Psyker,,false",
                    "test-lord-of-change,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-lord-of-change,1,12,10,6,5,20,6,5,100mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-lord-of-change,1,1,Bolt of Change,Ranged,18,9,2,9,-2,3,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-lord-of-change,1,1-2 Lord of Change",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _post_shoot_selected_target_effect_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-daemons-rule,test-faction,Test Daemons Rule,Test rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-lord-of-change,Lord of Change,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-lord-of-change,1,Faction,test-daemons-rule,"
                        "Test Daemons Rule,Test rule text.,"
                    ),
                    (
                        "test-lord-of-change,2,Datasheet,,Warpflame Locus,"
                        '"In your Shooting phase, after this model has shot, select one '
                        "enemy unit hit by one or more of those attacks. Until the end "
                        "of the phase, each time this model makes an attack that targets "
                        'that unit, add 1 to the Damage characteristic of that attack.",'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-lord-of-change,Character,,false",
                    "test-lord-of-change,Monster,,false",
                    "test-lord-of-change,Psyker,,false",
                    "test-lord-of-change,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-lord-of-change,1,12,10,6,5,20,6,5,100mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-lord-of-change,1,1,Bolt of Change,Ranged,18,9,2,9,-2,3,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-lord-of-change,1,1-2 Lord of Change",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )
