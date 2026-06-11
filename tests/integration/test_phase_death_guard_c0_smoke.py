from __future__ import annotations

import json
import math
from datetime import date
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusterRequest,
    RosterUnitPointValue,
    muster_army,
)
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import GameLifecycleStage
from warhammer40k_core.geometry.model_geometry import GeometrySourceKind, HeightSourceKind
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_patch import (
    PatchedSourceArtifact,
    SourcePatchTarget,
    SourceTransitionPatchOperation,
    SourceTransitionPatchOperationFamily,
    SourceTransitionPatchPackage,
    apply_transition_patch_package,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
)


@pytest.mark.integration
def test_phase_death_guard_c0_plague_marines_manifest_from_patched_catalog() -> None:
    package = _death_guard_c0_catalog_package()
    catalog = package.army_catalog
    datasheet = catalog.datasheet_by_id("dg-plague-marines")
    plague_bolter = _wargear_by_id(catalog, "dg-plague-bolter")
    plague_bolter_profile = plague_bolter.weapon_profile_by_id("dg-plague-bolter:standard")

    assert "BATTLELINE" in datasheet.keywords.keywords
    assert plague_bolter_profile.strength.final == 5
    assert plague_bolter_profile.range_profile.distance_inches == 24
    assert plague_bolter_profile.keywords[0].value == "Lethal Hits"
    assert all(
        artifact.artifact_name.endswith(".patched.json") for artifact in package.source_artifacts
    )

    army = muster_army(
        catalog=catalog,
        request=_plague_marines_muster_request(catalog),
        model_geometries=package.model_geometries,
    )
    unit = army.unit_by_id("army-alpha:plague-marines-1")
    model = unit.own_models[0]

    assert unit.datasheet_id == "dg-plague-marines"
    assert unit.faction_keywords == ("Death Guard",)
    assert unit.wargear_selections[0].wargear_ids == ("dg-plague-bolter",)
    assert len(unit.own_models) == 5
    assert model.model_profile_id == "dg-plague-marine"
    assert model.geometry.geometry_source_kind is GeometrySourceKind.CATALOG_GEOMETRY_RECORD
    assert model.geometry.geometry_source_id == "model-geometry:dg-plague-marine"
    assert model.geometry.height_source_kind is HeightSourceKind.CATALOG_GEOMETRY_RECORD
    assert math.isclose(model.geometry.primary_part().radius_x_inches, 32.0 / 25.4 / 2.0)
    assert math.isclose(model.geometry.height_inches, 1.55)

    state = _setup_state()
    state.record_army_definition(army)

    assert state.army_definition_for_player("player-a") == army
    assert len(state.starting_strength_records) == 1
    assert state.starting_strength_records[0].unit_instance_id == unit.unit_instance_id
    _assert_json_safe_round_trips(package=package, army=army, state=state)


def _assert_json_safe_round_trips(
    *,
    package: CanonicalCatalogPackage,
    army: ArmyDefinition,
    state: GameState,
) -> None:
    package_payload = cast(
        CanonicalCatalogPackagePayload,
        json.loads(json.dumps(package.to_payload(), sort_keys=True)),
    )
    army_payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    state_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    serialized = json.dumps(
        {
            "package": package_payload,
            "army": army_payload,
            "state": state_payload,
        },
        sort_keys=True,
    )

    assert "<" not in serialized
    assert "object at 0x" not in serialized
    assert (
        CanonicalCatalogPackage.from_payload(package_payload).to_payload() == package.to_payload()
    )
    assert ArmyDefinition.from_payload(army_payload).to_payload() == army.to_payload()
    assert GameState.from_payload(state_payload).to_payload() == state.to_payload()


def _death_guard_c0_catalog_package() -> CanonicalCatalogPackage:
    artifacts = _patched_death_guard_source_artifacts()
    return build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="phase-death-guard-c0-smoke",
            version="0.1.0",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="phase-death-guard-c0",
            source_date=date(2026, 6, 10),
        ),
        source_artifacts=artifacts,
    )


def _patched_death_guard_source_artifacts() -> tuple[PatchedSourceArtifact, ...]:
    datasheets = _artifact(
        table_name="Datasheets",
        csv_text=(
            "id,name,content_scope,keywords,faction_keywords\n"
            'dg-plague-marines,Plague Marines,matched_play,"Infantry, Chaos",'
            '"Death Guard"\n'
        ),
    )
    wargear = _artifact(
        table_name="Datasheets_wargear",
        csv_text=(
            "datasheet_id,line,name,wargear_id,weapon_profile_id,model_profile_id,range,a,"
            "skill_characteristic,skill,s,ap,d,weapon_keywords\n"
            "dg-plague-marines,1,Plague bolter,dg-plague-bolter,"
            "dg-plague-bolter:standard,dg-plague-marine,24,2,ballistic_skill,3+,4,-1,1,"
            '"Lethal Hits"\n'
        ),
    )
    patch_package = _death_guard_c0_patch_package(
        datasheet_row=_row_by_id(datasheets, "dg-plague-marines"),
        wargear_row=_row_by_id(wargear, "dg-plague-marines:1"),
    )

    return tuple(
        apply_transition_patch_package(artifact=artifact, patch_package=patch_package)
        for artifact in (
            _artifact(
                table_name="Factions",
                csv_text=(
                    "id,name,content_scope,faction_keywords,army_rule_id,army_rule_name\n"
                    'death-guard,Death Guard,matched_play,"Death Guard",nurgles-gift,'
                    "Nurgle's Gift\n"
                ),
            ),
            datasheets,
            _artifact(
                table_name="Datasheets_models",
                csv_text=(
                    "datasheet_id,line,name,model_profile_id,content_scope,m,t,sv,w,ld,oc,"
                    "ws,bs,min_models,max_models,base_size,height,height_units,"
                    "height_source_id,height_document_reference,height_reviewer_status,"
                    "height_evidence_kind\n"
                    'dg-plague-marines,1,Plague Marine,dg-plague-marine,matched_play,5",5,3+,'
                    "2,6+,2,3+,3+,5,10,32mm,1.55,inches,death-guard-pdf-p12,"
                    "Death Guard Faction Pack p.12,accepted,manual_measurement\n"
                ),
            ),
            wargear,
            _artifact(
                table_name="Enhancements",
                csv_text=(
                    "id,name,description,content_scope,points\n"
                    "beckoning-blight,Beckoning Blight,"
                    '"Official Death Guard update enhancement anchor.",matched_play,25\n'
                ),
            ),
            _artifact(
                table_name="Stratagems",
                csv_text=(
                    "id,name,description,content_scope,command_point_cost,timing_tags\n"
                    "cloud-of-flies,Cloud of Flies,"
                    '"Official Death Guard update stratagem anchor.",matched_play,1,shooting\n'
                ),
            ),
            _artifact(
                table_name="Detachments",
                csv_text=(
                    "id,name,description,content_scope,faction_id,detachment_point_cost,"
                    "unit_datasheet_ids,force_disposition_ids,enhancement_ids,stratagem_ids\n"
                    "tallyband-summoners,Tallyband Summoners,"
                    '"Death Guard C0 smoke detachment anchor.",matched_play,death-guard,2,'
                    "dg-plague-marines,disruption,beckoning-blight,cloud-of-flies\n"
                ),
            ),
        )
    )


def _death_guard_c0_patch_package(
    *,
    datasheet_row: NormalizedSourceRow,
    wargear_row: NormalizedSourceRow,
) -> SourceTransitionPatchPackage:
    return SourceTransitionPatchPackage(
        package_id=DataPackageId(
            namespace="gw",
            package_name="death-guard-transition-patches",
            version="11th-c0",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="phase-death-guard-c0",
            source_date=date(2026, 6, 10),
        ),
        official_source_package_id=DataPackageId(
            namespace="gw",
            package_name="death-guard-faction-pack",
            version="11th-2026-06-10",
        ),
        source_date="2026-06-10",
        source_edition="warhammer-40000-11th",
        faction_id="death-guard",
        operations=(
            _operation(
                operation_id="dg-c0-plague-marines-battleline",
                order_index=10,
                family=SourceTransitionPatchOperationFamily.ADD_KEYWORD,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets",
                    rows=(datasheet_row,),
                ),
                instruction_text="Add BATTLELINE to Plague Marines.",
                payload=(("column_name", "keywords"), ("keyword", "BATTLELINE")),
            ),
            _operation(
                operation_id="dg-c0-plague-bolter-strength",
                order_index=20,
                family=SourceTransitionPatchOperationFamily.REPLACE_WEAPON_CHARACTERISTIC,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets_wargear",
                    rows=(wargear_row,),
                ),
                instruction_text="Change Plague bolter Strength to 5.",
                payload=(("column_name", "s"), ("value", "5")),
            ),
        ),
    )


def _operation(
    *,
    operation_id: str,
    order_index: int,
    family: SourceTransitionPatchOperationFamily,
    target: SourcePatchTarget,
    instruction_text: str,
    payload: tuple[tuple[str, str], ...],
) -> SourceTransitionPatchOperation:
    return SourceTransitionPatchOperation.from_instruction(
        operation_id=operation_id,
        order_index=order_index,
        operation_family=family,
        target=target,
        instruction_text=instruction_text,
        source_ids=(f"phase-death-guard-c0:{operation_id}",),
        payload=payload,
    )


def _artifact(*, table_name: str, csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=DataPackageId(
            namespace="wahapedia",
            package_name="death-guard-c0-source-mirror",
            version="bridge-to-11th",
        ),
        table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=csv_text),
    )


def _row_by_id(artifact: WahapediaJsonArtifact, source_row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _plague_marines_muster_request(catalog: ArmyCatalog) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="death-guard",
            detachment_ids=("tallyband-summoners",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="plague-marines-1",
                datasheet_id="dg-plague-marines",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="dg-plague-marine",
                        model_count=5,
                    ),
                ),
            ),
        ),
        unit_points=(
            RosterUnitPointValue(
                unit_selection_id="plague-marines-1",
                points=90,
                source_id="death-guard-faction-pack:p12:plague-marines-points",
            ),
        ),
        roster_legality_required=False,
    )


def _setup_state() -> GameState:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="phase-death-guard-c0-smoke"
    )
    return GameState(
        game_id="phase-death-guard-c0-smoke-game",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.SETUP,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=0,
        battle_phase_index=None,
        battle_round=0,
        active_player_id=None,
    )


def _wargear_by_id(catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            return wargear
    raise AssertionError(f"Missing wargear {wargear_id}.")
