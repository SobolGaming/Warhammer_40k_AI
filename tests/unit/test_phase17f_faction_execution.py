from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.faction_rule_execution import (
    FactionRuleExecutionContext,
    FactionRuleExecutionRegistry,
    FactionRuleExecutionResult,
    FactionRuleExecutionStatus,
    default_faction_rule_execution_registry,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27 as faction_coverage_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27 as faction_execution_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageStatus,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionBlockReason,
    Phase17FExecutionPackage,
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
    Phase17FFactionExecutionError,
)


def test_phase17f_execution_package_covers_every_phase17e_coverage_row() -> None:
    coverage_package = faction_coverage_source.phase17e_coverage_package()
    execution_package = faction_execution_source.phase17f_execution_package()
    records_by_coverage_id = {
        record.coverage_descriptor_id: record for record in execution_package.execution_records
    }

    assert set(records_by_coverage_id) == {
        row.descriptor_id for row in coverage_package.coverage_rows
    }
    for coverage_row in coverage_package.coverage_rows:
        execution_record = records_by_coverage_id[coverage_row.descriptor_id]
        assert execution_record.coverage_kind is coverage_row.coverage_kind
        assert execution_record.coverage_status is coverage_row.status
        assert execution_record.faction_id == coverage_row.faction_id
        assert execution_record.detachment_id == coverage_row.detachment_id
        assert execution_record.source_ids == coverage_row.source_ids


def test_phase17f_execution_payload_is_deterministic_json_safe_and_round_trips() -> None:
    package = faction_execution_source.phase17f_execution_package()
    payload = package.to_payload()

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert (
        payload["source_payload_checksum_sha256"]
        == (
            faction_execution_source.source_package_identity_payload()[
                "source_payload_checksum_sha256"
            ]
        )
    )
    assert (
        payload["upstream_payload_checksum_sha256"]
        == (
            faction_coverage_source.source_package_identity_payload()[
                "source_payload_checksum_sha256"
            ]
        )
    )
    assert Phase17FExecutionPackage.from_payload(payload) == package

    stale_payload = payload.copy()
    stale_payload["source_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(Phase17FFactionExecutionError, match="checksum is stale"):
        Phase17FExecutionPackage.from_payload(stale_payload)

    stale_upstream_payload = payload.copy()
    stale_upstream_payload["upstream_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(Phase17FFactionExecutionError, match="upstream payload checksum"):
        Phase17FExecutionPackage.from_payload(stale_upstream_payload)


def test_phase17f_execution_statuses_are_explicit_for_all_phase17e_rows() -> None:
    coverage_package = faction_coverage_source.phase17e_coverage_package()
    execution_package = faction_execution_source.phase17f_execution_package()
    coverage_status_counts = coverage_package.status_counts()
    execution_status_counts = execution_package.status_counts()

    assert execution_status_counts[Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR.value] == 0
    assert execution_status_counts[Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER.value] == 0
    assert (
        execution_status_counts[Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED.value]
        == coverage_status_counts[Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED.value]
    )
    assert (
        execution_status_counts[
            Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP.value
        ]
        == coverage_status_counts[Phase17ECoverageStatus.UNSUPPORTED.value]
    )
    assert len(execution_package.blocked_records()) == len(execution_package.execution_records)
    assert execution_package.unapproved_blocked_records() == ()
    assert all(record.is_approved_blocked for record in execution_package.blocked_records())


def test_phase17f_registry_dispatches_every_record_without_missing_handlers() -> None:
    registry = default_faction_rule_execution_registry()
    context = _context()

    for record in registry.all_records():
        result = registry.execute(execution_id=record.execution_id, context=context)
        assert result.status is FactionRuleExecutionStatus.UNSUPPORTED
        assert result.source_ids == record.source_ids
        assert result.coverage_descriptor_id == record.coverage_descriptor_id
        if record.execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED:
            assert result.reason == "structured_rule_semantics_required"
        else:
            assert result.reason == (
                f"approved_phase17e_source_gap:{record.phase17e_unsupported_reason}"
            )
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result


def test_phase17f_registry_rejects_unknown_execution_id() -> None:
    registry = default_faction_rule_execution_registry()

    with pytest.raises(GameLifecycleError, match="missing execution record"):
        registry.execute(execution_id="phase17f:missing", context=_context())


def test_phase17f_registry_rejects_invalid_registry_inputs_and_contexts() -> None:
    record = faction_execution_source.phase17f_execution_package().execution_records[0]

    with pytest.raises(GameLifecycleError, match="records must be a tuple"):
        FactionRuleExecutionRegistry.from_records(
            cast(tuple[Phase17FExecutionRecord, ...], [record])
        )

    with pytest.raises(GameLifecycleError, match="records must contain"):
        FactionRuleExecutionRegistry.from_records((cast(Phase17FExecutionRecord, object()),))

    with pytest.raises(GameLifecycleError, match="record IDs must be unique"):
        FactionRuleExecutionRegistry.from_records((record, record))

    registry = FactionRuleExecutionRegistry.from_records((record,))
    with pytest.raises(GameLifecycleError, match="requires a context"):
        registry.execute(
            execution_id=record.execution_id,
            context=cast(FactionRuleExecutionContext, object()),
        )


def test_phase17f_registry_applies_executable_records_through_same_dispatch_path() -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    executable_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
        block_reason=None,
    )
    registry = FactionRuleExecutionRegistry.from_records((executable_record,))

    result = registry.execute(execution_id=executable_record.execution_id, context=_context())

    assert result.status is FactionRuleExecutionStatus.APPLIED
    assert result.reason is None
    assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result


def test_phase17f_context_payload_round_trips() -> None:
    context = _context()

    assert FactionRuleExecutionContext.from_payload(context.to_payload()) == context


def test_phase17f_execution_result_rejects_inconsistent_status_reason_shapes() -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    executable_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
        block_reason=None,
    )
    result = FactionRuleExecutionResult.applied(record=executable_record, context=_context())

    with pytest.raises(GameLifecycleError, match="cannot include reason"):
        replace(result, reason="unexpected")

    with pytest.raises(GameLifecycleError, match="requires reason"):
        replace(result, status=FactionRuleExecutionStatus.UNSUPPORTED)


def test_phase17f_execution_records_reject_inconsistent_block_shapes() -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    source_gap_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP
    )

    with pytest.raises(Phase17FFactionExecutionError, match="require block_reason"):
        replace(blocked_record, block_reason=None)

    with pytest.raises(Phase17FFactionExecutionError, match="Only blocked"):
        replace(
            blocked_record,
            execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
            block_reason=Phase17FExecutionBlockReason.STRUCTURED_RULE_SEMANTICS_REQUIRED,
        )

    with pytest.raises(Phase17FFactionExecutionError, match="require handler_id"):
        replace(blocked_record, handler_id=None)

    with pytest.raises(Phase17FFactionExecutionError, match="require rule_ir_hash"):
        replace(
            blocked_record,
            execution_status=Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
            block_reason=None,
            rule_ir_hash=None,
        )

    with pytest.raises(Phase17FFactionExecutionError, match="require phase17e"):
        replace(source_gap_record, phase17e_unsupported_reason=None)

    with pytest.raises(Phase17FFactionExecutionError, match="SHA-256 digest"):
        replace(
            blocked_record,
            execution_status=Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
            block_reason=None,
            rule_ir_hash="bad",
        )


def test_phase17f_execution_package_rejects_invalid_record_sets() -> None:
    record = faction_execution_source.phase17f_execution_package().execution_records[0]

    with pytest.raises(Phase17FFactionExecutionError, match="must be a tuple"):
        Phase17FExecutionPackage(
            execution_records=cast(tuple[Phase17FExecutionRecord, ...], [record])
        )

    with pytest.raises(Phase17FFactionExecutionError, match="must contain"):
        Phase17FExecutionPackage(execution_records=(cast(Phase17FExecutionRecord, object()),))

    with pytest.raises(Phase17FFactionExecutionError, match="must be unique"):
        Phase17FExecutionPackage(execution_records=(record, record))

    with pytest.raises(Phase17FFactionExecutionError, match="unknown Phase17E"):
        Phase17FExecutionPackage(
            execution_records=(replace(record, coverage_descriptor_id="phase17e:missing"),)
        )

    with pytest.raises(Phase17FFactionExecutionError, match="cover every Phase17E"):
        Phase17FExecutionPackage(execution_records=())


def _context() -> FactionRuleExecutionContext:
    return FactionRuleExecutionContext(
        game_id="game-phase17f",
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.COMMAND,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:unit-1",
        target_unit_instance_ids=("army-beta:unit-1",),
        trigger_payload={"event": "phase17f-smoke"},
    )


def _first_execution_record(status: Phase17FExecutionStatus) -> Phase17FExecutionRecord:
    for record in faction_execution_source.phase17f_execution_package().execution_records:
        if record.execution_status is status:
            return record
    raise AssertionError(f"Missing Phase17F execution status: {status.value}.")
