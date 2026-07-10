from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    BaseSizeDefinition,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetMusteringOption,
    DatasheetMusteringOptionEffect,
    DatasheetMusteringOptionEffectKind,
    UnitCompositionDefinition,
)
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
    ArmyMusterRequest,
    ArmyMusterRequestPayload,
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
    EnhancementAssignment,
    RosterLegalityReport,
    RosterUnitPointValue,
    WarlordSelection,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.attached_unit_formation import (
    AttachedUnitFormation,
    AttachedUnitFormationError,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.deployment import deployment_unit_selection_request
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    BattleSize,
    BattleSizeMusteringPolicy,
    DetachmentSelection,
    ListValidationError,
    ModelProfileSelection,
    MusteringOptionSelection,
    UnitMusterSelection,
    WargearSelection,
    battle_size_from_token,
    resolve_model_profile_selections,
    resolve_wargear_selections,
    selected_force_disposition_ids,
    validate_detachment_selection,
    validate_unit_selection_for_faction,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep
from warhammer40k_core.engine.rules_units import (
    RulesUnitComponent,
    RulesUnitComponentRole,
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.setup_flow import SetupFlow
from warhammer40k_core.engine.unit_factory import (
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)


def _unit_selection(
    *,
    unit_selection_id: str = "intercessor-unit-1",
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
    wargear_selections: tuple[WargearSelection, ...] = (),
    mustering_option_selections: tuple[MusteringOptionSelection, ...] = (),
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
        wargear_selections=wargear_selections,
        mustering_option_selections=mustering_option_selections,
    )


def _muster_request(
    catalog: ArmyCatalog,
    *,
    army_id: str = "army-alpha",
    player_id: str = "player-a",
    detachment_selection: DetachmentSelection | None = None,
    unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    unit_points: tuple[RosterUnitPointValue, ...] = (),
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
    warlord_selection: WarlordSelection | None = None,
    dedicated_transport_manifests: tuple[DedicatedTransportManifest, ...] = (),
    roster_legality_required: bool = False,
    catalog_id: str | None = None,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id if catalog_id is None else catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=detachment_selection
        if detachment_selection is not None
        else DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=unit_selections if unit_selections is not None else (_unit_selection(),),
        attachment_declarations=attachment_declarations,
        unit_points=unit_points,
        enhancement_assignments=enhancement_assignments,
        warlord_selection=warlord_selection,
        dedicated_transport_manifests=dedicated_transport_manifests,
        roster_legality_required=roster_legality_required,
        battle_size=battle_size,
    )


def _phase16_source_detachment(
    *,
    row: faction_detachment_source.SourceDetachmentRow,
    unit_datasheet_ids: tuple[str, ...],
) -> DetachmentDefinition:
    return DetachmentDefinition(
        detachment_id=row.detachment_id,
        name=row.name,
        faction_id=row.faction_id,
        detachment_point_cost=row.detachment_point_cost,
        unit_datasheet_ids=unit_datasheet_ids,
        force_disposition_ids=(row.force_disposition_id,),
        source_ids=row.source_ids,
    )


def _phase16_source_detachment_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    unit_datasheet_ids = tuple(datasheet.datasheet_id for datasheet in base_catalog.datasheets)
    source_factions = tuple(
        FactionDefinition(
            faction_id=row.faction_id,
            name=row.name,
            faction_keywords=row.faction_keywords,
            source_ids=row.source_ids,
        )
        for row in faction_detachment_source.faction_rows()
    )
    factions = (base_catalog.faction_by_id("core-marine-force"), *source_factions)
    detachments = tuple(
        _phase16_source_detachment(
            row=row,
            unit_datasheet_ids=unit_datasheet_ids,
        )
        for row in faction_detachment_source.detachment_rows()
    )

    return ArmyCatalog(
        catalog_id="phase16-faction-detachments-2026-27",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id=faction_detachment_source.SOURCE_PACKAGE_ID,
        datasheets=base_catalog.datasheets,
        wargear=base_catalog.wargear,
        factions=factions,
        army_rules=base_catalog.army_rules,
        detachments=detachments,
        source_ids=(faction_detachment_source.SOURCE_PACKAGE_ID,),
    )


def _phase16d_catalog(
    *,
    second_enhancement: bool = False,
    upgrade_enhancement: bool = False,
    epic_leader: bool = False,
) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    enhancements: tuple[EnhancementDefinition, ...] = (
        EnhancementDefinition(
            enhancement_id="core-enhancement-a",
            name="Core Enhancement A",
            source_id="enhancement:core-enhancement-a",
            points=25,
        ),
    )
    if second_enhancement:
        enhancements = (
            *enhancements,
            EnhancementDefinition(
                enhancement_id="core-enhancement-b",
                name="Core Enhancement B",
                source_id="enhancement:core-enhancement-b",
                points=30,
            ),
        )
    if upgrade_enhancement:
        enhancements = (
            *enhancements,
            EnhancementDefinition(
                enhancement_id="core-upgrade",
                name="Core Upgrade",
                source_id="enhancement:core-upgrade",
                subtypes=(EnhancementSubtype.UPGRADE,),
                points=20,
            ),
        )
    enhancement_ids = tuple(enhancement.enhancement_id for enhancement in enhancements)
    datasheets: list[DatasheetDefinition] = []
    for datasheet in base_catalog.datasheets:
        if datasheet.datasheet_id == "core-transport":
            datasheets.append(
                replace(
                    datasheet,
                    keywords=DatasheetKeywordSet(
                        keywords=("Dedicated Transport", "Transport", "Vehicle"),
                        faction_keywords=datasheet.keywords.faction_keywords,
                    ),
                )
            )
            continue
        if epic_leader and datasheet.datasheet_id == "core-character-leader":
            datasheets.append(
                replace(
                    datasheet,
                    keywords=DatasheetKeywordSet(
                        keywords=("Character", "Epic Hero", "Infantry", "Leader"),
                        faction_keywords=datasheet.keywords.faction_keywords,
                    ),
                )
            )
            continue
        datasheets.append(datasheet)
    detachment = replace(base_catalog.detachments[0], enhancement_ids=enhancement_ids)
    return ArmyCatalog(
        catalog_id="phase16d-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id=base_catalog.source_package_id,
        datasheets=tuple(datasheets),
        wargear=base_catalog.wargear,
        factions=base_catalog.factions,
        army_rules=base_catalog.army_rules,
        detachments=(detachment,),
        enhancements=enhancements,
        stratagems=base_catalog.stratagems,
        source_ids=base_catalog.source_ids,
    )


def _supreme_commander_catalog(
    *,
    supreme_datasheet_ids: tuple[str, ...] = (
        "test-supreme-commander-alpha",
        "test-supreme-commander-beta",
    ),
    forbidden_datasheet_ids: tuple[str, ...] = (),
) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_character = base_catalog.datasheet_by_id("core-character-leader")
    custom_datasheet_ids = (
        "test-supreme-commander-alpha",
        "test-supreme-commander-beta",
        "test-regular-character",
    )
    custom_datasheets: list[DatasheetDefinition] = []
    for datasheet_id in custom_datasheet_ids:
        ability_overlays: list[DatasheetAbilityDescriptor] = []
        if datasheet_id in supreme_datasheet_ids:
            ability_overlays.append(
                _warlord_mustering_ability(
                    ability_id=f"{datasheet_id}:supreme-commander",
                    name="SUPREME COMMANDER",
                    value=MUSTERING_WARLORD_REQUIRED,
                )
            )
        if datasheet_id in forbidden_datasheet_ids:
            ability_overlays.append(
                _warlord_mustering_ability(
                    ability_id=f"{datasheet_id}:cannot-be-warlord",
                    name="Cannot Be Warlord",
                    value=MUSTERING_WARLORD_FORBIDDEN,
                )
            )
        custom_datasheets.append(
            replace(
                base_character,
                datasheet_id=datasheet_id,
                name=datasheet_id.replace("-", " ").title(),
                keywords=DatasheetKeywordSet(
                    keywords=tuple(
                        sorted(
                            {
                                *base_character.keywords.keywords,
                                *(("Epic Hero",) if ability_overlays else ()),
                            }
                        )
                    ),
                    faction_keywords=base_character.keywords.faction_keywords,
                ),
                abilities=(*base_character.abilities, *ability_overlays),
                attachment_eligibilities=(),
                source_ids=(f"datasheet:{datasheet_id}",),
            )
        )
    detachment = replace(
        base_catalog.detachments[0],
        unit_datasheet_ids=tuple(
            sorted({*base_catalog.detachments[0].unit_datasheet_ids, *custom_datasheet_ids})
        ),
    )
    return ArmyCatalog(
        catalog_id="supreme-commander-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id=base_catalog.source_package_id,
        datasheets=(*base_catalog.datasheets, *custom_datasheets),
        wargear=base_catalog.wargear,
        factions=base_catalog.factions,
        army_rules=base_catalog.army_rules,
        detachments=(detachment,),
        enhancements=base_catalog.enhancements,
        stratagems=base_catalog.stratagems,
        source_ids=base_catalog.source_ids,
    )


def _warlord_mustering_ability(
    *,
    ability_id: str,
    name: str,
    value: str,
) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=ability_id,
        name=name,
        source_id=f"datasheet:{ability_id}",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=f"{name} mustering descriptor.",
        timing_tags=("mustering", "warlord"),
        rule_ir_payload={MUSTERING_WARLORD_RULE_KEY: value},
    )


def _catalog_with_datasheet_ability(
    catalog: ArmyCatalog,
    *,
    datasheet_id: str,
    ability: DatasheetAbilityDescriptor,
) -> ArmyCatalog:
    return replace(
        catalog,
        datasheets=tuple(
            replace(datasheet, abilities=(*datasheet.abilities, ability))
            if datasheet.datasheet_id == datasheet_id
            else datasheet
            for datasheet in catalog.datasheets
        ),
    )


def _daemonic_pact_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    datasheets = (
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-chaos-legionaries",
            name="Chaos Legionaries",
            keywords=("Character", "Infantry", "Battleline", "Heretic Astartes"),
            faction_keywords=("Heretic Astartes",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-bloodletters",
            name="Bloodletters",
            keywords=("Infantry", "Battleline", "Khorne"),
            faction_keywords=("Legiones Daemonica",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-bloodthirster",
            name="Bloodthirster",
            keywords=("Character", "Khorne", "Monster"),
            faction_keywords=("Legiones Daemonica",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-skull-cannon",
            name="Skull Cannon",
            keywords=("Khorne", "Vehicle"),
            faction_keywords=("Legiones Daemonica",),
        ),
        replace(
            _phase17g_datasheet(
                base_datasheet,
                datasheet_id="phase17g-soul-grinder",
                name="Soul Grinder",
                keywords=("Monster", "Vehicle"),
                faction_keywords=("Legiones Daemonica",),
            ),
            mustering_options=(
                DatasheetMusteringOption(
                    option_id="phase17g-soul-grinder:daemonic-allegiance:khorne",
                    selection_group_id="phase17g-soul-grinder:daemonic-allegiance",
                    label="Khorne",
                    required=True,
                    source_ids=("phase17k:soul-grinder:daemonic-allegiance",),
                    effects=(
                        DatasheetMusteringOptionEffect(
                            kind=DatasheetMusteringOptionEffectKind.ADD_KEYWORD,
                            keyword="KHORNE",
                        ),
                    ),
                ),
            ),
        ),
    )
    factions = (
        FactionDefinition(
            faction_id="chaos-space-marines",
            name="Chaos Space Marines",
            faction_keywords=("Heretic Astartes",),
            source_ids=("phase17g:heretic-astartes",),
        ),
        FactionDefinition(
            faction_id="chaos-daemons",
            name="Chaos Daemons",
            faction_keywords=("Legiones Daemonica",),
            source_ids=("phase17g:legiones-daemonica",),
        ),
    )
    enhancements = (
        EnhancementDefinition(
            enhancement_id="phase17g-dark-gift",
            name="Dark Gift",
            source_id="phase17g:dark-gift",
            points=10,
        ),
    )
    detachments = (
        DetachmentDefinition(
            detachment_id="phase17g-csm-detachment",
            name="Phase 17G CSM Detachment",
            faction_id="chaos-space-marines",
            detachment_point_cost=1,
            unit_datasheet_ids=("phase17g-chaos-legionaries",),
            force_disposition_ids=("phase17g-force",),
            enhancement_ids=("phase17g-dark-gift",),
            source_ids=("phase17g:detachment",),
        ),
    )
    return ArmyCatalog(
        catalog_id="phase17g-daemonic-pact-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-daemonic-pact-source",
        datasheets=datasheets,
        wargear=base_catalog.wargear,
        factions=factions,
        detachments=detachments,
        enhancements=enhancements,
        source_ids=("phase17g:daemonic-pact-catalog",),
    )


def _dreadblades_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    single_model_composition = (
        UnitCompositionDefinition(
            model_profile_id=base_datasheet.model_profiles[0].model_profile_id,
            min_models=1,
            max_models=1,
        ),
    )

    def single_model_datasheet(
        *,
        datasheet_id: str,
        name: str,
        keywords: tuple[str, ...],
        faction_keywords: tuple[str, ...],
    ) -> DatasheetDefinition:
        return replace(
            _phase17g_datasheet(
                base_datasheet,
                datasheet_id=datasheet_id,
                name=name,
                keywords=keywords,
                faction_keywords=faction_keywords,
            ),
            composition=single_model_composition,
        )

    datasheets = (
        single_model_datasheet(
            datasheet_id="phase17g-chaos-lord",
            name="Chaos Lord",
            keywords=("Character", "Chaos", "Heretic Astartes", "Infantry"),
            faction_keywords=("Heretic Astartes",),
        ),
        single_model_datasheet(
            datasheet_id="phase17g-tainted-mutant",
            name="Tainted Mutant",
            keywords=("Character", "Heretic Astartes", "Infantry"),
            faction_keywords=("Heretic Astartes",),
        ),
        single_model_datasheet(
            datasheet_id="phase17g-war-dog-stalker",
            name="War Dog Stalker",
            keywords=("Chaos", "Vehicle", "War Dog"),
            faction_keywords=("Chaos Knights",),
        ),
        single_model_datasheet(
            datasheet_id="phase17g-knight-abominant",
            name="Knight Abominant",
            keywords=("Character", "Chaos", "Titanic", "Vehicle"),
            faction_keywords=("Chaos Knights",),
        ),
    )
    factions = (
        FactionDefinition(
            faction_id="chaos-space-marines",
            name="Chaos Space Marines",
            faction_keywords=("Heretic Astartes",),
            source_ids=("phase17g:heretic-astartes",),
        ),
        FactionDefinition(
            faction_id="chaos-knights",
            name="Chaos Knights",
            faction_keywords=("Chaos Knights",),
            source_ids=("phase17g:chaos-knights",),
        ),
    )
    enhancements = (
        EnhancementDefinition(
            enhancement_id="phase17g-dark-panoply",
            name="Dark Panoply",
            source_id="phase17g:dark-panoply",
            points=20,
        ),
    )
    detachments = (
        DetachmentDefinition(
            detachment_id="phase17g-csm-detachment",
            name="Phase 17G CSM Detachment",
            faction_id="chaos-space-marines",
            detachment_point_cost=1,
            unit_datasheet_ids=("phase17g-chaos-lord", "phase17g-tainted-mutant"),
            force_disposition_ids=("phase17g-force",),
            enhancement_ids=("phase17g-dark-panoply",),
            source_ids=("phase17g:csm-detachment",),
        ),
    )
    return ArmyCatalog(
        catalog_id="phase17g-dreadblades-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-dreadblades-source",
        datasheets=datasheets,
        wargear=base_catalog.wargear,
        factions=factions,
        detachments=detachments,
        enhancements=enhancements,
        source_ids=("phase17g:dreadblades-catalog",),
    )


def _cult_of_dark_gods_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    datasheets = (
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-chaos-legionaries",
            name="Chaos Legionaries",
            keywords=("Battleline", "Character", "Chaos", "Heretic Astartes", "Infantry"),
            faction_keywords=("Heretic Astartes",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-khorne-berzerkers",
            name="Khorne Berzerkers",
            keywords=("Battleline", "Chaos", "Infantry", "Khorne"),
            faction_keywords=("World Eaters",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-rubric-marines",
            name="Rubric Marines",
            keywords=("Battleline", "Chaos", "Infantry", "Tzeentch"),
            faction_keywords=("Thousand Sons",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-plague-marines",
            name="Plague Marines",
            keywords=("Battleline", "Chaos", "Infantry", "Nurgle"),
            faction_keywords=("Death Guard",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-noise-marines",
            name="Noise Marines",
            keywords=("Battleline", "Chaos", "Infantry", "Slaanesh"),
            faction_keywords=("Emperor's Children",),
        ),
    )
    factions = (
        FactionDefinition(
            faction_id="chaos-space-marines",
            name="Chaos Space Marines",
            faction_keywords=("Heretic Astartes",),
            source_ids=("phase17g:heretic-astartes",),
        ),
        FactionDefinition(
            faction_id="world-eaters",
            name="World Eaters",
            faction_keywords=("World Eaters",),
            source_ids=("phase17g:world-eaters",),
        ),
        FactionDefinition(
            faction_id="thousand-sons",
            name="Thousand Sons",
            faction_keywords=("Thousand Sons",),
            source_ids=("phase17g:thousand-sons",),
        ),
        FactionDefinition(
            faction_id="death-guard",
            name="Death Guard",
            faction_keywords=("Death Guard",),
            source_ids=("phase17g:death-guard",),
        ),
        FactionDefinition(
            faction_id="emperors-children",
            name="Emperor's Children",
            faction_keywords=("Emperor's Children",),
            source_ids=("phase17g:emperors-children",),
        ),
    )
    detachments = (
        DetachmentDefinition(
            detachment_id="phase17g-csm-detachment",
            name="Phase 17G CSM Detachment",
            faction_id="chaos-space-marines",
            detachment_point_cost=1,
            unit_datasheet_ids=("phase17g-chaos-legionaries",),
            force_disposition_ids=("phase17g-force",),
            source_ids=("phase17g:csm-detachment",),
        ),
    )
    return ArmyCatalog(
        catalog_id="phase17g-cult-of-dark-gods-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-cult-of-dark-gods-source",
        datasheets=datasheets,
        wargear=base_catalog.wargear,
        factions=factions,
        detachments=detachments,
        source_ids=("phase17g:cult-of-dark-gods-catalog",),
    )


def _forbidden_pact_faction_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    datasheet = _phase17g_datasheet(
        base_datasheet,
        datasheet_id="phase17g-daemonettes",
        name="Daemonettes",
        keywords=("Battleline", "Infantry", "Slaanesh"),
        faction_keywords=("Legions of Excess",),
    )
    forbidden_factions = (
        ("legions-of-excess", "Legions of Excess"),
        ("plague-legions", "Plague Legions"),
        ("blood-legions", "Blood Legions"),
        ("scintillating-legions", "Scintillating Legions"),
    )
    factions = tuple(
        FactionDefinition(
            faction_id=faction_id,
            name=name,
            faction_keywords=(name,),
            source_ids=(f"phase17g:{faction_id}",),
        )
        for faction_id, name in forbidden_factions
    )
    detachments = tuple(
        DetachmentDefinition(
            detachment_id=f"phase17g-{faction_id}-detachment",
            name=f"Phase 17G {name} Detachment",
            faction_id=faction_id,
            detachment_point_cost=1,
            unit_datasheet_ids=("phase17g-daemonettes",),
            force_disposition_ids=("phase17g-force",),
            source_ids=(f"phase17g:{faction_id}:detachment",),
        )
        for faction_id, name in forbidden_factions
    )
    return ArmyCatalog(
        catalog_id="phase17g-forbidden-pact-factions-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-forbidden-pact-factions-source",
        datasheets=(datasheet,),
        wargear=base_catalog.wargear,
        factions=factions,
        detachments=detachments,
        source_ids=("phase17g:forbidden-pact-factions-catalog",),
    )


def _drukhari_corsairs_and_travelling_players_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    datasheets = (
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-drukhari-archon",
            name="Archon",
            keywords=("Character", "Infantry", "Drukhari"),
            faction_keywords=("Drukhari",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-harlequin-troupe-master",
            name="Troupe Master",
            keywords=("Character", "Infantry", "Harlequins"),
            faction_keywords=("Aeldari", "Harlequins"),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-corsair-voidscarred",
            name="Corsair Voidscarred",
            keywords=("Anhrathe", "Infantry"),
            faction_keywords=("Aeldari",),
        ),
        _phase17g_datasheet(
            base_datasheet,
            datasheet_id="phase17g-imperial-outsider",
            name="Imperial Outsider",
            keywords=("Character", "Infantry"),
            faction_keywords=("Imperium",),
        ),
    )
    factions = (
        FactionDefinition(
            faction_id="drukhari",
            name="Drukhari",
            faction_keywords=("Drukhari",),
            source_ids=("phase17g:drukhari",),
        ),
        FactionDefinition(
            faction_id="aeldari",
            name="Aeldari",
            faction_keywords=("Aeldari",),
            source_ids=("phase17g:aeldari",),
        ),
        FactionDefinition(
            faction_id="imperium",
            name="Imperium",
            faction_keywords=("Imperium",),
            source_ids=("phase17g:imperium",),
        ),
    )
    enhancements = (
        EnhancementDefinition(
            enhancement_id="phase17g-soul-trap",
            name="Soul Trap",
            source_id="phase17g:soul-trap",
            points=15,
        ),
    )
    detachments = (
        DetachmentDefinition(
            detachment_id="phase17g-drukhari-detachment",
            name="Phase 17G Drukhari Detachment",
            faction_id="drukhari",
            detachment_point_cost=1,
            unit_datasheet_ids=("phase17g-drukhari-archon",),
            force_disposition_ids=("phase17g-force",),
            enhancement_ids=("phase17g-soul-trap",),
            source_ids=("phase17g:drukhari-detachment",),
        ),
    )
    return ArmyCatalog(
        catalog_id="phase17g-drukhari-corsairs-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-drukhari-corsairs-source",
        datasheets=datasheets,
        wargear=base_catalog.wargear,
        factions=factions,
        detachments=detachments,
        enhancements=enhancements,
        source_ids=("phase17g:drukhari-corsairs-catalog",),
    )


def _freeblades_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    single_model_composition = (
        UnitCompositionDefinition(
            model_profile_id=base_datasheet.model_profiles[0].model_profile_id,
            min_models=1,
            max_models=1,
        ),
    )

    def single_model_datasheet(
        *,
        datasheet_id: str,
        name: str,
        keywords: tuple[str, ...],
        faction_keywords: tuple[str, ...],
    ) -> DatasheetDefinition:
        return replace(
            _phase17g_datasheet(
                base_datasheet,
                datasheet_id=datasheet_id,
                name=name,
                keywords=keywords,
                faction_keywords=faction_keywords,
            ),
            composition=single_model_composition,
        )

    datasheets = (
        single_model_datasheet(
            datasheet_id="phase17g-space-marine-captain",
            name="Space Marine Captain",
            keywords=("Character", "Infantry", "Adeptus Astartes"),
            faction_keywords=("Adeptus Astartes", "Imperium"),
        ),
        single_model_datasheet(
            datasheet_id="phase17g-tau-commander",
            name="Tau Commander",
            keywords=("Character", "Infantry", "Tau Empire"),
            faction_keywords=("Tau Empire",),
        ),
        single_model_datasheet(
            datasheet_id="phase17g-armiger-warglaive",
            name="Armiger Warglaive",
            keywords=("Armiger", "Vehicle"),
            faction_keywords=("Imperial Knights", "Imperium"),
        ),
        single_model_datasheet(
            datasheet_id="phase17g-knight-crusader",
            name="Knight Crusader",
            keywords=("Character", "Titanic", "Vehicle"),
            faction_keywords=("Imperial Knights", "Imperium"),
        ),
    )
    factions = (
        FactionDefinition(
            faction_id="adeptus-astartes",
            name="Adeptus Astartes",
            faction_keywords=("Adeptus Astartes", "Imperium"),
            source_ids=("phase17g:adeptus-astartes",),
        ),
        FactionDefinition(
            faction_id="tau-empire",
            name="Tau Empire",
            faction_keywords=("Tau Empire",),
            source_ids=("phase17g:tau-empire",),
        ),
        FactionDefinition(
            faction_id="imperial-knights",
            name="Imperial Knights",
            faction_keywords=("Imperial Knights", "Imperium"),
            source_ids=("phase17g:imperial-knights",),
        ),
    )
    enhancements = (
        EnhancementDefinition(
            enhancement_id="phase17g-master-crafted",
            name="Master-crafted Weapon",
            source_id="phase17g:master-crafted",
            points=20,
        ),
    )
    detachments = (
        DetachmentDefinition(
            detachment_id="phase17g-adeptus-astartes-detachment",
            name="Phase 17G Adeptus Astartes Detachment",
            faction_id="adeptus-astartes",
            detachment_point_cost=1,
            unit_datasheet_ids=("phase17g-space-marine-captain",),
            force_disposition_ids=("phase17g-force",),
            enhancement_ids=("phase17g-master-crafted",),
            source_ids=("phase17g:adeptus-astartes-detachment",),
        ),
        DetachmentDefinition(
            detachment_id="phase17g-tau-detachment",
            name="Phase 17G Tau Detachment",
            faction_id="tau-empire",
            detachment_point_cost=1,
            unit_datasheet_ids=("phase17g-tau-commander",),
            force_disposition_ids=("phase17g-force",),
            enhancement_ids=("phase17g-master-crafted",),
            source_ids=("phase17g:tau-detachment",),
        ),
    )
    return ArmyCatalog(
        catalog_id="phase17g-freeblades-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-freeblades-source",
        datasheets=datasheets,
        wargear=base_catalog.wargear,
        factions=factions,
        detachments=detachments,
        enhancements=enhancements,
        source_ids=("phase17g:freeblades-catalog",),
    )


def _phase17g_datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=faction_keywords,
        ),
        attachment_eligibilities=(),
    )


def _daemonic_pact_request(
    catalog: ArmyCatalog,
    *,
    unit_points: tuple[RosterUnitPointValue, ...],
    warlord_selection: WarlordSelection,
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
) -> ArmyMusterRequest:
    return _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="chaos-space-marines",
            detachment_ids=("phase17g-csm-detachment",),
            enhancement_ids=tuple(
                assignment.enhancement_id for assignment in enhancement_assignments
            ),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id="legionaries",
                datasheet_id="phase17g-chaos-legionaries",
            ),
            _unit_selection(
                unit_selection_id="bloodletters",
                datasheet_id="phase17g-bloodletters",
            ),
            _unit_selection(
                unit_selection_id="bloodthirster",
                datasheet_id="phase17g-bloodthirster",
            ),
            *(
                (
                    _unit_selection(
                        unit_selection_id="skull-cannon",
                        datasheet_id="phase17g-skull-cannon",
                    ),
                )
                if any(point.unit_selection_id == "skull-cannon" for point in unit_points)
                else ()
            ),
        ),
        unit_points=unit_points,
        enhancement_assignments=enhancement_assignments,
        warlord_selection=warlord_selection,
    )


def _dreadblades_request(
    catalog: ArmyCatalog,
    *,
    unit_points: tuple[RosterUnitPointValue, ...],
    warlord_selection: WarlordSelection,
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
    war_dog_count: int = 0,
    include_titanic: bool = False,
    base_datasheet_id: str = "phase17g-chaos-lord",
) -> ArmyMusterRequest:
    base_selection_id = "chaos-lord" if base_datasheet_id == "phase17g-chaos-lord" else "mutant"
    war_dog_selections = tuple(
        _unit_selection(
            unit_selection_id=f"war-dog-{index}",
            datasheet_id="phase17g-war-dog-stalker",
            model_count=1,
        )
        for index in range(1, war_dog_count + 1)
    )
    titanic_selections = (
        (
            _unit_selection(
                unit_selection_id="knight-abominant",
                datasheet_id="phase17g-knight-abominant",
                model_count=1,
            ),
        )
        if include_titanic
        else ()
    )
    return _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="chaos-space-marines",
            detachment_ids=("phase17g-csm-detachment",),
            enhancement_ids=tuple(
                assignment.enhancement_id for assignment in enhancement_assignments
            ),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id=base_selection_id,
                datasheet_id=base_datasheet_id,
                model_count=1,
            ),
            *war_dog_selections,
            *titanic_selections,
        ),
        unit_points=unit_points,
        enhancement_assignments=enhancement_assignments,
        warlord_selection=warlord_selection,
    )


def _cult_of_dark_gods_request(
    catalog: ArmyCatalog,
    *,
    unit_points: tuple[RosterUnitPointValue, ...],
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> ArmyMusterRequest:
    return _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="chaos-space-marines",
            detachment_ids=("phase17g-csm-detachment",),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id="legionaries",
                datasheet_id="phase17g-chaos-legionaries",
            ),
            _unit_selection(
                unit_selection_id="khorne-berzerkers",
                datasheet_id="phase17g-khorne-berzerkers",
            ),
            _unit_selection(
                unit_selection_id="rubric-marines",
                datasheet_id="phase17g-rubric-marines",
            ),
            _unit_selection(
                unit_selection_id="plague-marines",
                datasheet_id="phase17g-plague-marines",
            ),
            _unit_selection(
                unit_selection_id="noise-marines",
                datasheet_id="phase17g-noise-marines",
            ),
        ),
        unit_points=unit_points,
        warlord_selection=WarlordSelection(
            unit_selection_id="legionaries",
            source_id="phase17g:warlord",
        ),
        battle_size=battle_size,
    )


def _drukhari_corsairs_and_travelling_players_request(
    catalog: ArmyCatalog,
    *,
    unit_points: tuple[RosterUnitPointValue, ...],
    warlord_selection: WarlordSelection,
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
    include_outsider: bool = False,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> ArmyMusterRequest:
    return _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="drukhari",
            detachment_ids=("phase17g-drukhari-detachment",),
            enhancement_ids=tuple(
                assignment.enhancement_id for assignment in enhancement_assignments
            ),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id="archon",
                datasheet_id="phase17g-drukhari-archon",
            ),
            _unit_selection(
                unit_selection_id="troupe-master",
                datasheet_id="phase17g-harlequin-troupe-master",
            ),
            _unit_selection(
                unit_selection_id="voidscarred",
                datasheet_id="phase17g-corsair-voidscarred",
            ),
            *(
                (
                    _unit_selection(
                        unit_selection_id="outsider",
                        datasheet_id="phase17g-imperial-outsider",
                    ),
                )
                if include_outsider
                else ()
            ),
        ),
        unit_points=unit_points,
        enhancement_assignments=enhancement_assignments,
        warlord_selection=warlord_selection,
        battle_size=battle_size,
    )


def _freeblades_request(
    catalog: ArmyCatalog,
    *,
    unit_points: tuple[RosterUnitPointValue, ...],
    warlord_selection: WarlordSelection,
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
    armiger_count: int = 0,
    include_titanic: bool = False,
    faction_id: str = "adeptus-astartes",
) -> ArmyMusterRequest:
    if faction_id == "adeptus-astartes":
        base_selection_id = "captain"
        base_datasheet_id = "phase17g-space-marine-captain"
        detachment_id = "phase17g-adeptus-astartes-detachment"
    elif faction_id == "tau-empire":
        base_selection_id = "commander"
        base_datasheet_id = "phase17g-tau-commander"
        detachment_id = "phase17g-tau-detachment"
    else:
        raise AssertionError("unsupported Freeblades test faction")
    armiger_selections = tuple(
        _unit_selection(
            unit_selection_id=f"armiger-{index}",
            datasheet_id="phase17g-armiger-warglaive",
            model_count=1,
        )
        for index in range(1, armiger_count + 1)
    )
    titanic_selections = (
        (
            _unit_selection(
                unit_selection_id="knight-crusader",
                datasheet_id="phase17g-knight-crusader",
                model_count=1,
            ),
        )
        if include_titanic
        else ()
    )
    return _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
            enhancement_ids=tuple(
                assignment.enhancement_id for assignment in enhancement_assignments
            ),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id=base_selection_id,
                datasheet_id=base_datasheet_id,
                model_count=1,
            ),
            *armiger_selections,
            *titanic_selections,
        ),
        unit_points=unit_points,
        enhancement_assignments=enhancement_assignments,
        warlord_selection=warlord_selection,
    )


def _unit_points(unit_selection_id: str, points: int) -> RosterUnitPointValue:
    return RosterUnitPointValue(
        unit_selection_id=unit_selection_id,
        points=points,
        source_id=f"phase17g:points:{unit_selection_id}",
    )


def _phase16d_transport_roster_request(
    catalog: ArmyCatalog,
    *,
    army_id: str = "army-alpha",
    player_id: str = "player-a",
    enhancement_assignments: tuple[EnhancementAssignment, ...] | None = None,
    dedicated_transport_manifests: tuple[DedicatedTransportManifest, ...] | None = None,
    include_support: bool = False,
) -> ArmyMusterRequest:
    units = [
        _unit_selection(unit_selection_id="bodyguard-unit"),
        _unit_selection(
            unit_selection_id="leader-unit",
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            model_count=1,
        ),
        _unit_selection(
            unit_selection_id="transport-unit",
            datasheet_id="core-transport",
            model_profile_id="core-transport",
            model_count=1,
        ),
    ]
    attachment_declarations = [
        AttachmentDeclaration(
            source_unit_selection_id="leader-unit",
            bodyguard_unit_selection_id="bodyguard-unit",
        )
    ]
    if include_support:
        units.append(
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            )
        )
        attachment_declarations.append(
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            )
        )
    assignments = (
        (
            EnhancementAssignment(
                enhancement_id="core-enhancement-a",
                target_unit_selection_id="leader-unit",
                source_id="assignment:leader",
            ),
        )
        if enhancement_assignments is None
        else enhancement_assignments
    )
    cargo_ids = (
        ("bodyguard-unit", "leader-unit", "support-unit")
        if include_support
        else (
            "bodyguard-unit",
            "leader-unit",
        )
    )
    manifests = (
        (
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=cargo_ids,
                capacity_profile=_transport_capacity(max_model_count=7 if include_support else 6),
                source_id="manifest:transport-unit",
            ),
        )
        if dedicated_transport_manifests is None
        else dedicated_transport_manifests
    )
    return _muster_request(
        catalog,
        army_id=army_id,
        player_id=player_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=tuple(
                sorted({assignment.enhancement_id for assignment in assignments})
            ),
        ),
        unit_selections=tuple(units),
        attachment_declarations=tuple(attachment_declarations),
        unit_points=tuple(
            RosterUnitPointValue(
                unit_selection_id=selection.unit_selection_id,
                points=100,
                source_id=f"points:{selection.unit_selection_id}",
            )
            for selection in units
        ),
        enhancement_assignments=assignments,
        warlord_selection=WarlordSelection(
            unit_selection_id="leader-unit",
            source_id="warlord:leader-unit",
        ),
        dedicated_transport_manifests=manifests,
        roster_legality_required=True,
    )


def _transport_capacity(*, max_model_count: int) -> DedicatedTransportCapacityProfile:
    return DedicatedTransportCapacityProfile(
        transport_datasheet_id="core-transport",
        max_model_count=max_model_count,
        allowed_keywords=("Infantry",),
        excluded_keywords=(),
        source_id=f"transport-capacity:core-transport:{max_model_count}",
    )


def _phase16d_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _detachment_by_id(catalog: ArmyCatalog, detachment_id: str) -> DetachmentDefinition:
    matches = tuple(
        detachment
        for detachment in catalog.detachments
        if detachment.detachment_id == detachment_id
    )
    assert len(matches) == 1
    return matches[0]


def test_army_mustering_consumes_catalog_and_produces_runtime_instances() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)

    army = muster_army(catalog=catalog, request=request)
    payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)
    unit = army.unit_by_id("army-alpha:intercessor-unit-1")
    model = unit.own_models[0]

    assert army.stable_identity() == "army:army-alpha"
    assert army.catalog_id == catalog.catalog_id
    assert army.ruleset_id == catalog.ruleset_id
    assert unit.datasheet_id == "core-intercessor-like-infantry"
    assert unit.datasheet_source_ids == ("datasheet:core-intercessor-like-infantry",)
    assert len(unit.own_models) == 5
    assert unit.wargear_selections[0].wargear_ids == ("core-bolt-rifle",)
    assert model.datasheet_id == unit.datasheet_id
    assert model.model_profile_id == "core-intercessor-like"
    assert model.base_size.diameter_mm == 32.0
    assert model.starting_wounds == 2
    assert model.source_ids == (
        "datasheet:core-intercessor-like-infantry",
        "datasheet:core-intercessor-like-infantry:profile",
    )
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert ArmyDefinition.from_payload(payload).to_payload() == army.to_payload()


def test_muster_request_and_runtime_payloads_round_trip_without_object_reprs() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)
    request_payload = cast(
        ArmyMusterRequestPayload,
        json.loads(json.dumps(request.to_payload(), sort_keys=True)),
    )
    request_blob = json.dumps(request_payload, sort_keys=True)
    army = muster_army(catalog=catalog, request=ArmyMusterRequest.from_payload(request_payload))
    unit_payload = json.dumps(army.units[0].to_payload(), sort_keys=True)

    assert "<" not in request_blob
    assert "object at 0x" not in request_blob
    assert "<" not in unit_payload
    assert "object at 0x" not in unit_payload
    assert ArmyMusterRequest.from_payload(request_payload).to_payload() == request.to_payload()


def test_runtime_units_use_explicit_own_model_semantics() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    unit = army.units[0]

    assert isinstance(unit, UnitInstance)
    assert len(unit.own_models) == 5
    assert unit.own_model_ids() == tuple(model.model_instance_id for model in unit.own_models)
    assert not hasattr(unit, "models")


def test_attachment_declarations_form_runtime_attached_unit_from_structured_catalog() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )

    army = muster_army(catalog=catalog, request=request)
    payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    formation = army.attached_units[0]
    bodyguard = army.unit_by_id("army-alpha:bodyguard-unit")
    leader = army.unit_by_id("army-alpha:leader-unit")
    support = army.unit_by_id("army-alpha:support-unit")

    assert formation.attached_unit_instance_id == "attached-unit:army-alpha:bodyguard-unit"
    assert formation.bodyguard_unit_instance_id == bodyguard.unit_instance_id
    assert formation.leader_unit_instance_ids == (leader.unit_instance_id,)
    assert formation.support_unit_instance_ids == (support.unit_instance_id,)
    assert formation.component_unit_instance_ids == (
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
        support.unit_instance_id,
    )
    assert formation.attachment_source_ids == (
        "datasheet:core-character-leader:attachment:leader",
        "datasheet:core-character-support:attachment:support",
    )
    assert "ATTACHED_UNIT" in bodyguard.keywords
    assert "runtime-attached-unit:bodyguard" in bodyguard.own_models[0].source_ids
    assert "attached-role:leader" in leader.own_models[0].source_ids
    assert "runtime-attached-unit:leader" in leader.own_models[0].source_ids
    assert "attached-role:support" in support.own_models[0].source_ids
    assert "runtime-attached-unit:support" in support.own_models[0].source_ids
    assert "<" not in json.dumps(payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)
    assert ArmyDefinition.from_payload(payload).to_payload() == army.to_payload()


def test_support_units_must_be_declared_attached_but_leaders_can_muster_solo() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    support_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
        ),
    )
    leader_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="Support units must be declared"):
        muster_army(catalog=catalog, request=support_request)

    leader_army = muster_army(catalog=catalog, request=leader_request)
    leader = leader_army.unit_by_id("army-alpha:leader-unit")
    assert leader_army.attached_units == ()
    assert "ATTACHED_UNIT" not in leader.keywords


def test_rules_unit_view_resolves_physical_and_mustered_attached_units() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
            _unit_selection(unit_selection_id="loose-unit"),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )
    army = muster_army(catalog=catalog, request=request)
    formation = army.attached_units[0]
    bodyguard = army.unit_by_id("army-alpha:bodyguard-unit")
    leader = army.unit_by_id("army-alpha:leader-unit")
    support = army.unit_by_id("army-alpha:support-unit")
    loose_unit = army.unit_by_id("army-alpha:loose-unit")

    attached_view = rules_unit_view_from_armies(
        armies=(army,),
        unit_instance_id=bodyguard.unit_instance_id,
    )
    physical_view = rules_unit_view_from_armies(
        armies=(army,),
        unit_instance_id=loose_unit.unit_instance_id,
    )

    assert attached_view.unit_instance_id == formation.attached_unit_instance_id
    assert (
        rules_unit_id_for_unit_id(
            armies=(army,),
            unit_instance_id=support.unit_instance_id,
        )
        == formation.attached_unit_instance_id
    )
    assert attached_view.owner_player_id == "player-a"
    assert attached_view.component_unit_instance_ids == (
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
        support.unit_instance_id,
    )
    assert (
        attached_view.component_unit_id_for_model(leader.own_models[0].model_instance_id)
        == leader.unit_instance_id
    )
    assert (
        attached_view.component_role_for_model(support.own_models[0].model_instance_id) == "support"
    )
    assert attached_view.bodyguard_model_ids(attached_view.alive_models()) == tuple(
        model.model_instance_id for model in bodyguard.own_models
    )
    assert attached_view.character_model_ids(attached_view.alive_models()) == (
        leader.own_models[0].model_instance_id,
        support.own_models[0].model_instance_id,
    )
    assert "ATTACHED_UNIT" in attached_view.keywords
    assert "CORE MARINES" in attached_view.faction_keywords
    assert physical_view.unit_instance_id == loose_unit.unit_instance_id
    assert physical_view.attached_unit is None
    assert physical_view.bodyguard_model_ids(physical_view.alive_models()) == ()
    assert physical_view.character_model_ids(physical_view.alive_models()) == ()


def test_rules_unit_projection_value_objects_fail_fast() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    unit = army.units[0]
    component = RulesUnitComponent(unit=unit, role="unit")

    with pytest.raises(GameLifecycleError, match="UnitInstance"):
        RulesUnitComponent(unit=cast(UnitInstance, "bad-unit"), role="unit")
    with pytest.raises(GameLifecycleError, match="unsupported role"):
        RulesUnitComponent(unit=unit, role=cast(RulesUnitComponentRole, "bad-role"))
    with pytest.raises(GameLifecycleError, match="components must be a tuple"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=cast(tuple[RulesUnitComponent, ...], [component]),
        )
    with pytest.raises(GameLifecycleError, match="requires at least one component"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(),
        )
    with pytest.raises(GameLifecycleError, match="RulesUnitComponent values"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=cast(tuple[RulesUnitComponent, ...], ("bad-component",)),
        )
    with pytest.raises(GameLifecycleError, match="AttachedUnitFormation"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component,),
            attached_unit=cast(AttachedUnitFormation, "bad-attached-unit"),
        )
    with pytest.raises(GameLifecycleError, match="exactly one component"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component, component),
        )
    with pytest.raises(GameLifecycleError, match="unknown"):
        rules_unit_view_from_armies(armies=(army,), unit_instance_id="missing-unit")
    with pytest.raises(GameLifecycleError, match="not in the rules unit"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component,),
        ).component_unit_id_for_model("missing-model")
    with pytest.raises(GameLifecycleError, match="not in the rules unit"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component,),
        ).component_role_for_model("missing-model")


def test_attachment_declarations_reject_missing_eligibility_and_illegal_bodyguards() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    missing_eligibility_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="source-infantry"),
            _unit_selection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-boyz-like-infantry",
                model_profile_id="core-boyz-like",
                model_count=10,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="source-infantry",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )
    illegal_bodyguard_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-boyz-like-infantry",
                model_profile_id="core-boyz-like",
                model_count=10,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="no attachment eligibility"):
        muster_army(catalog=catalog, request=missing_eligibility_request)
    with pytest.raises(ArmyMusteringError, match="bodyguard datasheet"):
        muster_army(catalog=catalog, request=illegal_bodyguard_request)


def test_attachment_declarations_reject_duplicate_sources_and_duplicate_roles() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    with pytest.raises(ArmyMusteringError, match="unique source unit IDs"):
        _muster_request(
            catalog,
            unit_selections=(
                _unit_selection(unit_selection_id="bodyguard-unit"),
                _unit_selection(unit_selection_id="second-bodyguard-unit"),
                _unit_selection(
                    unit_selection_id="leader-unit",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
            ),
            attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader-unit",
                    bodyguard_unit_selection_id="bodyguard-unit",
                ),
                AttachmentDeclaration(
                    source_unit_selection_id="leader-unit",
                    bodyguard_unit_selection_id="second-bodyguard-unit",
                ),
            ),
        )

    duplicate_role_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="second-leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="second-leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="one Leader or one Support"):
        muster_army(catalog=catalog, request=duplicate_role_request)


def test_runtime_payloads_reject_hierarchy_and_source_drift() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    army_payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    unit_payload = army_payload["units"][0]

    foreign_army_payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army_payload, sort_keys=True)),
    )
    old_unit_id = foreign_army_payload["units"][0]["unit_instance_id"]
    new_unit_id = "other-army:intercessor-unit-1"
    foreign_army_payload["units"][0]["unit_instance_id"] = new_unit_id
    for model_payload in foreign_army_payload["units"][0]["own_models"]:
        model_payload["model_instance_id"] = model_payload["model_instance_id"].replace(
            old_unit_id,
            new_unit_id,
        )
    with pytest.raises(ArmyMusteringError, match="scoped to army_id"):
        ArmyDefinition.from_payload(foreign_army_payload)

    datasheet_mismatch = json.loads(json.dumps(unit_payload, sort_keys=True))
    datasheet_mismatch["own_models"][0]["datasheet_id"] = "other-datasheet"
    with pytest.raises(UnitFactoryError, match="datasheet_id"):
        UnitInstance.from_payload(datasheet_mismatch)

    model_scope_mismatch = json.loads(json.dumps(unit_payload, sort_keys=True))
    model_scope_mismatch["own_models"][0]["model_instance_id"] = "other-unit:model-001"
    with pytest.raises(UnitFactoryError, match="scoped to unit_instance_id"):
        UnitInstance.from_payload(model_scope_mismatch)

    empty_unit_sources = json.loads(json.dumps(unit_payload, sort_keys=True))
    empty_unit_sources["datasheet_source_ids"] = []
    with pytest.raises(UnitFactoryError, match="datasheet_source_ids"):
        UnitInstance.from_payload(empty_unit_sources)

    empty_model_sources = json.loads(json.dumps(unit_payload, sort_keys=True))
    empty_model_sources["own_models"][0]["source_ids"] = []
    with pytest.raises(UnitFactoryError, match="source_ids"):
        UnitInstance.from_payload(empty_model_sources)


def test_selected_wargear_must_be_legal_for_datasheet_option() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    illegal_wargear = WargearSelection(
        option_id="core-intercessor-like-infantry:default-wargear",
        model_profile_id="core-intercessor-like",
        wargear_ids=("core-heavy-cannon",),
    )
    request = _muster_request(
        catalog,
        unit_selections=(_unit_selection(wargear_selections=(illegal_wargear,)),),
    )

    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=catalog, request=request)


def test_model_profile_counts_must_match_datasheet_composition() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(
        catalog,
        unit_selections=(_unit_selection(model_count=4),),
    )

    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=catalog, request=request)


def test_detachment_enhancement_and_stratagem_selections_are_validated_as_data() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    enhancement = EnhancementDefinition(
        enhancement_id="core-enhancement",
        name="Core Enhancement",
        source_id="enhancement:core-enhancement",
    )
    stratagem = StratagemDefinition(
        stratagem_id="core-stratagem",
        name="Core Stratagem",
        source_id="stratagem:core-stratagem",
        command_point_cost=1,
    )
    detachment = replace(
        catalog.detachments[0],
        enhancement_ids=(enhancement.enhancement_id,),
        stratagem_ids=(stratagem.stratagem_id,),
    )
    catalog_with_content = ArmyCatalog(
        catalog_id="phase9c-with-detachment-content",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(detachment,),
        enhancements=(enhancement,),
        stratagems=(stratagem,),
        source_ids=catalog.source_ids,
    )
    valid_request = _muster_request(
        catalog_with_content,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=(enhancement.enhancement_id,),
            stratagem_ids=(stratagem.stratagem_id,),
        ),
    )
    invalid_request = _muster_request(
        catalog_with_content,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=("not-allowed",),
        ),
    )

    army = muster_army(catalog=catalog_with_content, request=valid_request)
    assert army.detachment_selection == valid_request.detachment_selection
    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=catalog_with_content, request=invalid_request)


def test_supported_battle_size_policies_are_source_backed() -> None:
    incursion = BattleSizeMusteringPolicy.incursion()
    policy = BattleSizeMusteringPolicy.strike_force()
    onslaught = BattleSizeMusteringPolicy.onslaught()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)

    assert incursion.points_limit == 1000
    assert incursion.battlefield_width_inches == 44.0
    assert incursion.battlefield_depth_inches == 30.0
    assert incursion.detachment_point_limit == 2
    assert policy.points_limit == 2000
    assert policy.battlefield_width_inches == 60.0
    assert policy.battlefield_depth_inches == 44.0
    assert policy.detachment_point_limit == 3
    assert policy.enhancement_limit == 4
    assert policy.unit_limit == 3
    assert policy.battleline_unit_limit == 6
    assert onslaught.points_limit == 3000
    assert onslaught.battlefield_width_inches == 90.0
    assert onslaught.battlefield_depth_inches == 44.0
    assert onslaught.detachment_point_limit == 4
    assert muster_army(catalog=catalog, request=request).battle_size.value == "strike_force"

    with pytest.raises(ListValidationError, match="Unsupported BattleSize"):
        battle_size_from_token("combat_patrol")
    with pytest.raises(ArmyMusteringError, match="battle_size"):
        replace(request, battle_size=cast(BattleSize, "combat_patrol"))


def test_strike_force_detachment_points_force_dispositions_and_unit_grants() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_detachment = catalog.detachments[0]
    vanguard_detachment = replace(
        base_detachment,
        detachment_id="core-vanguard",
        name="CORE Vanguard",
        detachment_point_cost=2,
        unit_datasheet_ids=("core-intercessor-like-infantry",),
        force_disposition_ids=("reconnaissance",),
        source_ids=("detachment:core-vanguard",),
    )
    support_detachment = replace(
        base_detachment,
        detachment_id="core-support",
        name="CORE Support",
        detachment_point_cost=1,
        unit_datasheet_ids=("core-character-leader", "core-intercessor-like-infantry"),
        force_disposition_ids=("take-and-hold",),
        source_ids=("detachment:core-support",),
    )
    multi_detachment_catalog = ArmyCatalog(
        catalog_id="phase16d-multi-detachment",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(base_detachment, support_detachment, vanguard_detachment),
        source_ids=catalog.source_ids,
    )
    legal_selection = DetachmentSelection(
        faction_id="core-marine-force",
        detachment_ids=("core-support", "core-vanguard"),
    )
    over_limit_selection = DetachmentSelection(
        faction_id="core-marine-force",
        detachment_ids=("core-combined-arms", "core-support", "core-vanguard"),
    )
    unsupported_unit_request = _muster_request(
        multi_detachment_catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-vanguard",),
        ),
        unit_selections=(
            _unit_selection(
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )

    faction, detachments = validate_detachment_selection(
        catalog=multi_detachment_catalog,
        selection=legal_selection,
    )
    army = muster_army(
        catalog=multi_detachment_catalog,
        request=_muster_request(multi_detachment_catalog, detachment_selection=legal_selection),
    )

    assert faction.faction_id == "core-marine-force"
    assert tuple(detachment.detachment_id for detachment in detachments) == (
        "core-support",
        "core-vanguard",
    )
    assert army.detachment_selection.detachment_ids == ("core-support", "core-vanguard")
    assert selected_force_disposition_ids(
        catalog=multi_detachment_catalog,
        selection=legal_selection,
    ) == ("reconnaissance", "take-and-hold")
    with pytest.raises(ListValidationError, match="Detachment Points"):
        validate_detachment_selection(
            catalog=multi_detachment_catalog,
            selection=over_limit_selection,
        )
    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=multi_detachment_catalog, request=unsupported_unit_request)


def test_phase16d_strict_roster_records_warlord_enhancement_and_transport_manifest() -> None:
    catalog = _phase16d_catalog()
    request = _phase16d_transport_roster_request(catalog)

    army = muster_army(catalog=catalog, request=request)
    payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    leader = army.unit_by_id("army-alpha:leader-unit")
    manifest = army.dedicated_transport_manifests[0]

    assert army.roster_legality_report.is_legal
    assert army.warlord_selection == request.warlord_selection
    assert "WARLORD" in leader.keywords
    assert army.enhancement_assignments == request.enhancement_assignments
    assert manifest.transport_unit_instance_id(army_id=army.army_id) == (
        "army-alpha:transport-unit"
    )
    assert manifest.embarked_unit_instance_ids(army_id=army.army_id) == (
        "army-alpha:bodyguard-unit",
        "army-alpha:leader-unit",
    )
    assert "<" not in json.dumps(payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)
    assert ArmyDefinition.from_payload(payload).to_payload() == army.to_payload()


def test_phase16d_strict_roster_reports_missing_source_data_and_unit_limits() -> None:
    catalog = _phase16d_catalog()
    request = _muster_request(
        catalog,
        unit_selections=tuple(
            _unit_selection(
                unit_selection_id=f"mob-{index}",
                datasheet_id="core-boyz-like-infantry",
                model_profile_id="core-boyz-like",
                model_count=10,
            )
            for index in range(1, 5)
        ),
        roster_legality_required=True,
    )

    report = validate_roster_legality(catalog=catalog, request=request)
    violation_codes = {violation.violation_code for violation in report.violations}

    assert not report.is_legal
    assert {
        "missing_warlord_selection",
        "source_awaiting_unit_points",
        "unit_limit_exceeded",
    } <= violation_codes
    with pytest.raises(ArmyMusteringError, match="RosterLegalityReport is invalid"):
        muster_army(catalog=catalog, request=request)


def test_mustering_allows_multiple_supreme_commanders_when_one_is_warlord() -> None:
    catalog = _supreme_commander_catalog()
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="leader-one",
                datasheet_id="test-supreme-commander-alpha",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="leader-two",
                datasheet_id="test-supreme-commander-beta",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="leader-one",
                points=100,
                source_id="points:leader-one",
            ),
            RosterUnitPointValue(
                unit_selection_id="leader-two",
                points=100,
                source_id="points:leader-two",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="leader-two",
            source_id="warlord:leader-two",
        ),
        roster_legality_required=True,
    )

    army = muster_army(catalog=catalog, request=request)
    keywords_by_unit_id = {unit.unit_instance_id: unit.keywords for unit in army.units}

    assert army.roster_legality_report.is_legal
    assert "WARLORD" not in keywords_by_unit_id["army-alpha:leader-one"]
    assert "WARLORD" in keywords_by_unit_id["army-alpha:leader-two"]


def test_mustering_requires_warlord_to_be_an_eligible_supreme_commander() -> None:
    catalog = _supreme_commander_catalog(supreme_datasheet_ids=("test-supreme-commander-alpha",))
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="supreme-commander",
                datasheet_id="test-supreme-commander-alpha",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="regular-character",
                datasheet_id="test-regular-character",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="supreme-commander",
                points=100,
                source_id="points:supreme-commander",
            ),
            RosterUnitPointValue(
                unit_selection_id="regular-character",
                points=100,
                source_id="points:regular-character",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="regular-character",
            source_id="warlord:regular-character",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)
    army = muster_army(catalog=catalog, request=request)

    assert "supreme_commander_warlord_required" in {
        violation.violation_code for violation in report.violations
    }
    assert all("WARLORD" not in unit.keywords for unit in army.units)


def test_mustering_warlord_forbidden_rule_takes_precedence_over_supreme_commander() -> None:
    catalog = _supreme_commander_catalog(
        forbidden_datasheet_ids=("test-supreme-commander-alpha",),
    )
    legal_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="forbidden-supreme",
                datasheet_id="test-supreme-commander-alpha",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="eligible-supreme",
                datasheet_id="test-supreme-commander-beta",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="forbidden-supreme",
                points=100,
                source_id="points:forbidden-supreme",
            ),
            RosterUnitPointValue(
                unit_selection_id="eligible-supreme",
                points=100,
                source_id="points:eligible-supreme",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="eligible-supreme",
            source_id="warlord:eligible-supreme",
        ),
        roster_legality_required=True,
    )
    forbidden_request = replace(
        legal_request,
        warlord_selection=WarlordSelection(
            unit_selection_id="forbidden-supreme",
            source_id="warlord:forbidden-supreme",
        ),
        roster_legality_required=False,
    )

    legal_army = muster_army(catalog=catalog, request=legal_request)
    forbidden_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=forbidden_request,
        ).violations
    }

    assert legal_army.roster_legality_report.is_legal
    assert "WARLORD" in legal_army.unit_by_id("army-alpha:eligible-supreme").keywords
    assert {"supreme_commander_warlord_required", "warlord_forbidden"} <= forbidden_codes


def test_mustering_reports_conflict_when_all_supreme_commanders_cannot_be_warlord() -> None:
    catalog = _supreme_commander_catalog(
        forbidden_datasheet_ids=(
            "test-supreme-commander-alpha",
            "test-supreme-commander-beta",
        ),
    )
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="blocked-supreme-one",
                datasheet_id="test-supreme-commander-alpha",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="blocked-supreme-two",
                datasheet_id="test-supreme-commander-beta",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="regular-character",
                datasheet_id="test-regular-character",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="blocked-supreme-one",
                points=100,
                source_id="points:blocked-supreme-one",
            ),
            RosterUnitPointValue(
                unit_selection_id="blocked-supreme-two",
                points=100,
                source_id="points:blocked-supreme-two",
            ),
            RosterUnitPointValue(
                unit_selection_id="regular-character",
                points=100,
                source_id="points:regular-character",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="regular-character",
            source_id="warlord:regular-character",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)
    army = muster_army(catalog=catalog, request=request)
    violation_codes = {violation.violation_code for violation in report.violations}

    assert "supreme_commander_warlord_conflict" in violation_codes
    assert all("WARLORD" not in unit.keywords for unit in army.units)


def test_mustering_reports_conflict_when_supreme_commander_is_not_a_character() -> None:
    catalog = _supreme_commander_catalog(
        supreme_datasheet_ids=("test-supreme-commander-alpha",),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                datasheet,
                keywords=DatasheetKeywordSet(
                    keywords=tuple(
                        keyword
                        for keyword in datasheet.keywords.keywords
                        if keyword.upper() != "CHARACTER"
                    ),
                    faction_keywords=datasheet.keywords.faction_keywords,
                ),
            )
            if datasheet.datasheet_id == "test-supreme-commander-alpha"
            else datasheet
            for datasheet in catalog.datasheets
        ),
    )
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="non-character-supreme",
                datasheet_id="test-supreme-commander-alpha",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="regular-character",
                datasheet_id="test-regular-character",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="non-character-supreme",
                points=100,
                source_id="points:non-character-supreme",
            ),
            RosterUnitPointValue(
                unit_selection_id="regular-character",
                points=100,
                source_id="points:regular-character",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="regular-character",
            source_id="warlord:regular-character",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert "supreme_commander_warlord_conflict" in {
        violation.violation_code for violation in report.violations
    }


def test_mustering_rejects_unsupported_warlord_mustering_descriptor() -> None:
    catalog = _supreme_commander_catalog(supreme_datasheet_ids=())
    invalid_ability = _warlord_mustering_ability(
        ability_id="test-regular-character:invalid-warlord-mustering",
        name="Invalid Warlord Mustering",
        value="unknown",
    )
    catalog = _catalog_with_datasheet_ability(
        catalog,
        datasheet_id="test-regular-character",
        ability=invalid_ability,
    )
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="regular-character",
                datasheet_id="test-regular-character",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="regular-character",
                points=100,
                source_id="points:regular-character",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="regular-character",
            source_id="warlord:regular-character",
        ),
    )

    with pytest.raises(
        ArmyMusteringError, match="mustering_warlord descriptor value is unsupported"
    ):
        validate_roster_legality(catalog=catalog, request=request)


def test_mustering_rejects_non_string_warlord_mustering_descriptor() -> None:
    catalog = _supreme_commander_catalog(supreme_datasheet_ids=())
    invalid_ability = DatasheetAbilityDescriptor(
        ability_id="test-regular-character:non-string-warlord-mustering",
        name="Invalid Warlord Mustering",
        source_id="datasheet:test-regular-character:non-string-warlord-mustering",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Malformed mustering descriptor.",
        timing_tags=("mustering", "warlord"),
        rule_ir_payload={MUSTERING_WARLORD_RULE_KEY: 1},
    )
    catalog = _catalog_with_datasheet_ability(
        catalog,
        datasheet_id="test-regular-character",
        ability=invalid_ability,
    )
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="regular-character",
                datasheet_id="test-regular-character",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="regular-character",
                points=100,
                source_id="points:regular-character",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="regular-character",
            source_id="warlord:regular-character",
        ),
    )

    with pytest.raises(
        ArmyMusteringError, match="mustering_warlord descriptor value must be a string"
    ):
        validate_roster_legality(catalog=catalog, request=request)


def test_mustering_allied_supreme_commander_cannot_override_warlord_restriction() -> None:
    catalog = _catalog_with_datasheet_ability(
        _daemonic_pact_catalog(),
        datasheet_id="phase17g-bloodthirster",
        ability=_warlord_mustering_ability(
            ability_id="phase17g-bloodthirster:supreme-commander",
            name="SUPREME COMMANDER",
            value=MUSTERING_WARLORD_REQUIRED,
        ),
    )
    request = _daemonic_pact_request(
        catalog,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("bloodthirster", 250),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="legionaries",
            source_id="phase17g:warlord",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert "supreme_commander_warlord_conflict" in {
        violation.violation_code for violation in report.violations
    }


def test_mustering_drukhari_allied_supreme_commander_cannot_override_warlord_restriction() -> None:
    catalog = _catalog_with_datasheet_ability(
        _drukhari_corsairs_and_travelling_players_catalog(),
        datasheet_id="phase17g-harlequin-troupe-master",
        ability=_warlord_mustering_ability(
            ability_id="phase17g-harlequin-troupe-master:supreme-commander",
            name="SUPREME COMMANDER",
            value=MUSTERING_WARLORD_REQUIRED,
        ),
    )
    request = _drukhari_corsairs_and_travelling_players_request(
        catalog,
        unit_points=(
            _unit_points("archon", 100),
            _unit_points("troupe-master", 250),
            _unit_points("voidscarred", 0),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="archon",
            source_id="phase17g:warlord",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert "supreme_commander_warlord_conflict" in {
        violation.violation_code for violation in report.violations
    }


def test_phase17g_daemonic_pact_allows_legiones_daemonica_allies() -> None:
    catalog = _daemonic_pact_catalog()
    request = _daemonic_pact_request(
        catalog,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("bloodletters", 250),
            _unit_points("bloodthirster", 250),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="legionaries",
            source_id="phase17g:warlord",
        ),
    )

    army = muster_army(catalog=catalog, request=request)

    assert army.roster_legality_report.is_legal
    assert {unit.datasheet_id for unit in army.units} == {
        "phase17g-bloodletters",
        "phase17g-bloodthirster",
        "phase17g-chaos-legionaries",
    }


def test_phase17g_daemonic_pact_reports_roster_violations() -> None:
    catalog = _daemonic_pact_catalog()
    request = _daemonic_pact_request(
        catalog,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("bloodletters", 250),
            _unit_points("bloodthirster", 260),
            _unit_points("skull-cannon", 40),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="phase17g-dark-gift",
                target_unit_selection_id="bloodthirster",
                source_id="phase17g:enhancement-assignment",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="bloodthirster",
            source_id="phase17g:warlord",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert {violation.violation_code for violation in report.violations} >= {
        "daemonic_pact_enhancement_forbidden",
        "daemonic_pact_god_ratio_exceeded",
        "daemonic_pact_points_limit_exceeded",
        "daemonic_pact_warlord_forbidden",
    }


def test_phase17g_daemonic_pact_counts_selected_mustering_god_keywords() -> None:
    catalog = _daemonic_pact_catalog()
    detachment_selection = DetachmentSelection(
        faction_id="chaos-space-marines",
        detachment_ids=("phase17g-csm-detachment",),
    )
    warlord_selection = WarlordSelection(
        unit_selection_id="legionaries",
        source_id="phase17g:warlord",
    )
    khorne_soul_grinder = _unit_selection(
        unit_selection_id="soul-grinder",
        datasheet_id="phase17g-soul-grinder",
        mustering_option_selections=(
            MusteringOptionSelection(
                option_id="phase17g-soul-grinder:daemonic-allegiance:khorne",
            ),
        ),
    )
    unsupported_request = _muster_request(
        catalog,
        detachment_selection=detachment_selection,
        unit_selections=(
            _unit_selection(
                unit_selection_id="legionaries",
                datasheet_id="phase17g-chaos-legionaries",
            ),
            khorne_soul_grinder,
        ),
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("soul-grinder", 150),
        ),
        warlord_selection=warlord_selection,
    )
    supported_request = replace(
        unsupported_request,
        unit_selections=(
            _unit_selection(
                unit_selection_id="legionaries",
                datasheet_id="phase17g-chaos-legionaries",
            ),
            _unit_selection(
                unit_selection_id="bloodletters",
                datasheet_id="phase17g-bloodletters",
            ),
            khorne_soul_grinder,
        ),
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("bloodletters", 0),
            _unit_points("soul-grinder", 150),
        ),
    )

    unsupported_report = validate_roster_legality(
        catalog=catalog,
        request=unsupported_request,
    )
    supported_report = validate_roster_legality(
        catalog=catalog,
        request=supported_request,
    )

    unsupported_violations = {
        violation.violation_code: violation for violation in unsupported_report.violations
    }
    assert unsupported_violations["daemonic_pact_god_ratio_exceeded"].unit_selection_id == (
        "soul-grinder"
    )
    assert "daemonic_pact_god_ratio_exceeded" not in {
        violation.violation_code for violation in supported_report.violations
    }


def test_phase17g_roster_legality_reports_missing_required_mustering_option() -> None:
    catalog = _daemonic_pact_catalog()
    request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="chaos-space-marines",
            detachment_ids=("phase17g-csm-detachment",),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id="legionaries",
                datasheet_id="phase17g-chaos-legionaries",
            ),
            _unit_selection(
                unit_selection_id="soul-grinder",
                datasheet_id="phase17g-soul-grinder",
            ),
        ),
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("soul-grinder", 150),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="legionaries",
            source_id="phase17g:warlord",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    violation = next(
        violation
        for violation in report.violations
        if violation.violation_code == "mustering_option_selection_invalid"
    )
    assert violation.unit_selection_id == "soul-grinder"
    assert "required option group" in violation.message


@pytest.mark.parametrize(
    ("battle_size", "cap"),
    [
        (BattleSize.INCURSION, 250),
        (BattleSize.STRIKE_FORCE, 500),
        (BattleSize.ONSLAUGHT, 750),
    ],
)
def test_phase17g_daemonic_pact_points_cap_scales_by_battle_size(
    battle_size: BattleSize,
    cap: int,
) -> None:
    catalog = _daemonic_pact_catalog()
    legal_request = _daemonic_pact_request(
        catalog,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("bloodletters", 0),
            _unit_points("bloodthirster", cap),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="legionaries",
            source_id="phase17g:warlord",
        ),
    )
    legal_request = replace(legal_request, battle_size=battle_size)
    over_cap_request = replace(
        legal_request,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("bloodletters", 0),
            _unit_points("bloodthirster", cap + 1),
        ),
    )

    legal_report = validate_roster_legality(catalog=catalog, request=legal_request)
    over_cap_report = validate_roster_legality(catalog=catalog, request=over_cap_request)

    assert legal_report.is_legal
    assert "daemonic_pact_points_limit_exceeded" in {
        violation.violation_code for violation in over_cap_report.violations
    }


def test_phase17g_dreadblades_allows_one_titanic_or_three_war_dogs_for_chaos_armies() -> None:
    catalog = _dreadblades_catalog()
    titanic_request = _dreadblades_request(
        catalog,
        unit_points=(
            _unit_points("chaos-lord", 100),
            _unit_points("knight-abominant", 400),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="chaos-lord",
            source_id="phase17g:warlord",
        ),
        include_titanic=True,
    )
    war_dog_request = _dreadblades_request(
        catalog,
        unit_points=(
            _unit_points("chaos-lord", 100),
            _unit_points("war-dog-1", 140),
            _unit_points("war-dog-2", 140),
            _unit_points("war-dog-3", 140),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="chaos-lord",
            source_id="phase17g:warlord",
        ),
        war_dog_count=3,
    )

    titanic_army = muster_army(catalog=catalog, request=titanic_request)
    war_dog_army = muster_army(catalog=catalog, request=war_dog_request)

    assert titanic_army.roster_legality_report.is_legal
    assert {unit.datasheet_id for unit in titanic_army.units} == {
        "phase17g-chaos-lord",
        "phase17g-knight-abominant",
    }
    assert war_dog_army.roster_legality_report.is_legal
    assert (
        sum(1 for unit in war_dog_army.units if unit.datasheet_id == "phase17g-war-dog-stalker")
        == 3
    )


def test_phase17g_dreadblades_reports_roster_violations() -> None:
    catalog = _dreadblades_catalog()
    request = _dreadblades_request(
        catalog,
        unit_points=(
            _unit_points("mutant", 100),
            _unit_points("war-dog-1", 140),
            _unit_points("knight-abominant", 400),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="phase17g-dark-panoply",
                target_unit_selection_id="war-dog-1",
                source_id="phase17g:enhancement-assignment",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="knight-abominant",
            source_id="phase17g:warlord",
        ),
        war_dog_count=1,
        include_titanic=True,
        base_datasheet_id="phase17g-tainted-mutant",
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert {violation.violation_code for violation in report.violations} >= {
        "dreadblades_chaos_army_required",
        "dreadblades_enhancement_forbidden",
        "dreadblades_limit_exceeded",
        "warlord_dreadblades_forbidden",
    }


def test_phase17g_cult_of_dark_gods_allows_cult_units_and_replaces_faction_keywords() -> None:
    catalog = _cult_of_dark_gods_catalog()
    request = _cult_of_dark_gods_request(
        catalog,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("khorne-berzerkers", 100),
            _unit_points("rubric-marines", 100),
            _unit_points("plague-marines", 100),
            _unit_points("noise-marines", 100),
        ),
    )

    army = muster_army(catalog=catalog, request=request)
    faction_keywords_by_datasheet = {
        unit.datasheet_id: unit.faction_keywords for unit in army.units
    }

    assert army.roster_legality_report.is_legal
    assert faction_keywords_by_datasheet["phase17g-khorne-berzerkers"] == ("HERETIC ASTARTES",)
    assert faction_keywords_by_datasheet["phase17g-rubric-marines"] == ("HERETIC ASTARTES",)
    assert faction_keywords_by_datasheet["phase17g-plague-marines"] == ("HERETIC ASTARTES",)
    assert faction_keywords_by_datasheet["phase17g-noise-marines"] == ("HERETIC ASTARTES",)


@pytest.mark.parametrize(
    ("battle_size", "cap"),
    [
        (BattleSize.INCURSION, 250),
        (BattleSize.STRIKE_FORCE, 500),
        (BattleSize.ONSLAUGHT, 750),
    ],
)
def test_phase17g_cult_of_dark_gods_points_cap_scales_by_battle_size(
    battle_size: BattleSize,
    cap: int,
) -> None:
    catalog = _cult_of_dark_gods_catalog()
    legal_request = _cult_of_dark_gods_request(
        catalog,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("khorne-berzerkers", cap),
            _unit_points("rubric-marines", 0),
            _unit_points("plague-marines", 0),
            _unit_points("noise-marines", 0),
        ),
        battle_size=battle_size,
    )
    over_cap_request = replace(
        legal_request,
        unit_points=(
            _unit_points("legionaries", 100),
            _unit_points("khorne-berzerkers", cap + 1),
            _unit_points("rubric-marines", 0),
            _unit_points("plague-marines", 0),
            _unit_points("noise-marines", 0),
        ),
    )

    legal_report = validate_roster_legality(catalog=catalog, request=legal_request)
    over_cap_report = validate_roster_legality(catalog=catalog, request=over_cap_request)

    assert legal_report.is_legal
    assert "cult_of_dark_gods_points_limit_exceeded" in {
        violation.violation_code for violation in over_cap_report.violations
    }


@pytest.mark.parametrize(
    ("faction_id", "detachment_id"),
    [
        ("legions-of-excess", "phase17g-legions-of-excess-detachment"),
        ("plague-legions", "phase17g-plague-legions-detachment"),
        ("blood-legions", "phase17g-blood-legions-detachment"),
        ("scintillating-legions", "phase17g-scintillating-legions-detachment"),
    ],
)
def test_phase17g_pact_army_factions_are_forbidden_by_default(
    faction_id: str,
    detachment_id: str,
) -> None:
    catalog = _forbidden_pact_faction_catalog()
    request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id="daemonettes",
                datasheet_id="phase17g-daemonettes",
            ),
        ),
        unit_points=(_unit_points("daemonettes", 100),),
        warlord_selection=WarlordSelection(
            unit_selection_id="daemonettes",
            source_id="phase17g:warlord",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert report.violations[0].violation_code == "detachment_selection_invalid"
    assert "forbids selecting" in report.violations[0].message


def test_phase17g_drukhari_corsairs_and_travelling_players_allows_allies() -> None:
    catalog = _drukhari_corsairs_and_travelling_players_catalog()
    request = _drukhari_corsairs_and_travelling_players_request(
        catalog,
        unit_points=(
            _unit_points("archon", 100),
            _unit_points("troupe-master", 250),
            _unit_points("voidscarred", 250),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="archon",
            source_id="phase17g:warlord",
        ),
    )

    army = muster_army(catalog=catalog, request=request)

    assert army.roster_legality_report.is_legal
    assert {unit.datasheet_id for unit in army.units} == {
        "phase17g-corsair-voidscarred",
        "phase17g-drukhari-archon",
        "phase17g-harlequin-troupe-master",
    }


@pytest.mark.parametrize(
    ("battle_size", "cap"),
    [
        (BattleSize.INCURSION, 250),
        (BattleSize.STRIKE_FORCE, 500),
        (BattleSize.ONSLAUGHT, 750),
    ],
)
def test_phase17g_drukhari_corsairs_points_cap_scales_by_battle_size(
    battle_size: BattleSize,
    cap: int,
) -> None:
    catalog = _drukhari_corsairs_and_travelling_players_catalog()
    legal_request = _drukhari_corsairs_and_travelling_players_request(
        catalog,
        unit_points=(
            _unit_points("archon", 100),
            _unit_points("troupe-master", cap),
            _unit_points("voidscarred", 0),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="archon",
            source_id="phase17g:warlord",
        ),
        battle_size=battle_size,
    )
    over_cap_request = replace(
        legal_request,
        unit_points=(
            _unit_points("archon", 100),
            _unit_points("troupe-master", cap + 1),
            _unit_points("voidscarred", 0),
        ),
    )

    legal_report = validate_roster_legality(catalog=catalog, request=legal_request)
    over_cap_report = validate_roster_legality(catalog=catalog, request=over_cap_request)

    assert legal_report.is_legal
    assert "drukhari_corsairs_and_travelling_players_points_limit_exceeded" in {
        violation.violation_code for violation in over_cap_report.violations
    }


def test_phase17g_drukhari_corsairs_reports_roster_violations() -> None:
    catalog = _drukhari_corsairs_and_travelling_players_catalog()
    request = _drukhari_corsairs_and_travelling_players_request(
        catalog,
        unit_points=(
            _unit_points("archon", 100),
            _unit_points("troupe-master", 300),
            _unit_points("voidscarred", 260),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="phase17g-soul-trap",
                target_unit_selection_id="troupe-master",
                source_id="phase17g:enhancement-assignment",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="troupe-master",
            source_id="phase17g:warlord",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert {violation.violation_code for violation in report.violations} >= {
        "drukhari_corsairs_and_travelling_players_enhancement_forbidden",
        "drukhari_corsairs_and_travelling_players_points_limit_exceeded",
        "warlord_drukhari_corsairs_and_travelling_players_forbidden",
    }


def test_phase17g_drukhari_corsairs_rejects_other_faction_allies() -> None:
    catalog = _drukhari_corsairs_and_travelling_players_catalog()
    request = _drukhari_corsairs_and_travelling_players_request(
        catalog,
        unit_points=(
            _unit_points("archon", 100),
            _unit_points("troupe-master", 200),
            _unit_points("voidscarred", 200),
            _unit_points("outsider", 50),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="archon",
            source_id="phase17g:warlord",
        ),
        include_outsider=True,
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert "unit_selection_invalid" in {violation.violation_code for violation in report.violations}


def test_phase17g_freeblades_allows_one_titanic_or_three_armigers_for_imperium_armies() -> None:
    catalog = _freeblades_catalog()
    titanic_request = _freeblades_request(
        catalog,
        unit_points=(
            _unit_points("captain", 100),
            _unit_points("knight-crusader", 400),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="captain",
            source_id="phase17g:warlord",
        ),
        include_titanic=True,
    )
    armiger_request = _freeblades_request(
        catalog,
        unit_points=(
            _unit_points("captain", 100),
            _unit_points("armiger-1", 140),
            _unit_points("armiger-2", 140),
            _unit_points("armiger-3", 140),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="captain",
            source_id="phase17g:warlord",
        ),
        armiger_count=3,
    )

    titanic_army = muster_army(catalog=catalog, request=titanic_request)
    armiger_army = muster_army(catalog=catalog, request=armiger_request)

    assert titanic_army.roster_legality_report.is_legal
    assert {unit.datasheet_id for unit in titanic_army.units} == {
        "phase17g-knight-crusader",
        "phase17g-space-marine-captain",
    }
    assert armiger_army.roster_legality_report.is_legal
    assert (
        sum(1 for unit in armiger_army.units if unit.datasheet_id == "phase17g-armiger-warglaive")
        == 3
    )


def test_phase17g_freeblades_reports_roster_violations() -> None:
    catalog = _freeblades_catalog()
    request = _freeblades_request(
        catalog,
        unit_points=(
            _unit_points("captain", 100),
            _unit_points("armiger-1", 140),
            _unit_points("knight-crusader", 400),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="phase17g-master-crafted",
                target_unit_selection_id="armiger-1",
                source_id="phase17g:enhancement-assignment",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="knight-crusader",
            source_id="phase17g:warlord",
        ),
        armiger_count=1,
        include_titanic=True,
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert {violation.violation_code for violation in report.violations} >= {
        "freeblades_enhancement_forbidden",
        "freeblades_limit_exceeded",
        "warlord_freeblades_forbidden",
    }


def test_phase17g_freeblades_rejects_non_imperium_faction_access() -> None:
    catalog = _freeblades_catalog()
    request = _freeblades_request(
        catalog,
        unit_points=(
            _unit_points("commander", 100),
            _unit_points("armiger-1", 140),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="commander",
            source_id="phase17g:warlord",
        ),
        armiger_count=1,
        faction_id="tau-empire",
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert "unit_selection_invalid" in {violation.violation_code for violation in report.violations}


def test_phase16d_enhancement_points_count_toward_strike_force_limit() -> None:
    catalog = _phase16d_catalog()
    request = replace(
        _phase16d_transport_roster_request(catalog),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="bodyguard-unit",
                points=1800,
                source_id="points:bodyguard-unit",
            ),
            RosterUnitPointValue(
                unit_selection_id="leader-unit",
                points=100,
                source_id="points:leader-unit",
            ),
            RosterUnitPointValue(
                unit_selection_id="transport-unit",
                points=90,
                source_id="points:transport-unit",
            ),
        ),
    )

    codes = {
        violation.violation_code
        for violation in validate_roster_legality(catalog=catalog, request=request).violations
    }

    assert "points_limit_exceeded" in codes
    with pytest.raises(ArmyMusteringError, match="RosterLegalityReport is invalid"):
        muster_army(catalog=catalog, request=request)


def test_phase16d_upgrade_assignments_share_one_selection_and_pay_per_unit() -> None:
    catalog = _phase16d_catalog(upgrade_enhancement=True)
    assignments = tuple(
        EnhancementAssignment(
            enhancement_id="core-upgrade",
            target_unit_selection_id=selection_id,
            source_id=f"assignment:{selection_id}",
        )
        for selection_id in ("squad-one", "squad-two", "squad-three")
    )
    request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=("core-upgrade",),
        ),
        unit_selections=(
            _unit_selection(unit_selection_id="squad-one"),
            _unit_selection(unit_selection_id="squad-two"),
            _unit_selection(unit_selection_id="squad-three"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="squad-one",
                points=100,
                source_id="points:squad-one",
            ),
            RosterUnitPointValue(
                unit_selection_id="squad-two",
                points=100,
                source_id="points:squad-two",
            ),
            RosterUnitPointValue(
                unit_selection_id="squad-three",
                points=100,
                source_id="points:squad-three",
            ),
            RosterUnitPointValue(
                unit_selection_id="leader-unit",
                points=100,
                source_id="points:leader-unit",
            ),
        ),
        enhancement_assignments=assignments,
        warlord_selection=WarlordSelection(
            unit_selection_id="leader-unit",
            source_id="warlord:leader-unit",
        ),
        roster_legality_required=True,
    )
    over_points_request = replace(
        request,
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="squad-one",
                points=1650,
                source_id="points:squad-one",
            ),
            RosterUnitPointValue(
                unit_selection_id="squad-two",
                points=100,
                source_id="points:squad-two",
            ),
            RosterUnitPointValue(
                unit_selection_id="squad-three",
                points=100,
                source_id="points:squad-three",
            ),
            RosterUnitPointValue(
                unit_selection_id="leader-unit",
                points=100,
                source_id="points:leader-unit",
            ),
        ),
    )

    assert validate_roster_legality(catalog=catalog, request=request).violations == ()
    army = muster_army(catalog=catalog, request=request)
    over_points_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=over_points_request,
        ).violations
    }

    assert army.detachment_selection.enhancement_ids == ("core-upgrade",)
    assert {
        (assignment.enhancement_id, assignment.target_unit_selection_id, assignment.source_id)
        for assignment in army.enhancement_assignments
    } == {
        (assignment.enhancement_id, assignment.target_unit_selection_id, assignment.source_id)
        for assignment in assignments
    }
    assert "points_limit_exceeded" in over_points_codes


def test_phase16d_upgrade_assignment_limits_and_targets_are_validated() -> None:
    catalog = _phase16d_catalog(upgrade_enhancement=True)
    too_many_assignments = tuple(
        EnhancementAssignment(
            enhancement_id="core-upgrade",
            target_unit_selection_id=selection_id,
            source_id=f"assignment:{selection_id}",
        )
        for selection_id in ("squad-one", "squad-two", "squad-three", "squad-four")
    )
    too_many_request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=("core-upgrade",),
        ),
        unit_selections=(
            _unit_selection(unit_selection_id="squad-one"),
            _unit_selection(unit_selection_id="squad-two"),
            _unit_selection(unit_selection_id="squad-three"),
            _unit_selection(unit_selection_id="squad-four"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="squad-one",
                points=100,
                source_id="points:squad-one",
            ),
            RosterUnitPointValue(
                unit_selection_id="squad-two",
                points=100,
                source_id="points:squad-two",
            ),
            RosterUnitPointValue(
                unit_selection_id="squad-three",
                points=100,
                source_id="points:squad-three",
            ),
            RosterUnitPointValue(
                unit_selection_id="squad-four",
                points=100,
                source_id="points:squad-four",
            ),
            RosterUnitPointValue(
                unit_selection_id="leader-unit",
                points=100,
                source_id="points:leader-unit",
            ),
        ),
        enhancement_assignments=too_many_assignments,
        warlord_selection=WarlordSelection(
            unit_selection_id="leader-unit",
            source_id="warlord:leader-unit",
        ),
        roster_legality_required=True,
    )
    character_request = replace(
        too_many_request,
        unit_selections=(
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="leader-unit",
                points=100,
                source_id="points:leader-unit",
            ),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="core-upgrade",
                target_unit_selection_id="leader-unit",
                source_id="assignment:leader-unit",
            ),
        ),
    )

    too_many_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=too_many_request,
        ).violations
    }
    character_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=character_request,
        ).violations
    }

    assert "upgrade_assignment_limit_exceeded" in too_many_codes
    assert "enhancement_limit_exceeded" not in too_many_codes
    assert "upgrade_character_forbidden" in character_codes


def test_phase16d_standard_enhancements_remain_single_assignment() -> None:
    catalog = _phase16d_catalog()
    request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=("core-enhancement-a",),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id="leader-one",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="leader-two",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="leader-one",
                points=100,
                source_id="points:leader-one",
            ),
            RosterUnitPointValue(
                unit_selection_id="leader-two",
                points=100,
                source_id="points:leader-two",
            ),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="core-enhancement-a",
                target_unit_selection_id="leader-one",
                source_id="assignment:leader-one",
            ),
            EnhancementAssignment(
                enhancement_id="core-enhancement-a",
                target_unit_selection_id="leader-two",
                source_id="assignment:leader-two",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="leader-one",
            source_id="warlord:leader-one",
        ),
        roster_legality_required=True,
    )

    codes = {
        violation.violation_code
        for violation in validate_roster_legality(catalog=catalog, request=request).violations
    }

    assert "enhancement_repeated_assignment_forbidden" in codes


def test_phase16d_enhancement_restrictions_cover_epic_and_attached_squads() -> None:
    epic_catalog = _phase16d_catalog(epic_leader=True)
    epic_request = _muster_request(
        epic_catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=("core-enhancement-a",),
        ),
        unit_selections=(
            _unit_selection(
                unit_selection_id="epic-one",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="epic-two",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="epic-one",
                points=100,
                source_id="points:epic-one",
            ),
            RosterUnitPointValue(
                unit_selection_id="epic-two",
                points=100,
                source_id="points:epic-two",
            ),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="core-enhancement-a",
                target_unit_selection_id="epic-one",
                source_id="assignment:epic-one",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="epic-one",
            source_id="warlord:epic-one",
        ),
        roster_legality_required=True,
    )
    attached_catalog = _phase16d_catalog(second_enhancement=True)
    attached_request = _phase16d_transport_roster_request(
        attached_catalog,
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="core-enhancement-a",
                target_unit_selection_id="leader-unit",
                source_id="assignment:leader",
            ),
            EnhancementAssignment(
                enhancement_id="core-enhancement-b",
                target_unit_selection_id="support-unit",
                source_id="assignment:support",
            ),
        ),
        include_support=True,
    )

    epic_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=epic_catalog,
            request=epic_request,
        ).violations
    }
    attached_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=attached_catalog,
            request=attached_request,
        ).violations
    }

    assert {"epic_hero_not_unique", "epic_hero_enhancement_forbidden"} <= epic_codes
    assert "attached_squad_enhancement_limit_exceeded" in attached_codes
    with pytest.raises(ArmyMusteringError, match="RosterLegalityReport is invalid"):
        muster_army(catalog=epic_catalog, request=epic_request)
    with pytest.raises(ArmyMusteringError, match="RosterLegalityReport is invalid"):
        muster_army(catalog=attached_catalog, request=attached_request)


def test_phase16d_upgrade_and_leader_enhancement_cannot_stack_on_attached_squad() -> None:
    catalog = _phase16d_catalog(upgrade_enhancement=True)
    request = _phase16d_transport_roster_request(
        catalog,
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="core-upgrade",
                target_unit_selection_id="bodyguard-unit",
                source_id="assignment:bodyguard",
            ),
            EnhancementAssignment(
                enhancement_id="core-enhancement-a",
                target_unit_selection_id="leader-unit",
                source_id="assignment:leader",
            ),
        ),
    )

    codes = {
        violation.violation_code
        for violation in validate_roster_legality(catalog=catalog, request=request).violations
    }

    assert "attached_squad_enhancement_limit_exceeded" in codes


def test_phase16d_transport_manifest_validates_capacity_and_attached_group_completeness() -> None:
    catalog = _phase16d_catalog()
    missing_manifest = _phase16d_transport_roster_request(
        catalog,
        dedicated_transport_manifests=(),
    )
    incomplete_group = _phase16d_transport_roster_request(
        catalog,
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=("bodyguard-unit",),
                capacity_profile=_transport_capacity(max_model_count=6),
                source_id="manifest:incomplete",
            ),
        ),
    )
    over_capacity = _phase16d_transport_roster_request(
        catalog,
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=("bodyguard-unit", "leader-unit"),
                capacity_profile=_transport_capacity(max_model_count=5),
                source_id="manifest:over-capacity",
            ),
        ),
    )
    empty_cargo = _phase16d_transport_roster_request(
        catalog,
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=(),
                capacity_profile=_transport_capacity(max_model_count=6),
                source_id="manifest:empty",
            ),
        ),
    )

    incomplete_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=incomplete_group,
        ).violations
    }
    over_capacity_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=over_capacity,
        ).violations
    }
    empty_cargo_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=empty_cargo,
        ).violations
    }
    missing_manifest_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=missing_manifest,
        ).violations
    }

    assert "dedicated_transport_missing_starting_cargo" in missing_manifest_codes
    assert "transport_manifest_attached_unit_incomplete" in incomplete_codes
    assert "transport_manifest_capacity_exceeded" in over_capacity_codes
    assert "dedicated_transport_empty_starting_cargo" not in empty_cargo_codes
    assert validate_roster_legality(catalog=catalog, request=empty_cargo).is_legal


def test_phase16d_roster_payload_value_objects_fail_fast() -> None:
    catalog = _phase16d_catalog()
    army = muster_army(catalog=catalog, request=_phase16d_transport_roster_request(catalog))

    with pytest.raises(ArmyMusteringError, match="cannot embark itself"):
        DedicatedTransportManifest(
            transport_unit_selection_id="transport-unit",
            embarked_unit_selection_ids=("transport-unit",),
            capacity_profile=_transport_capacity(max_model_count=1),
            source_id="manifest:self",
        )
    with pytest.raises(ArmyMusteringError, match="capacity_profile"):
        DedicatedTransportManifest(
            transport_unit_selection_id="transport-unit",
            embarked_unit_selection_ids=("bodyguard-unit",),
            capacity_profile=cast(DedicatedTransportCapacityProfile, "bad-capacity"),
            source_id="manifest:bad-capacity",
        )
    with pytest.raises(ArmyMusteringError, match="is_legal payload drift"):
        RosterLegalityReport.from_payload(
            {
                "battle_size": "strike_force",
                "is_legal": False,
                "violations": [],
            }
        )
    with pytest.raises(AttachedUnitFormationError, match="requires a leader or support"):
        AttachedUnitFormation(
            attached_unit_instance_id="attached-unit:army-alpha:bodyguard-unit",
            bodyguard_unit_instance_id="army-alpha:bodyguard-unit",
            component_unit_instance_ids=(
                "army-alpha:bodyguard-unit",
                "army-alpha:leader-unit",
            ),
            source_id="attached-unit:missing-role",
        )
    with pytest.raises(AttachedUnitFormationError, match="component_unit_instance_ids"):
        AttachedUnitFormation(
            attached_unit_instance_id="attached-unit:army-alpha:bodyguard-unit",
            bodyguard_unit_instance_id="army-alpha:bodyguard-unit",
            leader_unit_instance_ids=("army-alpha:leader-unit",),
            component_unit_instance_ids=(
                "army-alpha:bodyguard-unit",
                "army-alpha:wrong-unit",
            ),
            source_id="attached-unit:bad-components",
        )
    with pytest.raises(ArmyMusteringError, match="roster_legality_report"):
        replace(army, roster_legality_report=cast(RosterLegalityReport, "bad-report"))


def test_phase16d_roster_reports_source_reference_diagnostics() -> None:
    catalog = _phase16d_catalog()
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="transport-unit",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="bodyguard-unit",
                points=1000,
                source_id="points:bodyguard",
            ),
            RosterUnitPointValue(
                unit_selection_id="leader-unit",
                points=1000,
                source_id="points:leader",
            ),
            RosterUnitPointValue(
                unit_selection_id="transport-unit",
                points=1000,
                source_id="points:transport",
            ),
            RosterUnitPointValue(
                unit_selection_id="missing-unit",
                points=10,
                source_id="points:missing",
            ),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="missing-enhancement",
                target_unit_selection_id="leader-unit",
                source_id="assignment:missing",
            ),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="bodyguard-unit",
            source_id="warlord:bodyguard",
        ),
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=("missing-cargo",),
                capacity_profile=_transport_capacity(max_model_count=1),
                source_id="manifest:unknown-cargo",
            ),
            DedicatedTransportManifest(
                transport_unit_selection_id="leader-unit",
                embarked_unit_selection_ids=("bodyguard-unit",),
                capacity_profile=DedicatedTransportCapacityProfile(
                    transport_datasheet_id="core-transport",
                    max_model_count=10,
                    allowed_keywords=("Terminator",),
                    excluded_keywords=(),
                    source_id="transport-capacity:leader-drift",
                ),
                source_id="manifest:leader-as-transport",
            ),
        ),
        roster_legality_required=True,
    )
    invalid_unit_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="missing-datasheet",
                datasheet_id="missing-datasheet",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )
    invalid_detachment_request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="missing-faction",
            detachment_ids=("core-combined-arms",),
        ),
    )

    codes = {
        violation.violation_code
        for violation in validate_roster_legality(catalog=catalog, request=request).violations
    }
    invalid_unit_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=invalid_unit_request,
        ).violations
    }
    invalid_detachment_codes = {
        violation.violation_code
        for violation in validate_roster_legality(
            catalog=catalog,
            request=invalid_detachment_request,
        ).violations
    }

    assert {
        "unit_points_unknown_unit",
        "points_limit_exceeded",
        "warlord_character_required",
        "enhancement_not_selected",
        "enhancement_not_allowed_by_detachment",
        "enhancement_unknown",
        "transport_manifest_unknown_cargo",
        "transport_manifest_transport_required",
        "transport_manifest_dedicated_transport_required",
        "transport_manifest_capacity_datasheet_drift",
        "transport_manifest_cargo_ineligible",
    } <= codes
    assert "unit_selection_invalid" in invalid_unit_codes
    assert "detachment_selection_invalid" in invalid_detachment_codes


def test_phase16d_setup_records_starting_transport_cargo_from_manifest() -> None:
    catalog = _phase16d_catalog()
    config = GameConfig(
        game_id="phase16d-setup-cargo",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _phase16d_transport_roster_request(catalog),
            _phase16d_transport_roster_request(
                catalog,
                army_id="army-beta",
                player_id="player-b",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("area-denial", "assassination"),
        mission_setup=_phase16d_mission_setup(),
    )
    state = GameState.from_config(config)
    while state.current_setup_step is not SetupStep.MUSTER_ARMIES:
        state.complete_current_setup_step()
    decisions = DecisionController()

    SetupFlow().advance(state=state, decisions=decisions, config=config)

    cargo = state.transport_cargo_state_for_transport("army-alpha:transport-unit")
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == (
        "army-alpha:bodyguard-unit",
        "army-alpha:leader-unit",
    )
    assert {
        "army-alpha:bodyguard-unit:core-intercessor-like:001",
        "army-alpha:bodyguard-unit:core-intercessor-like:002",
        "army-alpha:bodyguard-unit:core-intercessor-like:003",
        "army-alpha:bodyguard-unit:core-intercessor-like:004",
        "army-alpha:bodyguard-unit:core-intercessor-like:005",
        "army-alpha:leader-unit:core-character-leader:001",
    } <= set(state.embarked_model_ids())
    attached_record = state.starting_strength_record_for_unit(
        "attached-unit:army-alpha:bodyguard-unit"
    )
    transport_record = state.starting_strength_record_for_unit("army-alpha:transport-unit")
    assert attached_record.starting_model_count == 6
    assert attached_record.single_model_starting_wounds is None
    assert transport_record.starting_model_count == 1
    assert transport_record.single_model_starting_wounds == 10
    with pytest.raises(GameLifecycleError, match="StartingStrengthRecord"):
        state.starting_strength_record_for_unit("army-alpha:bodyguard-unit")
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert "battle_formation_transport_manifest_recorded" in event_types


def test_phase16d_empty_dedicated_transport_manifest_records_setup_consequence() -> None:
    catalog = _phase16d_catalog()
    empty_transport_request = _phase16d_transport_roster_request(
        catalog,
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=(),
                capacity_profile=_transport_capacity(max_model_count=6),
                source_id="manifest:empty",
            ),
        ),
    )
    config = GameConfig(
        game_id="phase16d-empty-transport",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            empty_transport_request,
            _phase16d_transport_roster_request(
                catalog,
                army_id="army-beta",
                player_id="player-b",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("area-denial", "assassination"),
        mission_setup=_phase16d_mission_setup(),
    )
    state = GameState.from_config(config)
    while state.current_setup_step is not SetupStep.MUSTER_ARMIES:
        state.complete_current_setup_step()
    decisions = DecisionController()

    setup_flow = SetupFlow()
    setup_flow.advance(state=state, decisions=decisions, config=config)
    setup_flow.advance(state=state, decisions=decisions, config=config)

    consequence = state.dedicated_transport_setup_consequence_for_transport(
        "army-alpha:transport-unit"
    )
    assert consequence is not None
    assert consequence.destroyed_battle_round == 1
    assert consequence.source_id == "manifest:empty"
    assert state.transport_cargo_state_for_transport("army-alpha:transport-unit") is None
    assert "army-alpha:transport-unit:core-transport:001" in state.unavailable_model_ids()

    deployment_request = deployment_unit_selection_request(
        state=state,
        ruleset_descriptor=config.ruleset_descriptor,
        player_id="player-a",
    )
    option_ids = tuple(option.option_id for option in deployment_request.options)
    payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )

    assert "deploy:army-alpha:transport-unit" not in option_ids
    assert "deploy:attached-unit:army-alpha:bodyguard-unit" in option_ids
    assert "dedicated_transport_setup_consequence_recorded" in tuple(
        event.event_type for event in decisions.event_log.records
    )
    assert GameState.from_payload(payload).to_payload() == state.to_payload()


def test_phase16d_game_config_requires_strict_roster_legality_for_production() -> None:
    catalog = _phase16d_catalog()
    strict_config = GameConfig(
        game_id="phase16d-strict-config",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _phase16d_transport_roster_request(catalog),
            _phase16d_transport_roster_request(
                catalog,
                army_id="army-beta",
                player_id="player-b",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("area-denial", "assassination"),
    )

    assert not strict_config.allow_legacy_non_strict_rosters
    with pytest.raises(GameLifecycleError, match="production path requires"):
        GameConfig(
            game_id="phase16d-non-strict-config",
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            army_muster_requests=(
                _muster_request(catalog),
                _muster_request(
                    catalog,
                    army_id="army-beta",
                    player_id="player-b",
                    unit_selections=(_unit_selection(unit_selection_id="beta-unit"),),
                ),
            ),
            player_ids=("player-a", "player-b"),
            turn_order=("player-a", "player-b"),
            fixed_secondary_mission_ids=("area-denial", "assassination"),
        )


def test_phase16_faction_detachment_source_rows_are_normalized() -> None:
    faction_rows = faction_detachment_source.faction_rows()
    detachment_rows = faction_detachment_source.detachment_rows()
    payload = faction_detachment_source.source_payload()
    faction_names = {row.faction_id: row.name for row in faction_rows}
    detachment_names = {row.detachment_id: row.name for row in detachment_rows}
    new_detachment_ids = {row.detachment_id for row in detachment_rows if row.is_new_for_eleventh}

    assert len(faction_rows) == 28
    assert len(detachment_rows) == 266
    assert payload["source_package_id"] == faction_detachment_source.SOURCE_PACKAGE_ID
    assert {row.faction_id for row in faction_rows} >= {
        "chaos-daemons",
        "chaos-space-marines",
        "imperial-agents",
        "imperial-knights",
        "leagues-of-votann",
        "space-marines",
        "tau-empire",
    }
    assert next(row for row in faction_rows if row.faction_id == "tau-empire").name == (
        "T'au Empire"
    )
    assert detachment_names["delve-assault-shift"] == "Delve Assault Shift"
    assert detachment_names["needgaard-oathband"] == "Needgaard Oathband"
    assert "advanced-acquisition-cadre" in new_detachment_ids
    assert "abhuman-auxiliaries" in new_detachment_ids
    assert "cabal-of-chaos" in new_detachment_ids
    assert "throne-bonded-outriders" in new_detachment_ids
    assert faction_names["emperors-children"] == "Emperor's Children"
    assert all("New - " not in row.name for row in detachment_rows)
    assert all(ord(character) < 128 for row in faction_rows for character in row.name)
    assert all(ord(character) < 128 for row in detachment_rows for character in row.name)


def test_phase16_chaos_faction_detachment_source_rows_match_requested_matrix() -> None:
    chaos_faction_ids = {
        "chaos-daemons",
        "chaos-knights",
        "chaos-space-marines",
        "death-guard",
        "emperors-children",
        "thousand-sons",
        "world-eaters",
    }
    rows_by_faction = {
        faction_id: tuple(
            (
                row.raw_name,
                row.force_disposition_id,
                row.detachment_point_cost,
                row.is_new_for_eleventh,
            )
            for row in faction_detachment_source.detachment_rows()
            if row.faction_id == faction_id
        )
        for faction_id in chaos_faction_ids
    }

    assert rows_by_faction == {
        "chaos-space-marines": (
            ("Cabal of Chaos", "disruption", 1, True),
            ("Devotees of Destruction", "priority-assets", 1, True),
            ("Murdertalon Raiders", "purge-the-foe", 1, True),
            ("Chaos Cult", "priority-assets", 2, False),
            ("Creations of Bile", "purge-the-foe", 3, False),
            ("Cult of the Arkifane", "priority-assets", 2, False),
            ("Deceptors", "disruption", 2, False),
            ("Dread Talons", "disruption", 2, False),
            ("Fellhammer Siege-host", "take-and-hold", 2, False),
            ("Huron's Marauders", "disruption", 3, False),
            ("Nightmare Hunt", "disruption", 2, False),
            ("Pactbound Zealots", "priority-assets", 3, False),
            ("Renegade Raiders", "reconnaissance", 3, False),
            ("Renegade Warband", "priority-assets", 2, False),
            ("Soulforged Warpack", "purge-the-foe", 2, False),
            ("Veterans of the Long War", "take-and-hold", 2, False),
            ("Warpstrike Champions", "disruption", 2, False),
        ),
        "world-eaters": (
            ("Butchers of Khorne", "disruption", 1, True),
            ("Brazen Engines", "purge-the-foe", 1, True),
            ("Vessels of Wrath", "priority-assets", 1, True),
            ("Berzerker Warband", "purge-the-foe", 3, False),
            ("Cult of Blood", "priority-assets", 2, False),
            ("Goretrack Onslaught", "take-and-hold", 2, False),
            ("Khorne Daemonkin", "reconnaissance", 2, False),
            ("Possessed Slaughterband", "purge-the-foe", 2, False),
        ),
        "emperors-children": (
            ("Elegant Brutes", "take-and-hold", 1, True),
            ("Frenzied Host", "disruption", 1, True),
            ("Spectacle of Slaughter", "purge-the-foe", 1, True),
            ("Carnival of Excess", "priority-assets", 2, False),
            ("Coterie of the Conceited", "purge-the-foe", 3, False),
            ("Court of the Phoenician", "purge-the-foe", 2, False),
            ("Mercurial Host", "reconnaissance", 2, False),
            ("Peerless Bladesmen", "priority-assets", 2, False),
            ("Rapid Evisceration", "disruption", 2, False),
            ("Slaanesh's Chosen", "purge-the-foe", 2, False),
        ),
        "death-guard": (
            ("Paragons of Putrescence", "priority-assets", 1, True),
            ("Contagion Engines", "purge-the-foe", 1, True),
            ("Flyblown Host", "reconnaissance", 1, True),
            ("Champions of Contagion", "take-and-hold", 2, False),
            ("Death Lord's Chosen", "priority-assets", 2, False),
            ("Mortarion's Hammer", "purge-the-foe", 2, False),
            ("Shamblerot Vectorium", "disruption", 2, False),
            ("Tallyband Summoners", "disruption", 2, False),
            ("Virulent Vectorium", "take-and-hold", 3, False),
        ),
        "thousand-sons": (
            ("Ritual of Regeneration", "purge-the-foe", 1, True),
            ("Sekhetar Cohort", "priority-assets", 1, True),
            ("Servants of Change", "reconnaissance", 1, True),
            ("Changehost of Deceit", "reconnaissance", 2, False),
            ("Grand Coven", "priority-assets", 3, False),
            ("Hexwarp Thrallband", "take-and-hold", 2, False),
            ("Rubricae Phalanx", "take-and-hold", 3, False),
            ("Warpforged Cabal", "disruption", 2, False),
            ("Warpmeld Pact", "purge-the-foe", 2, False),
        ),
        "chaos-knights": (
            ("Bastions of Tyranny", "disruption", 1, True),
            ("Hunting Warpack", "reconnaissance", 1, True),
            ("Iconoclast Fiefdom", "take-and-hold", 1, True),
            ("Helhunt Lance", "disruption", 2, False),
            ("Houndpack Lance", "reconnaissance", 2, False),
            ("Infernal Lance", "purge-the-foe", 3, False),
            ("Lords of Dread", "priority-assets", 2, False),
            ("Traitoris Lance", "purge-the-foe", 2, False),
        ),
        "chaos-daemons": (
            ("Cavalcade of Chaos", "disruption", 1, True),
            ("Lords of the Warp", "purge-the-foe", 1, True),
            ("Warptide", "reconnaissance", 1, True),
            ("Blood Legion", "purge-the-foe", 2, False),
            ("Daemonic Incursion", "disruption", 3, False),
            ("Legion of Excess", "priority-assets", 2, False),
            ("Plague Legion", "take-and-hold", 2, False),
            ("Scintillating Legion", "priority-assets", 2, False),
            ("Shadow Legion", "purge-the-foe", 2, False),
        ),
    }


def test_phase16_imperial_faction_detachment_source_rows_match_requested_matrix() -> None:
    imperial_faction_ids = {
        "adepta-sororitas",
        "adeptus-custodes",
        "adeptus-mechanicus",
        "astra-militarum",
        "imperial-agents",
        "imperial-knights",
    }
    rows_by_faction = {
        faction_id: tuple(
            (
                row.raw_name,
                row.force_disposition_id,
                row.detachment_point_cost,
                row.is_new_for_eleventh,
            )
            for row in faction_detachment_source.detachment_rows()
            if row.faction_id == faction_id
        )
        for faction_id in imperial_faction_ids
    }

    assert rows_by_faction == {
        "astra-militarum": (
            ("Abhuman Auxiliaries", "take-and-hold", 1, True),
            ("Bridgehead Strike", "priority-assets", 1, True),
            ("Designation Force", "reconnaissance", 1, True),
            ("Armoured Infantry", "take-and-hold", 2, False),
            ("Combined Arms", "take-and-hold", 3, False),
            ("Grizzled Company", "priority-assets", 3, False),
            ("Hammer of the Emperor", "purge-the-foe", 2, False),
            ("Mechanised Assault", "purge-the-foe", 2, False),
            ("Recon Element", "reconnaissance", 3, False),
            ("Siege Regiment", "disruption", 2, False),
            ("Steel Hammer", "purge-the-foe", 2, False),
        ),
        "adepta-sororitas": (
            ("Chorus of Condemnation", "reconnaissance", 1, True),
            ("Sacred Champions", "take-and-hold", 1, True),
            ("Sanctified Orators", "purge-the-foe", 1, True),
            ("Army of Faith", "take-and-hold", 2, False),
            ("Bringers of Flame", "purge-the-foe", 3, False),
            ("Champions of Faith", "disruption", 2, False),
            ("Hallowed Martyrs", "priority-assets", 3, False),
            ("Penitent Host", "take-and-hold", 2, False),
        ),
        "adeptus-mechanicus": (
            ("Cohort Acquisitus", "reconnaissance", 1, True),
            ("Lords of the Forge", "priority-assets", 1, True),
            ("Luminen Auto-Choir", "disruption", 1, True),
            ("Cohort Cybernetica", "take-and-hold", 2, False),
            ("Data-psalm Conclave", "disruption", 2, False),
            ("Eradication Cohort", "purge-the-foe", 3, False),
            ("Explorator Maniple", "priority-assets", 2, False),
            ("Haloscreed Battle Clade", "purge-the-foe", 3, False),
            ("Rad-zone Corps", "take-and-hold", 2, False),
            ("Skitarii Hunter Cohort", "reconnaissance", 2, False),
        ),
        "imperial-knights": (
            ("Dominus Foebreakers", "purge-the-foe", 1, True),
            ("Questor Forgepact", "disruption", 1, True),
            ("Throne-bonded Outriders", "reconnaissance", 1, True),
            ("Freeblade Company", "purge-the-foe", 3, False),
            ("Gate Warden Lance", "priority-assets", 2, False),
            ("Questoris Companions", "take-and-hold", 3, False),
            ("Spearhead-at-arms", "reconnaissance", 2, False),
            ("Valourstrike Lance", "purge-the-foe", 2, False),
        ),
        "adeptus-custodes": (
            ("Might of the Moritoi", "purge-the-foe", 1, True),
            ("Silent Hunters", "reconnaissance", 1, True),
            ("Tharanatoi Hammerblow", "priority-assets", 1, True),
            ("Auric Champions", "priority-assets", 2, False),
            ("Lions of the Emperor", "disruption", 2, False),
            ("Null Maiden Vigil", "reconnaissance", 2, False),
            ("Shield Host", "purge-the-foe", 2, False),
            ("Solar Spearhead", "take-and-hold", 2, False),
            ("Talons of the Emperor", "take-and-hold", 3, False),
        ),
        "imperial-agents": (
            ("Imperialis Fleet", "disruption", 3, False),
            ("Ordo Hereticus, Purgation Force", "priority-assets", 3, False),
            ("Ordo Malleus, Daemon Hunters", "reconnaissance", 3, False),
            ("Ordo Xenos, Alien Hunters", "purge-the-foe", 3, False),
            ("Veiled Blade Elimination Force", "purge-the-foe", 3, False),
        ),
    }


def test_phase16_faction_detachment_source_rows_fail_fast_on_bad_data() -> None:
    with pytest.raises(faction_detachment_source.FactionDetachmentSourceError, match="slug"):
        faction_detachment_source.SourceFactionRow(
            faction_id="Bad Faction",
            raw_name="Bad Faction",
        )
    with pytest.raises(faction_detachment_source.FactionDetachmentSourceError, match="raw_name"):
        faction_detachment_source.SourceFactionRow(
            faction_id="bad-faction",
            raw_name=cast(str, 1),
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="detachment_id",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="wrong-id",
            raw_name="Gladius Task Force",
            force_disposition_id="priority-assets",
            detachment_point_cost=3,
            is_new_for_eleventh=False,
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="force_disposition_id",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="gladius-task-force",
            raw_name="Gladius Task Force",
            force_disposition_id="unknown-disposition",
            detachment_point_cost=3,
            is_new_for_eleventh=False,
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="detachment_point_cost",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="gladius-task-force",
            raw_name="Gladius Task Force",
            force_disposition_id="priority-assets",
            detachment_point_cost=4,
            is_new_for_eleventh=False,
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="is_new_for_eleventh",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="gladius-task-force",
            raw_name="Gladius Task Force",
            force_disposition_id="priority-assets",
            detachment_point_cost=3,
            is_new_for_eleventh=cast(bool, "yes"),
        )


def test_phase16_faction_detachment_matrix_supports_strike_force_combinations() -> None:
    catalog = _phase16_source_detachment_catalog()
    gladius_task_force = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("gladius-task-force",),
    )
    firestorm_plus_fulguris = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("firestorm-assault-force", "fulguris-task-force"),
    )
    black_templar_force = DetachmentSelection(
        faction_id="black-templars",
        detachment_ids=(
            "companions-of-vehemence",
            "marshals-household",
        ),
    )

    _space_marines, space_marine_detachments = validate_detachment_selection(
        catalog=catalog,
        selection=gladius_task_force,
    )
    assert tuple(detachment.detachment_id for detachment in space_marine_detachments) == (
        "gladius-task-force",
    )
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=gladius_task_force,
    ) == ("priority-assets",)
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=firestorm_plus_fulguris,
    ) == ("disruption", "purge-the-foe")
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=black_templar_force,
    ) == ("priority-assets", "purge-the-foe")


def test_phase16_faction_detachment_matrix_supports_chaos_strike_force_combinations() -> None:
    catalog = _phase16_source_detachment_catalog()
    chaos_space_marine_new_detachments = DetachmentSelection(
        faction_id="chaos-space-marines",
        detachment_ids=(
            "cabal-of-chaos",
            "devotees-of-destruction",
            "murdertalon-raiders",
        ),
    )
    daemon_combined_force = DetachmentSelection(
        faction_id="chaos-daemons",
        detachment_ids=(
            "cavalcade-of-chaos",
            "legion-of-excess",
        ),
    )
    death_guard_virulent_vectorium = DetachmentSelection(
        faction_id="death-guard",
        detachment_ids=("virulent-vectorium",),
    )
    over_limit_daemon_force = DetachmentSelection(
        faction_id="chaos-daemons",
        detachment_ids=(
            "daemonic-incursion",
            "warptide",
        ),
    )

    faction, detachments = validate_detachment_selection(
        catalog=catalog,
        selection=chaos_space_marine_new_detachments,
    )

    assert faction.faction_id == "chaos-space-marines"
    assert tuple(detachment.detachment_id for detachment in detachments) == (
        "cabal-of-chaos",
        "devotees-of-destruction",
        "murdertalon-raiders",
    )
    assert tuple(detachment.detachment_point_cost for detachment in detachments) == (1, 1, 1)
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=chaos_space_marine_new_detachments,
    ) == ("disruption", "priority-assets", "purge-the-foe")
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=daemon_combined_force,
    ) == ("disruption", "priority-assets")
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=death_guard_virulent_vectorium,
    ) == ("take-and-hold",)
    with pytest.raises(ListValidationError, match="Detachment Points"):
        validate_detachment_selection(catalog=catalog, selection=over_limit_daemon_force)


def test_phase16_faction_detachment_matrix_applies_source_corrections() -> None:
    catalog = _phase16_source_detachment_catalog()

    assert _detachment_by_id(catalog, "librarius-conclave").force_disposition_ids == (
        "reconnaissance",
    )
    assert _detachment_by_id(catalog, "subversion-assets").force_disposition_ids == (
        "reconnaissance",
    )
    assert _detachment_by_id(catalog, "anvil-siege-force").force_disposition_ids == (
        "take-and-hold",
    )
    assert _detachment_by_id(catalog, "armoured-speartip").force_disposition_ids == (
        "take-and-hold",
    )
    assert _detachment_by_id(catalog, "vanguard-spearhead").force_disposition_ids == (
        "reconnaissance",
    )
    assert _detachment_by_id(catalog, "black-spear-task-force").force_disposition_ids == (
        "priority-assets",
    )
    assert _detachment_by_id(catalog, "warpbane-task-force").force_disposition_ids == (
        "purge-the-foe",
    )
    assert _detachment_by_id(catalog, "saga-of-the-bold").force_disposition_ids == (
        "priority-assets",
    )


def test_phase16_faction_detachment_matrix_fails_closed_on_invalid_rows() -> None:
    catalog = _phase16_source_detachment_catalog()
    over_strike_force_limit = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("gladius-task-force", "bastion-task-force"),
    )
    cross_faction_selection = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("marshals-household",),
    )

    with pytest.raises(ListValidationError, match="Detachment Points"):
        validate_detachment_selection(catalog=catalog, selection=over_strike_force_limit)
    with pytest.raises(ListValidationError, match="does not belong to faction"):
        validate_detachment_selection(catalog=catalog, selection=cross_faction_selection)


def test_detachment_selection_fails_closed_on_awaiting_source_grants() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    missing_cost_catalog = ArmyCatalog(
        catalog_id="missing-detachment-cost",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(replace(catalog.detachments[0], detachment_point_cost=None),),
    )
    missing_force_disposition_catalog = ArmyCatalog(
        catalog_id="missing-force-disposition",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(replace(catalog.detachments[0], force_disposition_ids=()),),
    )

    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=missing_cost_catalog, request=_muster_request(missing_cost_catalog))
    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(
            catalog=missing_force_disposition_catalog,
            request=_muster_request(missing_force_disposition_catalog),
        )


def test_mustering_rejects_request_catalog_identity_drift() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog, catalog_id="other-catalog")

    with pytest.raises(ArmyMusteringError, match="catalog_id"):
        muster_army(catalog=catalog, request=request)


def test_mustering_rejects_unknown_datasheets_and_missing_detachments() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    unknown_datasheet_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                datasheet_id="missing-datasheet",
                model_profile_id="core-intercessor-like",
            ),
        ),
    )
    missing_detachment_request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("missing-detachment",),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=catalog, request=unknown_datasheet_request)
    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=catalog, request=missing_detachment_request)


def test_mustering_value_objects_fail_fast_on_invalid_shapes() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)
    army = muster_army(catalog=catalog, request=request)

    with pytest.raises(ArmyMusteringError, match="ruleset_id"):
        replace(request, ruleset_id=cast(RulesetId, "bad-ruleset"))
    with pytest.raises(ArmyMusteringError, match="detachment_selection"):
        replace(request, detachment_selection=cast(DetachmentSelection, "bad-detachment"))
    with pytest.raises(ArmyMusteringError, match="unit_selections"):
        replace(request, unit_selections=())
    with pytest.raises(ArmyMusteringError, match="unique"):
        replace(request, unit_selections=(request.unit_selections[0], request.unit_selections[0]))
    with pytest.raises(ArmyMusteringError, match="unit_instance_id"):
        army.unit_by_id("missing-unit")
    with pytest.raises(ArmyMusteringError, match="ruleset_id"):
        replace(army, ruleset_id=cast(RulesetId, "bad-ruleset"))
    with pytest.raises(ArmyMusteringError, match="detachment_selection"):
        replace(army, detachment_selection=cast(DetachmentSelection, "bad-detachment"))
    with pytest.raises(ArmyMusteringError, match="units"):
        replace(army, units=())
    with pytest.raises(ArmyMusteringError, match="catalog"):
        muster_army(catalog=cast(ArmyCatalog, "bad-catalog"), request=request)
    with pytest.raises(ArmyMusteringError, match="request"):
        muster_army(catalog=catalog, request=cast(ArmyMusterRequest, "bad-request"))
    with pytest.raises(ArmyMusteringError, match="source_package_id"):
        muster_army(catalog=catalog, request=replace(request, source_package_id="other-package"))
    with pytest.raises(ArmyMusteringError, match="ruleset_id"):
        muster_army(
            catalog=catalog,
            request=replace(
                request,
                ruleset_id=RulesetId.warhammer_40000_eleventh(version="other-ruleset"),
            ),
        )


def test_list_validation_fails_fast_on_invalid_selection_shapes() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    detachment_selection = DetachmentSelection(
        faction_id="core-marine-force",
        detachment_ids=("core-combined-arms",),
    )
    unit_selection = _unit_selection()
    faction = catalog.faction_by_id("core-marine-force")
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")

    with pytest.raises(ListValidationError, match="catalog"):
        validate_detachment_selection(
            catalog=cast(ArmyCatalog, "bad-catalog"),
            selection=detachment_selection,
        )
    with pytest.raises(ListValidationError, match="selection"):
        validate_detachment_selection(
            catalog=catalog,
            selection=cast(DetachmentSelection, "bad-selection"),
        )
    with pytest.raises(ListValidationError, match="not found"):
        validate_detachment_selection(
            catalog=catalog,
            selection=DetachmentSelection(
                faction_id="missing-faction",
                detachment_ids=("core-combined-arms",),
            ),
        )
    with pytest.raises(ListValidationError, match="catalog"):
        validate_unit_selection_for_faction(
            catalog=cast(ArmyCatalog, "bad-catalog"),
            selection=unit_selection,
            faction=faction,
        )
    with pytest.raises(ListValidationError, match="selection"):
        validate_unit_selection_for_faction(
            catalog=catalog,
            selection=cast(UnitMusterSelection, "bad-selection"),
            faction=faction,
        )
    with pytest.raises(ListValidationError, match="faction"):
        validate_unit_selection_for_faction(
            catalog=catalog,
            selection=unit_selection,
            faction=cast(FactionDefinition, "bad-faction"),
        )
    with pytest.raises(ListValidationError, match="not legal for faction"):
        validate_unit_selection_for_faction(
            catalog=catalog,
            selection=unit_selection,
            faction=FactionDefinition(
                faction_id="other-faction",
                name="Other Faction",
                faction_keywords=("Other Keyword",),
            ),
        )
    with pytest.raises(ListValidationError, match="datasheet"):
        resolve_model_profile_selections(
            datasheet=cast(DatasheetDefinition, "bad-datasheet"),
            selections=unit_selection.model_profile_selections,
        )
    with pytest.raises(ListValidationError, match="composition"):
        resolve_model_profile_selections(
            datasheet=datasheet,
            selections=(ModelProfileSelection(model_profile_id="missing-profile", model_count=1),),
        )
    with pytest.raises(ListValidationError, match="exceeds"):
        resolve_model_profile_selections(
            datasheet=datasheet,
            selections=(
                ModelProfileSelection(model_profile_id="core-intercessor-like", model_count=11),
            ),
        )
    with pytest.raises(ListValidationError, match="unknown datasheet option"):
        resolve_wargear_selections(
            catalog=catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="unknown-option",
                    model_profile_id="core-intercessor-like",
                    wargear_ids=("core-bolt-rifle",),
                ),
            ),
        )
    with pytest.raises(ListValidationError, match="minimum"):
        resolve_wargear_selections(
            catalog=catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="core-intercessor-like-infantry:default-wargear",
                    model_profile_id="core-intercessor-like",
                    wargear_ids=(),
                ),
            ),
        )
    with pytest.raises(ListValidationError, match="must not include"):
        DetachmentSelection(faction_id="faction:bad", detachment_ids=("core-combined-arms",))
    with pytest.raises(ListValidationError, match="at least 1"):
        ModelProfileSelection(model_profile_id="core-intercessor-like", model_count=0)


def test_unit_factory_instances_and_validators_fail_fast() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    unit = army.units[0]
    model = unit.own_models[0]
    factory = UnitFactory(catalog)
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")

    assert model.stable_identity().startswith("model:army-alpha:intercessor-unit-1")
    assert model.is_alive is True
    assert unit.stable_identity() == "unit:army-alpha:intercessor-unit-1"
    assert unit.alive_own_models() == unit.own_models

    with pytest.raises(UnitFactoryError, match="catalog"):
        UnitFactory(catalog=cast(ArmyCatalog, "bad-catalog"))
    with pytest.raises(UnitFactoryError, match="selection"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=cast(UnitMusterSelection, "bad-selection"),
            datasheet=datasheet,
        )
    with pytest.raises(UnitFactoryError, match="datasheet"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=_unit_selection(),
            datasheet=cast(DatasheetDefinition, "bad-datasheet"),
        )
    with pytest.raises(UnitFactoryError, match="does not match datasheet"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=replace(_unit_selection(), datasheet_id="core-transport"),
            datasheet=datasheet,
        )
    with pytest.raises(UnitFactoryError, match="factory catalog definition"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=_unit_selection(),
            datasheet=replace(datasheet, source_ids=("datasheet:altered",)),
        )
    with pytest.raises(UnitFactoryError, match="base_size"):
        replace(model, base_size=cast(BaseSizeDefinition, "bad-base"))
    with pytest.raises(UnitFactoryError, match="wounds_remaining"):
        replace(model, starting_wounds=1, wounds_remaining=2)
    with pytest.raises(UnitFactoryError, match="characteristics"):
        replace(model, characteristics=())
    with pytest.raises(UnitFactoryError, match="own_models"):
        replace(unit, own_models=())
    with pytest.raises(UnitFactoryError, match="duplicate"):
        replace(unit, own_models=(model, model))
    with pytest.raises(UnitFactoryError, match="wargear_selections"):
        replace(unit, wargear_selections=cast(tuple[WargearSelection, ...], "bad-wargear"))
    with pytest.raises(UnitFactoryError, match="must not include"):
        replace(unit, unit_instance_id="unit:bad")
    with pytest.raises(UnitFactoryError, match="must be a string"):
        replace(model, model_instance_id=cast(str, 1))
