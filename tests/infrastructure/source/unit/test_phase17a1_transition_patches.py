from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17a1_transition_patches import (
    CatalogVersion,
    DataPackageId,
    NormalizedSourceRow,
    PatchedSourceArtifact,
    PatchedSourceArtifactPayload,
    Path,
    SourceFaqClassification,
    SourcePatchDiagnostic,
    SourcePatchDiagnosticPayload,
    SourcePatchDiagnosticReason,
    SourcePatchError,
    SourcePatchTarget,
    SourceTextField,
    SourceTransitionPatchOperation,
    SourceTransitionPatchOperationFamily,
    SourceTransitionPatchPackage,
    SourceTransitionPatchPackagePayload,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
    _abilities_artifact,
    _catalog_version,
    _datasheets_artifact,
    _operation,
    _patch_package,
    _patch_package_id,
    _patched_row_by_id,
    _row_by_id,
    _source_package_id,
    _text_field,
    _text_replace_package,
    _wargear_artifact,
    apply_transition_patch_package,
    apply_transition_patches,
    build_transition_patch_package,
    contains_html_markup,
    date,
    hashlib,
    json,
    parse_normalized_tokens,
    pytest,
    replace,
    source_row_hash,
)


def test_phase17a1_death_guard_transition_examples_apply_in_stable_order() -> None:
    artifact = _datasheets_artifact(
        'id,name,keywords\ndg-pox,Poxwalkers,"INFANTRY"\ndg-pm,Plague Marines,"INFANTRY, CHAOS"\n'
    )
    poxwalkers = _row_by_id(artifact, "dg-pox")
    plague_marines = _row_by_id(artifact, "dg-pm")
    keyword_target = SourcePatchTarget.from_rows(
        source_table="Datasheets",
        rows=(poxwalkers, plague_marines),
        allow_multi_row=True,
    )
    package = _patch_package(
        operations=(
            _operation(
                operation_id="dg-002-add-battleline",
                order_index=20,
                family=SourceTransitionPatchOperationFamily.ADD_KEYWORD,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets",
                    rows=(plague_marines,),
                ),
                instruction_text="Add the BATTLELINE keyword to Plague Marines.",
                payload=(("column_name", "keywords"), ("keyword", "BATTLELINE")),
            ),
            _operation(
                operation_id="dg-001-add-faction",
                order_index=10,
                family=SourceTransitionPatchOperationFamily.ADD_KEYWORD,
                target=keyword_target,
                instruction_text="Add the DEATH GUARD keyword to these datasheets.",
                payload=(("column_name", "keywords"), ("keyword", "DEATH GUARD")),
            ),
        )
    )

    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    second_patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    patched_plague_marines = _patched_row_by_id(patched, "dg-pm")
    patched_poxwalkers = _patched_row_by_id(patched, "dg-pox")

    assert package.operations[0].operation_id == "dg-001-add-faction"
    assert patched.to_json_bytes() == second_patched.to_json_bytes()
    assert patched_plague_marines.runtime_fields_payload()["keywords"] == (
        "INFANTRY, CHAOS, DEATH GUARD, BATTLELINE"
    )
    assert patched_poxwalkers.runtime_fields_payload()["keywords"] == "INFANTRY, DEATH GUARD"
    assert all(row.source_package_id == _patch_package_id() for row in patched.rows)


def test_phase17a1_rule_text_patch_operations_rerun_normalization_and_strip_html() -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"<p>roll d3 attacks.</p>"\n'
    )
    package = _patch_package(
        operations=(
            _operation(
                operation_id="dg-aura-replace",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.REPLACE_DATASHEET_ABILITY,
                target=SourcePatchTarget.from_rows(
                    source_table="Abilities",
                    rows=(_row_by_id(artifact, "dg-aura:DG"),),
                ),
                instruction_text="Replace the ability text with the official update.",
                payload=(
                    ("column_name", "description"),
                    (
                        "text",
                        "<p>roll d6 within 12 inches - target's <b>feel no pain</b> applies.</p>",
                    ),
                ),
            ),
            _operation(
                operation_id="dg-aura-append",
                order_index=2,
                family=SourceTransitionPatchOperationFamily.APPEND_RULE_TEXT,
                target=SourcePatchTarget.from_rows(
                    source_table="Abilities",
                    rows=(_row_by_id(artifact, "dg-aura:DG"),),
                ),
                instruction_text="Append the designer note.",
                payload=(("column_name", "description"), ("text", "<p>Add 1 to the roll.</p>")),
            ),
        )
    )

    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    row = _patched_row_by_id(patched, "dg-aura:DG")
    description = _text_field(row, "description")

    assert row.runtime_fields_payload()["description"] == (
        "roll d6 within 12 inches - target's feel no pain applies.\nAdd 1 to the roll."
    )
    assert description.normalized_text == (
        "roll D6 within 12\" - target's Feel No Pain applies.\nAdd 1 to the roll."
    )
    assert description.parsed_tokens.dice_expressions[0].span.text == "D6"
    assert description.parsed_tokens.distance_predicates[0].distance_inches == 12.0
    assert not contains_html_markup(row.runtime_fields_payload()["description"])
    assert not contains_html_markup(description.sanitized_text)
    assert not contains_html_markup(description.normalized_text)


def test_phase17a1_artifact_hash_changes_on_source_or_patch_drift() -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D6."\n'
    )
    drifted_artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D3."\n'
    )
    package = _text_replace_package(artifact=artifact, text="Roll D6 within 12 inches.")
    patch_drift_package = _text_replace_package(
        artifact=artifact,
        text="Roll D6 within 18 inches.",
    )

    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    source_drift = apply_transition_patch_package(
        artifact=drifted_artifact,
        patch_package=package,
        raise_on_blocking=False,
    )
    patch_drift = apply_transition_patch_package(
        artifact=artifact,
        patch_package=patch_drift_package,
    )

    assert patched.artifact_hash() != source_drift.artifact_hash()
    assert source_drift.blocking_diagnostics()[0].reason is SourcePatchDiagnosticReason.TARGET_DRIFT
    assert patched.artifact_hash() != patch_drift.artifact_hash()


def test_phase17a1_packages_and_patched_artifacts_round_trip_and_reject_hash_drift() -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D6."\n'
    )
    package = _text_replace_package(artifact=artifact, text="Roll D6 within 12 inches.")
    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    package_payload = cast(
        SourceTransitionPatchPackagePayload,
        json.loads(json.dumps(package.to_payload(), sort_keys=True)),
    )
    artifact_payload = cast(
        PatchedSourceArtifactPayload,
        json.loads(json.dumps(patched.to_payload(), sort_keys=True)),
    )

    assert SourceTransitionPatchPackage.from_payload(package_payload).to_payload() == (
        package.to_payload()
    )
    assert PatchedSourceArtifact.from_payload(artifact_payload).to_payload() == (
        patched.to_payload()
    )

    package_payload["package_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(SourcePatchError, match="package_hash"):
        SourceTransitionPatchPackage.from_payload(package_payload)

    artifact_payload["artifact_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(SourcePatchError, match="artifact_hash"):
        PatchedSourceArtifact.from_payload(artifact_payload)


def test_phase17a1_tools_write_canonical_package_and_patched_artifacts(tmp_path: Path) -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D6."\n'
    )
    package = _text_replace_package(artifact=artifact, text="Roll D6 within 12 inches.")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    package_input = tmp_path / "transition_patch_package.json"
    package_output = tmp_path / "canonical" / "transition_patch_package.json"
    input_dir.mkdir()
    (input_dir / "Abilities.json").write_bytes(artifact.to_json_bytes())
    package_input.write_text(
        json.dumps(package.to_payload(), sort_keys=True, indent=2),
        encoding="utf-8",
    )

    canonical = build_transition_patch_package(
        input_path=package_input,
        output_path=package_output,
    )
    patched = apply_transition_patches(
        input_dir=input_dir,
        output_dir=output_dir,
        patch_package=canonical,
    )

    assert package_output.exists()
    assert (output_dir / "Abilities.patched.json").exists()
    assert (output_dir / "transition_patch_package.json").exists()
    assert len(patched) == 1
    assert (
        _patched_row_by_id(patched[0], "dg-aura:DG").runtime_fields_payload()["description"]
        == "Roll D6 within 12 inches."
    )


def test_phase17a1_apply_cli_stages_outputs_until_all_artifacts_succeed(
    tmp_path: Path,
) -> None:
    abilities_artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D6."\n'
    )
    datasheets_source = _datasheets_artifact('id,name,keywords\ndg-pm,Plague Marines,"INFANTRY"\n')
    datasheets_drifted = _datasheets_artifact(
        'id,name,keywords\ndg-pm,Plague Marines,"INFANTRY, CHAOS"\n'
    )
    package = _patch_package(
        operations=(
            _operation(
                operation_id="dg-replace-ability-text",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
                target=SourcePatchTarget.from_rows(
                    source_table="Abilities",
                    rows=(_row_by_id(abilities_artifact, "dg-aura:DG"),),
                ),
                instruction_text="Replace the source rule text.",
                payload=(("column_name", "description"), ("text", "Roll D6 within 12 inches.")),
            ),
            _operation(
                operation_id="dg-add-datasheet-keyword",
                order_index=2,
                family=SourceTransitionPatchOperationFamily.ADD_KEYWORD,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets",
                    rows=(_row_by_id(datasheets_source, "dg-pm"),),
                ),
                instruction_text="Add DEATH GUARD to Plague Marines.",
                payload=(("column_name", "keywords"), ("keyword", "DEATH GUARD")),
            ),
        )
    )
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "Abilities.json").write_bytes(abilities_artifact.to_json_bytes())
    (input_dir / "Datasheets.json").write_bytes(datasheets_drifted.to_json_bytes())

    with pytest.raises(SourcePatchError, match="target_drift"):
        apply_transition_patches(
            input_dir=input_dir,
            output_dir=output_dir,
            patch_package=package,
        )

    assert not output_dir.exists()


def test_phase17a1_apply_cli_rejects_patch_package_with_missing_target_table(
    tmp_path: Path,
) -> None:
    abilities_artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D6."\n'
    )
    datasheets_artifact = _datasheets_artifact(
        'id,name,keywords\ndg-pm,Plague Marines,"INFANTRY"\n'
    )
    package = _patch_package(
        operations=(
            _operation(
                operation_id="dg-add-datasheet-keyword",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.ADD_KEYWORD,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets",
                    rows=(_row_by_id(datasheets_artifact, "dg-pm"),),
                ),
                instruction_text="Add DEATH GUARD to Plague Marines.",
                payload=(("column_name", "keywords"), ("keyword", "DEATH GUARD")),
            ),
        )
    )
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    diagnostic_dir = tmp_path / "diagnostics"
    input_dir.mkdir()
    (input_dir / "Abilities.json").write_bytes(abilities_artifact.to_json_bytes())

    with pytest.raises(SourcePatchError, match="Datasheets"):
        apply_transition_patches(
            input_dir=input_dir,
            output_dir=output_dir,
            patch_package=package,
        )
    assert not output_dir.exists()

    patched = apply_transition_patches(
        input_dir=input_dir,
        output_dir=diagnostic_dir,
        patch_package=package,
        raise_on_blocking=False,
    )
    diagnostics_payload = json.loads(
        (diagnostic_dir / "transition_patch_diagnostics.json").read_text(encoding="utf-8")
    )

    assert patched == ()
    assert not (diagnostic_dir / "Abilities.patched.json").exists()
    assert not (diagnostic_dir / "transition_patch_package.json").exists()
    assert diagnostics_payload["missing_tables"] == ["Datasheets"]
    assert diagnostics_payload["diagnostics"][0]["reason"] == "missing_source_table"
    assert diagnostics_payload["diagnostics"][0]["operation_id"] == "dg-add-datasheet-keyword"


def test_phase17a1_build_tool_accepts_unhashed_draft_patch_packages(tmp_path: Path) -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D6."\n'
    )
    package = _text_replace_package(artifact=artifact, text="Roll D6 within 12 inches.")
    missing_hash_input = tmp_path / "missing_hash_package.json"
    empty_hash_input = tmp_path / "empty_hash_package.json"
    missing_hash_output = tmp_path / "missing_hash" / "transition_patch_package.json"
    empty_hash_output = tmp_path / "empty_hash" / "transition_patch_package.json"
    missing_hash_payload = dict(package.to_payload())
    missing_hash_payload.pop("package_hash")
    empty_hash_payload = dict(package.to_payload())
    empty_hash_payload["package_hash"] = ""
    missing_hash_input.write_text(
        json.dumps(missing_hash_payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    empty_hash_input.write_text(
        json.dumps(empty_hash_payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )

    missing_hash_package = build_transition_patch_package(
        input_path=missing_hash_input,
        output_path=missing_hash_output,
    )
    empty_hash_package = build_transition_patch_package(
        input_path=empty_hash_input,
        output_path=empty_hash_output,
    )
    missing_hash_canonical = json.loads(missing_hash_output.read_text(encoding="utf-8"))
    empty_hash_canonical = json.loads(empty_hash_output.read_text(encoding="utf-8"))

    assert missing_hash_package.package_hash() == package.package_hash()
    assert empty_hash_package.package_hash() == package.package_hash()
    assert missing_hash_canonical["package_hash"] == package.package_hash()
    assert empty_hash_canonical["package_hash"] == package.package_hash()


def test_phase17a1_patch_type_validation_is_fail_fast() -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\ndg-aura,DG,Nurgle Gift,"Roll D6."\n'
    )
    row = _row_by_id(artifact, "dg-aura:DG")
    target = SourcePatchTarget.from_rows(source_table="Abilities", rows=(row,))
    operation = _operation(
        operation_id="valid",
        order_index=1,
        family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
        target=target,
        instruction_text="Replace the source rule text.",
        payload=(("column_name", "description"), ("text", "Roll D6.")),
    )
    package = _patch_package(operations=(operation,))
    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    diagnostic = SourcePatchDiagnostic(
        operation_id="diag",
        source_table="Abilities",
        source_row_id="dg-aura:DG",
        reason=SourcePatchDiagnosticReason.MALFORMED_TARGET,
        message="Bad target.",
    )
    diagnostic_payload = cast(
        SourcePatchDiagnosticPayload,
        json.loads(json.dumps(diagnostic.to_payload(), sort_keys=True)),
    )

    assert SourcePatchTarget.from_payload(target.to_payload()) == target
    assert SourcePatchDiagnostic.from_payload(diagnostic_payload) == diagnostic
    assert source_row_hash(row) == source_row_hash(row)

    with pytest.raises(SourcePatchError, match="rows must not be empty"):
        SourcePatchTarget.from_rows(source_table="Abilities", rows=())
    with pytest.raises(SourcePatchError, match="contain source rows"):
        SourcePatchTarget.from_rows(
            source_table="Abilities",
            rows=cast(tuple[NormalizedSourceRow, ...], ("bad",)),
        )
    with pytest.raises(SourcePatchError, match="row table"):
        SourcePatchTarget.from_rows(source_table="Datasheets", rows=(row,))
    with pytest.raises(SourcePatchError, match="allow_multi_row"):
        SourcePatchTarget(source_table="Abilities", allow_multi_row=cast(bool, "bad"))
    with pytest.raises(SourcePatchError, match="reason"):
        SourcePatchDiagnostic(
            operation_id="diag",
            source_table="Abilities",
            source_row_id=None,
            reason=cast(SourcePatchDiagnosticReason, "bad"),
            message="Bad reason.",
        )
    with pytest.raises(SourcePatchError, match="blocking"):
        SourcePatchDiagnostic(
            operation_id="diag",
            source_table="Abilities",
            source_row_id=None,
            reason=SourcePatchDiagnosticReason.MALFORMED_TARGET,
            message="Bad blocking.",
            blocking=cast(bool, "bad"),
        )
    diagnostic_payload["reason"] = "unknown"
    with pytest.raises(SourcePatchError, match="diagnostic reason"):
        SourcePatchDiagnostic.from_payload(diagnostic_payload)

    with pytest.raises(SourcePatchError, match="missing required keys"):
        _operation(
            operation_id="missing-payload",
            order_index=1,
            family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
            target=target,
            instruction_text="Replace the source rule text.",
            payload=(),
        )
    with pytest.raises(SourcePatchError, match="order_index"):
        _operation(
            operation_id="negative-order",
            order_index=-1,
            family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
            target=target,
            instruction_text="Replace the source rule text.",
            payload=(("column_name", "description"), ("text", "Roll D6.")),
        )
    with pytest.raises(SourcePatchError, match="normalized_instruction_text"):
        SourceTransitionPatchOperation(
            operation_id="stale-normalized",
            order_index=1,
            operation_family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
            target=target,
            instruction_text="Replace the source rule text.",
            normalized_instruction_text="drifted",
            parsed_instruction_tokens=parse_normalized_tokens("drifted"),
            source_ids=("gw:death-guard:2026-06-01:page-1",),
            payload=(("column_name", "description"), ("text", "Roll D6.")),
        )
    with pytest.raises(SourcePatchError, match="operation_family"):
        SourceTransitionPatchOperation(
            operation_id="bad-family",
            order_index=1,
            operation_family=cast(SourceTransitionPatchOperationFamily, "bad"),
            target=target,
            instruction_text="Replace the source rule text.",
            normalized_instruction_text="Replace the source rule text.",
            parsed_instruction_tokens=parse_normalized_tokens("Replace the source rule text."),
            source_ids=("gw:death-guard:2026-06-01:page-1",),
            payload=(("column_name", "description"), ("text", "Roll D6.")),
        )

    with pytest.raises(SourcePatchError, match="source_edition"):
        replace(package, source_edition="warhammer-40000-12th")
    with pytest.raises(SourcePatchError, match="11th Edition"):
        replace(
            package,
            package_id=DataPackageId(
                namespace="gw",
                package_name="death-guard-transition-patches",
                version="transition",
            ),
        )
    with pytest.raises(SourcePatchError, match="operations"):
        replace(package, operations=())
    with pytest.raises(SourcePatchError, match="artifact"):
        apply_transition_patch_package(
            artifact=cast(WahapediaJsonArtifact, "bad"),
            patch_package=package,
        )
    with pytest.raises(SourcePatchError, match="patch_package"):
        apply_transition_patch_package(
            artifact=artifact,
            patch_package=cast(SourceTransitionPatchPackage, "bad"),
        )
    with pytest.raises(SourcePatchError, match="raise_on_blocking"):
        apply_transition_patch_package(
            artifact=artifact,
            patch_package=package,
            raise_on_blocking=cast(bool, "bad"),
        )
    with pytest.raises(SourcePatchError, match="row package"):
        PatchedSourceArtifact(
            source_package_id=_source_package_id(),
            source_table="Abilities",
            source_artifact_hash=artifact.artifact_hash(),
            patch_package_hash=package.package_hash(),
            source_edition="warhammer-40000-11th",
            rows=patched.rows,
        )
    with pytest.raises(SourcePatchError, match="NormalizedSourceRow"):
        source_row_hash(cast(NormalizedSourceRow, "bad"))


__all__: list[str] = []
__all__ += ["CatalogVersion", "SourceFaqClassification", "SourceTextField", "WahapediaCsvTable"]
__all__ += ["_catalog_version", "_wargear_artifact", "date"]
