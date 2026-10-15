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


def test_phase17a1_keyword_add_updates_declared_targets_and_rejects_missing_targets() -> None:
    artifact = _datasheets_artifact(
        'id,name,keywords\ndg-pox,Poxwalkers,"INFANTRY"\ndg-pm,Plague Marines,"INFANTRY, CHAOS"\n'
    )
    target = SourcePatchTarget.from_rows(
        source_table="Datasheets",
        rows=artifact.rows,
        allow_multi_row=True,
    )
    package = _patch_package(
        operations=(
            _operation(
                operation_id="dg-add-faction",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.ADD_KEYWORD,
                target=target,
                instruction_text="Add DEATH GUARD to every declared target.",
                payload=(("column_name", "keywords"), ("keyword", "DEATH GUARD")),
            ),
        )
    )
    missing_package = _patch_package(
        operations=(
            _operation(
                operation_id="dg-missing",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.ADD_KEYWORD,
                target=replace(
                    SourcePatchTarget.from_rows(
                        source_table="Datasheets",
                        rows=(_row_by_id(artifact, "dg-pm"),),
                    ),
                    source_row_ids=("missing-row",),
                    expected_row_hashes=(("missing-row", hashlib.sha256(b"x").hexdigest()),),
                ),
                instruction_text="Add DEATH GUARD to a missing row.",
                payload=(("column_name", "keywords"), ("keyword", "DEATH GUARD")),
            ),
        )
    )

    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    rejected = apply_transition_patch_package(
        artifact=artifact,
        patch_package=missing_package,
        raise_on_blocking=False,
    )

    assert all("DEATH GUARD" in row.runtime_fields_payload()["keywords"] for row in patched.rows)
    assert rejected.blocking_diagnostics()[0].reason is (
        SourcePatchDiagnosticReason.UNRESOLVED_TARGET
    )
    with pytest.raises(SourcePatchError, match="unresolved_target"):
        apply_transition_patch_package(artifact=artifact, patch_package=missing_package)


def test_phase17a1_weapon_characteristic_replacement_is_exact_and_source_linked() -> None:
    artifact = _wargear_artifact(
        "datasheet_id,line,line_in_wargear,name,strength,range\n"
        "dg-pm,1,1,Plague bolter,4,24\n"
        "dg-pm,2,1,Plague knife,3,Melee\n"
    )
    package = _patch_package(
        operations=(
            _operation(
                operation_id="dg-plague-bolter-strength",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.REPLACE_WEAPON_CHARACTERISTIC,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets_wargear",
                    rows=(_row_by_id(artifact, "dg-pm:1:1:2"),),
                ),
                instruction_text="Change Plague bolter Strength to 5.",
                payload=(("column_name", "strength"), ("value", "5")),
            ),
        )
    )

    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)

    assert _patched_row_by_id(patched, "dg-pm:1:1:2").runtime_fields_payload()["strength"] == "5"
    assert _patched_row_by_id(patched, "dg-pm:2:1:3").runtime_fields_payload()["strength"] == "3"
    assert patched.source_artifact_hash == artifact.artifact_hash()
    assert patched.patch_package_hash == package.package_hash()


def test_phase17a1_profile_characteristic_replacement_is_not_weapon_specific() -> None:
    artifact = _datasheets_artifact(
        'id,name,m,oc,keywords\nwe-heldrake,Heldrake,20",0,"AIRCRAFT, VEHICLE"\n'
    )
    heldrake = _row_by_id(artifact, "we-heldrake")
    package = _patch_package(
        operations=(
            _operation(
                operation_id="we-heldrake-move",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.REPLACE_PROFILE_CHARACTERISTIC,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets",
                    rows=(heldrake,),
                ),
                instruction_text='Change Heldrake M to 12".',
                payload=(("column_name", "m"), ("value", '12"')),
            ),
            _operation(
                operation_id="we-heldrake-oc",
                order_index=2,
                family=SourceTransitionPatchOperationFamily.REPLACE_PROFILE_CHARACTERISTIC,
                target=SourcePatchTarget.from_rows(
                    source_table="Datasheets",
                    rows=(heldrake,),
                ),
                instruction_text="Change Heldrake OC to '-'.",
                payload=(("column_name", "oc"), ("value", "-")),
            ),
        )
    )

    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)
    patched_heldrake = _patched_row_by_id(patched, "we-heldrake")
    operation_payloads = package.to_payload()["operations"]

    assert operation_payloads[0]["operation_family"] == "replace_profile_characteristic"
    assert patched_heldrake.runtime_fields_payload()["m"] == '12"'
    assert patched_heldrake.runtime_fields_payload()["oc"] == "-"
    assert patched.source_artifact_hash == artifact.artifact_hash()
    assert patched.patch_package_hash == package.package_hash()


def test_phase17a1_target_diagnostics_cover_unresolved_ambiguous_stale_and_malformed() -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\na-1,DG,Shared,"Roll D6."\na-2,DG,Shared,"Roll D3."\n'
    )
    row = _row_by_id(artifact, "a-1:DG")
    wrong_hash = hashlib.sha256(b"wrong").hexdigest()
    package = _patch_package(
        operations=(
            _operation(
                operation_id="unresolved",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
                target=replace(
                    SourcePatchTarget.from_rows(source_table="Abilities", rows=(row,)),
                    source_row_ids=("missing",),
                    expected_row_hashes=(("missing", wrong_hash),),
                ),
                instruction_text="Replace a missing row.",
                payload=(("column_name", "description"), ("text", "Roll D6.")),
            ),
            _operation(
                operation_id="ambiguous",
                order_index=2,
                family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
                target=SourcePatchTarget(
                    source_table="Abilities",
                    field_selectors=(("name", "Shared"),),
                    expected_row_hashes=(),
                ),
                instruction_text="Replace rows matched by an ambiguous selector.",
                payload=(("column_name", "description"), ("text", "Roll D6.")),
            ),
            _operation(
                operation_id="stale",
                order_index=3,
                family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
                target=replace(
                    SourcePatchTarget.from_rows(source_table="Abilities", rows=(row,)),
                    expected_row_hashes=((row.source_row_id, wrong_hash),),
                ),
                instruction_text="Replace a stale row.",
                payload=(("column_name", "description"), ("text", "Roll D6.")),
            ),
            _operation(
                operation_id="malformed",
                order_index=4,
                family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
                target=SourcePatchTarget(source_table="Abilities"),
                instruction_text="Replace a malformed target.",
                payload=(("column_name", "description"), ("text", "Roll D6.")),
            ),
        )
    )

    patched = apply_transition_patch_package(
        artifact=artifact,
        patch_package=package,
        raise_on_blocking=False,
    )
    reasons = {diagnostic.reason for diagnostic in patched.blocking_diagnostics()}

    assert reasons == {
        SourcePatchDiagnosticReason.UNRESOLVED_TARGET,
        SourcePatchDiagnosticReason.AMBIGUOUS_TARGET,
        SourcePatchDiagnosticReason.TARGET_DRIFT,
        SourcePatchDiagnosticReason.MALFORMED_TARGET,
    }
    with pytest.raises(SourcePatchError, match="ambiguous_target"):
        patched.require_success()


def test_phase17a1_faq_classification_rejects_executable_advisory_records() -> None:
    artifact = _abilities_artifact(
        'id,faction_id,name,description\nfaq-row,DG,FAQ Anchor,"Roll D6."\n'
    )
    target = SourcePatchTarget.from_rows(
        source_table="Abilities",
        rows=(_row_by_id(artifact, "faq-row:DG"),),
    )

    with pytest.raises(SourcePatchError, match="advisory-only"):
        _operation(
            operation_id="bad-faq",
            order_index=1,
            family=SourceTransitionPatchOperationFamily.RECORD_FAQ_ANSWER,
            target=target,
            instruction_text="FAQ: this changes executable behavior.",
            payload=(
                ("answer_text", "This changes the dice roll."),
                ("changes_executable_behavior", "true"),
            ),
            faq_classification=SourceFaqClassification.ADVISORY_ONLY,
        )

    package = _patch_package(
        operations=(
            _operation(
                operation_id="advisory-faq",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.RECORD_FAQ_ANSWER,
                target=target,
                instruction_text="FAQ: designer note only.",
                payload=(
                    ("answer_text", "This answer explains intent only."),
                    ("changes_executable_behavior", "false"),
                ),
                faq_classification=SourceFaqClassification.ADVISORY_ONLY,
            ),
            _operation(
                operation_id="unsupported-faq",
                order_index=2,
                family=SourceTransitionPatchOperationFamily.MARK_UNSUPPORTED,
                target=target,
                instruction_text="FAQ: executable change requires future handler support.",
                payload=(("reason", "FAQ changes executable behavior not supported yet."),),
                faq_classification=SourceFaqClassification.UNSUPPORTED_EXECUTABLE_CHANGE,
            ),
        )
    )

    patched = apply_transition_patch_package(artifact=artifact, patch_package=package)

    assert [diagnostic.reason for diagnostic in patched.diagnostics] == [
        SourcePatchDiagnosticReason.ADVISORY_ONLY_FAQ,
        SourcePatchDiagnosticReason.UNSUPPORTED_EXECUTABLE_CHANGE,
    ]
    assert not patched.blocking_diagnostics()


__all__: list[str] = []
__all__ += ["CatalogVersion", "DataPackageId", "NormalizedSourceRow", "PatchedSourceArtifact"]
__all__ += ["PatchedSourceArtifactPayload", "Path", "SourcePatchDiagnostic"]
__all__ += ["SourcePatchDiagnosticPayload", "SourceTextField", "SourceTransitionPatchOperation"]
__all__ += ["SourceTransitionPatchPackage", "SourceTransitionPatchPackagePayload"]
__all__ += ["WahapediaCsvTable", "WahapediaJsonArtifact", "_catalog_version", "_patch_package_id"]
__all__ += ["_source_package_id", "_text_field", "_text_replace_package"]
__all__ += ["apply_transition_patches", "build_transition_patch_package", "cast"]
__all__ += ["contains_html_markup", "date", "json", "parse_normalized_tokens", "source_row_hash"]
