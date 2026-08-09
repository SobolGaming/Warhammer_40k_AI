from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Literal, TypedDict, cast

from warhammer40k_core import __version__ as ENGINE_VERSION
from warhammer40k_core.adapters.capability_manifest_runtime import (
    runtime_rule_semantics as _runtime_rule_semantics,
)
from warhammer40k_core.adapters.capability_manifest_runtime import (
    selected_content_ids_for_request as _selected_content_ids_for_request,
)
from warhammer40k_core.adapters.capability_manifest_runtime import (
    semantic_runtime_rows as _semantic_runtime_rows,
)
from warhammer40k_core.adapters.capability_manifest_runtime import (
    validate_selected_ability_runtime_evidence as _validate_selected_ability_runtime_evidence,
)
from warhammer40k_core.adapters.capability_manifest_runtime import (
    validate_selected_manifest_runtime_evidence as _validate_selected_manifest_runtime_evidence,
)
from warhammer40k_core.adapters.capability_manifest_runtime import (
    validate_selected_runtime_manifest_identity as _validate_selected_runtime_manifest_identity,
)
from warhammer40k_core.adapters.external_contract import EXTERNAL_CONTRACT_VERSION
from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.core.missions import MissionPackDefinition, PrimaryMissionDefinition
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
    ability_coverage_rows_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifest,
    RuntimeContentManifestRow,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle_for_armies,
    runtime_content_manifest_for_ruleset,
)
from warhammer40k_core.engine.faction_content.runtime_evidence import (
    active_runtime_evidence_ids,
)
from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.interaction_metadata import (
    DecisionInteractionSupportPayload,
    InteractionKind,
    decision_interaction_support_rows,
)
from warhammer40k_core.engine.missions import supported_mission_packs
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.model_geometry import (
    GeometrySourceKind,
    HeightSourceKind,
)

CAPABILITY_MANIFEST_SCHEMA_VERSION = "capability-manifest-v1"
CAPABILITY_MANIFEST_SCHEMA_ID = (
    "https://warhammer40k-core.local/contracts/v4/capability-manifest.schema.json"
)
# Updated with the canonical schema file hash by the Phase 18D contract change.
CAPABILITY_MANIFEST_SCHEMA_SHA256 = (
    "320d31af5048139c3543d094d0e271f29ecd23cc65e634a034bc8e97442ff281"
)
ENGINE_BUILD_ID = f"warhammer40k-core-v2:{ENGINE_VERSION}"


class CapabilityDimension(StrEnum):
    LOADABLE = "LOADABLE"
    DISPLAYABLE = "DISPLAYABLE"
    MUSTERABLE = "MUSTERABLE"
    PHYSICALLY_PLAYABLE = "PHYSICALLY_PLAYABLE"
    SEMANTICALLY_EXECUTABLE = "SEMANTICALLY_EXECUTABLE"
    FULL_GAME_SUPPORTED = "FULL_GAME_SUPPORTED"
    NETWORK_SAFE = "NETWORK_SAFE"
    REPLAY_VERIFIED = "REPLAY_VERIFIED"


type CapabilityStatus = Literal["supported", "unsupported", "not_applicable"]


class CapabilityResultPayload(TypedDict):
    dimension: str
    status: CapabilityStatus
    evidence_refs: list[str]
    source_ids: list[str]
    reason_code: str | None


class CapabilityRowPayload(TypedDict):
    row_id: str
    row_kind: str
    player_id: str | None
    owner_id: str
    display_name: str
    source_ids: list[str]
    load_support: str
    semantic_execution: str
    capabilities: list[CapabilityResultPayload]
    metadata: dict[str, JsonValue]


class UnsupportedEffectPayload(TypedDict):
    effect_id: str
    rule_row_id: str
    player_id: str | None
    source_ids: list[str]
    reason_code: str
    message: str


class IdentityPayload(TypedDict):
    identity_id: str
    identity_hash: str


class SourcePackageIdentityPayload(IdentityPayload):
    source_kind: str


class CapabilityStatusCountsPayload(TypedDict):
    supported: int
    unsupported: int
    not_applicable: int


class CertificationClaimsPayload(TypedDict):
    phase20a_certified: bool
    phase20d_release_eligible: bool
    evidence_refs: list[str]
    blocker_reason_codes: list[str]


class CapabilityManifestPayload(TypedDict):
    schema_version: str
    manifest_id: str
    viewer_scope: str
    selection_hash: str
    identities: dict[str, JsonValue]
    mode_capabilities: list[CapabilityResultPayload]
    capability_counts: dict[str, CapabilityStatusCountsPayload]
    roster_rows: list[CapabilityRowPayload]
    unit_rows: list[CapabilityRowPayload]
    rule_rows: list[CapabilityRowPayload]
    mission_rows: list[CapabilityRowPayload]
    geometry_rows: list[CapabilityRowPayload]
    unsupported_effects: list[UnsupportedEffectPayload]
    interaction_kinds: list[str]
    decision_family_rows: list[DecisionInteractionSupportPayload]
    hidden_information_status: CapabilityResultPayload
    replay_evidence_refs: list[str]
    certified_scenario_evidence_refs: list[str]
    certification_claims: CertificationClaimsPayload


def build_capability_manifest(
    *,
    config: GameConfig,
    armies: tuple[ArmyDefinition, ...],
    runtime_manifest: RuntimeContentManifest,
    runtime_bundle: RuntimeContentBundle,
) -> CapabilityManifestPayload:
    if type(config) is not GameConfig:
        raise GameLifecycleError("Capability manifest requires a GameConfig.")
    if type(armies) is not tuple or any(type(army) is not ArmyDefinition for army in armies):
        raise GameLifecycleError("Capability manifest armies must contain ArmyDefinition values.")
    if type(runtime_manifest) is not RuntimeContentManifest:
        raise GameLifecycleError("Capability manifest requires a RuntimeContentManifest.")
    if type(runtime_bundle) is not RuntimeContentBundle:
        raise GameLifecycleError("Capability manifest requires a RuntimeContentBundle.")
    if {army.army_id for army in armies} != {
        request.army_id for request in config.army_muster_requests
    }:
        raise GameLifecycleError("Capability manifest army selection drifted from GameConfig.")
    expected_activation = RuntimeContentActivation.from_armies(
        armies=armies,
        catalog=config.army_catalog,
    )
    if (
        runtime_bundle.activation.roster_content_ids() != expected_activation.roster_content_ids()
        or runtime_bundle.activation.loaded_unit_instance_ids
        != expected_activation.loaded_unit_instance_ids
        or runtime_bundle.activation.selected_enhancement_assignments
        != expected_activation.selected_enhancement_assignments
    ):
        raise GameLifecycleError(
            "Capability manifest runtime bundle activation drifted from selected armies."
        )

    ability_rows = ability_coverage_rows_from_catalog(
        config.army_catalog,
        datasheet_ids=tuple(
            sorted(
                {
                    selection.datasheet_id
                    for request in config.army_muster_requests
                    for selection in request.unit_selections
                }
            )
        ),
    )
    ability_rows_by_datasheet = _group_ability_rows(ability_rows)
    expected_runtime_bundle = build_runtime_content_bundle_for_armies(
        config=config,
        armies=armies,
    )
    expected_runtime_manifest = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=config.ruleset_descriptor,
        config=config,
    )
    expected_active_evidence_ids = active_runtime_evidence_ids(expected_runtime_bundle)
    active_evidence_ids = active_runtime_evidence_ids(runtime_bundle)
    _validate_selected_ability_runtime_evidence(
        ability_rows=ability_rows,
        expected_active_evidence_ids=expected_active_evidence_ids,
        active_evidence_ids=active_evidence_ids,
    )
    _validate_selected_manifest_runtime_evidence(
        config=config,
        runtime_manifest=runtime_manifest,
        faction_execution_registry=expected_runtime_bundle.faction_rule_execution_registry,
        expected_active_evidence_ids=expected_active_evidence_ids,
        active_evidence_ids=active_evidence_ids,
    )
    _validate_selected_runtime_manifest_identity(
        config=config,
        runtime_manifest=runtime_manifest,
        expected_runtime_manifest=expected_runtime_manifest,
    )
    roster_rows = _roster_rows(
        config=config,
        armies=armies,
        ability_rows_by_datasheet=ability_rows_by_datasheet,
        runtime_manifest=runtime_manifest,
        faction_execution_registry=expected_runtime_bundle.faction_rule_execution_registry,
    )
    unit_rows = _unit_rows(
        config=config,
        armies=armies,
        ability_rows_by_datasheet=ability_rows_by_datasheet,
    )
    rule_rows = _rule_rows(
        config=config,
        ability_rows_by_datasheet=ability_rows_by_datasheet,
        runtime_manifest=runtime_manifest,
        faction_execution_registry=expected_runtime_bundle.faction_rule_execution_registry,
    )
    mission_rows, mission_pack = _mission_rows(config=config)
    geometry_rows = _geometry_rows(armies=armies)
    all_rows = (*roster_rows, *unit_rows, *rule_rows, *mission_rows, *geometry_rows)
    unsupported_effects = _unsupported_effects(rule_rows)
    mode_capabilities = _mode_capabilities(all_rows)
    hidden_information_status = _supported_result(
        CapabilityDimension.NETWORK_SAFE,
        evidence_refs=(
            "adapter:redaction:public_support_profile_payload",
            f"contract:{CAPABILITY_MANIFEST_SCHEMA_VERSION}:viewer-scope",
        ),
        source_ids=(CAPABILITY_MANIFEST_SCHEMA_ID,),
    )
    selection_hash = _hash_json(
        {
            "army_muster_requests": [
                request.to_payload() for request in config.army_muster_requests
            ],
            "mission_setup": (
                None if config.mission_setup is None else config.mission_setup.to_payload()
            ),
        }
    )
    identities = _identities(config=config, mission_pack=mission_pack)
    claims = _certification_claims(
        mode_capabilities=mode_capabilities,
        certified_scenario_evidence_refs=(),
        replay_evidence_refs=(),
    )
    payload: CapabilityManifestPayload = {
        "schema_version": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "manifest_id": _manifest_id(
            selection_hash=selection_hash,
            row_ids=tuple(row["row_id"] for row in all_rows),
            viewer_scope="omniscient",
        ),
        "viewer_scope": "omniscient",
        "selection_hash": selection_hash,
        "identities": identities,
        "mode_capabilities": mode_capabilities,
        "capability_counts": _capability_counts(all_rows),
        "roster_rows": roster_rows,
        "unit_rows": unit_rows,
        "rule_rows": rule_rows,
        "mission_rows": mission_rows,
        "geometry_rows": geometry_rows,
        "unsupported_effects": unsupported_effects,
        "interaction_kinds": sorted(kind.value for kind in InteractionKind),
        "decision_family_rows": decision_interaction_support_rows(),
        "hidden_information_status": hidden_information_status,
        "replay_evidence_refs": [],
        "certified_scenario_evidence_refs": [],
        "certification_claims": claims,
    }
    return cast(CapabilityManifestPayload, validate_json_value(cast(JsonValue, payload)))


def project_capability_manifest(
    payload: CapabilityManifestPayload,
    *,
    viewer_player_id: str | None,
    omniscient: bool,
) -> CapabilityManifestPayload:
    if type(omniscient) is not bool:
        raise GameLifecycleError("Capability manifest omniscient flag must be a bool.")
    if viewer_player_id is not None and (
        type(viewer_player_id) is not str or not viewer_player_id.strip()
    ):
        raise GameLifecycleError("Capability manifest viewer_player_id must be a string or None.")
    if omniscient:
        return payload
    viewer_scope = "omniscient" if omniscient else (viewer_player_id or "public")

    def visible(row: CapabilityRowPayload) -> bool:
        return omniscient or row["player_id"] is None or row["player_id"] == viewer_player_id

    roster_rows = [row for row in payload["roster_rows"] if visible(row)]
    unit_rows = [row for row in payload["unit_rows"] if visible(row)]
    rule_rows = [row for row in payload["rule_rows"] if visible(row)]
    mission_rows = [row for row in payload["mission_rows"] if visible(row)]
    geometry_rows = [row for row in payload["geometry_rows"] if visible(row)]
    all_rows = (*roster_rows, *unit_rows, *rule_rows, *mission_rows, *geometry_rows)
    visible_rule_ids = {row["row_id"] for row in rule_rows}
    unsupported_effects = [
        effect
        for effect in payload["unsupported_effects"]
        if effect["rule_row_id"] in visible_rule_ids
    ]
    mode_capabilities = _mode_capabilities(all_rows)
    selection_hash = _projected_selection_hash(
        viewer_scope=viewer_scope,
        roster_rows=roster_rows,
        mission_rows=mission_rows,
    )
    certification_claims = _project_certification_claims(
        authoritative_claims=payload["certification_claims"],
        projected_claims=_certification_claims(
            mode_capabilities=mode_capabilities,
            certified_scenario_evidence_refs=tuple(payload["certified_scenario_evidence_refs"]),
            replay_evidence_refs=tuple(payload["replay_evidence_refs"]),
        ),
    )
    projected = dict(payload)
    projected.update(
        {
            "manifest_id": _manifest_id(
                selection_hash=selection_hash,
                row_ids=tuple(row["row_id"] for row in all_rows),
                viewer_scope=viewer_scope,
            ),
            "viewer_scope": viewer_scope,
            "selection_hash": selection_hash,
            "mode_capabilities": mode_capabilities,
            "capability_counts": _capability_counts(all_rows),
            "roster_rows": roster_rows,
            "unit_rows": unit_rows,
            "rule_rows": rule_rows,
            "mission_rows": mission_rows,
            "geometry_rows": geometry_rows,
            "unsupported_effects": unsupported_effects,
            "certification_claims": certification_claims,
        }
    )
    return cast(
        CapabilityManifestPayload,
        validate_json_value(cast(JsonValue, projected)),
    )


def _roster_rows(
    *,
    config: GameConfig,
    armies: tuple[ArmyDefinition, ...],
    ability_rows_by_datasheet: Mapping[str, tuple[AbilityCoverageRow, ...]],
    runtime_manifest: RuntimeContentManifest,
    faction_execution_registry: FactionRuleExecutionRegistry,
) -> list[CapabilityRowPayload]:
    army_by_id = {army.army_id: army for army in armies}
    rows: list[CapabilityRowPayload] = []
    for request in config.army_muster_requests:
        army = army_by_id[request.army_id]
        runtime_rows = runtime_manifest.reachable_rows_for_content_ids(
            _selected_content_ids_for_request(request)
        )
        semantic_runtime_rows = _semantic_runtime_rows(runtime_rows)
        semantic_supported = all(
            _runtime_rule_semantics(
                row,
                faction_execution_registry=faction_execution_registry,
            )[0]
            for row in semantic_runtime_rows
        ) and all(
            coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
            for selection in request.unit_selections
            for coverage in ability_rows_by_datasheet.get(selection.datasheet_id, ())
        )
        physical_supported = all(
            model.geometry.geometry_source_kind is GeometrySourceKind.CATALOG_GEOMETRY_RECORD
            and model.geometry.height_source_kind is HeightSourceKind.CATALOG_GEOMETRY_RECORD
            for unit in army.units
            for model in unit.own_models
        )
        source_ids = tuple(
            sorted(
                {
                    *(source_id for unit in army.units for source_id in unit.datasheet_source_ids),
                    *(source_id for row in runtime_rows for source_id in row.source_ids),
                }
            )
        )
        rows.append(
            _row(
                row_id=f"roster:{request.player_id}:{request.army_id}",
                row_kind="roster",
                player_id=request.player_id,
                owner_id=request.army_id,
                display_name=f"{request.detachment_selection.faction_id} roster",
                source_ids=source_ids,
                load_support="engine_mustered",
                semantic_execution=("executable" if semantic_supported else "incomplete"),
                applicable={
                    CapabilityDimension.LOADABLE: (True, "", (f"army:{army.army_id}",)),
                    CapabilityDimension.DISPLAYABLE: (
                        True,
                        "",
                        ("adapter:rules_catalog_view", "adapter:unit_display_projection"),
                    ),
                    CapabilityDimension.MUSTERABLE: (
                        army.roster_legality_report.is_legal,
                        "roster_legality_invalid",
                        (f"roster-legality:{army.army_id}",),
                    ),
                    CapabilityDimension.PHYSICALLY_PLAYABLE: (
                        physical_supported,
                        "accepted_model_geometry_missing",
                        tuple(
                            sorted(
                                model.geometry.height_source_id or model.model_profile_id
                                for unit in army.units
                                for model in unit.own_models
                            )
                        ),
                    ),
                    CapabilityDimension.SEMANTICALLY_EXECUTABLE: (
                        semantic_supported,
                        "selected_rule_semantics_incomplete",
                        tuple(sorted(row.content_id for row in semantic_runtime_rows))
                        or (f"roster-rule-set:{army.army_id}:empty",),
                    ),
                    CapabilityDimension.NETWORK_SAFE: (
                        True,
                        "",
                        ("adapter:redaction:capability_manifest",),
                    ),
                },
                metadata={
                    "army_muster_request": cast(JsonValue, request.to_payload()),
                    "faction_id": request.detachment_selection.faction_id,
                    "detachment_ids": list(request.detachment_selection.detachment_ids),
                    "unit_count": len(request.unit_selections),
                    "legality_status": (
                        "legal" if army.roster_legality_report.is_legal else "invalid"
                    ),
                },
            )
        )
    return sorted(rows, key=lambda row: row["row_id"])


def _unit_rows(
    *,
    config: GameConfig,
    armies: tuple[ArmyDefinition, ...],
    ability_rows_by_datasheet: Mapping[str, tuple[AbilityCoverageRow, ...]],
) -> list[CapabilityRowPayload]:
    army_by_id = {army.army_id: army for army in armies}
    rows: list[CapabilityRowPayload] = []
    for request in config.army_muster_requests:
        army = army_by_id[request.army_id]
        if len(request.unit_selections) != len(army.units):
            raise GameLifecycleError("Capability manifest unit selection count drifted.")
        for selection, unit in zip(request.unit_selections, army.units, strict=True):
            coverage_rows = ability_rows_by_datasheet.get(selection.datasheet_id, ())
            semantic_supported = all(
                coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
                for coverage in coverage_rows
            )
            physical_supported = all(
                model.geometry.geometry_source_kind is GeometrySourceKind.CATALOG_GEOMETRY_RECORD
                and model.geometry.height_source_kind is HeightSourceKind.CATALOG_GEOMETRY_RECORD
                for model in unit.own_models
            )
            rows.append(
                _row(
                    row_id=f"unit:{request.player_id}:{selection.unit_selection_id}",
                    row_kind="unit",
                    player_id=request.player_id,
                    owner_id=selection.unit_selection_id,
                    display_name=unit.name,
                    source_ids=unit.datasheet_source_ids,
                    load_support="catalog_loaded",
                    semantic_execution=("executable" if semantic_supported else "incomplete"),
                    applicable={
                        CapabilityDimension.LOADABLE: (
                            True,
                            "",
                            (f"catalog:datasheet:{selection.datasheet_id}",),
                        ),
                        CapabilityDimension.DISPLAYABLE: (
                            True,
                            "",
                            (f"adapter:unit-display:{unit.unit_instance_id}",),
                        ),
                        CapabilityDimension.MUSTERABLE: (
                            True,
                            "",
                            (f"unit:{unit.unit_instance_id}",),
                        ),
                        CapabilityDimension.PHYSICALLY_PLAYABLE: (
                            physical_supported,
                            "accepted_model_geometry_missing",
                            tuple(model.model_profile_id for model in unit.own_models),
                        ),
                        CapabilityDimension.SEMANTICALLY_EXECUTABLE: (
                            semantic_supported,
                            "datasheet_ability_semantics_incomplete",
                            tuple(coverage.coverage_row_id for coverage in coverage_rows)
                            or (f"catalog:datasheet:{selection.datasheet_id}:no-abilities",),
                        ),
                        CapabilityDimension.NETWORK_SAFE: (
                            True,
                            "",
                            ("adapter:redaction:capability_manifest",),
                        ),
                    },
                    metadata={
                        "army_id": request.army_id,
                        "datasheet_id": selection.datasheet_id,
                        "model_profile_ids": cast(
                            list[JsonValue],
                            sorted({model.model_profile_id for model in unit.own_models}),
                        ),
                        "wargear_ids": cast(
                            list[JsonValue],
                            sorted(
                                {
                                    wargear_id
                                    for model in unit.own_models
                                    for wargear_id in model.wargear_ids
                                }
                            ),
                        ),
                    },
                )
            )
    return sorted(rows, key=lambda row: row["row_id"])


def _rule_rows(
    *,
    config: GameConfig,
    ability_rows_by_datasheet: Mapping[str, tuple[AbilityCoverageRow, ...]],
    runtime_manifest: RuntimeContentManifest,
    faction_execution_registry: FactionRuleExecutionRegistry,
) -> list[CapabilityRowPayload]:
    rows: list[CapabilityRowPayload] = []
    ability_by_id = {
        (datasheet.datasheet_id, ability.ability_id): ability
        for datasheet in config.army_catalog.datasheets
        for ability in datasheet.abilities
    }
    for request in config.army_muster_requests:
        for selection in request.unit_selections:
            for coverage in ability_rows_by_datasheet.get(selection.datasheet_id, ()):
                descriptor = ability_by_id[(selection.datasheet_id, coverage.ability_id)]
                executable = coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
                rows.append(
                    _ability_rule_row(
                        player_id=request.player_id,
                        unit_selection_id=selection.unit_selection_id,
                        coverage=coverage,
                        descriptor=descriptor,
                        executable=executable,
                    )
                )
        for runtime_row in _semantic_runtime_rows(
            runtime_manifest.reachable_rows_for_content_ids(
                _selected_content_ids_for_request(request)
            )
        ):
            rows.append(
                _runtime_rule_row(
                    player_id=request.player_id,
                    row=runtime_row,
                    faction_execution_registry=faction_execution_registry,
                )
            )
    return sorted(rows, key=lambda row: row["row_id"])


def _ability_rule_row(
    *,
    player_id: str,
    unit_selection_id: str,
    coverage: AbilityCoverageRow,
    descriptor: DatasheetAbilityDescriptor,
    executable: bool,
) -> CapabilityRowPayload:
    return _row(
        row_id=f"rule:{player_id}:{unit_selection_id}:ability:{coverage.ability_id}",
        row_kind="rule",
        player_id=player_id,
        owner_id=coverage.ability_id,
        display_name=coverage.ability_name,
        source_ids=(descriptor.source_id,),
        load_support=coverage.catalog_support.value,
        semantic_execution=coverage.support_stage.value,
        applicable={
            CapabilityDimension.LOADABLE: (
                True,
                "",
                (f"catalog:ability:{coverage.ability_id}",),
            ),
            CapabilityDimension.DISPLAYABLE: (
                True,
                "",
                (f"catalog:ability:{coverage.ability_id}:descriptor",),
            ),
            CapabilityDimension.SEMANTICALLY_EXECUTABLE: (
                executable,
                f"ability_{coverage.support_stage.value}",
                tuple(coverage.runtime_consumer_ids),
            ),
            CapabilityDimension.NETWORK_SAFE: (
                True,
                "",
                ("adapter:redaction:capability_manifest",),
            ),
        },
        metadata={
            "datasheet_id": coverage.datasheet_id,
            "unit_selection_id": unit_selection_id,
            "coverage_row_id": coverage.coverage_row_id,
            "semantic_categories": list(coverage.semantic_categories),
            "runtime_consumer_ids": list(coverage.runtime_consumer_ids),
            "diagnostic_reasons": list(coverage.diagnostic_reasons),
        },
    )


def _runtime_rule_row(
    *,
    player_id: str,
    row: RuntimeContentManifestRow,
    faction_execution_registry: FactionRuleExecutionRegistry,
) -> CapabilityRowPayload:
    loadable = row.support_status is RuntimeContentSupportStatus.SUPPORTED
    (
        executable,
        semantic_execution,
        semantic_evidence_refs,
        excluded_execution_record_ids,
    ) = _runtime_rule_semantics(
        row,
        faction_execution_registry=faction_execution_registry,
    )
    load_reason = (
        "" if loadable else row.unsupported_reason or f"runtime_{row.support_status.value}"
    )
    semantic_reason = "" if executable else f"runtime_semantic_{semantic_execution}"
    return _row(
        row_id=f"rule:{player_id}:runtime:{row.family.value}:{row.content_id}",
        row_kind="rule",
        player_id=player_id,
        owner_id=row.content_id,
        display_name=row.content_id,
        source_ids=row.source_ids,
        load_support=row.support_status.value,
        semantic_execution=semantic_execution,
        applicable={
            CapabilityDimension.LOADABLE: (
                loadable,
                load_reason,
                ((row.module_path,) if row.module_path is not None else ()),
            ),
            CapabilityDimension.DISPLAYABLE: (
                True,
                "",
                tuple(row.source_ids),
            ),
            CapabilityDimension.SEMANTICALLY_EXECUTABLE: (
                executable,
                semantic_reason,
                semantic_evidence_refs,
            ),
            CapabilityDimension.NETWORK_SAFE: (
                True,
                "",
                ("adapter:redaction:capability_manifest",),
            ),
        },
        metadata={
            "content_family": row.family.value,
            "source_package_id": row.source_package_id,
            "source_package_hash": row.source_package_hash,
            "execution_record_ids": list(row.execution_record_ids),
            "excluded_aggregate_execution_record_ids": list(excluded_execution_record_ids),
            "aggregate_semantic_execution": row.semantic_status.value,
            "required_for_matched_play": row.required_for_matched_play,
        },
    )


def _mission_rows(
    *,
    config: GameConfig,
) -> tuple[list[CapabilityRowPayload], MissionPackDefinition | None]:
    setup = config.mission_setup
    if setup is None:
        return (
            [
                _row(
                    row_id=f"mission:{config.game_id}:not-selected",
                    row_kind="mission",
                    player_id=None,
                    owner_id="not-selected",
                    display_name="No mission selected",
                    source_ids=(_ruleset_identity(config),),
                    load_support="not_selected",
                    semantic_execution="not_selected",
                    applicable={
                        CapabilityDimension.LOADABLE: (
                            False,
                            "mission_not_selected",
                            (),
                        ),
                        CapabilityDimension.DISPLAYABLE: (
                            False,
                            "mission_not_selected",
                            (),
                        ),
                        CapabilityDimension.PHYSICALLY_PLAYABLE: (
                            False,
                            "mission_geometry_not_selected",
                            (),
                        ),
                        CapabilityDimension.SEMANTICALLY_EXECUTABLE: (
                            False,
                            "mission_not_selected",
                            (),
                        ),
                        CapabilityDimension.NETWORK_SAFE: (
                            True,
                            "",
                            ("adapter:redaction:capability_manifest",),
                        ),
                    },
                    metadata={"mission_pack_id": None, "mission_setup_hash": _hash_json(None)},
                )
            ],
            None,
        )
    mission_pack = next(
        (
            candidate
            for candidate in supported_mission_packs()
            if candidate.mission_pack_id == setup.mission_pack_id
        ),
        None,
    )
    if mission_pack is None:
        executable = False
        primary = None
        semantic_reason = "mission_pack_not_supported"
        source_ids: tuple[str, ...] = (setup.source_id,)
    else:
        primary = next(
            (
                candidate
                for candidate in mission_pack.primary_missions
                if candidate.primary_mission_id == setup.primary_mission_id
            ),
            None,
        )
        executable = primary is not None and _primary_mission_executable(primary)
        semantic_reason = (
            ""
            if executable
            else (
                "primary_mission_not_found"
                if primary is None
                else "primary_mission_scoring_pending"
            )
        )
        source_ids = tuple(
            sorted(
                {
                    setup.source_id,
                    *(name for name in (() if primary is None else (primary.source_id,))),
                }
            )
        )
    physical = setup.battlefield_layout_id is not None and bool(
        setup.deployment_zones and setup.battlefield_regions and setup.terrain_features
    )
    row = _row(
        row_id=f"mission:{setup.mission_pack_id}:{setup.mission_pool_entry_id}",
        row_kind="mission",
        player_id=None,
        owner_id=setup.mission_pool_entry_id,
        display_name=setup.primary_mission_id,
        source_ids=source_ids,
        load_support=("engine_loaded" if mission_pack is not None else "unsupported"),
        semantic_execution=("executable" if executable else "incomplete"),
        applicable={
            CapabilityDimension.LOADABLE: (
                mission_pack is not None,
                "mission_pack_not_supported",
                (setup.source_id,),
            ),
            CapabilityDimension.DISPLAYABLE: (
                True,
                "",
                (f"mission-setup:{setup.mission_pool_entry_id}",),
            ),
            CapabilityDimension.PHYSICALLY_PLAYABLE: (
                physical,
                "battlefield_layout_geometry_incomplete",
                tuple(
                    item
                    for item in (setup.battlefield_layout_id, setup.terrain_layout_id)
                    if item is not None
                ),
            ),
            CapabilityDimension.SEMANTICALLY_EXECUTABLE: (
                executable,
                semantic_reason,
                (() if primary is None else (primary.source_id,)),
            ),
            CapabilityDimension.NETWORK_SAFE: (
                True,
                "",
                ("adapter:redaction:capability_manifest",),
            ),
        },
        metadata={
            "mission_setup_hash": _hash_json(setup.to_payload()),
            "mission_pack_id": setup.mission_pack_id,
            "primary_mission_id": setup.primary_mission_id,
            "battlefield_layout_id": setup.battlefield_layout_id,
            "terrain_layout_id": setup.terrain_layout_id,
        },
    )
    return [row], mission_pack


def _geometry_rows(*, armies: tuple[ArmyDefinition, ...]) -> list[CapabilityRowPayload]:
    rows: list[CapabilityRowPayload] = []
    for army in armies:
        for unit in army.units:
            geometry_by_profile = {
                model.model_profile_id: model.geometry for model in unit.own_models
            }
            source_ids_by_profile = {
                model.model_profile_id: model.source_ids for model in unit.own_models
            }
            for model_profile_id, geometry in sorted(geometry_by_profile.items()):
                accepted = (
                    geometry.geometry_source_kind is GeometrySourceKind.CATALOG_GEOMETRY_RECORD
                    and geometry.height_source_kind is HeightSourceKind.CATALOG_GEOMETRY_RECORD
                )
                rows.append(
                    _row(
                        row_id=(
                            f"geometry:{army.player_id}:{unit.unit_instance_id}:{model_profile_id}"
                        ),
                        row_kind="geometry",
                        player_id=army.player_id,
                        owner_id=model_profile_id,
                        display_name=model_profile_id,
                        source_ids=source_ids_by_profile[model_profile_id],
                        load_support=geometry.geometry_source_kind.value,
                        semantic_execution="not_applicable",
                        applicable={
                            CapabilityDimension.LOADABLE: (
                                True,
                                "",
                                (geometry.geometry_source_id or model_profile_id,),
                            ),
                            CapabilityDimension.DISPLAYABLE: (
                                True,
                                "",
                                (f"adapter:model-display:{model_profile_id}",),
                            ),
                            CapabilityDimension.PHYSICALLY_PLAYABLE: (
                                accepted,
                                "heuristic_model_height_not_certified",
                                tuple(
                                    item
                                    for item in (
                                        geometry.geometry_source_id,
                                        geometry.height_source_id,
                                    )
                                    if item is not None
                                ),
                            ),
                            CapabilityDimension.NETWORK_SAFE: (
                                True,
                                "",
                                ("adapter:redaction:capability_manifest",),
                            ),
                        },
                        metadata={
                            "unit_instance_id": unit.unit_instance_id,
                            "geometry_source_kind": geometry.geometry_source_kind.value,
                            "height_source_kind": geometry.height_source_kind.value,
                            "height_inches": geometry.height_inches,
                        },
                    )
                )
    return sorted(rows, key=lambda row: row["row_id"])


def _row(
    *,
    row_id: str,
    row_kind: str,
    player_id: str | None,
    owner_id: str,
    display_name: str,
    source_ids: Iterable[str],
    load_support: str,
    semantic_execution: str,
    applicable: Mapping[CapabilityDimension, tuple[bool, str, tuple[str, ...]]],
    metadata: dict[str, JsonValue],
) -> CapabilityRowPayload:
    canonical_sources = tuple(sorted(set(source_ids)))
    capabilities: list[CapabilityResultPayload] = []
    for dimension in CapabilityDimension:
        if dimension in applicable:
            supported, reason_code, evidence_refs = applicable[dimension]
            capabilities.append(
                _supported_result(
                    dimension,
                    evidence_refs=evidence_refs,
                    source_ids=canonical_sources,
                )
                if supported
                else _unsupported_result(
                    dimension,
                    reason_code=reason_code,
                    evidence_refs=evidence_refs,
                    source_ids=canonical_sources,
                )
            )
            continue
        if dimension is CapabilityDimension.FULL_GAME_SUPPORTED:
            capabilities.append(
                _unsupported_result(
                    dimension,
                    reason_code="certified_full_game_evidence_missing",
                    evidence_refs=(),
                    source_ids=canonical_sources,
                )
            )
            continue
        if dimension is CapabilityDimension.REPLAY_VERIFIED:
            capabilities.append(
                _unsupported_result(
                    dimension,
                    reason_code="certified_replay_evidence_missing",
                    evidence_refs=(),
                    source_ids=canonical_sources,
                )
            )
            continue
        capabilities.append(
            _not_applicable_result(
                dimension,
                reason_code=f"{row_kind}_{dimension.value.lower()}_not_applicable",
                source_ids=canonical_sources,
            )
        )
    return {
        "row_id": row_id,
        "row_kind": row_kind,
        "player_id": player_id,
        "owner_id": owner_id,
        "display_name": display_name,
        "source_ids": list(canonical_sources),
        "load_support": load_support,
        "semantic_execution": semantic_execution,
        "capabilities": capabilities,
        "metadata": metadata,
    }


def _mode_capabilities(
    rows: tuple[CapabilityRowPayload, ...],
) -> list[CapabilityResultPayload]:
    results: list[CapabilityResultPayload] = []
    for dimension in CapabilityDimension:
        row_results = [
            result
            for row in rows
            for result in row["capabilities"]
            if result["dimension"] == dimension.value and result["status"] != "not_applicable"
        ]
        evidence_refs = tuple(
            sorted(
                {
                    *(reference for result in row_results for reference in result["evidence_refs"]),
                    *(
                        row["row_id"]
                        for row in rows
                        if any(
                            result["dimension"] == dimension.value
                            and result["status"] != "not_applicable"
                            for result in row["capabilities"]
                        )
                    ),
                }
            )
        )
        source_ids = tuple(
            sorted({source_id for result in row_results for source_id in result["source_ids"]})
        )
        unsupported = [result for result in row_results if result["status"] == "unsupported"]
        if unsupported or not row_results:
            reasons = sorted(
                {
                    result["reason_code"]
                    for result in unsupported
                    if result["reason_code"] is not None
                }
            )
            reason_code = (
                reasons[0]
                if len(reasons) == 1
                else ("multiple_capability_blockers" if reasons else "capability_evidence_missing")
            )
            results.append(
                _unsupported_result(
                    dimension,
                    reason_code=reason_code,
                    evidence_refs=evidence_refs,
                    source_ids=source_ids,
                )
            )
        else:
            results.append(
                _supported_result(
                    dimension,
                    evidence_refs=evidence_refs,
                    source_ids=source_ids,
                )
            )
    return results


def _unsupported_effects(
    rule_rows: list[CapabilityRowPayload],
) -> list[UnsupportedEffectPayload]:
    effects: list[UnsupportedEffectPayload] = []
    for row in rule_rows:
        semantic = _result_for_dimension(
            row["capabilities"], CapabilityDimension.SEMANTICALLY_EXECUTABLE
        )
        if semantic["status"] != "unsupported":
            continue
        reason_code = semantic["reason_code"]
        if reason_code is None:
            raise GameLifecycleError("Unsupported rule capability requires a reason code.")
        effects.append(
            {
                "effect_id": f"unsupported-effect:{row['row_id']}",
                "rule_row_id": row["row_id"],
                "player_id": row["player_id"],
                "source_ids": list(row["source_ids"]),
                "reason_code": reason_code,
                "message": f"{row['display_name']} is not fully executable: {reason_code}.",
            }
        )
    return sorted(effects, key=lambda effect: effect["effect_id"])


def _identities(
    *,
    config: GameConfig,
    mission_pack: MissionPackDefinition | None,
) -> dict[str, JsonValue]:
    mission_identity: JsonValue = None
    terrain_identity: JsonValue = None
    source_packages: list[SourcePackageIdentityPayload] = [
        {
            "identity_id": config.army_catalog.source_package_id,
            "identity_hash": _hash_json(config.army_catalog.to_payload()),
            "source_kind": "army_catalog",
        }
    ]
    if config.mission_setup is not None:
        mission_identity = {
            "identity_id": config.mission_setup.mission_pack_id,
            "identity_hash": (
                _hash_json(config.mission_setup.to_payload())
                if mission_pack is None
                else _hash_json(mission_pack.to_payload())
            ),
        }
        terrain_identity = {
            "identity_id": config.mission_setup.terrain_layout_id,
            "identity_hash": _hash_json(
                {
                    "battlefield_layout_id": config.mission_setup.battlefield_layout_id,
                    "terrain_layout_id": config.mission_setup.terrain_layout_id,
                    "terrain_areas": [
                        area.to_payload() for area in config.mission_setup.terrain_areas
                    ],
                    "terrain_features": [
                        feature.to_payload() for feature in config.mission_setup.terrain_features
                    ],
                }
            ),
        }
        if mission_pack is not None:
            source_packages.append(
                {
                    "identity_id": mission_pack.source_package.source_package_id,
                    "identity_hash": mission_pack.source_package.source_commit_or_import_hash,
                    "source_kind": "mission_pack",
                }
            )
    sorted_source_packages = sorted(source_packages, key=lambda row: row["identity_id"])
    return {
        "ruleset": {
            "identity_id": _ruleset_identity(config),
            "identity_hash": config.ruleset_descriptor.descriptor_hash,
        },
        "catalog": {
            "identity_id": config.army_catalog.catalog_id,
            "identity_hash": _hash_json(config.army_catalog.to_payload()),
        },
        "source_packages": cast(JsonValue, sorted_source_packages),
        "mission_pack": mission_identity,
        "terrain_layout": terrain_identity,
        "engine_build": {
            "identity_id": ENGINE_BUILD_ID,
            "identity_hash": _hash_text(ENGINE_BUILD_ID),
        },
        "contract_schema": {
            "identity_id": CAPABILITY_MANIFEST_SCHEMA_ID,
            "identity_hash": CAPABILITY_MANIFEST_SCHEMA_SHA256,
            "contract_version": EXTERNAL_CONTRACT_VERSION,
        },
    }


def _certification_claims(
    *,
    mode_capabilities: list[CapabilityResultPayload],
    certified_scenario_evidence_refs: tuple[str, ...],
    replay_evidence_refs: tuple[str, ...],
) -> CertificationClaimsPayload:
    status_by_dimension = {result["dimension"]: result["status"] for result in mode_capabilities}
    blockers = sorted(
        {
            result["reason_code"]
            for result in mode_capabilities
            if result["status"] != "supported" and result["reason_code"] is not None
        }
    )
    phase20a = bool(certified_scenario_evidence_refs) and all(
        status_by_dimension[dimension.value] == "supported"
        for dimension in CapabilityDimension
        if dimension is not CapabilityDimension.REPLAY_VERIFIED
    )
    phase20d = (
        phase20a
        and bool(replay_evidence_refs)
        and status_by_dimension[CapabilityDimension.REPLAY_VERIFIED.value] == "supported"
    )
    return {
        "phase20a_certified": phase20a,
        "phase20d_release_eligible": phase20d,
        "evidence_refs": sorted({*certified_scenario_evidence_refs, *replay_evidence_refs}),
        "blocker_reason_codes": blockers,
    }


def _project_certification_claims(
    *,
    authoritative_claims: CertificationClaimsPayload,
    projected_claims: CertificationClaimsPayload,
) -> CertificationClaimsPayload:
    blocker_reason_codes = set(projected_claims["blocker_reason_codes"])
    if not authoritative_claims["phase20a_certified"] and projected_claims["phase20a_certified"]:
        blocker_reason_codes.add("authoritative_certification_blockers_redacted")
    if (
        not authoritative_claims["phase20d_release_eligible"]
        and projected_claims["phase20d_release_eligible"]
    ):
        blocker_reason_codes.add("authoritative_release_blockers_redacted")
    return {
        "phase20a_certified": authoritative_claims["phase20a_certified"],
        "phase20d_release_eligible": authoritative_claims["phase20d_release_eligible"],
        "evidence_refs": projected_claims["evidence_refs"],
        "blocker_reason_codes": sorted(blocker_reason_codes),
    }


def _projected_selection_hash(
    *,
    viewer_scope: str,
    roster_rows: list[CapabilityRowPayload],
    mission_rows: list[CapabilityRowPayload],
) -> str:
    return _hash_json(
        {
            "viewer_scope": viewer_scope,
            "army_muster_requests": [
                _required_selection_metadata(row, "army_muster_request") for row in roster_rows
            ],
            "public_mission_data_hashes": [
                _required_selection_metadata(row, "mission_setup_hash") for row in mission_rows
            ],
        }
    )


def _required_selection_metadata(row: CapabilityRowPayload, key: str) -> JsonValue:
    if key not in row["metadata"]:
        raise GameLifecycleError(
            f"Capability {row['row_kind']} row {row['row_id']} is missing {key} metadata."
        )
    return row["metadata"][key]


def _capability_counts(
    rows: tuple[CapabilityRowPayload, ...],
) -> dict[str, CapabilityStatusCountsPayload]:
    return {
        dimension.value: {
            "supported": sum(
                _result_for_dimension(row["capabilities"], dimension)["status"] == "supported"
                for row in rows
            ),
            "unsupported": sum(
                _result_for_dimension(row["capabilities"], dimension)["status"] == "unsupported"
                for row in rows
            ),
            "not_applicable": sum(
                _result_for_dimension(row["capabilities"], dimension)["status"] == "not_applicable"
                for row in rows
            ),
        }
        for dimension in CapabilityDimension
    }


def _supported_result(
    dimension: CapabilityDimension,
    *,
    evidence_refs: Iterable[str],
    source_ids: Iterable[str],
) -> CapabilityResultPayload:
    evidence = sorted(set(evidence_refs))
    if not evidence:
        raise GameLifecycleError("Supported capability results require evidence references.")
    return {
        "dimension": dimension.value,
        "status": "supported",
        "evidence_refs": evidence,
        "source_ids": sorted(set(source_ids)),
        "reason_code": None,
    }


def _unsupported_result(
    dimension: CapabilityDimension,
    *,
    reason_code: str,
    evidence_refs: Iterable[str],
    source_ids: Iterable[str],
) -> CapabilityResultPayload:
    if type(reason_code) is not str or not reason_code.strip():
        raise GameLifecycleError("Unsupported capability results require a reason code.")
    return {
        "dimension": dimension.value,
        "status": "unsupported",
        "evidence_refs": sorted(set(evidence_refs)),
        "source_ids": sorted(set(source_ids)),
        "reason_code": reason_code,
    }


def _not_applicable_result(
    dimension: CapabilityDimension,
    *,
    reason_code: str,
    source_ids: Iterable[str],
) -> CapabilityResultPayload:
    return {
        "dimension": dimension.value,
        "status": "not_applicable",
        "evidence_refs": [],
        "source_ids": sorted(set(source_ids)),
        "reason_code": reason_code,
    }


def _result_for_dimension(
    results: list[CapabilityResultPayload],
    dimension: CapabilityDimension,
) -> CapabilityResultPayload:
    matches = [result for result in results if result["dimension"] == dimension.value]
    if len(matches) != 1:
        raise GameLifecycleError("Capability row must contain every dimension exactly once.")
    return matches[0]


def _group_ability_rows(
    rows: tuple[AbilityCoverageRow, ...],
) -> dict[str, tuple[AbilityCoverageRow, ...]]:
    grouped: dict[str, list[AbilityCoverageRow]] = {}
    for row in rows:
        grouped.setdefault(row.datasheet_id, []).append(row)
    return {
        datasheet_id: tuple(sorted(values, key=lambda row: row.coverage_row_id))
        for datasheet_id, values in grouped.items()
    }


def _primary_mission_executable(primary: PrimaryMissionDefinition) -> bool:
    if primary.scoring_kind == "event_companion_primary_source_known_engine_pending":
        return False
    return bool(primary.scoring_rules)


def _manifest_id(
    *,
    selection_hash: str,
    row_ids: tuple[str, ...],
    viewer_scope: str,
) -> str:
    identity_hash = _hash_json(
        {
            "selection_hash": selection_hash,
            "row_ids": list(row_ids),
            "viewer_scope": viewer_scope,
        }
    )
    return f"capability-manifest:{identity_hash}"


def _ruleset_identity(config: GameConfig) -> str:
    ruleset_id = config.ruleset_descriptor.ruleset_id
    return f"{ruleset_id.game}:{ruleset_id.edition.value}:{ruleset_id.version}"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
