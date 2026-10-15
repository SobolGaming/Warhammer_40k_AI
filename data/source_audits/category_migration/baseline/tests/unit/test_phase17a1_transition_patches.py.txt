from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from tools.apply_transition_patches import apply_transition_patches
from tools.build_transition_patch import build_transition_patch_package

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.html_sanitizer import contains_html_markup
from warhammer40k_core.rules.parsed_tokens import parse_normalized_tokens
from warhammer40k_core.rules.source_patch import (
    PatchedSourceArtifact,
    PatchedSourceArtifactPayload,
    SourceFaqClassification,
    SourcePatchDiagnostic,
    SourcePatchDiagnosticPayload,
    SourcePatchDiagnosticReason,
    SourcePatchError,
    SourcePatchTarget,
    SourceTransitionPatchOperation,
    SourceTransitionPatchOperationFamily,
    SourceTransitionPatchPackage,
    SourceTransitionPatchPackagePayload,
    apply_transition_patch_package,
    source_row_hash,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    SourceTextField,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
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


def _operation(
    *,
    operation_id: str,
    order_index: int,
    family: SourceTransitionPatchOperationFamily,
    target: SourcePatchTarget,
    instruction_text: str,
    payload: tuple[tuple[str, str], ...],
    faq_classification: SourceFaqClassification | None = None,
) -> SourceTransitionPatchOperation:
    return SourceTransitionPatchOperation.from_instruction(
        operation_id=operation_id,
        order_index=order_index,
        operation_family=family,
        target=target,
        instruction_text=instruction_text,
        source_ids=("gw:death-guard:2026-06-01:page-1",),
        payload=payload,
        faq_classification=faq_classification,
    )


def _patch_package(
    *,
    operations: tuple[SourceTransitionPatchOperation, ...],
) -> SourceTransitionPatchPackage:
    return SourceTransitionPatchPackage(
        package_id=_patch_package_id(),
        catalog_version=_catalog_version(),
        official_source_package_id=DataPackageId(
            namespace="gw",
            package_name="death-guard-faction-pack",
            version="11th-2026-06-01",
        ),
        source_date="2026-06-01",
        source_edition="warhammer-40000-11th",
        faction_id="death-guard",
        operations=operations,
    )


def _text_replace_package(
    *,
    artifact: WahapediaJsonArtifact,
    text: str,
) -> SourceTransitionPatchPackage:
    return _patch_package(
        operations=(
            _operation(
                operation_id="dg-text-replace",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
                target=SourcePatchTarget.from_rows(
                    source_table="Abilities",
                    rows=(_row_by_id(artifact, "dg-aura:DG"),),
                ),
                instruction_text="Replace the source rule text.",
                payload=(("column_name", "description"), ("text", text)),
            ),
        )
    )


def _abilities_artifact(csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text=csv_text),
    )


def _datasheets_artifact(csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name="Datasheets", csv_text=csv_text),
    )


def _wargear_artifact(csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(
            table_name="Datasheets_wargear",
            csv_text=csv_text,
        ),
    )


def _row_by_id(artifact: WahapediaJsonArtifact, source_row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _patched_row_by_id(
    artifact: PatchedSourceArtifact,
    source_row_id: str,
) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _text_field(row: NormalizedSourceRow, column_name: str) -> SourceTextField:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field
    raise AssertionError(f"Missing text field {column_name}.")


def _source_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="wahapedia",
        package_name="source-mirror",
        version="11th-transition",
    )


def _patch_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="gw",
        package_name="death-guard-transition-patches",
        version="11th-2026-06-01",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="phase17a1-test",
        source_date=date(2026, 6, 1),
    )
