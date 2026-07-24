from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from tools.apply_source_overlays import apply_source_overlays
from tools.fetch_official_sources import load_official_source_manifest

from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    command_point_consumer_ids_for_clause,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th import generated_manifest
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    july_2026_candidate as chaos_daemons_july_candidate,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    july_2026_updates as chaos_daemons_july_updates,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    manifest as chaos_daemons_june_manifest,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    july_2026_candidate as emperors_children_july_candidate,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    manifest as emperors_children_june_manifest,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    july_2026_candidate as thousand_sons_july_candidate,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    manifest as thousand_sons_june_manifest,
)
from warhammer40k_core.engine.stratagem_phase_use_exceptions import (
    stratagem_phase_use_exception,
)
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.rule_ir import RuleEffectKind, parameter_payload
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    OverlaySourceArtifactPayload,
    SourceOverlayError,
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
    apply_source_release_overlays,
    build_source_release_overlay_report,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_detachments_2026_27,
    faction_execution_2026_27,
    faction_subrules_2026_27,
    july_faction_packs_2026_07,
)
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.source_reference_generation import (
    SourceReferenceCatalog,
    SourceReferenceCatalogPayload,
    build_source_reference_catalog,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
)


def test_phase17_source_overlay_applies_add_update_and_supersede_operations() -> None:
    artifact = _abilities_artifact()
    row = artifact.rows[0]
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update-angels-fury",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(row),
                fields=(("description", "<p>Roll D6 within 12 inches.</p>"),),
            ),
            _operation(
                op_id="add-new-detachment-rule",
                order_index=2,
                kind=SourceOverlayOperationKind.ADD_ROW,
                source_row_id="ability-2:SM",
                expected_preimage_hash=None,
                fields=(
                    ("id", "ability-2"),
                    ("faction_id", "SM"),
                    ("name", "New Rule"),
                    ("description", "Add 1 to the roll."),
                ),
            ),
            _operation(
                op_id="supersede-old-text",
                order_index=3,
                kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(
                    _updated_row_after_first_operation(artifact, package_hash_placeholder=False)
                ),
                fields=(),
            ),
        )
    )

    overlay_artifact = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )[0]
    ability_1 = _row_by_id(overlay_artifact, "ability-1:SM")
    ability_2 = _row_by_id(overlay_artifact, "ability-2:SM")
    payload = cast(
        OverlaySourceArtifactPayload,
        json.loads(json.dumps(overlay_artifact.to_payload(), sort_keys=True)),
    )

    assert ability_1.runtime_fields_payload()["description"] == "Roll D6 within 12 inches."
    assert ability_1.runtime_fields_payload()["core_v2_superseded_by"] == "supersede-old-text"
    assert ability_2.runtime_fields_payload()["name"] == "New Rule"
    assert OverlaySourceArtifact.from_payload(payload).to_payload() == overlay_artifact.to_payload()


def test_phase17_source_overlay_rejects_stale_preimage_and_duplicate_field_edits() -> None:
    artifact = _abilities_artifact()
    stale_package = _overlay_pack(
        operations=(
            _operation(
                op_id="stale",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=hashlib.sha256(b"stale").hexdigest(),
                fields=(("description", "Roll D3."),),
            ),
        )
    )

    rejected = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(stale_package.package_id,)),
        overlay_packs=(stale_package,),
        raise_on_blocking=False,
    )[0]

    assert rejected.blocking_diagnostics()[0].reason.value == "target_drift"
    with pytest.raises(SourceOverlayError, match="duplicate field edit"):
        _overlay_pack(
            operations=(
                _operation(
                    op_id="first",
                    order_index=1,
                    kind=SourceOverlayOperationKind.UPDATE_ROW,
                    source_row_id="ability-1:SM",
                    expected_preimage_hash=source_row_hash(artifact.rows[0]),
                    fields=(("description", "Roll D3."),),
                ),
                _operation(
                    op_id="second",
                    order_index=2,
                    kind=SourceOverlayOperationKind.UPDATE_ROW,
                    source_row_id="ability-1:SM",
                    expected_preimage_hash=source_row_hash(artifact.rows[0]),
                    fields=(("description", "Roll D6."),),
                ),
            )
        )


def test_phase17_source_release_manifest_rejects_empty_bridge_and_non_11th_target() -> None:
    native_manifest = SourceReleaseManifest(
        release_id="core-11-native-wahapedia-test",
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        base_source_edition="warhammer-40000-11th",
        target_edition="warhammer-40000-11th",
        overlay_package_ids=(),
    )

    assert native_manifest.overlay_package_ids == ()
    with pytest.raises(SourceOverlayError, match="target_edition must be 11th Edition"):
        SourceReleaseManifest(
            release_id="core-11-invalid-target-test",
            catalog_version=_catalog_version(),
            base_source_package_id=_source_package_id(),
            base_source_edition="warhammer-40000-11th",
            target_edition="warhammer-40000-future",
            overlay_package_ids=(),
        )
    with pytest.raises(SourceOverlayError, match="bridge releases require at least one"):
        _release_manifest(overlay_package_ids=())


def test_phase17_source_release_requires_exact_supplied_overlay_packs() -> None:
    artifact = _abilities_artifact()
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", "Roll D6 within 12 inches."),),
            ),
        )
    )
    extra_package = _overlay_pack(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="core-11-source-overlay-extra",
            version="2026-06-01",
        ),
        operations=(
            _operation(
                op_id="add-extra",
                order_index=1,
                kind=SourceOverlayOperationKind.ADD_ROW,
                source_row_id="ability-extra:SM",
                expected_preimage_hash=None,
                fields=(
                    ("id", "ability-extra"),
                    ("faction_id", "SM"),
                    ("name", "Extra Rule"),
                    ("description", "Add 1 to the roll."),
                ),
            ),
        ),
    )

    with pytest.raises(SourceOverlayError, match="exactly match the release manifest"):
        apply_source_release_overlays(
            source_artifacts=(artifact,),
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package, extra_package),
        )
    with pytest.raises(SourceOverlayError, match="duplicate package IDs"):
        apply_source_release_overlays(
            source_artifacts=(artifact,),
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package, package),
        )


def test_phase17_source_overlay_update_preserves_raw_overlay_text_in_references() -> None:
    artifact = _abilities_artifact()
    raw_overlay_text = "<p>Roll D6 within 12 inches.</p>"
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", raw_overlay_text),),
            ),
        )
    )
    overlay_artifact = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )[0]
    description = _row_by_id(overlay_artifact, "ability-1:SM").text_fields[1]
    reference_catalog = build_source_reference_catalog(
        package_id=_reference_package_id(),
        catalog_version=_catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=(overlay_artifact,),
    )
    reference = reference_catalog.source_text_by_id(description.source_text_id)

    assert (
        _row_by_id(overlay_artifact, "ability-1:SM").runtime_fields_payload()["description"]
        == "Roll D6 within 12 inches."
    )
    assert reference.raw_text == raw_overlay_text
    assert reference.sanitized_text == "Roll D6 within 12 inches."
    assert reference.normalized_text == 'Roll D6 within 12".'


def test_phase17_source_overlay_cli_writes_diagnostics_before_blocking(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    artifact = _abilities_artifact()
    stale_package = _overlay_pack(
        operations=(
            _operation(
                op_id="stale",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=hashlib.sha256(b"stale").hexdigest(),
                fields=(("description", "Roll D6."),),
            ),
        )
    )
    (input_dir / "Abilities.json").write_bytes(artifact.to_json_bytes())

    with pytest.raises(SourceOverlayError, match="failed with diagnostics"):
        apply_source_overlays(
            input_dir=input_dir,
            output_dir=output_dir,
            release_manifest=_release_manifest(overlay_package_ids=(stale_package.package_id,)),
            overlay_packs=(stale_package,),
        )
    diagnostics = json.loads((output_dir / "source_overlay_diagnostics.json").read_text())

    assert diagnostics["diagnostics"][0]["reason"] == "target_drift"


def test_phase17_source_overlay_missing_source_table_blocks_and_reports(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    artifact = _abilities_artifact()
    package = _overlay_pack(
        operations=(
            SourceOverlayOperation(
                op_id="missing-table",
                order_index=1,
                operation_kind=SourceOverlayOperationKind.ADD_ROW,
                target_edition="warhammer-40000-11th",
                source_table="Missing_Table",
                source_row_id="missing-1",
                source_reference="gw-11e-transition-update:p1",
                effective_date="2026-06-01",
                reason="Test missing source table.",
                expected_preimage_hash=None,
                fields=(("id", "missing-1"),),
            ),
        )
    )

    with pytest.raises(SourceOverlayError, match="missing_source_table"):
        apply_source_release_overlays(
            source_artifacts=(artifact,),
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package,),
        )
    report = build_source_release_overlay_report(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )

    assert report.release_diagnostics[0].reason.value == "missing_source_table"
    assert report.blocking_diagnostics()[0].reason.value == "missing_source_table"

    (input_dir / "Abilities.json").write_bytes(artifact.to_json_bytes())
    with pytest.raises(SourceOverlayError, match="failed with diagnostics"):
        apply_source_overlays(
            input_dir=input_dir,
            output_dir=output_dir,
            release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
            overlay_packs=(package,),
        )
    diagnostics = json.loads((output_dir / "source_overlay_diagnostics.json").read_text())

    assert diagnostics["diagnostics"] == [
        {
            "blocking": True,
            "message": "Overlay operation references a missing source table.",
            "op_id": "missing-table",
            "reason": "missing_source_table",
            "source_row_id": "missing-1",
            "source_table": "Missing_Table",
        }
    ]


def test_phase17_source_overlay_and_reference_payloads_reject_hash_drift() -> None:
    artifact = _abilities_artifact()
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", "Roll D6 within 12 inches."),),
            ),
        )
    )
    manifest = _release_manifest(overlay_package_ids=(package.package_id,))
    overlay_artifact = apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=manifest,
        overlay_packs=(package,),
    )[0]
    reference_catalog = build_source_reference_catalog(
        package_id=_reference_package_id(),
        catalog_version=_catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=(overlay_artifact,),
    )
    pack_payload = cast(
        SourceOverlayPackPayload,
        json.loads(json.dumps(package.to_payload(), sort_keys=True)),
    )
    manifest_payload = cast(
        SourceReleaseManifestPayload,
        json.loads(json.dumps(manifest.to_payload(), sort_keys=True)),
    )
    reference_payload = cast(
        SourceReferenceCatalogPayload,
        json.loads(json.dumps(reference_catalog.to_payload(), sort_keys=True)),
    )

    assert SourceOverlayPack.from_payload(pack_payload) == package
    assert SourceReleaseManifest.from_payload(manifest_payload) == manifest
    assert SourceReferenceCatalog.from_payload(reference_payload).to_payload() == (
        reference_catalog.to_payload()
    )
    assert (
        reference_catalog.source_text_by_id(
            overlay_artifact.rows[0].text_fields[1].source_text_id
        ).normalized_text
        == 'Roll D6 within 12".'
    )

    pack_payload["package_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(SourceOverlayError, match="package_hash"):
        SourceOverlayPack.from_payload(pack_payload)
    reference_payload["catalog_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(ValueError, match="catalog_hash"):
        SourceReferenceCatalog.from_payload(reference_payload)


def test_july_faction_pack_staging_ledger_matches_pending_and_predecessor_manifests() -> None:
    root = Path(__file__).resolve().parents[2]
    pending = _official_source_identities(
        root / "data" / "source_manifests" / "gw_11e_pending_faction_packs_2026_07.yaml"
    )
    current = _official_source_identities(
        root / "data" / "source_manifests" / "gw_11e_faction_packs.yaml"
    )
    ledger = july_faction_packs_2026_07.delta_ledger()

    july_faction_packs_2026_07.audit_manifest_links(
        ledger=ledger,
        pending_packages=pending,
        current_packages=current,
    )

    assert len(ledger.pack_reviews) == 27
    assert all(review.review_items for review in ledger.pack_reviews)
    assert "gw-11e-deathwatch-faction-pack-2026-06" not in {
        review.predecessor_package_id for review in ledger.pack_reviews
    }
    dispositions = {
        item.disposition for review in ledger.pack_reviews for item in review.review_items
    }
    assert dispositions == {
        "rules_updates_already_applied",
        "in_scope_source_only",
        "in_scope_runtime_affected",
        "excluded_imperial_armour",
        "excluded_legends",
    }


def test_july_runtime_affected_rows_link_to_stable_active_source_ids() -> None:
    root = Path(__file__).resolve().parents[2]
    source_json = (
        root
        / "data"
        / "source_snapshots"
        / "wahapedia"
        / ("".join(("1", "0", "th")) + "-edition")
        / "2026-06-14"
        / "json"
    )
    source_row_ids = {row.source_row_id for row in faction_subrules_2026_27.enhancement_rows()} | {
        row.source_row_id for row in faction_subrules_2026_27.stratagem_rows()
    }

    july_faction_packs_2026_07.audit_runtime_predecessor_references(
        ledger=july_faction_packs_2026_07.delta_ledger(),
        stable_reference_ids_by_kind={
            "phase17e_descriptor_id": {
                row.descriptor_id for row in faction_coverage_2026_27.coverage_rows()
            },
            "source_row_id": source_row_ids,
            "datasheet_id": _source_row_ids(source_json / "Datasheets.json"),
            "datasheet_ability_id": _source_row_ids(source_json / "Datasheets_abilities.json"),
        },
    )


def test_july_load_only_rows_are_typed_linked_and_explicitly_blocked() -> None:
    detachments = july_faction_packs_2026_07.detachments()
    subrules = july_faction_packs_2026_07.subrules()
    phase17e = july_faction_packs_2026_07.phase17e_coverage()
    phase17f = july_faction_packs_2026_07.phase17f_execution()
    scaffolds = july_faction_packs_2026_07.runtime_scaffolds()

    assert {row.detachment_name for row in detachments.rows} == {
        "Equatorial Hordes",
        "Frenzied Host",
        "Vengeful Hosts",
    }
    frenzied_host = next(row for row in detachments.rows if row.detachment_name == "Frenzied Host")
    assert frenzied_host.tags == []
    assert frenzied_host.removed_tags == ["host"]
    assert {row.rule_name for row in subrules.rows} == {
        "Avenging Angel",
        "Concealed Krumpin'",
        "Dey're Over 'Ere",
        "Echojump",
        "Empyric Wellspring",
        "Eruption of Vitality",
        "Evasive Manoeuvres",
        "Foetid Resurgence",
        "Frantic Focus",
        "Fusillade",
        "Hagiomnifex",
        "Imperator Unleashed",
        "Infernal Puppeteer",
        "Jungle Know-wotz",
        "Kaleidoscopic Tempest",
        "Know No Fear",
        "Kunnin' Hunta",
        "Meteoric Onslaught",
        "Murdermind",
        "Mysterious Guardian",
        "On My Signal",
        "Ordained Sacrifice",
        "Orksbane",
        "Purge by Sectors",
        "Reletavistic Tether",
        "Sorrowscent Vulture",
        "Stragglerz",
        "Temporal Corridor",
        "Thieves of Pain",
        "Unkillable Scourge",
    }
    assert all(row.load_support_status == "loaded" for row in detachments.rows)
    assert all(row.load_support_status == "loaded" for row in subrules.rows)
    assert all(row.semantic_execution_status == "blocked" for row in detachments.rows)
    assert all(row.semantic_execution_status == "blocked" for row in subrules.rows)
    assert all(row.coverage_status == "unsupported" for row in phase17e.rows)
    assert all(
        row.execution_status == "blocked_structured_semantics_required" for row in phase17f.rows
    )
    assert all(row.named_handler_id is None for row in scaffolds.rows)
    july_faction_packs_2026_07.audit_load_only_artifact_links(
        detachments=detachments,
        subrules=subrules,
        phase17e=phase17e,
        phase17f=phase17f,
        runtime_scaffolds=scaffolds,
    )


def test_july_datasheet_preview_preserves_inventory_and_support_boundaries() -> None:
    datasheets = july_faction_packs_2026_07.datasheets()
    preview = july_faction_packs_2026_07.datasheet_support_preview()
    rows_by_id = {row.datasheet_id: row for row in datasheets.rows}

    assert {(row.datasheet_id, row.datasheet_name) for row in datasheets.rows} == {
        ("000000724", "Ratlings"),
        ("000000969", "Defiler"),
        ("000003834", "Tempestus Aquilons"),
        ("000004210", "Thulia Ghuld"),
        ("000004216", "Commissar Yarrick"),
        ("000004221", "Wazdakka Gutsmek"),
        ("000004225", "The Red Terror"),
    }
    assert datasheets.excluded_content_categories == ["imperial-armour", "legends"]
    assert {
        datasheet_id
        for datasheet_id, row in rows_by_id.items()
        if row.inventory_status == "historical_predecessor_only"
    } == {"000000724", "000003834"}
    assert all(row.historical_provenance_retained for row in datasheets.rows)
    assert all(row.runtime_support_claim == "unknown" for row in datasheets.rows)
    assert all(row.semantic_execution_status == "blocked" for row in datasheets.rows)
    assert "Mobile" in {
        operation.replacement_value for operation in rows_by_id["000004210"].overlay_operations
    }
    assert "Mobile" in {
        operation.replacement_value for operation in rows_by_id["000004225"].overlay_operations
    }
    assert {
        operation.target_source_row_id
        for operation in rows_by_id["000004225"].overlay_operations
        if operation.operation_kind == "remove_ability"
    } == {"000004225:5"}
    datasheet_reference = next(
        artifact
        for artifact in july_faction_packs_2026_07.staging_package().staged_data_artifacts
        if artifact.artifact_id == datasheets.artifact_id
    )
    july_faction_packs_2026_07.audit_datasheet_preview_links(
        datasheets=datasheets,
        preview=preview,
        datasheet_artifact_sha256=datasheet_reference.artifact_sha256,
    )


def test_july_daemonic_manifestation_artifact_is_candidate_only_and_executable() -> None:
    artifact = july_faction_packs_2026_07.daemonic_manifestation()

    assert artifact.rule_name == "Daemonic Manifestation"
    assert artifact.predecessor_source_rule_id == "phase17f:phase17e:chaos-daemons:army-rule"
    assert artifact.semantic_execution_status == "executable_named_handler"
    assert artifact.provider_activation_status == "candidate_only"
    assert (
        artifact.named_handler_classification
        == "approved_successor_of_existing_army_rule_orchestrator"
    )
    assert artifact.named_handler_budget_execution_id == artifact.predecessor_source_rule_id
    assert artifact.decision_types == [
        "select_healing_model",
        "submit_healing_revival_placement",
    ]


def test_july_chaos_daemons_runtime_artifact_is_candidate_only_and_contract_stable() -> None:
    artifact = july_faction_packs_2026_07.chaos_daemons_runtime_updates()

    assert artifact.provider_activation_status == "candidate_only"
    assert artifact.ingress_decision_type == "submit_placement_proposal"
    assert artifact.stratagem_cost_decision_type == "select_stratagem_cost_modifier_option"
    assert artifact.adapter_contract_status == "existing_contract_unchanged"
    assert chaos_daemons_july_updates.replacement_keywords_for_datasheet(
        chaos_daemons_july_updates.SCREAMERS_DATASHEET_ID
    ) == (
        "BEAST",
        "FLY",
        "CHAOS",
        "DAEMON",
        "TZEENTCH",
        "SCREAMERS",
    )
    unsupported = chaos_daemons_july_updates.unsupported_ability_rows()
    assert [(row.rule_name, row.semantic_execution_status) for row in unsupported] == [
        ("Altered Reality", "unsupported")
    ]
    june_contribution = chaos_daemons_june_manifest.runtime_contribution()
    candidate_contribution = chaos_daemons_july_candidate.runtime_contribution()
    assert all(
        record.definition.source_id != artifact.rows[0].source_row_id
        for record in june_contribution.stratagem_records
    )
    assert any(
        record.definition.source_id == artifact.rows[0].source_row_id
        for record in candidate_contribution.stratagem_records
    )


def test_july_exalted_patron_artifact_is_candidate_only_generic_rule_ir() -> None:
    artifact = july_faction_packs_2026_07.exalted_patron()
    rule_ir = artifact.rule_ir()
    execution_record = artifact.execution_record()

    assert artifact.provider_activation_status == "candidate_only"
    assert artifact.target_required_keywords == ["LORD EXULTANT"]
    assert artifact.removed_ability_ids == ["may_attach_to_flawless_blades"]
    assert tuple(effect.kind for clause in rule_ir.clauses for effect in clause.effects) == (
        RuleEffectKind.MODIFY_MOVE_DISTANCE,
    )
    assert parameter_payload(rule_ir.clauses[1].effects[0].parameters) == {"delta": 1}
    assert execution_record.rule_ir_hash == rule_ir.ir_hash()
    assert (
        emperors_children_july_candidate.runtime_contribution().contribution_id
        == artifact.runtime_provider_id
    )
    assert (
        emperors_children_june_manifest.runtime_contribution().contribution_id
        != artifact.runtime_provider_id
    )

    june_record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.execution_id == artifact.phase17f_execution_id
    )
    staged_record = next(
        record
        for record in emperors_children_july_candidate.faction_execution_records()
        if record.execution_id == artifact.phase17f_execution_id
    )
    assert june_record.rule_ir_hash != staged_record.rule_ir_hash
    assert staged_record == execution_record

    frenzied_host = next(
        row
        for row in july_faction_packs_2026_07.phase17f_execution().rows
        if row.source_row_id.endswith(":subrule:emperors-children:frenzied-host:frantic-focus")
    )
    assert frenzied_host.execution_status == "blocked_structured_semantics_required"
    assert frenzied_host.runtime_consumer_ids == []


def test_july_thousand_sons_defiler_artifact_and_provider_remain_candidate_only() -> None:
    artifact = july_faction_packs_2026_07.thousand_sons_defiler()
    june = thousand_sons_june_manifest.runtime_contribution()
    candidate = thousand_sons_july_candidate.runtime_contribution()
    record = candidate.stratagem_records[0]
    exception = stratagem_phase_use_exception(record.definition)

    assert artifact.aligned_defiler_datasheet_ids == [
        "000001030",
        "000004207",
        "000004208",
        "000004209",
    ]
    assert artifact.audited_chaos_space_marines_datasheet_id == "000000969"
    assert artifact.old_rule_ir_semantics == "removed_minimum_hit_threshold"
    assert artifact.semantic_execution_status == "executable_generic_runtime"
    assert artifact.provider_activation_status == "candidate_only"
    assert june.contribution_id != artifact.runtime_provider_id
    assert june.stratagem_records == ()
    assert june.stratagem_cost_modifier_bindings == ()
    assert candidate.contribution_id == artifact.runtime_provider_id
    assert record.definition.handler_id == artifact.counteroffensive_handler_id
    assert exception is not None
    assert exception.source_ability_id == artifact.source_ability_id
    assert exception.eligible_datasheet_ids == (artifact.datasheet_id,)
    assert tuple(binding.modifier_id for binding in candidate.stratagem_cost_modifier_bindings) == (
        artifact.runtime_consumer_ids[1],
    )

    active_thousand_sons_row = next(
        row
        for row in generated_manifest.generated_runtime_content_rows()
        if row.owner_faction_id == "thousand-sons" and row.owner_detachment_id is None
    )
    assert active_thousand_sons_row.module_path is not None
    assert active_thousand_sons_row.module_path.endswith(".thousand_sons.manifest")
    assert "july_2026_candidate" not in active_thousand_sons_row.module_path


def test_july_kairos_uses_existing_generic_stratagem_cost_semantics() -> None:
    record = next(
        record
        for record in chaos_daemons_july_updates.runtime_contribution().ability_records
        if record.datasheet_id == chaos_daemons_july_updates.KAIROS_DATASHEET_ID
    )
    clauses = catalog_rule_clauses_from_record(record)

    assert len(clauses) == 1
    assert command_point_consumer_ids_for_clause(clauses[0]) == (
        CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    )
    assert record.definition.source_id.startswith(july_faction_packs_2026_07.SOURCE_PACKAGE_ID)


def test_july_cutover_guard_keeps_staged_ids_out_of_june_defaults() -> None:
    root = Path(__file__).resolve().parents[2]
    current = _official_source_identities(
        root / "data" / "source_manifests" / "gw_11e_faction_packs.yaml"
    )
    current_docs = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((root / "docs" / "factions").glob("*.md"))
    }
    active_phase17_package_ids = (
        faction_detachments_2026_27.SOURCE_PACKAGE_ID,
        faction_subrules_2026_27.SOURCE_PACKAGE_ID,
        faction_coverage_2026_27.SOURCE_PACKAGE_ID,
        faction_execution_2026_27.SOURCE_PACKAGE_ID,
    )
    active_runtime_package_ids = tuple(
        sorted(
            {row.source_package_id for row in generated_manifest.generated_runtime_content_rows()}
        )
    )

    july_faction_packs_2026_07.audit_staged_package_is_not_active(
        current_source_package_ids=tuple(sorted(current)),
        phase17_source_package_ids=active_phase17_package_ids,
        runtime_source_package_ids=active_runtime_package_ids,
        generated_current_documents=current_docs,
    )

    with pytest.raises(
        july_faction_packs_2026_07.JulyFactionPackStagingError,
        match="leaked into an active",
    ):
        july_faction_packs_2026_07.audit_staged_package_is_not_active(
            current_source_package_ids=(
                *tuple(sorted(current)),
                july_faction_packs_2026_07.SOURCE_PACKAGE_ID,
            ),
            phase17_source_package_ids=active_phase17_package_ids,
            runtime_source_package_ids=active_runtime_package_ids,
            generated_current_documents=current_docs,
        )


def _official_source_identities(path: Path) -> dict[str, tuple[str, str]]:
    identities: dict[str, tuple[str, str]] = {}
    for entry in load_official_source_manifest(path):
        if entry.local_cache_path is None:
            raise AssertionError("Faction-pack manifest entry must declare a local cache path.")
        identities[entry.package_id] = (entry.sha256, entry.local_cache_path)
    return identities


def _source_row_ids(path: Path) -> set[str]:
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    if type(raw_payload) is not dict:
        raise AssertionError("Source artifact must contain a JSON object.")
    rows = cast(dict[str, object], raw_payload)["rows"]
    if type(rows) is not list:
        raise AssertionError("Source artifact rows must be a list.")
    source_row_ids: set[str] = set()
    for raw_row in cast(list[object], rows):
        if type(raw_row) is not dict:
            raise AssertionError("Source artifact row must be a JSON object.")
        source_row_id = cast(dict[str, object], raw_row)["source_row_id"]
        if type(source_row_id) is not str:
            raise AssertionError("Source artifact row ID must be a string.")
        source_row_ids.add(source_row_id)
    return source_row_ids


def _updated_row_after_first_operation(
    artifact: WahapediaJsonArtifact,
    *,
    package_hash_placeholder: bool,
) -> NormalizedSourceRow:
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update-angels-fury",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", "<p>Roll D6 within 12 inches.</p>"),),
            ),
        )
    )
    if package_hash_placeholder:
        assert package.package_hash()
    return apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )[0].rows[0]


def _operation(
    *,
    op_id: str,
    order_index: int,
    kind: SourceOverlayOperationKind,
    source_row_id: str,
    expected_preimage_hash: str | None,
    fields: tuple[tuple[str, str], ...],
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=kind,
        target_edition="warhammer-40000-11th",
        source_table="Abilities",
        source_row_id=source_row_id,
        source_reference="gw-11e-transition-update:p1",
        effective_date="2026-06-01",
        reason="Apply 11e transition update.",
        expected_preimage_hash=expected_preimage_hash,
        fields=fields,
    )


def _overlay_pack(
    *,
    operations: tuple[SourceOverlayOperation, ...],
    package_id: DataPackageId | None = None,
) -> SourceOverlayPack:
    return SourceOverlayPack(
        package_id=package_id if package_id is not None else _overlay_package_id(),
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        target_edition="warhammer-40000-11th",
        effective_date="2026-06-01",
        operations=operations,
    )


def _release_manifest(
    *,
    overlay_package_ids: tuple[DataPackageId, ...],
) -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="core-11-from-wahapedia-bridge-test",
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        base_source_edition=_previous_source_edition(),
        target_edition="warhammer-40000-11th",
        overlay_package_ids=overlay_package_ids,
    )


def _abilities_artifact() -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(
            table_name="Abilities",
            csv_text='id,faction_id,name,description\nability-1,SM,Angels Fury,"Roll D3."\n',
        ),
    )


def _row_by_id(artifact: OverlaySourceArtifact, source_row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _source_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="wahapedia",
        package_name="source-mirror",
        version="bridge-2026-06-01",
    )


def _overlay_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="core-11-source-overlay",
        version="2026-06-01",
    )


def _reference_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="core-11-source-reference",
        version="2026-06-01",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="core-11-from-wahapedia-bridge-test",
        source_date=date(2026, 6, 1),
    )


def _previous_source_edition() -> str:
    return "warhammer-40000-" + "1" + "0th"
