from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import cast

from warhammer40k_core.core.model_geometry_catalog import (
    GeometrySourceUnits,
)
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
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


def unit_resource_wargear_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Battle Focus,Army rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-aspect-warriors,Aspect Warriors,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    ("test-aspect-warriors,1,Faction,test-army-rule,Battle Focus,Army rule text.,"),
                    (
                        'test-aspect-warriors,2,Wargear,,Aspect Shrine Token,"Once per battle '
                        "for each Aspect Shrine token this unit has, you can change the result "
                        "of one Hit roll or one Wound roll made for a model in this unit "
                        '(excluding CHARACTER models) to an unmodified 6.",'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-aspect-warriors,Infantry,,false",
                    "test-aspect-warriors,Aeldari,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-aspect-warriors,1,7,3,3,-,1,6,1,28.5mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_options",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    (
                        'test-aspect-warriors,1,"For every 5 models in this unit, it can have '
                        '1 Aspect Shrine token."'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    'test-aspect-warriors,1,"1 Aspect Exarch and 4-9 Aspect Warriors"',
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Aeldari")),
        ),
    )


def flesh_hounds_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-shadow,test-faction,The Shadow of Chaos,Army rule text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-flesh-hounds,Flesh Hounds,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-flesh-hounds,1,Faction,test-shadow,,,",
                    (
                        "test-flesh-hounds,2,Wargear,,Spare Charm,"
                        "Add 1 to Charge rolls made for the bearer's unit.,"
                    ),
                    (
                        "test-flesh-hounds,3,Wargear,,Collar of Khorne,"
                        "The bearer has the Feel No Pain 3+ ability against Psychic Attacks "
                        "and mortal wounds.,"
                    ),
                    (
                        "test-flesh-hounds,4,Datasheet,,Hunters from the Warp,"
                        "\"At the end of your opponent's turn, if this unit is not within "
                        "Engagement Range of one or more enemy units, you can remove it "
                        'from the battlefield and place it into Strategic Reserves.",'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-flesh-hounds,Beasts,,false",
                    "test-flesh-hounds,Chaos,,false",
                    "test-flesh-hounds,Daemon,,false",
                    "test-flesh-hounds,Khorne,,false",
                    "test-flesh-hounds,Legiones Daemonica,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-flesh-hounds,1,12,4,6,5,2,7,1,60mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_options",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    (
                        "test-flesh-hounds,1,1 Flesh Hound that is not equipped with a "
                        "Spare Charm can be equipped with 1 Collar of Khorne."
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-flesh-hounds,1,5 Flesh Hounds")),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def same_faction_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
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
                    "test-datasheet-a,Alpha Unit,test-faction",
                    "test-datasheet-b,Beta Unit,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-datasheet-a,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-datasheet-b,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-datasheet-a,Alpha,,false",
                    "test-datasheet-a,Test Faction,,true",
                    "test-datasheet-b,Beta,,false",
                    "test-datasheet-b,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-datasheet-a,1,6,4,3,-,2,7,1,32mm",
                    "test-datasheet-b,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-datasheet-a,1,1 Alpha",
                    "test-datasheet-b,1,1 Beta",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def keyword_ability_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                    "core-deep-strike,,Deep Strike,Deep Strike text.",
                    "core-infiltrators,,Infiltrators,Infiltrators text.",
                    "core-leader,,Leader,Leader text.",
                    "core-support,,Support,Support text.",
                    'core-scouts,,"Scouts 6""",Scouts text.',
                    "core-firing-deck,,Firing Deck 2,Firing Deck text.",
                    "core-deadly-demise,,Deadly Demise D3,Deadly Demise text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(("id,name,faction_id", "test-keyword-unit,Keyword Unit,test-faction")),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-keyword-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-keyword-unit,2,Core,core-deep-strike,,,",
                    "test-keyword-unit,3,Core,core-infiltrators,,,",
                    "test-keyword-unit,4,Core,core-leader,,,",
                    "test-keyword-unit,5,Core,core-support,,,",
                    "test-keyword-unit,6,Core,core-scouts,,,",
                    "test-keyword-unit,7,Core,core-firing-deck,,,",
                    "test-keyword-unit,8,Core,core-deadly-demise,,,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-keyword-unit,Infantry,,false",
                    "test-keyword-unit,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-keyword-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-keyword-unit,1,1 Alpha")),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def conditioned_weapon_keyword_bridge_artifacts(
    description: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_conditioned_weapon_keyword_source_artifacts(description),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-condition-keyword-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-condition-keyword-unit",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:condition-keyword-height",
                height_document_reference="test-doc:condition-keyword-height",
            ),
        ),
    )


def _conditioned_weapon_keyword_source_artifacts(
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
                    "test-condition-keyword-unit,Condition Keyword Unit,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-condition-keyword-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-condition-keyword-unit,Infantry,,false",
                    "test-condition-keyword-unit,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    (
                        "test-condition-keyword-unit,1,1,Aperture rifle,Ranged,24,2,3,4,-1,1,"
                        f'"{description}"'
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-condition-keyword-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-condition-keyword-unit,1,1 Alpha")),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def warlord_mustering_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
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
                    "test-supreme-commander,Supreme Commander,test-faction",
                    "test-warlord-forbidden,Forbidden Warlord,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-supreme-commander,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-supreme-commander,2,Special (right column),,"
                        'SUPREME COMMANDER,"If this model is in your army, '
                        'it must be your WARLORD.",'
                    ),
                    (
                        "test-supreme-commander,3,Special (right column),,"
                        "TACTICAL ACUMEN,This model can observe tactical options.,"
                    ),
                    (
                        "test-warlord-forbidden,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-warlord-forbidden,2,Fortification (left column),,"
                        "ENSLAVED STAR GOD,This model cannot be your WARLORD.,"
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-supreme-commander,Character,,false",
                    "test-supreme-commander,Epic Hero,,false",
                    "test-supreme-commander,Test Faction,,true",
                    "test-warlord-forbidden,Character,,false",
                    "test-warlord-forbidden,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-supreme-commander,1,6,4,3,-,4,6,1,32mm",
                    "test-warlord-forbidden,1,6,4,3,-,4,6,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-supreme-commander,1,1 Commander",
                    "test-warlord-forbidden,1,1 Forbidden",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def unsupported_ability_type_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
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
                    "test-unsupported-ability-type,Unsupported Ability Type,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-unsupported-ability-type,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    ("test-unsupported-ability-type,2,Unmapped,,Bad Ability,Test rule text.,"),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-unsupported-ability-type,Character,,false",
                    "test-unsupported-ability-type,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-unsupported-ability-type,1,6,4,3,-,4,6,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-unsupported-ability-type,1,1 Invalid",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def support_attachment_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                    "core-support,,Support,Support text.",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-support-unit,Support Unit,test-faction",
                    "test-bodyguard-unit,Bodyguard Unit,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-support-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-support-unit,2,Core,core-support,,,",
                    "test-bodyguard-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-support-unit,Character,,false",
                    "test-support-unit,Infantry,,false",
                    "test-support-unit,Test Faction,,true",
                    "test-bodyguard-unit,Infantry,,false",
                    "test-bodyguard-unit,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_leader",
            "\n".join(
                (
                    "leader_id,attached_id",
                    "test-support-unit,test-bodyguard-unit",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-support-unit,1,1,Support blade,Melee,Melee,1,3,4,0,1,",
                    "test-bodyguard-unit,1,1,Bodyguard blade,Melee,Melee,1,3,4,0,1,",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-support-unit,1,6,4,3,-,2,7,1,32mm",
                    "test-bodyguard-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-support-unit,1,1 Support",
                    "test-bodyguard-unit,1,1 Bodyguard",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def unsupported_wargear_rule_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
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
                    "test-unsupported-unit,Unsupported Unit,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-unsupported-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-unsupported-unit,2,Wargear,,Scatter Icon,"
                        "Roll a scatter die and consult the legacy table.,"
                    ),
                    (
                        "test-unsupported-unit,3,Wargear,,Hit Charm,"
                        "Add 1 to hit rolls for the bearer's unit.,"
                    ),
                    "test-unsupported-unit,4,Wargear,,Tithe Charm,Gain 1CP.,",
                    (
                        "test-unsupported-unit,5,Wargear,,Broken Instrument,"
                        "Add 1 to Charge rolls made for the bearer's unit. "
                        "Roll a scatter die and consult the legacy table.,"
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-unsupported-unit,Infantry,,false",
                    "test-unsupported-unit,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-unsupported-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-unsupported-unit,1,1 Alpha")),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def unowned_wargear_profile_ability_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
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
                    "test-wargear-profile-owner,Wargear Profile Owner,test-faction",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-wargear-profile-owner,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-wargear-profile-owner,2,Wargear profile,,Summoning Horn,"
                        "Return one destroyed model.,"
                    ),
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-wargear-profile-owner,Infantry,,false",
                    "test-wargear-profile-owner,Test Faction,,true",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-wargear-profile-owner,1,1,Rotten bell,Ranged,12,1,3,4,0,1,[Lethal Hits]",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-wargear-profile-owner,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-wargear-profile-owner,1,1 Profile Bearer",
                )
            ),
        ),
        artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def artifact_from_csv(table_name: str, csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=bridge_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=f"{csv_text}\n"),
    )


def source_artifacts_with_datasheet_option_description(
    *,
    datasheet_id: str,
    option_row_id: str,
    description: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    patched = False
    for artifact in wahapedia_source_artifacts():
        if artifact.source_table != "Datasheets_options":
            artifacts.append(artifact)
            continue
        patched_rows: list[NormalizedSourceRow] = []
        for row in artifact.rows:
            fields = row.runtime_fields_payload()
            if fields["datasheet_id"] == datasheet_id and row.source_row_id == option_row_id:
                patched = True
                patched_rows.append(
                    replace(
                        row,
                        fields=tuple(
                            (column, description if column == "description" else value)
                            for column, value in row.fields
                        ),
                    )
                )
                continue
            patched_rows.append(row)
        artifacts.append(replace(artifact, rows=tuple(patched_rows)))
    if not patched:
        raise ValueError("Missing Datasheets_options row to patch.")
    return tuple(artifacts)


def csv_field(value: str) -> str:
    return value.replace('"', '""')


@lru_cache(maxsize=1)
def wahapedia_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name in _REQUIRED_TABLES:
        payload = json.loads(
            (_WAHAPEDIA_10E_JSON / f"{table_name}.json").read_text(encoding="utf-8")
        )
        artifacts.append(
            WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
        )
    return tuple(artifacts)


def artifact_by_table(
    artifacts: tuple[WahapediaJsonArtifact, ...],
    table_name: str,
) -> WahapediaJsonArtifact:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact
    raise ValueError(f"Missing artifact table: {table_name}.")


def optional_artifact_rows(
    artifacts: tuple[WahapediaJsonArtifact, ...],
    table_name: str,
) -> tuple[NormalizedSourceRow, ...]:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact.rows
    return ()


def row_by_id(artifact: WahapediaJsonArtifact, row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == row_id:
            return row
    raise ValueError(f"Missing source row: {row_id}.")


def source_ids_from_row(row: NormalizedSourceRow) -> tuple[str, ...]:
    return tuple(
        source_id.strip()
        for source_id in row.runtime_fields_payload()["source_ids"].split(",")
        if source_id.strip()
    )


def bridge_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="wahapedia-" + "1" + "0" + "e-bridge",
        version="phase17k-test",
    )


def catalog_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="chaos-daemons-bridge-catalog",
        version="phase17k-test",
    )


def catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="warhammer-40000-11th-phase17k",
        source_date=date(2026, 6, 10),
    )
