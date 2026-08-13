from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tools.generate_chaos_daemons_roster_catalog import build_catalog_package

from warhammer40k_core.adapters.capability_manifest import (
    CapabilityManifestPayload,
    CapabilityResultPayload,
    CapabilityRowPayload,
    build_capability_manifest,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageSupportStage,
    ability_coverage_rows_from_catalog,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusteringError,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.army_points import (
    calculate_mfm_army_points,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifest,
    RuntimeContentModuleFamily,
    RuntimeContentSemanticStatus,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle_for_armies,
    runtime_content_manifest_for_ruleset,
)
from warhammer40k_core.engine.faction_content.runtime_evidence import (
    RuntimeEvidenceProvider,
    active_runtime_evidence_inventory,
)
from warhammer40k_core.engine.faction_rule_execution import (
    FactionRuleExecutionRegistry,
    default_faction_rule_generic_ir_executor,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.player_army_list import (
    PlayerArmyListError,
    army_muster_request_from_player_army_list,
    load_player_army_list,
    player_army_list_from_json_bytes,
)
from warhammer40k_core.geometry.model_geometry import GeometrySourceKind, HeightSourceKind
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07,
    mfm_2026_07,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

_ROOT = Path(__file__).resolve().parents[2]
_ARMY_LIST_PATH = _ROOT / "data" / "army_lists" / "cavalcade-shadow-bloodthirster.json"
_RECONCILIATION_PATH = (
    _ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "chaos_daemons_roster_2026_07"
    / chaos_daemons_roster_2026_07.RECONCILIATION_ARTIFACT_PATH
)
_APOCALYPTIC_STEEDS_ID = "chaos-daemons:cavalcade-of-chaos:apocalyptic-steeds-upgrade"
_DAEMON_LORD_OF_KHORNE_RUNTIME_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:bloodthirster:daemon_lord_of_khorne"
)
_DAEMONIC_MANIFESTATION_EXECUTION_ID = (
    "gw-11e-faction-packs-2026-07:phase17f:army-rule:chaos-daemons:daemonic-manifestation"
)
_DAEMONIC_MANIFESTATION_RUNTIME_ID = (
    "warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos:july_2026"
)
_DAEMONIC_MANIFESTATION_PREDECESSOR_EXECUTION_ID = "phase17f:phase17e:chaos-daemons:army-rule"
catalog_package = chaos_daemons_roster_2026_07.catalog_package

type _ExactRosterRuntime = tuple[
    GameConfig,
    tuple[ArmyDefinition, ...],
    RuntimeContentManifest,
    RuntimeContentBundle,
    CapabilityManifestPayload,
]


@pytest.fixture(scope="module")
def exact_roster_runtime() -> _ExactRosterRuntime:
    package = catalog_package()
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    points_source = mfm_2026_07.source_package()
    requests = tuple(
        army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=army_list,
            points_source_package=points_source,
            army_id=f"chaos-daemons-army-{player_suffix}",
            player_id=f"player-{player_suffix}",
        )
        for player_suffix in ("a", "b")
    )
    config = GameConfig(
        game_id="chaos-daemons-exact-roster-runtime-proof",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="phase17o-chaos-daemons-exact-roster-runtime-proof"
        ),
        army_catalog=package.army_catalog,
        army_muster_requests=requests,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
            terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-1",
            attacker_player_id="player-a",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
        model_geometries=package.model_geometries,
    )
    armies = tuple(
        muster_army(
            catalog=package.army_catalog,
            request=replace(request, roster_legality_required=False),
            model_geometries=config.model_geometries,
        )
        for request in requests
    )
    runtime_manifest = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=config.ruleset_descriptor,
        config=config,
    )
    runtime_bundle = build_runtime_content_bundle_for_armies(
        config=config,
        armies=armies,
    )
    manifest = build_capability_manifest(
        config=config,
        armies=armies,
        runtime_manifest=runtime_manifest,
        runtime_bundle=runtime_bundle,
    )
    return config, armies, runtime_manifest, runtime_bundle, manifest


def _capability_result(
    row: CapabilityRowPayload,
    dimension: str,
) -> CapabilityResultPayload:
    return next(result for result in row["capabilities"] if result["dimension"] == dimension)


def test_saved_player_army_list_reconciles_with_exact_current_mfm_points() -> None:
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    package = catalog_package()
    catalog = package.army_catalog
    points_source = mfm_2026_07.source_package()

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
        "bloodcrushers-1": (1, 190, 190),
        "bloodcrushers-2": (2, 190, 190),
        "bloodcrushers-3": (3, 210, 210),
        "bloodthirster": (1, 320, 320),
        "lord-of-change-1": (1, 320, 320),
        "lord-of-change-2": (2, 320, 320),
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
        (_APOCALYPTIC_STEEDS_ID, "bloodcrushers-1", 10),
        (_APOCALYPTIC_STEEDS_ID, "bloodcrushers-2", 10),
    )
    assert calculation.total_points == 2075
    assert request.points_source_package_id == points_source.source_package_id
    assert sum(point.points for point in request.unit_points) == 2055
    assert sum(point.points for point in request.enhancement_point_values) == 20
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
            _APOCALYPTIC_STEEDS_ID,
            "bloodcrushers-1",
            10,
            (
                "gw-11e-mfm-2026-07:faction:chaos-daemons:detachment:"
                "cavalcade-of-chaos:enhancement:apocalyptic-steeds"
            ),
        ),
        (
            _APOCALYPTIC_STEEDS_ID,
            "bloodcrushers-2",
            10,
            (
                "gw-11e-mfm-2026-07:faction:chaos-daemons:detachment:"
                "cavalcade-of-chaos:enhancement:apocalyptic-steeds"
            ),
        ),
    )

    assert request.roster_legality_required is True
    with pytest.raises(ArmyMusteringError, match="points_limit_exceeded"):
        muster_army(
            catalog=catalog,
            request=request,
        )

    army = muster_army(
        catalog=catalog,
        request=replace(request, roster_legality_required=False),
    )

    assert army.force_disposition_id == "purge-the-foe"
    assert army.points_source_package_id == points_source.source_package_id
    assert army.enhancement_point_values == request.enhancement_point_values
    assert not army.roster_legality_report.is_legal
    assert tuple(
        violation.violation_code for violation in army.roster_legality_report.violations
    ) == ("points_limit_exceeded",)
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
            catalog=catalog_package().army_catalog,
            army_list=drifted,
            points_source_package=mfm_2026_07.source_package(),
            army_id="drifted-player-list",
            player_id="player-a",
        )


def test_player_army_list_rejects_force_disposition_not_granted_by_detachments() -> None:
    army_list = replace(
        load_player_army_list(_ARMY_LIST_PATH),
        force_disposition_id="priority-assets",
    )
    catalog = catalog_package().army_catalog
    request = army_muster_request_from_player_army_list(
        catalog=catalog,
        army_list=army_list,
        points_source_package=mfm_2026_07.source_package(),
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

    pre_game = player_army_list_from_json_bytes(json.dumps(payload).encode())

    assert pre_game.provenance.game_result is None
    assert "game_result" not in pre_game.to_payload()["provenance"]

    payload["provenance"]["game_result"] = None
    with pytest.raises(PlayerArmyListError, match="non-canonical"):
        player_army_list_from_json_bytes(json.dumps(payload).encode())


def test_player_army_list_rejects_stale_catalog_enhancement_points() -> None:
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    catalog = catalog_package().army_catalog
    stale_catalog = replace(
        catalog,
        enhancements=tuple(
            replace(enhancement, points=999)
            if enhancement.enhancement_id == _APOCALYPTIC_STEEDS_ID
            else enhancement
            for enhancement in catalog.enhancements
        ),
    )

    with pytest.raises(PlayerArmyListError, match="catalog Enhancement points"):
        army_muster_request_from_player_army_list(
            catalog=stale_catalog,
            army_list=army_list,
            points_source_package=mfm_2026_07.source_package(),
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
            catalog=catalog_package().army_catalog,
            army_list=mismatched,
            points_source_package=mfm_2026_07.source_package(),
            army_id="mismatched-enhancement-source",
            player_id="player-a",
        )


def test_roster_catalog_artifact_round_trips_with_complete_detachment_dependencies() -> None:
    package = catalog_package()
    catalog = package.army_catalog
    detachments = {detachment.detachment_id: detachment for detachment in catalog.detachments}

    assert build_catalog_package().to_json_bytes() == package.to_json_bytes()
    assert CanonicalCatalogPackage.from_payload(package.to_payload()).to_payload() == (
        package.to_payload()
    )
    assert tuple(record.model_profile_id for record in package.model_geometries) == (
        chaos_daemons_roster_2026_07.EXPECTED_GEOMETRY_PROFILE_IDS
    )
    assert (
        tuple(
            diagnostic.model_profile_id for diagnostic in package.diagnostics if diagnostic.blocking
        )
        == chaos_daemons_roster_2026_07.EXPECTED_GEOMETRY_BLOCKED_PROFILE_IDS
    )
    assert all(
        diagnostic.reason.value == "unreviewed_evidence" for diagnostic in package.diagnostics
    )
    assert set(detachments["cavalcade-of-chaos"].enhancement_ids) == {
        "chaos-daemons:cavalcade-of-chaos:apocalyptic-steeds-upgrade",
        "chaos-daemons:cavalcade-of-chaos:soul-shattering-charge-upgrade",
    }
    assert len(detachments["cavalcade-of-chaos"].stratagem_ids) == 3
    assert len(detachments["shadow-legion"].enhancement_ids) == 4
    assert len(detachments["shadow-legion"].stratagem_ids) == 6


def test_roster_catalog_has_exact_official_pdf_reconciliation_and_clean_runtime_identity() -> None:
    package = catalog_package()
    catalog = package.army_catalog
    reconciliation = chaos_daemons_roster_2026_07.reconciliation_manifest()
    datasheets = {datasheet.datasheet_id: datasheet for datasheet in catalog.datasheets}
    encoded_catalog = package.to_json_bytes().decode()

    assert tuple(row.datasheet_id for row in reconciliation.datasheets) == (
        chaos_daemons_roster_2026_07.EXPECTED_DATASHEET_IDS
    )
    assert "source-mirror" not in encoded_catalog
    assert "chaos-daemons-roster-source-extract" not in encoded_catalog
    assert {
        artifact.artifact_name: artifact.artifact_hash for artifact in package.source_artifacts
    }[chaos_daemons_roster_2026_07.EXPECTED_RECONCILIATION_SOURCE_ARTIFACT[0]] == (
        chaos_daemons_roster_2026_07.EXPECTED_RECONCILIATION_SOURCE_ARTIFACT[1]
    )
    for review in reconciliation.datasheets:
        datasheet = datasheets[review.datasheet_id]
        assert datasheet.keywords.keywords == review.expected_keywords
        assert datasheet.keywords.faction_keywords == review.expected_faction_keywords
        assert "SHADOW LEGION" not in datasheet.keywords.keywords
        assert review.official_source_id in datasheet.source_ids
        assert (
            chaos_daemons_roster_2026_07.catalog_datasheet_gameplay_hash(
                catalog=catalog,
                datasheet_id=review.datasheet_id,
            )
            == review.catalog_gameplay_hash
        )

    belakor = datasheets["000001148"]
    assert tuple((effect.wounds_min, effect.wounds_max) for effect in belakor.damaged_effects) == (
        (1, 7),
    )


def test_roster_catalog_gameplay_hash_covers_rule_execution_identity() -> None:
    catalog = catalog_package().army_catalog
    datasheet = next(row for row in catalog.datasheets if row.datasheet_id == "000001115")
    ability = next(row for row in datasheet.abilities if row.rule_ir_payload is not None)
    assert ability.rule_ir_payload is not None
    mutated_ability = replace(
        ability,
        rule_ir_payload={
            **ability.rule_ir_payload,
            "rule_id": f"{ability.rule_ir_payload['rule_id']}:drift",
        },
    )
    mutated_datasheet = replace(
        datasheet,
        abilities=tuple(
            mutated_ability if row.ability_id == ability.ability_id else row
            for row in datasheet.abilities
        ),
    )
    mutated_catalog = replace(
        catalog,
        datasheets=tuple(
            mutated_datasheet if row.datasheet_id == datasheet.datasheet_id else row
            for row in catalog.datasheets
        ),
    )

    assert chaos_daemons_roster_2026_07.catalog_datasheet_gameplay_hash(
        catalog=mutated_catalog,
        datasheet_id=datasheet.datasheet_id,
    ) != chaos_daemons_roster_2026_07.catalog_datasheet_gameplay_hash(
        catalog=catalog,
        datasheet_id=datasheet.datasheet_id,
    )


def test_roster_reconciliation_rejects_rehashed_official_fact_drift() -> None:
    decoded: object = json.loads(_RECONCILIATION_PATH.read_bytes())
    assert isinstance(decoded, dict)
    payload = cast(dict[str, object], decoded)
    datasheet_rows_value = payload["datasheets"]
    assert isinstance(datasheet_rows_value, list)
    datasheet_rows = cast(list[object], datasheet_rows_value)
    belakor_row: dict[str, object] | None = None
    for value in datasheet_rows:
        if not isinstance(value, dict):
            continue
        row = cast(dict[str, object], value)
        if row.get("datasheet_id") == "000001148":
            belakor_row = row
            break
    assert belakor_row is not None
    belakor_row["expected_damaged_wounds_max"] = 6
    payload["artifact_hash"] = ""
    payload["artifact_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    with pytest.raises(
        chaos_daemons_roster_2026_07.ChaosDaemonsRosterReconciliationError,
        match="review identity drifted",
    ):
        chaos_daemons_roster_2026_07.reconciliation_from_json_bytes(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )


def test_shadow_legion_keyword_is_granted_only_by_selected_detachment() -> None:
    package = catalog_package()
    army_list = load_player_army_list(_ARMY_LIST_PATH)
    points_source = mfm_2026_07.source_package()
    with_shadow_request = army_muster_request_from_player_army_list(
        catalog=package.army_catalog,
        army_list=army_list,
        points_source_package=points_source,
        army_id="with-shadow-legion",
        player_id="player-a",
    )
    with_shadow = muster_army(
        catalog=package.army_catalog,
        request=replace(with_shadow_request, roster_legality_required=False),
    )
    without_shadow_list = replace(
        army_list,
        detachment_selection=replace(
            army_list.detachment_selection,
            detachment_ids=("cavalcade-of-chaos",),
        ),
        force_disposition_id="disruption",
    )
    without_shadow_request = army_muster_request_from_player_army_list(
        catalog=package.army_catalog,
        army_list=without_shadow_list,
        points_source_package=points_source,
        army_id="without-shadow-legion",
        player_id="player-a",
    )
    without_shadow = muster_army(
        catalog=package.army_catalog,
        request=replace(without_shadow_request, roster_legality_required=False),
    )

    assert all(not army.roster_legality_report.is_legal for army in (with_shadow, without_shadow))
    assert all(
        tuple(violation.violation_code for violation in army.roster_legality_report.violations)
        == ("points_limit_exceeded",)
        for army in (with_shadow, without_shadow)
    )
    assert all("SHADOW LEGION" in unit.keywords for unit in with_shadow.units)
    assert all("SHADOW LEGION" not in unit.keywords for unit in without_shadow.units)


def test_exact_roster_phase17o_support_has_active_runtime_evidence(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, manifest = exact_roster_runtime

    assert config.allow_legacy_non_strict_rosters is False
    assert config.model_geometries is not None
    assert tuple(record.model_profile_id for record in config.model_geometries) == (
        chaos_daemons_roster_2026_07.EXPECTED_GEOMETRY_PROFILE_IDS
    )
    assert GameConfig.from_payload(config.to_payload()).model_geometries == config.model_geometries
    assert len(config.army_muster_requests) == 2
    assert {request.player_id for request in config.army_muster_requests} == {
        "player-a",
        "player-b",
    }
    assert all(not army.roster_legality_report.is_legal for army in armies)
    assert all(
        tuple(violation.violation_code for violation in army.roster_legality_report.violations)
        == ("points_limit_exceeded",)
        for army in armies
    )
    assert all(
        calculate_mfm_army_points(
            catalog=config.army_catalog,
            request=request,
            source_package=mfm_2026_07.source_package(),
        ).total_points
        == 2075
        for request in config.army_muster_requests
    )

    selected_datasheet_ids = tuple(
        sorted(
            {
                selection.datasheet_id
                for request in config.army_muster_requests
                for selection in request.unit_selections
            }
        )
    )
    assert selected_datasheet_ids == (
        "000001115",
        "000001120",
        "000001132",
        "000001148",
        "000002582",
    )
    ability_coverage = ability_coverage_rows_from_catalog(
        config.army_catalog,
        datasheet_ids=selected_datasheet_ids,
    )
    assert ability_coverage
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        and row.runtime_consumer_ids
        for row in ability_coverage
    )

    ability_rule_rows = tuple(
        row for row in manifest["rule_rows"] if "coverage_row_id" in row["metadata"]
    )
    assert ability_rule_rows
    assert all(
        _capability_result(row, "SEMANTICALLY_EXECUTABLE")["status"] == "supported"
        and _capability_result(row, "SEMANTICALLY_EXECUTABLE")["evidence_refs"]
        and row["metadata"]["runtime_consumer_ids"]
        for row in ability_rule_rows
    )
    geometry_kinds_by_profile = {
        model.model_profile_id: {
            (candidate.geometry.geometry_source_kind, candidate.geometry.height_source_kind)
            for army in armies
            for unit in army.units
            for candidate in unit.own_models
            if candidate.model_profile_id == model.model_profile_id
        }
        for army in armies
        for unit in army.units
        for model in unit.own_models
    }
    accepted_geometry_profile_ids = frozenset(
        chaos_daemons_roster_2026_07.EXPECTED_GEOMETRY_PROFILE_IDS
    )
    blocked_geometry_profile_ids = frozenset(
        chaos_daemons_roster_2026_07.EXPECTED_GEOMETRY_BLOCKED_PROFILE_IDS
    )
    assert frozenset(geometry_kinds_by_profile) == (
        accepted_geometry_profile_ids | blocked_geometry_profile_ids
    )
    assert all(
        geometry_kinds_by_profile[profile_id]
        == {
            (
                GeometrySourceKind.CATALOG_GEOMETRY_RECORD,
                HeightSourceKind.CATALOG_GEOMETRY_RECORD,
            )
        }
        for profile_id in accepted_geometry_profile_ids
    )
    assert all(
        geometry_kinds_by_profile[profile_id]
        == {(GeometrySourceKind.CATALOG_BASE_SIZE, HeightSourceKind.KEYWORD_HEURISTIC)}
        for profile_id in blocked_geometry_profile_ids
    )

    for row in manifest["roster_rows"]:
        physical_result = _capability_result(row, "PHYSICALLY_PLAYABLE")
        assert physical_result["status"] == "unsupported"
        assert physical_result["reason_code"] == "accepted_model_geometry_missing"
        assert _capability_result(row, "SEMANTICALLY_EXECUTABLE")["status"] == "supported"
    supported_unit_rows = tuple(
        row
        for row in manifest["unit_rows"]
        if _capability_result(row, "PHYSICALLY_PLAYABLE")["status"] == "supported"
    )
    unsupported_unit_rows = tuple(
        row
        for row in manifest["unit_rows"]
        if _capability_result(row, "PHYSICALLY_PLAYABLE")["status"] == "unsupported"
    )
    assert len(supported_unit_rows) == 8
    assert {row["owner_id"] for row in supported_unit_rows} == {
        "belakor",
        "bloodcrushers-1",
        "bloodcrushers-2",
        "bloodcrushers-3",
    }
    assert len(unsupported_unit_rows) == 8
    assert {row["owner_id"] for row in unsupported_unit_rows} == {
        "bloodthirster",
        "lord-of-change-1",
        "lord-of-change-2",
        "plaguebearers",
    }
    assert all(
        _capability_result(row, "PHYSICALLY_PLAYABLE")["reason_code"]
        == "accepted_model_geometry_missing"
        for row in unsupported_unit_rows
    )
    assert all(
        _capability_result(row, "SEMANTICALLY_EXECUTABLE")["status"] == "supported"
        for row in manifest["unit_rows"]
    )
    assert all(
        _capability_result(row, "MUSTERABLE")["status"] == "unsupported"
        and _capability_result(row, "MUSTERABLE")["reason_code"] == "roster_legality_invalid"
        and row["metadata"]["legality_status"] == "invalid"
        for row in manifest["roster_rows"]
    )
    assert all(
        _capability_result(row, "MUSTERABLE")["status"] == "supported"
        for row in manifest["unit_rows"]
    )
    supported_geometry_rows = tuple(
        row
        for row in manifest["geometry_rows"]
        if _capability_result(row, "PHYSICALLY_PLAYABLE")["status"] == "supported"
    )
    unsupported_geometry_rows = tuple(
        row
        for row in manifest["geometry_rows"]
        if _capability_result(row, "PHYSICALLY_PLAYABLE")["status"] == "unsupported"
    )
    assert len(supported_geometry_rows) == 14
    assert {row["owner_id"] for row in supported_geometry_rows} == accepted_geometry_profile_ids
    assert all(
        row["metadata"]["geometry_source_kind"] == GeometrySourceKind.CATALOG_GEOMETRY_RECORD.value
        and row["metadata"]["height_source_kind"] == HeightSourceKind.CATALOG_GEOMETRY_RECORD.value
        for row in supported_geometry_rows
    )
    assert len(unsupported_geometry_rows) == 10
    assert {row["owner_id"] for row in unsupported_geometry_rows} == blocked_geometry_profile_ids
    assert all(
        _capability_result(row, "PHYSICALLY_PLAYABLE")["reason_code"]
        == "heuristic_model_height_not_certified"
        and row["metadata"]["geometry_source_kind"] == GeometrySourceKind.CATALOG_BASE_SIZE.value
        and row["metadata"]["height_source_kind"] == HeightSourceKind.KEYWORD_HEURISTIC.value
        for row in unsupported_geometry_rows
    )
    assert all(
        _capability_result(row, "SEMANTICALLY_EXECUTABLE")["status"] == "supported"
        for row in manifest["rule_rows"]
    )

    selected_detachment_ids = frozenset(
        detachment_id
        for request in config.army_muster_requests
        for detachment_id in request.detachment_selection.detachment_ids
    )
    assert selected_detachment_ids == {"cavalcade-of-chaos", "shadow-legion"}
    selected_detachments = tuple(
        detachment
        for detachment in config.army_catalog.detachments
        if detachment.detachment_id in selected_detachment_ids
    )
    enhancement_ids = frozenset(
        enhancement_id
        for detachment in selected_detachments
        for enhancement_id in detachment.enhancement_ids
    )
    stratagem_ids = frozenset(
        stratagem_id
        for detachment in selected_detachments
        for stratagem_id in detachment.stratagem_ids
    )
    assert len(enhancement_ids) == 6
    assert len(stratagem_ids) == 9

    enhancement_rows = tuple(
        row
        for row in runtime_manifest.rows
        if row.family is RuntimeContentModuleFamily.ENHANCEMENT
        and row.content_id in enhancement_ids
    )
    stratagem_rows = tuple(
        row
        for row in runtime_manifest.rows
        if row.family is RuntimeContentModuleFamily.STRATAGEM and row.content_id in stratagem_ids
    )
    detachment_rows = tuple(
        row
        for row in runtime_manifest.rows
        if row.family is RuntimeContentModuleFamily.DETACHMENT
        and row.content_id in selected_detachment_ids
    )
    assert {row.content_id for row in enhancement_rows} == enhancement_ids
    assert {row.content_id for row in stratagem_rows} == stratagem_ids
    assert {row.content_id for row in detachment_rows} == selected_detachment_ids
    closure_rows = (*enhancement_rows, *stratagem_rows, *detachment_rows)
    assert all(
        row.support_status is RuntimeContentSupportStatus.SUPPORTED
        and row.semantic_status is RuntimeContentSemanticStatus.IMPLEMENTED
        and row.execution_record_ids
        for row in closure_rows
    )
    closure_execution_ids = frozenset(
        execution_id for row in closure_rows for execution_id in row.execution_record_ids
    )
    assert len(closure_execution_ids) == 17
    assert all(execution_id.startswith("phase17f:") for execution_id in closure_execution_ids)
    bundle_summary = runtime_bundle.to_summary_payload()
    assert closure_execution_ids <= frozenset(bundle_summary["selected_execution_record_ids"])

    faction_row = next(
        row
        for row in runtime_manifest.rows
        if row.family is RuntimeContentModuleFamily.FACTION and row.content_id == "chaos-daemons"
    )
    assert _DAEMONIC_MANIFESTATION_EXECUTION_ID in faction_row.execution_record_ids
    assert _DAEMONIC_MANIFESTATION_PREDECESSOR_EXECUTION_ID not in (
        faction_row.execution_record_ids
    )
    daemonic_manifestation_record = (
        runtime_bundle.faction_rule_execution_registry.record_by_execution_id(
            _DAEMONIC_MANIFESTATION_EXECUTION_ID
        )
    )
    assert daemonic_manifestation_record.handler_id == _DAEMONIC_MANIFESTATION_RUNTIME_ID
    all_faction_execution_ids = {
        record.execution_id
        for record in runtime_bundle.faction_rule_execution_registry.all_records()
    }
    assert _DAEMONIC_MANIFESTATION_PREDECESSOR_EXECUTION_ID not in all_faction_execution_ids
    active_evidence = active_runtime_evidence_inventory(runtime_bundle)
    active_evidence_id_set = active_evidence.evidence_ids
    assert _DAEMONIC_MANIFESTATION_EXECUTION_ID in active_evidence_id_set
    assert _DAEMONIC_MANIFESTATION_PREDECESSOR_EXECUTION_ID not in active_evidence_id_set

    apocalyptic_execution_id = next(
        row.execution_record_ids[0]
        for row in enhancement_rows
        if row.content_id == _APOCALYPTIC_STEEDS_ID
    )
    assert bundle_summary["enhancement_effect_binding_ids"] == [apocalyptic_execution_id]
    assert {
        (binding.effect_id, binding.enhancement_id)
        for binding in runtime_bundle.enhancement_effect_registry.all_bindings()
    } == {(apocalyptic_execution_id, _APOCALYPTIC_STEEDS_ID)}
    assert {
        (record.provider, record.owner_content_id)
        for record in active_evidence.records_for_evidence_id(apocalyptic_execution_id)
    } >= {
        (RuntimeEvidenceProvider.FACTION_EXECUTION_RECORD, _APOCALYPTIC_STEEDS_ID),
        (RuntimeEvidenceProvider.ENHANCEMENT_EFFECT_BINDING, _APOCALYPTIC_STEEDS_ID),
    }

    mode_capabilities = {result["dimension"]: result for result in manifest["mode_capabilities"]}
    assert mode_capabilities["MUSTERABLE"]["status"] == "unsupported"
    assert mode_capabilities["MUSTERABLE"]["reason_code"] == "roster_legality_invalid"
    assert mode_capabilities["PHYSICALLY_PLAYABLE"]["status"] == "unsupported"
    assert mode_capabilities["PHYSICALLY_PLAYABLE"]["reason_code"] == (
        "multiple_capability_blockers"
    )
    assert mode_capabilities["SEMANTICALLY_EXECUTABLE"]["status"] == "supported"
    assert mode_capabilities["FULL_GAME_SUPPORTED"]["status"] == "unsupported"
    assert mode_capabilities["REPLAY_VERIFIED"]["status"] == "unsupported"
    assert manifest["certified_scenario_evidence_refs"] == []
    assert manifest["replay_evidence_refs"] == []
    assert manifest["certification_claims"]["phase20a_certified"] is False
    assert manifest["certification_claims"]["phase20d_release_eligible"] is False
    for row in (*manifest["roster_rows"], *manifest["unit_rows"], *manifest["rule_rows"]):
        assert _capability_result(row, "FULL_GAME_SUPPORTED")["status"] == "unsupported"
        assert _capability_result(row, "REPLAY_VERIFIED")["status"] == "unsupported"


def test_exact_roster_phase17o_rejects_inactive_named_runtime_evidence(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    original_bindings = runtime_bundle.runtime_modifier_registry.hit_roll_modifier_bindings
    drifted_bindings = tuple(
        binding
        for binding in original_bindings
        if binding.modifier_id != _DAEMON_LORD_OF_KHORNE_RUNTIME_ID
    )
    assert len(drifted_bindings) == len(original_bindings) - 1
    drifted_bundle = replace(
        runtime_bundle,
        runtime_modifier_registry=replace(
            runtime_bundle.runtime_modifier_registry,
            hit_roll_modifier_bindings=drifted_bindings,
        ),
    )

    with pytest.raises(GameLifecycleError, match="inactive runtime consumer evidence") as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=runtime_manifest,
            runtime_bundle=drifted_bundle,
        )

    assert _DAEMON_LORD_OF_KHORNE_RUNTIME_ID in str(exc_info.value)


def test_exact_roster_phase17o_rejects_missing_selected_enhancement_effect_binding(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    original_bindings = runtime_bundle.enhancement_effect_registry.all_bindings()
    assert len(original_bindings) == 1
    apocalyptic_binding = original_bindings[0]
    assert apocalyptic_binding.enhancement_id == _APOCALYPTIC_STEEDS_ID
    drifted_bundle = replace(
        runtime_bundle,
        enhancement_effect_registry=replace(
            runtime_bundle.enhancement_effect_registry,
            bindings=(),
        ),
    )

    drifted_evidence = active_runtime_evidence_inventory(drifted_bundle)
    apocalyptic_records = drifted_evidence.records_for_evidence_id(apocalyptic_binding.effect_id)
    assert any(
        record.provider is RuntimeEvidenceProvider.FACTION_EXECUTION_RECORD
        for record in apocalyptic_records
    )
    assert all(
        record.provider is not RuntimeEvidenceProvider.ENHANCEMENT_EFFECT_BINDING
        for record in apocalyptic_records
    )

    with pytest.raises(GameLifecycleError, match="inactive runtime consumer evidence") as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=runtime_manifest,
            runtime_bundle=drifted_bundle,
        )

    message = str(exc_info.value)
    assert apocalyptic_binding.effect_id in message
    assert RuntimeEvidenceProvider.ENHANCEMENT_EFFECT_BINDING.value in message
    assert _APOCALYPTIC_STEEDS_ID in message


def test_exact_roster_phase17o_rejects_selected_enhancement_binding_identity_drift(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    original_binding = runtime_bundle.enhancement_effect_registry.all_bindings()[0]
    drifted_binding = replace(
        original_binding,
        enhancement_id="chaos-daemons:cavalcade-of-chaos:wrong-enhancement",
        source_id="test:wrong-enhancement-source",
    )
    drifted_bundle = replace(
        runtime_bundle,
        enhancement_effect_registry=replace(
            runtime_bundle.enhancement_effect_registry,
            bindings=(drifted_binding,),
        ),
    )

    drifted_records = active_runtime_evidence_inventory(drifted_bundle).records_for_evidence_id(
        original_binding.effect_id
    )
    assert any(
        record.provider is RuntimeEvidenceProvider.ENHANCEMENT_EFFECT_BINDING
        and record.owner_content_id == drifted_binding.enhancement_id
        and record.source_id == drifted_binding.source_id
        for record in drifted_records
    )

    with pytest.raises(GameLifecycleError, match="inactive runtime consumer evidence") as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=runtime_manifest,
            runtime_bundle=drifted_bundle,
        )

    message = str(exc_info.value)
    assert original_binding.effect_id in message
    assert original_binding.enhancement_id in message
    assert original_binding.source_id in message


def test_exact_roster_phase17o_rejects_missing_brass_stampede_runtime_hook(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    brass_stampede_consumer_id = "catalog-ir:unit-move-completed-mortal-wounds"
    original_bindings = runtime_bundle.unit_move_completed_mortal_wound_hook_registry.all_bindings()
    assert brass_stampede_consumer_id in {binding.hook_id for binding in original_bindings}
    drifted_bundle = replace(
        runtime_bundle,
        unit_move_completed_mortal_wound_hook_registry=replace(
            runtime_bundle.unit_move_completed_mortal_wound_hook_registry,
            bindings=tuple(
                binding
                for binding in original_bindings
                if binding.hook_id != brass_stampede_consumer_id
            ),
        ),
        hook_bindings_by_event={},
    )

    with pytest.raises(GameLifecycleError, match="inactive runtime consumer evidence") as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=runtime_manifest,
            runtime_bundle=drifted_bundle,
        )

    assert brass_stampede_consumer_id in str(exc_info.value)


def test_exact_roster_phase17o_rejects_missing_soul_shattering_execution_record(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    soul_shattering_content_id = "chaos-daemons:cavalcade-of-chaos:soul-shattering-charge-upgrade"
    soul_shattering_execution_id = next(
        row.execution_record_ids[0]
        for row in runtime_manifest.rows
        if row.family is RuntimeContentModuleFamily.ENHANCEMENT
        and row.content_id == soul_shattering_content_id
    )
    original_records = runtime_bundle.faction_rule_execution_registry.all_records()
    drifted_records = tuple(
        record for record in original_records if record.execution_id != soul_shattering_execution_id
    )
    assert len(drifted_records) == len(original_records) - 1
    drifted_bundle = replace(
        runtime_bundle,
        faction_rule_execution_registry=FactionRuleExecutionRegistry.from_records(
            drifted_records,
            generic_ir_executor=default_faction_rule_generic_ir_executor,
        ),
    )

    with pytest.raises(GameLifecycleError, match="inactive runtime consumer evidence") as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=runtime_manifest,
            runtime_bundle=drifted_bundle,
        )

    assert soul_shattering_execution_id in str(exc_info.value)


def test_exact_roster_phase17o_rejects_active_execution_evidence_owned_by_another_rule(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    apocalyptic_steeds_row = next(
        row
        for row in runtime_manifest.rows
        if row.family is RuntimeContentModuleFamily.ENHANCEMENT
        and row.content_id == _APOCALYPTIC_STEEDS_ID
    )
    cavalcade_row = next(
        row
        for row in runtime_manifest.rows
        if row.family is RuntimeContentModuleFamily.DETACHMENT
        and row.content_id == "cavalcade-of-chaos"
    )
    wrong_execution_id = next(
        execution_id
        for execution_id in cavalcade_row.execution_record_ids
        if execution_id not in apocalyptic_steeds_row.execution_record_ids
    )
    assert wrong_execution_id in active_runtime_evidence_inventory(runtime_bundle).evidence_ids
    drifted_rows = tuple(
        replace(row, execution_record_ids=(wrong_execution_id,))
        if row.content_id == _APOCALYPTIC_STEEDS_ID
        else row
        for row in runtime_manifest.rows
    )
    drifted_manifest = RuntimeContentManifest(rows=drifted_rows)

    with pytest.raises(
        GameLifecycleError,
        match="selected runtime rows drifted from the canonical runtime manifest",
    ) as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=drifted_manifest,
            runtime_bundle=runtime_bundle,
        )

    assert _APOCALYPTIC_STEEDS_ID in str(exc_info.value)


def test_exact_roster_phase17o_rejects_blocked_faction_execution_as_active_evidence(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    blocked_record = next(
        record
        for record in runtime_bundle.faction_rule_execution_registry.all_records()
        if record.is_blocked and record.faction_id == "chaos-daemons"
    )
    assert (
        blocked_record.execution_id
        in runtime_bundle.to_summary_payload()["faction_execution_record_ids"]
    )
    assert (
        blocked_record.execution_id
        not in active_runtime_evidence_inventory(runtime_bundle).evidence_ids
    )

    drifted_rows = tuple(
        replace(
            row,
            execution_record_ids=(blocked_record.execution_id,),
            semantic_status=RuntimeContentSemanticStatus.IMPLEMENTED,
        )
        if row.family is RuntimeContentModuleFamily.DETACHMENT
        and row.content_id == "cavalcade-of-chaos"
        else row
        for row in runtime_manifest.rows
    )
    drifted_manifest = RuntimeContentManifest(rows=drifted_rows)

    with pytest.raises(
        GameLifecycleError, match="unregistered runtime consumer evidence"
    ) as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=drifted_manifest,
            runtime_bundle=runtime_bundle,
        )

    assert blocked_record.execution_id in str(exc_info.value)


def test_exact_roster_phase17o_rejects_predecessor_faction_execution_identity(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    drifted_rows = tuple(
        replace(
            row,
            execution_record_ids=tuple(
                _DAEMONIC_MANIFESTATION_PREDECESSOR_EXECUTION_ID
                if execution_id == _DAEMONIC_MANIFESTATION_EXECUTION_ID
                else execution_id
                for execution_id in row.execution_record_ids
            ),
        )
        if row.family is RuntimeContentModuleFamily.FACTION and row.content_id == "chaos-daemons"
        else row
        for row in runtime_manifest.rows
    )
    drifted_manifest = RuntimeContentManifest(rows=drifted_rows)

    with pytest.raises(GameLifecycleError, match="missing execution record"):
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=drifted_manifest,
            runtime_bundle=runtime_bundle,
        )


def test_exact_roster_phase17o_rejects_executable_faction_record_without_typed_handler_binding(
    exact_roster_runtime: _ExactRosterRuntime,
) -> None:
    config, armies, runtime_manifest, runtime_bundle, _ = exact_roster_runtime
    original_records = runtime_bundle.faction_rule_execution_registry.all_records()
    named_record = next(
        record
        for record in original_records
        if record.execution_id == _DAEMONIC_MANIFESTATION_EXECUTION_ID
    )
    assert named_record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert named_record.handler_id == _DAEMONIC_MANIFESTATION_RUNTIME_ID
    original_bindings = runtime_bundle.battle_shock_hook_registry.all_bindings()
    assert named_record.handler_id in {binding.hook_id for binding in original_bindings}
    drifted_bundle = replace(
        runtime_bundle,
        battle_shock_hook_registry=replace(
            runtime_bundle.battle_shock_hook_registry,
            bindings=tuple(
                binding
                for binding in original_bindings
                if binding.hook_id != named_record.handler_id
            ),
        ),
        hook_bindings_by_event={},
    )

    with pytest.raises(GameLifecycleError, match="requires a registered handler") as exc_info:
        build_capability_manifest(
            config=config,
            armies=armies,
            runtime_manifest=runtime_manifest,
            runtime_bundle=drifted_bundle,
        )

    assert named_record.execution_id in str(exc_info.value)
    assert _DAEMONIC_MANIFESTATION_RUNTIME_ID in str(exc_info.value)
