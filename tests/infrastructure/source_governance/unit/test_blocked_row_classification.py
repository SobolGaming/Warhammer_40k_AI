from __future__ import annotations

from tests.shared.category_migration.phase17i_blocked_row_classification import (
    Phase17FExecutionStatus,
    RuleTemplateFamily,
    _payload_checksum,
    classification_source,
    execution_source,
    hashlib,
    json,
    pytest,
    replace,
    rule_template_by_id,
)


def test_phase17i_source_text_boundaries_are_explicit() -> None:
    report = classification_source.phase17i_blocked_row_classification_report()
    source_text_rows = tuple(
        row
        for row in report.classification_rows
        if row.classification_source_kind
        is classification_source.Phase17IClassificationSourceKind.WAHAPEDIA_BRIDGE_TEXT
    )
    metadata_only_rows = tuple(
        row
        for row in report.classification_rows
        if row.classification_source_kind
        is classification_source.Phase17IClassificationSourceKind.PHASE17F_METADATA_ONLY
    )

    assert report.structured_blocked_count == 1884
    assert report.source_text_matched_count == 1785
    assert report.source_text_missing_count == 99
    assert len(source_text_rows) == report.source_text_matched_count
    assert len(metadata_only_rows) == report.source_text_missing_count
    assert all(row.source_text_source_id is not None for row in source_text_rows)
    assert all(row.source_text_source_id is None for row in metadata_only_rows)
    assert all(row.ir_clause_count > 0 for row in source_text_rows)
    assert all(row.ir_clause_count == 0 for row in metadata_only_rows)
    assert all(row.unsupported_clause_count == 0 for row in metadata_only_rows)
    assert all(
        classification_source.Phase17IMissingCapabilityFamily.SOURCE_TEXT_NOT_AVAILABLE
        not in row.missing_capability_families
        for row in source_text_rows
    )
    assert all(
        classification_source.Phase17IMissingCapabilityFamily.SOURCE_TEXT_NOT_AVAILABLE
        in row.missing_capability_families
        for row in metadata_only_rows
    )
    execution_records = execution_source.phase17f_execution_package().execution_records
    assert {row.execution_id for row in report.classification_rows} == {
        record.execution_id
        for record in execution_records
        if record.execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    }
    (sheathed,) = [
        record
        for record in execution_records
        if record.execution_id
        == "phase17f:phase17e:stratagem:chaos-daemons:blood-legion:000009816007"
    ]
    assert sheathed.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert sheathed.rule_ir_hash is not None
    (blood_begets_skulls,) = [
        record
        for record in execution_records
        if record.execution_id
        == "phase17f:phase17e:stratagem:chaos-daemons:blood-legion:000009816005"
    ]
    assert blood_begets_skulls.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert blood_begets_skulls.rule_ir_hash == (
        "8477afd53ad9754e1f662fab6407f7aa0e63a1f9e6081f37784c3ffe4c33f730"
    )

    (skulls_beget_blood,) = [
        record
        for record in execution_records
        if record.execution_id
        == "phase17f:phase17e:stratagem:chaos-daemons:blood-legion:000009816004"
    ]
    assert skulls_beget_blood.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert skulls_beget_blood.rule_ir_hash == (
        "78f34fe0a7220bea1f16b7190d6879c7e15f93e12d208c184c6329d70ee39970"
    )
    (wrath_undeniable,) = [
        record
        for record in execution_records
        if record.execution_id
        == "phase17f:phase17e:stratagem:chaos-daemons:blood-legion:000009816002"
    ]
    assert wrath_undeniable.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert wrath_undeniable.rule_ir_hash == (
        "432609839320500af5714ef183fe2b3f562fd25afd4a2e27df20d6dedb5afd55"
    )
    (onslaught,) = [
        record
        for record in execution_records
        if record.execution_id
        == "phase17f:phase17e:stratagem:chaos-daemons:blood-legion:000009816003"
    ]
    assert onslaught.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert onslaught.rule_ir_hash == (
        "b7905db674b31fb7ab48f218106aadaa4ce3ca5af1e49027b06c4c4bfc891a22"
    )


def test_phase17i_missing_capability_report_groups_rows_by_family() -> None:
    report = classification_source.phase17i_blocked_row_classification_report()
    summary_by_family = {
        summary.family: summary for summary in report.missing_capability_summaries()
    }

    assert summary_by_family["generic_ir_execution_binding"].row_count == 1884
    assert summary_by_family["generic_ir_execution_binding"].coverage_kind_counts == {
        "detachment_enhancement": 654,
        "detachment_rule": 256,
        "detachment_stratagem": 969,
        "faction_army_rule": 5,
    }
    assert summary_by_family["unrepresented_rule_language"].row_count == 1749
    assert summary_by_family["duration_and_expiry_state"].row_count == 935
    assert summary_by_family["faction_resource_ledger"].row_count == 994
    assert summary_by_family["stratagem_activation_and_targeting"].coverage_kind_counts == {
        "detachment_stratagem": 969
    }
    assert summary_by_family["stratagem_effect_execution"].coverage_kind_counts == {
        "detachment_stratagem": 969
    }
    assert summary_by_family["enhancement_assignment_effect"].coverage_kind_counts == {
        "detachment_enhancement": 654
    }
    assert summary_by_family["stratagem_cost_modifier_runtime"].row_count == 1
    assert summary_by_family["stratagem_cost_modifier_runtime"].coverage_kind_counts == {
        "detachment_enhancement": 1,
    }
    assert summary_by_family["detachment_rule_state"].coverage_kind_counts == {
        "detachment_rule": 256
    }
    assert summary_by_family["army_rule_state"].coverage_kind_counts == {"faction_army_rule": 5}
    assert summary_by_family["source_text_not_available"].coverage_kind_counts == {
        "detachment_enhancement": 4,
        "detachment_rule": 84,
        "detachment_stratagem": 6,
        "faction_army_rule": 5,
    }


def test_phase17i_existing_template_report_uses_phase17c_template_families() -> None:
    report = classification_source.phase17i_blocked_row_classification_report()
    template_summary_by_family = {
        summary.family: summary for summary in report.existing_template_summaries()
    }
    phase17c_family_values = {family.value for family in RuleTemplateFamily}

    assert set(template_summary_by_family) <= phase17c_family_values
    assert template_summary_by_family["selected_target_constraint"].row_count == 1068
    assert template_summary_by_family["characteristic_set"].row_count == 18
    assert template_summary_by_family["keyword_gate"].row_count == 715
    assert template_summary_by_family["dice_roll_modification"].row_count == 170
    assert template_summary_by_family["conditional_weapon_ability_grant"].row_count == 148
    assert template_summary_by_family["characteristic_modification"].row_count == 122
    assert template_summary_by_family["grant_ability"].row_count == 87
    for row in report.classification_rows:
        assert set(row.existing_template_families) <= phase17c_family_values
        assert set(row.existing_template_families) == {
            rule_template_by_id(template_id).family.value
            for template_id in row.existing_template_ids
        }


def test_phase17i_payload_is_deterministic_json_safe_and_round_trips() -> None:
    report = classification_source.phase17i_blocked_row_classification_report()
    payload = report.to_payload()

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert (
        payload["source_payload_checksum_sha256"]
        == classification_source.source_package_identity_payload()["source_payload_checksum_sha256"]
    )
    assert (
        payload["upstream_payload_checksum_sha256"]
        == execution_source.source_package_identity_payload()["source_payload_checksum_sha256"]
    )
    assert (
        classification_source.Phase17IBlockedRowClassificationReport.from_payload(payload) == report
    )

    stale_payload = payload.copy()
    stale_payload["source_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(
        classification_source.Phase17IBlockedRowClassificationError,
        match="payload is stale",
    ):
        classification_source.Phase17IBlockedRowClassificationReport.from_payload(stale_payload)

    drifted_payload = report.to_payload()
    drifted_payload["classification_rows"][0]["rule_name"] = "Drifted Rule Name"
    drifted_payload["source_payload_checksum_sha256"] = _payload_checksum(drifted_payload)
    with pytest.raises(
        classification_source.Phase17IBlockedRowClassificationError,
        match="mismatched rule_name",
    ):
        classification_source.Phase17IBlockedRowClassificationReport.from_payload(drifted_payload)


def test_phase17i_validation_rejects_inconsistent_classification_shapes() -> None:
    report = classification_source.phase17i_blocked_row_classification_report()
    source_text_row = next(
        row
        for row in report.classification_rows
        if row.classification_source_kind
        is classification_source.Phase17IClassificationSourceKind.WAHAPEDIA_BRIDGE_TEXT
    )
    metadata_only_row = next(
        row
        for row in report.classification_rows
        if row.classification_source_kind
        is classification_source.Phase17IClassificationSourceKind.PHASE17F_METADATA_ONLY
    )

    with pytest.raises(
        classification_source.Phase17IBlockedRowClassificationError,
        match="source_text_source_id",
    ):
        replace(source_text_row, source_text_source_id=None)

    missing_without_source_gap = tuple(
        family
        for family in metadata_only_row.missing_capability_families
        if family
        is not classification_source.Phase17IMissingCapabilityFamily.SOURCE_TEXT_NOT_AVAILABLE
    )
    with pytest.raises(
        classification_source.Phase17IBlockedRowClassificationError,
        match="source_text_not_available",
    ):
        replace(
            metadata_only_row,
            missing_capability_families=missing_without_source_gap,
        )

    mismatched_row = replace(
        source_text_row,
        execution_id="phase17f:phase17e:unknown:blocked-row",
    )
    with pytest.raises(
        classification_source.Phase17IBlockedRowClassificationError,
        match="unknown structured-blocked execution row",
    ):
        classification_source.Phase17IBlockedRowClassificationReport(
            classification_rows=(mismatched_row, *report.classification_rows[1:]),
            wahapedia_artifact_hashes=report.wahapedia_artifact_hashes,
        )


__all__: list[str] = []
__all__ += ["Phase17FExecutionStatus", "hashlib"]
