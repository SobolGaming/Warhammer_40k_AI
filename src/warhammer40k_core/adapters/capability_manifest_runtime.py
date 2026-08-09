from __future__ import annotations

from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifest,
    RuntimeContentManifestRow,
    RuntimeContentModuleFamily,
    RuntimeContentSemanticStatus,
)
from warhammer40k_core.engine.faction_content.runtime_evidence import (
    ActiveRuntimeEvidenceInventory,
    validate_active_runtime_consumer_ids,
)
from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

_SEMANTIC_RUNTIME_CONTENT_FAMILIES = frozenset(
    {
        RuntimeContentModuleFamily.FACTION,
        RuntimeContentModuleFamily.DETACHMENT,
        RuntimeContentModuleFamily.ENHANCEMENT,
        RuntimeContentModuleFamily.STRATAGEM,
    }
)
_EXECUTABLE_FACTION_EXECUTION_STATUSES = frozenset(
    {
        Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
        Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
    }
)


def semantic_runtime_rows(
    rows: tuple[RuntimeContentManifestRow, ...],
) -> tuple[RuntimeContentManifestRow, ...]:
    if type(rows) is not tuple or any(type(row) is not RuntimeContentManifestRow for row in rows):
        raise GameLifecycleError("Semantic runtime rows require manifest row values.")
    return tuple(row for row in rows if row.family in _SEMANTIC_RUNTIME_CONTENT_FAMILIES)


def runtime_rule_semantics(
    row: RuntimeContentManifestRow,
    *,
    faction_execution_registry: FactionRuleExecutionRegistry,
) -> tuple[bool, str, tuple[str, ...], tuple[str, ...]]:
    if type(row) is not RuntimeContentManifestRow:
        raise GameLifecycleError("Runtime rule semantics require a manifest row.")
    if type(faction_execution_registry) is not FactionRuleExecutionRegistry:
        raise GameLifecycleError("Runtime rule semantics require a faction execution registry.")
    if row.family is not RuntimeContentModuleFamily.FACTION:
        return (
            row.semantic_status is RuntimeContentSemanticStatus.IMPLEMENTED,
            row.semantic_status.value,
            row.execution_record_ids,
            (),
        )

    records = tuple(
        faction_execution_registry.record_by_execution_id(execution_id)
        for execution_id in row.execution_record_ids
    )
    if any(record.faction_id != row.owner_faction_id for record in records):
        raise GameLifecycleError("Faction runtime execution record owner drifted.")
    army_rule_records = tuple(
        record
        for record in records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
    )
    intake_records = tuple(
        record
        for record in records
        if record.coverage_kind is Phase17ECoverageKind.DATASHEET_INTAKE
    )
    army_rule_ids = tuple(record.execution_id for record in army_rule_records)
    intake_ids = tuple(record.execution_id for record in intake_records)
    classified_ids = frozenset(
        record.execution_id for record in (*army_rule_records, *intake_records)
    )
    exact_army_rule_and_intake_aggregate = (
        len(army_rule_records) == 1
        and bool(intake_records)
        and classified_ids == frozenset(row.execution_record_ids)
    )
    army_rule_executable = (
        len(army_rule_records) == 1
        and army_rule_records[0].execution_status in _EXECUTABLE_FACTION_EXECUTION_STATUSES
    )
    executable = army_rule_executable and (
        row.semantic_status is RuntimeContentSemanticStatus.IMPLEMENTED
        or (
            row.semantic_status is RuntimeContentSemanticStatus.PARTIAL
            and exact_army_rule_and_intake_aggregate
        )
    )
    return (
        executable,
        (
            RuntimeContentSemanticStatus.IMPLEMENTED.value
            if executable
            else row.semantic_status.value
        ),
        army_rule_ids,
        intake_ids,
    )


def validate_selected_ability_runtime_evidence(
    *,
    ability_rows: tuple[AbilityCoverageRow, ...],
    expected_active_evidence: ActiveRuntimeEvidenceInventory,
    active_evidence: ActiveRuntimeEvidenceInventory,
) -> None:
    for coverage in ability_rows:
        if coverage.support_stage is not AbilityCoverageSupportStage.ENGINE_CONSUMED:
            continue
        validate_active_runtime_consumer_ids(
            runtime_consumer_ids=coverage.runtime_consumer_ids,
            expected_active_evidence=expected_active_evidence,
            active_evidence=active_evidence,
            context=coverage.coverage_row_id,
        )


def validate_selected_manifest_runtime_evidence(
    *,
    config: GameConfig,
    runtime_manifest: RuntimeContentManifest,
    faction_execution_registry: FactionRuleExecutionRegistry,
    expected_active_evidence: ActiveRuntimeEvidenceInventory,
    active_evidence: ActiveRuntimeEvidenceInventory,
) -> None:
    for request in config.army_muster_requests:
        rows = semantic_runtime_rows(
            runtime_manifest.reachable_rows_for_content_ids(
                selected_content_ids_for_request(request)
            )
        )
        for row in rows:
            executable, _, evidence_refs, _ = runtime_rule_semantics(
                row,
                faction_execution_registry=faction_execution_registry,
            )
            if not executable:
                continue
            validate_active_runtime_consumer_ids(
                runtime_consumer_ids=evidence_refs,
                expected_active_evidence=expected_active_evidence,
                active_evidence=active_evidence,
                context=f"runtime:{row.family.value}:{row.content_id}",
            )


def validate_selected_runtime_manifest_identity(
    *,
    config: GameConfig,
    runtime_manifest: RuntimeContentManifest,
    expected_runtime_manifest: RuntimeContentManifest,
) -> None:
    if type(config) is not GameConfig:
        raise GameLifecycleError("Runtime manifest identity validation requires a GameConfig.")
    if type(runtime_manifest) is not RuntimeContentManifest:
        raise GameLifecycleError("Runtime manifest identity validation requires a manifest.")
    if type(expected_runtime_manifest) is not RuntimeContentManifest:
        raise GameLifecycleError(
            "Runtime manifest identity validation requires a canonical expected manifest."
        )
    selected_content_ids = tuple(
        sorted(
            {
                content_id
                for request in config.army_muster_requests
                for content_id in selected_content_ids_for_request(request)
            }
        )
    )
    actual_rows = {
        row.content_id: row
        for row in runtime_manifest.reachable_rows_for_content_ids(selected_content_ids)
    }
    expected_rows = {
        row.content_id: row
        for row in expected_runtime_manifest.reachable_rows_for_content_ids(selected_content_ids)
    }
    drifted_content_ids = tuple(
        sorted(
            content_id
            for content_id in actual_rows.keys() | expected_rows.keys()
            if actual_rows.get(content_id) != expected_rows.get(content_id)
        )
    )
    if drifted_content_ids:
        raise GameLifecycleError(
            "Capability manifest selected runtime rows drifted from the canonical runtime "
            "manifest: " + ", ".join(drifted_content_ids) + "."
        )


def selected_content_ids_for_request(request: ArmyMusterRequest) -> tuple[str, ...]:
    if type(request) is not ArmyMusterRequest:
        raise GameLifecycleError("Selected content IDs require an ArmyMusterRequest.")
    selected = {
        request.detachment_selection.faction_id,
        *request.detachment_selection.detachment_ids,
        *request.detachment_selection.enhancement_ids,
        *request.detachment_selection.stratagem_ids,
        *(selection.datasheet_id for selection in request.unit_selections),
        *(
            wargear_id
            for selection in request.unit_selections
            for wargear_selection in selection.wargear_selections
            for wargear_id in wargear_selection.wargear_ids
        ),
    }
    return tuple(sorted(selected))
