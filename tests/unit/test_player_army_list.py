from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
)
from warhammer40k_core.core.model_geometry_catalog import GeometrySourceUnits
from warhammer40k_core.engine.army_mustering import (
    ArmyMusteringError,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.army_points import (
    calculate_mfm_army_points,
    catalog_with_mfm_points,
)
from warhammer40k_core.engine.player_army_list import (
    PlayerArmyListError,
    army_muster_request_from_player_army_list,
    load_player_army_list,
    player_army_list_from_json_bytes,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import mfm_2026_06
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import DEFAULT_HEIGHT_OVERRIDES
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

_ROOT = Path(__file__).resolve().parents[2]
_ARMY_LIST_PATH = _ROOT / "data" / "army_lists" / "cavalcade-shadow-bloodthirster.json"
_WAHAPEDIA_JSON = (
    _ROOT
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
_DATASHEET_IDS = (
    "000001115",
    "000002582",
    "000001120",
    "000001132",
    "000001148",
)


def test_saved_player_army_list_musters_with_exact_current_mfm_points() -> None:
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    catalog = _player_army_list_catalog()
    points_source = mfm_2026_06.source_package()

    request = army_muster_request_from_player_army_list(
        catalog=catalog,
        army_list=army_list,
        points_source_package=points_source,
        army_id="cavalcade-shadow-bloodthirster",
        player_id="player-a",
    )
    calculation = calculate_mfm_army_points(
        catalog=catalog,
        request=request,
        source_package=points_source,
    )
    lines_by_selection_id = {
        line.unit_selection_id: (line.unit_number, line.base_points, line.total_points)
        for line in calculation.unit_lines
    }

    assert army_list.force_disposition_id == "purge-the-foe"
    assert army_list.detachment_selection.detachment_ids == (
        "cavalcade-of-chaos",
        "shadow-legion",
    )
    assert lines_by_selection_id == {
        "belakor": (1, 390, 390),
        "bloodcrushers-1": (1, 180, 180),
        "bloodcrushers-2": (2, 180, 180),
        "bloodcrushers-3": (3, 190, 190),
        "bloodthirster": (1, 320, 320),
        "lord-of-change-1": (1, 300, 300),
        "lord-of-change-2": (2, 300, 300),
        "plaguebearers": (1, 115, 115),
    }
    assert tuple(
        (
            line.enhancement_id,
            line.target_unit_selection_id,
            line.points,
        )
        for line in calculation.enhancement_lines
    ) == (
        ("apocalyptic-steeds", "bloodcrushers-1", 10),
        ("apocalyptic-steeds", "bloodcrushers-2", 10),
    )
    assert calculation.total_points == 1995
    assert request.points_source_package_id == points_source.source_package_id
    assert sum(point.points for point in request.unit_points) == 1975
    assert tuple(
        (
            point.enhancement_id,
            point.target_unit_selection_id,
            point.points,
            point.source_id,
        )
        for point in request.enhancement_point_values
    ) == (
        (
            "apocalyptic-steeds",
            "bloodcrushers-1",
            10,
            (
                "gw-11e-mfm-2026-06:faction:chaos-daemons:detachment:"
                "cavalcade-of-chaos:enhancement:apocalyptic-steeds"
            ),
        ),
        (
            "apocalyptic-steeds",
            "bloodcrushers-2",
            10,
            (
                "gw-11e-mfm-2026-06:faction:chaos-daemons:detachment:"
                "cavalcade-of-chaos:enhancement:apocalyptic-steeds"
            ),
        ),
    )

    army = muster_army(catalog=catalog, request=request)

    assert army.force_disposition_id == "purge-the-foe"
    assert army.points_source_package_id == points_source.source_package_id
    assert army.enhancement_point_values == request.enhancement_point_values
    assert army.roster_legality_report.is_legal
    assert len(army.units) == 8
    assert army.warlord_selection is not None
    assert army.warlord_selection.unit_selection_id == "belakor"
    units_by_selection_id = {
        unit.unit_instance_id.removeprefix(f"{army.army_id}:"): unit for unit in army.units
    }
    for selection_id in ("lord-of-change-1", "lord-of-change-2"):
        assert len(units_by_selection_id[selection_id].own_models) == 1
        assert set(units_by_selection_id[selection_id].own_models[0].wargear_ids) == {
            "000001120:bolt-of-change",
            "000001120:staff-of-tzeentch",
        }
    assert ArmyMusterRequest.from_payload(request.to_payload()).to_payload() == request.to_payload()


def test_player_army_list_rejects_per_unit_point_drift_even_when_total_is_unchanged() -> None:
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    first, second, *remaining = army_list.units
    drifted = replace(
        army_list,
        units=(
            replace(first, declared_points=first.declared_points + 1),
            replace(second, declared_points=second.declared_points - 1),
            *remaining,
        ),
    )

    with pytest.raises(PlayerArmyListError, match="declared unit points"):
        army_muster_request_from_player_army_list(
            catalog=_player_army_list_catalog(),
            army_list=drifted,
            points_source_package=mfm_2026_06.source_package(),
            army_id="drifted-player-list",
            player_id="player-a",
        )


def test_player_army_list_rejects_force_disposition_not_granted_by_detachments() -> None:
    army_list = replace(
        load_player_army_list(_ARMY_LIST_PATH),
        force_disposition_id="priority-assets",
    )
    catalog = _player_army_list_catalog()
    request = army_muster_request_from_player_army_list(
        catalog=catalog,
        army_list=army_list,
        points_source_package=mfm_2026_06.source_package(),
        army_id="invalid-force-disposition",
        player_id="player-a",
    )

    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=catalog, request=request)


def test_player_army_list_json_loader_is_strict_and_round_trips() -> None:
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    payload = json.loads(_ARMY_LIST_PATH.read_bytes())
    payload["unknown_field"] = "must-fail-closed"

    with pytest.raises(PlayerArmyListError, match="JSON artifact is invalid"):
        player_army_list_from_json_bytes(json.dumps(payload).encode())

    assert (
        player_army_list_from_json_bytes(json.dumps(army_list.to_payload()).encode()).to_payload()
        == army_list.to_payload()
    )


def test_player_army_list_allows_missing_pre_game_result_but_rejects_null() -> None:
    payload = json.loads(_ARMY_LIST_PATH.read_bytes())
    del payload["provenance"]["game_result"]

    pre_game = player_army_list_from_json_bytes(json.dumps(payload).encode())

    assert pre_game.provenance.game_result is None
    assert "game_result" not in pre_game.to_payload()["provenance"]

    payload["provenance"]["game_result"] = None
    with pytest.raises(PlayerArmyListError, match="non-canonical"):
        player_army_list_from_json_bytes(json.dumps(payload).encode())


def test_player_army_list_rejects_stale_catalog_enhancement_points() -> None:
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    catalog = _player_army_list_catalog()
    stale_catalog = replace(
        catalog,
        enhancements=tuple(
            replace(enhancement, points=999)
            if enhancement.enhancement_id == "apocalyptic-steeds"
            else enhancement
            for enhancement in catalog.enhancements
        ),
    )

    with pytest.raises(PlayerArmyListError, match="catalog Enhancement points"):
        army_muster_request_from_player_army_list(
            catalog=stale_catalog,
            army_list=army_list,
            points_source_package=mfm_2026_06.source_package(),
            army_id="stale-enhancement-price",
            player_id="player-a",
        )


def test_player_army_list_rejects_non_mfm_enhancement_assignment_source() -> None:
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    first, *remaining = army_list.enhancement_assignments
    mismatched = replace(
        army_list,
        enhancement_assignments=(
            replace(first, source_id="player-list:unverified-enhancement-source"),
            *remaining,
        ),
    )

    with pytest.raises(PlayerArmyListError, match="assignment source"):
        army_muster_request_from_player_army_list(
            catalog=_player_army_list_catalog(),
            army_list=mismatched,
            points_source_package=mfm_2026_06.source_package(),
            army_id="mismatched-enhancement-source",
            player_id="player-a",
        )


@lru_cache(maxsize=1)
def _player_army_list_catalog() -> ArmyCatalog:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="wahapedia-" + "1" + "0" + "e-bridge",
            version="player-army-list-test",
        ),
        datasheet_ids=_DATASHEET_IDS,
        height_overrides=(*DEFAULT_HEIGHT_OVERRIDES, *_player_list_height_overrides()),
    )
    package = build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="player-army-list-catalog",
            version="v1",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-player-army-list",
            source_date=date(2026, 6, 17),
        ),
        source_artifacts=bridge_artifacts,
    )
    datasheet_ids = tuple(datasheet.datasheet_id for datasheet in package.army_catalog.datasheets)
    apocalyptic_steeds = EnhancementDefinition(
        enhancement_id="apocalyptic-steeds",
        name="Apocalyptic Steeds (Upgrade)",
        source_id=(
            "gw-11e-mfm-2026-06:faction:chaos-daemons:detachment:"
            "cavalcade-of-chaos:enhancement:apocalyptic-steeds"
        ),
        subtypes=(EnhancementSubtype.UPGRADE,),
        target_required_keywords=("MOUNTED",),
    )
    chaos_daemons_faction = replace(
        package.army_catalog.factions[0],
        faction_id="chaos-daemons",
    )
    catalog = replace(
        package.army_catalog,
        factions=(chaos_daemons_faction,),
        detachments=(
            DetachmentDefinition(
                detachment_id="cavalcade-of-chaos",
                name="Cavalcade of Chaos",
                faction_id="chaos-daemons",
                detachment_point_cost=1,
                unit_datasheet_ids=datasheet_ids,
                force_disposition_ids=("disruption",),
                enhancement_ids=(apocalyptic_steeds.enhancement_id,),
                source_ids=(
                    "gw-11e-mfm-2026-06:faction:chaos-daemons:detachment:cavalcade-of-chaos",
                ),
            ),
            DetachmentDefinition(
                detachment_id="shadow-legion",
                name="Shadow Legion",
                faction_id="chaos-daemons",
                detachment_point_cost=2,
                unit_datasheet_ids=datasheet_ids,
                force_disposition_ids=("purge-the-foe",),
                source_ids=("gw-11e-mfm-2026-06:faction:chaos-daemons:detachment:shadow-legion",),
            ),
        ),
        enhancements=(apocalyptic_steeds,),
    )
    return catalog_with_mfm_points(
        catalog=catalog,
        faction_id="chaos-daemons",
        source_package=mfm_2026_06.source_package(),
    )


@lru_cache(maxsize=1)
def _wahapedia_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return tuple(
        WahapediaJsonArtifact.from_payload(
            cast(
                WahapediaJsonArtifactPayload,
                json.loads((_WAHAPEDIA_JSON / f"{table_name}.json").read_text(encoding="utf-8")),
            )
        )
        for table_name in _REQUIRED_TABLES
    )


def _player_list_height_overrides() -> tuple[ModelHeightOverride, ...]:
    return tuple(
        ModelHeightOverride(
            datasheet_id=datasheet_id,
            model_name=model_name,
            height=height,
            height_units=GeometrySourceUnits.INCHES,
            height_source_id=f"player-army-list-test:{datasheet_id}:{model_name}:height",
            height_document_reference=document_reference,
        )
        for datasheet_id, model_name, height, document_reference in (
            (
                "000002582",
                "Bloodthirster",
                5.75,
                "Chaos Daemons Faction Pack p.16-17",
            ),
            (
                "000001120",
                "Lord of Change",
                5.5,
                "Chaos Daemons Faction Pack p.40-41",
            ),
            (
                "000001132",
                "Plagueridden",
                1.8,
                "Chaos Daemons Faction Pack p.78-79",
            ),
            (
                "000001132",
                "Plaguebearers",
                1.8,
                "Chaos Daemons Faction Pack p.78-79",
            ),
            (
                "000001148",
                "Be'lakor - EPIC HERO",
                5.0,
                "Chaos Daemons Faction Pack p.12-13",
            ),
        )
    )
